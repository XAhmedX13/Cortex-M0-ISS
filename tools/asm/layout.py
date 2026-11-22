"""Layout pass: sections, offsets, item placement, and section bases."""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from tools.asm.errors import ErrorCollector
from tools.asm.lexer import Line
from tools.asm.symbols import SymbolTable

DEFAULT_BASES = {
    ".vectors": 0x00000000,
    ".text": 0x00000100,
    ".data": 0x20000000,
}

DirectiveHandler = Callable[["Assembler", Line], None]
ItemWriter = Callable[["Assembler", "Item"], None]


@dataclass
class Item:
    """One thing placed during pass 1 and filled during pass 2."""

    line: int
    section: str
    offset: int
    size: int
    kind: str
    mnemonic: str = ""
    operands: List[str] = field(default_factory=list)
    pool_key: str = ""


@dataclass
class Section:
    """One output section with a location counter and final bytes."""

    name: str
    size: int = 0
    base: int = 0
    is_nobits: bool = False
    data: bytearray = field(default_factory=bytearray)


def align_up(value: int, alignment: int) -> int:
    """Round a value up to the next multiple of alignment."""
    return ((value + alignment - 1) // alignment) * alignment


def base_mnemonic(mnemonic: str) -> str:
    """Remove an ignored .n or .w mnemonic suffix."""
    for suffix in (".n", ".w"):
        if mnemonic.endswith(suffix):
            return mnemonic[: -len(suffix)]
    return mnemonic


class Assembler:
    """Shared state for both assembler passes."""

    def __init__(
        self,
        file: str,
        errors: ErrorCollector,
        section_overrides: Optional[Dict[str, int]] = None,
    ) -> None:
        """Create the default text section and empty layout state."""
        self.file = file
        self.errors = errors
        self.section_overrides = section_overrides or {}
        self.sections: Dict[str, Section] = {".text": Section(".text")}
        self.items: List[Item] = []
        self.symbols = SymbolTable(self.sections)
        self.current_section = ".text"
        self.source_lines: Dict[int, str] = {}
        self.listing: List[tuple] = []
        self.directive_handler: Optional[DirectiveHandler] = None
        self.item_writer: Optional[ItemWriter] = None

    def set_directive_handler(self, handler: DirectiveHandler) -> None:
        """Install the function that handles assembler directives."""
        self.directive_handler = handler

    def set_item_writer(self, writer: ItemWriter) -> None:
        """Install the function that fills an item with final bytes."""
        self.item_writer = writer

    def get_section(self, name: str, is_nobits: bool = False) -> Section:
        """Return a section, creating it on first use."""
        section = self.sections.get(name)
        if section is None:
            section = Section(name=name, is_nobits=is_nobits)
            self.sections[name] = section
        elif is_nobits:
            section.is_nobits = True
        return section

    def set_section(self, name: str, is_nobits: bool = False) -> None:
        """Switch subsequent layout to the named section."""
        self.get_section(name, is_nobits)
        self.current_section = name

    def current(self) -> Section:
        """Return the section currently receiving items."""
        return self.sections[self.current_section]

    def current_offset(self) -> int:
        """Return the current location counter within the current section."""
        return self.current().size

    def emit(
        self,
        kind: str,
        size: int,
        line: int,
        mnemonic: str = "",
        operands: Optional[List[str]] = None,
        pool_key: str = "",
    ) -> Item:
        """Place an item at the current offset and advance the location counter."""
        section = self.current()
        item = Item(
            line=line,
            section=section.name,
            offset=section.size,
            size=size,
            kind=kind,
            mnemonic=mnemonic,
            operands=operands or [],
            pool_key=pool_key,
        )
        section.size += size
        self.items.append(item)
        return item

    def align(self, boundary: int, line: int, kind: str = "padding") -> None:
        """Emit zero padding until the current offset is aligned."""
        padding = (-self.current_offset()) % boundary
        if padding:
            self.emit(kind, padding, line)

    def define_label(self, name: str, line: int) -> None:
        """Define an ordinary or numeric local label at the current offset."""
        section = self.current()
        if name.isdigit():
            self.symbols.define_numeric_local(name, section.name, section.size, line)
        else:
            self.symbols.define(name, section.name, section.size, self.file, line, self.errors)

    def flush_pools(self) -> None:
        """Flush pending literal pools; reserved for M4."""
        return None

    def process_lines(self, lines: List[Line]) -> None:
        """Run pass 1 over every parsed source line."""
        for line in lines:
            if line.label:
                self.define_label(line.label, line.number)
            if not line.mnemonic:
                continue
            if line.mnemonic.startswith("."):
                if self.directive_handler is None:
                    self.errors.add_error(
                        self.file, line.number, f"unsupported directive: {line.mnemonic}"
                    )
                else:
                    self.directive_handler(self, line)
                continue
            size = 4 if base_mnemonic(line.mnemonic) == "bl" else 2
            self.emit("instr", size, line.number, line.mnemonic, line.operands)
        self.flush_pools()

    def assign_section_bases(self) -> None:
        """Assign final base addresses to all sections after pass 1."""
        for name, address in self.section_overrides.items():
            section = self.sections.get(name)
            if section is None:
                continue
            if address % 4 != 0:
                self.errors.add_error(self.file, 0, f"section base not 4-byte aligned: {name}")
            section.base = address

        rom_names: List[str] = []
        for preferred in (".vectors", ".text"):
            if preferred in self.sections:
                rom_names.append(preferred)
        for name, section in self.sections.items():
            if name in rom_names or name == ".data" or section.is_nobits:
                continue
            rom_names.append(name)

        rom_cursor = 0
        for name in rom_names:
            section = self.sections[name]
            if name not in self.section_overrides:
                section.base = DEFAULT_BASES.get(name, align_up(rom_cursor, 4))
            rom_cursor = section.base + section.size

        ram_cursor = DEFAULT_BASES[".data"]
        data = self.sections.get(".data")
        if data is not None:
            if ".data" not in self.section_overrides:
                data.base = DEFAULT_BASES[".data"]
            ram_cursor = data.base + data.size
        for name, section in self.sections.items():
            if not section.is_nobits or name in self.section_overrides:
                continue
            section.base = align_up(ram_cursor, 4)
            ram_cursor = section.base + section.size

    def fill_bytes(self) -> None:
        """Prepare section buffers and run pass 2 over every placed item."""
        for section in self.sections.values():
            if not section.is_nobits:
                section.data = bytearray(section.size)
        for item in self.items:
            section = self.sections[item.section]
            if section.is_nobits:
                continue
            if item.kind == "padding":
                section.data[item.offset : item.offset + item.size] = bytearray(item.size)
            elif self.item_writer is None:
                self.errors.add_error(
                    self.file,
                    item.line,
                    f"item writer not configured for {item.kind}: {item.mnemonic}",
                )
            else:
                self.item_writer(self, item)
            address = section.base + item.offset
            chunk = bytes(section.data[item.offset : item.offset + item.size])
            self.listing.append((address, chunk.hex(), item.line))
