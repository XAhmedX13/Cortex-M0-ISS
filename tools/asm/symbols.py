"""Symbol table, absolute equates and numeric local label support."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    from .errors import AsmError
    from .expr import EvalContext, Expression
except ImportError:
    from errors import AsmError
    from expr import EvalContext, Expression


@dataclass
class Symbol:
    """A named value: either section-relative or absolute."""

    name: str
    section=None
    offset: int = 0
    absolute_value: Optional[int] = None
    expression: Optional[Expression] = None
    is_thumb_func: bool = False
    is_global: bool = False
    defined: bool = False
    definition=None
    definition_section=None
    definition_offset: int = 0

    def address(self) -> int:
        """Return the final numeric value after section bases are assigned."""
        if self.absolute_value is not None:
            return self.absolute_value
        if self.section is None or self.section.base is None:
            raise AsmError("section address is not known for symbol: " + self.name)
        return self.section.base + self.offset


@dataclass
class LocalDefinition:
    """One definition of a numeric local label such as ``1:``."""

    name: str
    seq: int
    section: Any
    offset: int
    statement: Any


class SymbolTable:
    """Hold all symbols and resolve forward references in pass two."""

    def __init__(self, diagnostics) -> None:
        """Create an empty symbol table with no pending Thumb function flag."""
        self.diagnostics = diagnostics
        self.symbols: Dict[str, Symbol] = {}
        self.numeric_locals: Dict[str, List[LocalDefinition]] = {}
        self.pending_thumb_func = False
        self.resolving: List[str] = []

    def set_pending_thumb_func(self) -> None:
        """Remember that the next defined label is a Thumb function symbol."""
        self.pending_thumb_func = True

    def take_pending_thumb_func(self) -> bool:
        """Consume and return the pending Thumb function flag."""
        value = self.pending_thumb_func
        self.pending_thumb_func = False
        return value

    def mark_global(self, name: str) -> None:
        """Mark a symbol as global, creating a placeholder if it is not yet defined."""
        symbol = self.symbols.get(name)
        if symbol is None:
            symbol = Symbol(name)
            self.symbols[name] = symbol
        symbol.is_global = True

    def define(self, name: str, section, offset: int, statement) -> Symbol:
        """Define a section-relative label at the current location counter."""
        symbol = self._prepare_definition(name, statement)
        symbol.section = section
        symbol.offset = offset
        symbol.absolute_value = None
        symbol.expression = None
        symbol.defined = True
        symbol.definition = statement
        symbol.definition_section = section
        symbol.definition_offset = offset
        return symbol

    def define_absolute(self, name: str, expression: Expression, statement,
                        section=None, offset: int = 0) -> Symbol:
        """Define an absolute symbol whose expression may use forward references."""
        symbol = self._prepare_definition(name, statement)
        symbol.section = None
        symbol.offset = 0
        symbol.absolute_value = None
        symbol.expression = expression
        symbol.defined = True
        symbol.definition = statement
        symbol.definition_section = section
        symbol.definition_offset = offset
        return symbol

    def define_numeric(self, name: str, section, offset: int, statement) -> None:
        """Record a numeric local label definition in source order."""
        self.take_pending_thumb_func()
        definition = LocalDefinition(name, statement.seq, section, offset, statement)
        self.numeric_locals.setdefault(name, []).append(definition)

    def value(self, name: str, context: EvalContext) -> int:
        """Resolve a symbol to an integer, applying the Thumb bit for data uses."""
        if name[-1:].lower() in ("f", "b") and name[:-1].isdigit():
            return self._numeric_local_value(name, context)
        symbol = self.symbols.get(name)
        if symbol is None or not symbol.defined:
            raise AsmError("undefined symbol: " + name, context.statement.file,
                           context.statement.line, context.statement.source)
        if name in self.resolving:
            raise AsmError("circular symbol definition: " + name,
                           context.statement.file, context.statement.line,
                           context.statement.source)
        value = self._symbol_value(symbol, context)
        if context.use == "data" and symbol.is_thumb_func:
            value |= 1
        return value & 0xFFFFFFFF

    def iter_symbols(self) -> List[Symbol]:
        """Return named symbols in sorted order for the listing symbol table."""
        return [self.symbols[name] for name in sorted(self.symbols)]

    def _prepare_definition(self, name: str, statement) -> Symbol:
        """Create or update a symbol and reject duplicate definitions."""
        symbol = self.symbols.get(name)
        if symbol is None:
            symbol = Symbol(name)
            self.symbols[name] = symbol
        elif symbol.defined:
            raise AsmError("duplicate label: " + name, statement.file,
                           statement.line, statement.source)
        symbol.is_thumb_func = self.take_pending_thumb_func()
        return symbol

    def _symbol_value(self, symbol: Symbol, context: EvalContext) -> int:
        """Return a symbol's raw value, evaluating an equate if necessary."""
        if symbol.expression is None:
            return symbol.address()
        self.resolving.append(symbol.name)
        try:
            location = context.location
            if symbol.definition_section is not None and symbol.definition_section.base is not None:
                location = symbol.definition_section.base + symbol.definition_offset
            nested = EvalContext(symbol.definition, location, context.use)
            return symbol.expression.evaluate(self, nested)
        finally:
            self.resolving.pop()

    def _numeric_local_value(self, name: str, context: EvalContext) -> int:
        """Resolve a ``1f`` or ``1b`` reference using source line order."""
        digits = name[:-1]
        direction = name[-1].lower()
        definitions = self.numeric_locals.get(digits, [])
        reference_seq = context.statement.seq
        if direction == "f":
            candidates = [item for item in definitions if item.seq > reference_seq]
            definition = min(candidates, key=lambda item: item.seq, default=None)
        else:
            candidates = [item for item in definitions if item.seq <= reference_seq]
            definition = max(candidates, key=lambda item: item.seq, default=None)
        if definition is None:
            raise AsmError("undefined local label: " + name,
                           context.statement.file, context.statement.line,
                           context.statement.source)
        if definition.section.base is None:
            raise AsmError("section address is not known for local label: " + name)
        return definition.section.base + definition.offset
