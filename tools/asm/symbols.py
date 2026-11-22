"""Symbol table and numeric local label handling."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from tools.asm.errors import ErrorCollector
from tools.asm.expr import is_numeric_local_reference


@dataclass
class Symbol:
    """One named address known to the assembler."""

    name: str
    section: str = ""
    offset: int = 0
    is_thumb_func: bool = False
    is_global: bool = False
    is_absolute: bool = False
    value: int = 0


@dataclass
class NumericLocal:
    """One definition of an all-digit local label."""

    line: int
    section: str
    offset: int


class SymbolTable:
    """Map source names to addresses after section bases are assigned."""

    def __init__(self, sections: Dict[str, Any]) -> None:
        """Start with no symbols and no pending thumb_func directive."""
        self.sections = sections
        self.symbols: Dict[str, Symbol] = {}
        self.numeric_locals: Dict[str, List[NumericLocal]] = {}
        self.global_names: List[str] = []
        self.pending_thumb_func = False

    def set_pending_thumb_func(self) -> None:
        """Mark the next defined label as a Thumb function symbol."""
        self.pending_thumb_func = True

    def mark_global(self, name: str) -> None:
        """Mark a name as global, before or after its definition."""
        if name not in self.global_names:
            self.global_names.append(name)
        symbol = self.symbols.get(name)
        if symbol is not None:
            symbol.is_global = True

    def define(
        self,
        name: str,
        section: str,
        offset: int,
        file: str,
        line: int,
        errors: ErrorCollector,
    ) -> Optional[Symbol]:
        """Define an ordinary label at an offset within a section."""
        if name in self.symbols:
            errors.add_error(file, line, f"duplicate label: {name}")
            return None
        thumb_func = self.pending_thumb_func
        self.pending_thumb_func = False
        symbol = Symbol(
            name=name,
            section=section,
            offset=offset,
            is_thumb_func=thumb_func,
            is_global=name in self.global_names,
        )
        self.symbols[name] = symbol
        return symbol

    def define_absolute(
        self,
        name: str,
        value: int,
        file: str,
        line: int,
        errors: ErrorCollector,
    ) -> Optional[Symbol]:
        """Define an absolute symbol created by .equ or .set."""
        if name in self.symbols:
            errors.add_error(file, line, f"duplicate label: {name}")
            return None
        symbol = Symbol(
            name=name,
            is_absolute=True,
            value=value,
            is_global=name in self.global_names,
        )
        self.symbols[name] = symbol
        return symbol

    def define_numeric_local(
        self, name: str, section: str, offset: int, line: int
    ) -> NumericLocal:
        """Record one definition of an all-digit local label."""
        self.pending_thumb_func = False
        entry = NumericLocal(line=line, section=section, offset=offset)
        self.numeric_locals.setdefault(name, []).append(entry)
        return entry

    def section_address(self, section: str, offset: int) -> int:
        """Return the final address of a section offset."""
        target = self.sections.get(section)
        if target is None:
            return offset
        return target.base + offset

    def numeric_address(self, entry: NumericLocal) -> int:
        """Return the final address of a numeric local definition."""
        return self.section_address(entry.section, entry.offset)

    def resolve_numeric(
        self, name: str, line: int, file: str, errors: ErrorCollector
    ) -> int:
        """Resolve a 1f or 1b reference against the reference line number."""
        digit = name[:-1]
        entries = self.numeric_locals.get(digit, [])
        if name[-1] == "f":
            matches = [entry for entry in entries if entry.line > line]
            entry = matches[0] if matches else None
        else:
            matches = [entry for entry in entries if entry.line <= line]
            entry = matches[-1] if matches else None
        if entry is None:
            errors.add_error(file, line, f"undefined symbol: {name}")
            return 0
        return self.numeric_address(entry)

    def resolve(
        self,
        name: str,
        line: int,
        file: str,
        errors: ErrorCollector,
        as_data: bool = False,
    ) -> int:
        """Resolve a name to an integer address in the current pass."""
        if is_numeric_local_reference(name):
            return self.resolve_numeric(name, line, file, errors)
        symbol = self.symbols.get(name)
        if symbol is None:
            errors.add_error(file, line, f"undefined symbol: {name}")
            return 0
        address = symbol.value if symbol.is_absolute else self.section_address(
            symbol.section, symbol.offset
        )
        if as_data and symbol.is_thumb_func:
            address |= 1
        return address

    def make_resolver(
        self,
        line: int,
        file: str,
        errors: ErrorCollector,
        as_data: bool = False,
    ) -> Callable[[str], int]:
        """Build the one-argument resolver callback expected by expr.evaluate."""

        def resolve(name: str) -> int:
            """Resolve a name using the captured line and data-mode settings."""
            return self.resolve(name, line, file, errors, as_data)

        return resolve
