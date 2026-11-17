"""Sections, layout items and the two-pass assembly pipeline model."""

from dataclasses import dataclass, field
from typing import Any, List, Optional

try:
    from .errors import AsmError
    from .expr import Expression
    from .symbols import SymbolTable
except ImportError:
    from errors import AsmError
    from expr import Expression
    from symbols import SymbolTable


# Default section bases. These match the course linker flags: vectors at zero,
# text at 0x100, RAM data at 0x20000000, and read-only sections after ROM code.
DEFAULT_SECTION_BASES = {
    ".vectors": 0x00000000,
    ".text": 0x00000100,
    ".data": 0x20000000,
}
RAM_SECTION_NAMES = {".data", ".bss"}


@dataclass
class Item:
    """One emitted item whose final bytes are filled in during pass two."""

    section: Any
    offset: int
    size: int
    kind: str
    statement: Any
    mnemonic: str = ""
    operands: List[str] = field(default_factory=list)
    data_specs: List[Any] = field(default_factory=list)
    literal_bytes: bytes = b""
    fill_spec: Any = None
    expression: Optional[Expression] = None
    pool_entry: Any = None
    encoded: bytes = b""

    def address(self) -> int:
        """Return the item's absolute address after section bases are assigned."""
        if self.section.base is None:
            raise AsmError("section address is not known for this item")
        return self.section.base + self.offset


@dataclass
class Section:
    """A named output section and the items placed inside it."""

    name: str
    items: List[Item] = field(default_factory=list)
    size: int = 0
    base: Optional[int] = None
    alignment: int = 4
    is_nobits: bool = False

    def add_item(self, size: int, kind: str, statement, **details) -> Item:
        """Append a zero-size placeholder and advance this section's counter."""
        item = Item(self, self.size, size, kind, statement, **details)
        self.items.append(item)
        self.size += size
        return item

    def byte_image(self) -> bytes:
        """Concatenate all encoded item bytes in section order."""
        image = bytearray()
        for item in self.items:
            image.extend(item.encoded)
        return bytes(image)


@dataclass
class LiteralPoolEntry:
    """One unique expression waiting to be written as a literal pool word."""

    expression: Expression
    key: str
    statement: Any
    offset: Optional[int] = None
    item: Optional[Item] = None

    def address(self) -> int:
        """Return the absolute address of the allocated pool word."""
        if self.item is None:
            raise AsmError("literal pool entry was never placed")
        return self.item.address()


@dataclass
class LiteralPool:
    """Pending literal pool entries for one section."""

    section: Section
    entries: List[LiteralPoolEntry] = field(default_factory=list)
    by_key: dict = field(default_factory=dict)

    def request(self, expression_text: str, statement) -> LiteralPoolEntry:
        """Find or create the pool word for an expression."""
        expression = Expression(expression_text, statement)
        key = expression.canonical
        if key not in self.by_key:
            entry = LiteralPoolEntry(expression, key, statement)
            self.entries.append(entry)
            self.by_key[key] = entry
        return self.by_key[key]


class Program:
    """Collect all sections, symbols and layout decisions for one source file."""

    def __init__(self, diagnostics, section_overrides=None) -> None:
        """Create the default text section and an empty symbol table."""
        self.diagnostics = diagnostics
        self.overrides = dict(section_overrides or {})
        self.sections = {}
        self.section_order = []
        self.symbols = SymbolTable(diagnostics)
        self.pending_pools = {}
        self.stop = False
        self._last_statement = None
        self._current_section = None
        self._current_section = self.ensure_section(".text")

    @property
    def current_section(self) -> Section:
        """Return the section selected by the most recent section directive."""
        return self._current_section

    def ensure_section(self, name: str, is_nobits: bool = False) -> Section:
        """Create a section on first use and return it."""
        if name not in self.sections:
            section = Section(name, is_nobits=is_nobits)
            self.sections[name] = section
            self.section_order.append(section)
        if is_nobits:
            self.sections[name].is_nobits = True
        return self.sections[name]

    def set_section(self, name: str, is_nobits: bool = False) -> None:
        """Switch the location counter to a named section."""
        self._current_section = self.ensure_section(name, is_nobits)

    def define_label(self, name: str, statement) -> None:
        """Define a label at the current location counter."""
        if name.isdigit():
            self.symbols.define_numeric(name, self.current_section,
                                        self.current_section.size, statement)
        else:
            self.symbols.define(name, self.current_section,
                                self.current_section.size, statement)

    def define_equ(self, name: str, expression_text: str, statement) -> None:
        """Define an absolute symbol from expression text."""
        expression = Expression(expression_text, statement)
        self.symbols.define_absolute(name, expression, statement,
                                     self.current_section,
                                     self.current_section.size)

    def mark_global(self, name: str) -> None:
        """Mark a symbol as global."""
        self.symbols.mark_global(name)

    def set_pending_thumb_func(self) -> None:
        """Mark the next label as a Thumb function symbol."""
        self.symbols.set_pending_thumb_func()

    def emit_data(self, statement, specs: List[Any]) -> Item:
        """Emit data whose byte values are evaluated in pass two."""
        total_size = sum(size for size, _ in specs)
        return self.current_section.add_item(total_size, "bytes", statement,
                                             data_specs=specs)

    def emit_literal_bytes(self, statement, data: bytes) -> Item:
        """Emit bytes that are already known during layout."""
        return self.current_section.add_item(len(data), "bytes", statement,
                                             literal_bytes=data)

    def emit_space(self, statement, count: int, fill_text: str) -> Item:
        """Reserve a number of bytes with a fill expression."""
        return self.current_section.add_item(count, "bytes", statement,
                                             fill_spec=fill_text)

    def emit_padding(self, statement, count: int) -> Item:
        """Emit zero padding for alignment."""
        return self.current_section.add_item(count, "padding", statement)

    def align(self, statement, alignment: int) -> None:
        """Advance the current section to the next multiple of ``alignment``."""
        count = (-self.current_section.size) % alignment
        if count:
            self.emit_padding(statement, count)

    def add_pool_request(self, expression_text: str, statement) -> LiteralPoolEntry:
        """Register a ``ldr =expr`` request in this section's pending pool."""
        section = self.current_section
        if section.name not in self.pending_pools:
            self.pending_pools[section.name] = LiteralPool(section)
        return self.pending_pools[section.name].request(expression_text, statement)

    def flush_pool(self, statement=None) -> None:
        """Flush the current section's pending literal pool."""
        self._flush_pool(self.current_section, statement)

    def finish_layout(self) -> None:
        """Flush every section's pending pool after the last source line."""
        for section in self.section_order:
            if section.name in self.pending_pools:
                self._flush_pool(section, None)

    def layout_statement(self, statement) -> None:
        """Define labels and handle one statement during pass one."""
        self._last_statement = statement
        for label in statement.labels:
            self.define_label(label, statement)
        if statement.kind == "empty":
            return
        if statement.kind == "directive":
            if __package__:
                from .directives import handle_directive
            else:
                from directives import handle_directive
            handle_directive(self, statement)
            return
        self._layout_instruction(statement)

    def assign_base_addresses(self) -> None:
        """Assign aligned base addresses to all sections after layout."""
        for section in self.section_order:
            if section.name in self.overrides:
                base = self.overrides[section.name]
                if base % 4:
                    raise AsmError("section address must be a multiple of 4: " +
                                   section.name)
                section.base = base
        rom_end = self._place_rom_sections()
        self._place_ram_sections()
        for section in self.section_order:
            if section.base is None:
                section.base = _align_up(rom_end, 4)
                rom_end = section.base + section.size

    def sorted_sections(self) -> List[Section]:
        """Return sections with assigned addresses in ascending address order."""
        return sorted(self.sections.values(), key=lambda section: section.base or 0)

    def check_vector_warning(self) -> None:
        """Warn when a plausible reset vector has its Thumb bit clear."""
        section = self.sections.get(".vectors")
        if section is None or len(section.items) < 2:
            return
        data = section.byte_image()
        if len(data) < 8:
            return
        initial_sp = int.from_bytes(data[0:4], "little")
        reset = int.from_bytes(data[4:8], "little")
        if 0x20000000 <= initial_sp <= 0x20100000 and reset < 0x20000000 and reset % 2 == 0:
            self.diagnostics.warning("reset vector bit 0 is clear; the simulator will raise INVSTATE",
                                     section.items[1].statement)

    def _layout_instruction(self, statement) -> None:
        """Create a two-byte item, or a four-byte item for ``bl``."""
        if __package__:
            from .encode import base_mnemonic
        else:
            from encode import base_mnemonic
        name = base_mnemonic(statement.mnemonic)
        size = 4 if name == "bl" else 2
        pool_entry = None
        if name == "ldr" and len(statement.operands) == 2:
            text = statement.operands[1].strip()
            if text.startswith("="):
                pool_entry = self.add_pool_request(text[1:], statement)
        self.current_section.add_item(size, "instr", statement,
                                      mnemonic=statement.mnemonic,
                                      operands=list(statement.operands),
                                      pool_entry=pool_entry)

    def _flush_pool(self, section: Section, statement) -> None:
        """Pad and emit the unique words of one pending literal pool."""
        pool = self.pending_pools.get(section.name)
        if pool is None or not pool.entries:
            return
        owner = statement or pool.entries[0].statement
        saved = getattr(self, "_current_section", None)
        self._current_section = section
        self.align(owner, 4)
        for entry in pool.entries:
            item = section.add_item(4, "pool_word", owner, expression=entry.expression)
            entry.offset = item.offset
            entry.item = item
        self._current_section = saved
        del self.pending_pools[section.name]

    def _place_rom_sections(self) -> int:
        """Place vectors, text and other read-only sections in ROM."""
        placed_end = 0
        for name in (".vectors", ".text"):
            section = self.sections.get(name)
            if section is None:
                continue
            if section.base is None:
                section.base = DEFAULT_SECTION_BASES[name]
            placed_end = max(placed_end, section.base + section.size)
        for section in self.section_order:
            if section.base is not None or section.name in RAM_SECTION_NAMES:
                continue
            section.base = _align_up(placed_end, 4)
            placed_end = section.base + section.size
        return placed_end

    def _place_ram_sections(self) -> None:
        """Place data at its RAM default and bss immediately after data."""
        data = self.sections.get(".data")
        if data is not None and data.base is None:
            data.base = DEFAULT_SECTION_BASES[".data"]
        bss = self.sections.get(".bss")
        if bss is not None and bss.base is None:
            start = data.base + data.size if data is not None else DEFAULT_SECTION_BASES[".data"]
            bss.base = _align_up(start, 4)


def _align_up(value: int, alignment: int) -> int:
    """Return the smallest multiple of ``alignment`` not below ``value``."""
    return (value + alignment - 1) // alignment * alignment
