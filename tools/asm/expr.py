"""Expression parsing and evaluation for assembly operands."""

from dataclasses import dataclass
from typing import Any, List, Optional, Set, Tuple

try:
    from .errors import AsmError
    from .lexer import parse_character_literal
except ImportError:
    from errors import AsmError
    from lexer import parse_character_literal


SYMBOL_START = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_.$"
SYMBOL_CHARS = SYMBOL_START + "0123456789"
HEX_DIGITS = "0123456789abcdefABCDEF"


@dataclass
class EvalContext:
    """Information an expression needs in order to resolve its symbols."""

    statement: Any
    location: Optional[int] = None
    use: str = "data"


def tokenize(expression: str, statement) -> List[Tuple[str, Any]]:
    """Turn expression text into a small list of number, symbol and operator tokens."""
    tokens = []
    index = 0
    while index < len(expression):
        char = expression[index]
        if char.isspace():
            index += 1
            continue
        if char == "'":
            end = _find_quote_end(expression, index, statement)
            value = parse_character_literal(expression[index:end + 1], statement)
            tokens.append(("number", value))
            index = end + 1
            continue
        if char.isdigit():
            token, index = _read_number_or_local(expression, index, statement)
            tokens.append(token)
            continue
        if char in SYMBOL_START:
            end = index + 1
            while end < len(expression) and expression[end] in SYMBOL_CHARS:
                end += 1
            word = expression[index:end]
            tokens.append(("location", None) if word == "." else ("symbol", word))
            index = end
            continue
        if expression.startswith("<<", index) or expression.startswith(">>", index):
            tokens.append(("operator", expression[index:index + 2]))
            index += 2
            continue
        if char in "+-*|&~()":
            tokens.append(("operator", char))
            index += 1
            continue
        raise AsmError("invalid character in expression: " + char,
                       statement.file, statement.line, statement.source)
    return tokens


def _find_quote_end(expression: str, start: int, statement) -> int:
    """Find the closing quote of a character literal."""
    index = start + 1
    while index < len(expression):
        if expression[index] == "\\":
            index += 2
            continue
        if expression[index] == "'":
            return index
        index += 1
    raise AsmError("unterminated character literal", statement.file,
                   statement.line, statement.source)


def _read_number_or_local(expression: str, start: int, statement) -> Tuple[Tuple[str, Any], int]:
    """Read a decimal, hexadecimal, binary number or numeric local label."""
    remaining = expression[start:]
    if remaining[:2].lower() == "0x":
        end = start + 2
        while end < len(expression) and expression[end] in HEX_DIGITS:
            end += 1
        if end == start + 2:
            raise AsmError("bad hexadecimal number", statement.file,
                           statement.line, statement.source)
        return ("number", int(expression[start:end], 16)), end
    if remaining[:2].lower() == "0b":
        end = start + 2
        while end < len(expression) and expression[end] in "01":
            end += 1
        if end == start + 2:
            raise AsmError("bad binary number", statement.file,
                           statement.line, statement.source)
        return ("number", int(expression[start:end], 2)), end
    end = start
    while end < len(expression) and expression[end].isdigit():
        end += 1
    if end < len(expression) and expression[end] in "fFbB":
        return ("symbol", expression[start:end + 1]), end + 1
    return ("number", int(expression[start:end])), end


class Parser:
    """Recursive-descent parser with the usual arithmetic precedence."""

    def __init__(self, tokens: List[Tuple[str, Any]], statement) -> None:
        """Store the token list and the source statement for errors."""
        self.tokens = tokens
        self.position = 0
        self.statement = statement

    def parse(self):
        """Parse a complete expression and require all tokens to be consumed."""
        node = self.parse_or()
        if self.position != len(self.tokens):
            self.fail("unexpected token in expression")
        return node

    def parse_or(self):
        """Parse bitwise OR, the lowest supported precedence."""
        return self.parse_binary(self.parse_and, ("|",))

    def parse_and(self):
        """Parse bitwise AND."""
        return self.parse_binary(self.parse_shift, ("&",))

    def parse_shift(self):
        """Parse left and right shifts."""
        return self.parse_binary(self.parse_add, ("<<", ">>"))

    def parse_add(self):
        """Parse addition and subtraction."""
        return self.parse_binary(self.parse_multiply, ("+", "-"))

    def parse_multiply(self):
        """Parse multiplication."""
        return self.parse_binary(self.parse_unary, ("*",))

    def parse_binary(self, subparser, operators):
        """Fold a chain of one precedence level into a left-associated AST."""
        node = subparser()
        while self._peek_operator() in operators:
            operator = self.tokens[self.position][1]
            self.position += 1
            node = ("binary", operator, node, subparser())
        return node

    def parse_unary(self):
        """Parse the supported unary operators."""
        operator = self._peek_operator()
        if operator in ("+", "-", "~"):
            self.position += 1
            return ("unary", operator, self.parse_unary())
        return self.parse_primary()

    def parse_primary(self):
        """Parse a number, symbol, location counter or parenthesized expression."""
        if self.position >= len(self.tokens):
            self.fail("missing operand in expression")
        kind, value = self.tokens[self.position]
        self.position += 1
        if kind == "number":
            return ("number", value)
        if kind == "symbol":
            return ("symbol", value)
        if kind == "location":
            return ("location", None)
        if value == "(":
            node = self.parse_or()
            if self._peek_operator() != ")":
                self.fail("missing closing parenthesis")
            self.position += 1
            return node
        self.fail("unexpected operator in expression")

    def _peek_operator(self):
        """Return the next operator token, or None when there is none."""
        if self.position < len(self.tokens) and self.tokens[self.position][0] == "operator":
            return self.tokens[self.position][1]
        return None

    def fail(self, message: str) -> None:
        """Raise an error at the expression's source line."""
        raise AsmError(message, self.statement.file, self.statement.line,
                       self.statement.source)


class Expression:
    """A parsed expression that can be evaluated after all symbols are known."""

    def __init__(self, text: str, statement) -> None:
        """Parse the supplied text immediately so syntax errors are found early."""
        self.text = text
        self.canonical = "".join(text.lower().split())
        self.node = Parser(tokenize(text, statement), statement).parse()
        self.symbols_used: Set[str] = set()
        self._collect_symbols(self.node)

    def _collect_symbols(self, node) -> None:
        """Record the symbol names referenced anywhere in this expression."""
        if node[0] == "symbol":
            self.symbols_used.add(node[1])
        elif node[0] == "unary":
            self._collect_symbols(node[2])
        elif node[0] == "binary":
            self._collect_symbols(node[2])
            self._collect_symbols(node[3])

    def evaluate(self, symbols, context: EvalContext) -> int:
        """Evaluate the parsed expression using a symbol table and context."""
        return _evaluate_node(self.node, symbols, context)


def _evaluate_node(node, symbols, context: EvalContext) -> int:
    """Evaluate one AST node recursively."""
    kind = node[0]
    if kind == "number":
        return node[1]
    if kind == "location":
        if context.location is None:
            raise AsmError("location counter is not available here",
                           context.statement.file, context.statement.line,
                           context.statement.source)
        return context.location
    if kind == "symbol":
        return symbols.value(node[1], context)
    if kind == "unary":
        value = _evaluate_node(node[2], symbols, context)
        return _apply_unary(node[1], value)
    left = _evaluate_node(node[2], symbols, context)
    right = _evaluate_node(node[3], symbols, context)
    return _apply_binary(node[1], left, right, context)


def _apply_unary(operator: str, value: int) -> int:
    """Apply a unary arithmetic or bitwise operator."""
    if operator == "+":
        return value
    if operator == "-":
        return -value
    return ~value


def _apply_binary(operator: str, left: int, right: int, context: EvalContext) -> int:
    """Apply a binary operator, checking for invalid shift counts."""
    if operator == "+":
        return left + right
    if operator == "-":
        return left - right
    if operator == "*":
        return left * right
    if operator == "|":
        return left | right
    if operator == "&":
        return left & right
    if operator in ("<<", ">>"):
        if right < 0:
            raise AsmError("negative shift count", context.statement.file,
                           context.statement.line, context.statement.source)
        return left << right if operator == "<<" else left >> right
    raise AsmError("unsupported expression operator: " + operator,
                   context.statement.file, context.statement.line,
                   context.statement.source)
