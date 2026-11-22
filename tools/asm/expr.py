"""Number parsing and expression evaluation for assembler operands."""

from typing import Callable, List, NamedTuple, Optional

from tools.asm.errors import ErrorCollector

HEX_DIGITS = "0123456789abcdefABCDEF"
CHAR_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", '"': '"'}


class Token(NamedTuple):
    """One token produced by the expression tokenizer."""

    kind: str
    value: object


class ExpressionError(Exception):
    """Raised when the expression grammar cannot consume the tokens."""


def is_symbol_start(char: str) -> bool:
    """Return True if a character can start a named symbol."""
    return char.isalpha() or char in "_$"


def is_symbol_continue(char: str) -> bool:
    """Return True if a character can continue a named symbol."""
    return char.isalnum() or char in "_.$"


def is_numeric_local_reference(text: str) -> bool:
    """Return True for numeric local references such as 1f or 12b."""
    return len(text) >= 2 and text[-1] in "fb" and text[:-1].isdigit()


def parse_char_literal(token: str, file: str, line: int, errors: ErrorCollector) -> Optional[int]:
    """Convert a single-quoted character literal to its integer value."""
    if len(token) < 3 or token[0] != "'" or token[-1] != "'":
        errors.add_error(file, line, "invalid character literal")
        return None
    body = token[1:-1]
    if len(body) == 1 and body != "\\":
        return ord(body)
    if len(body) == 2 and body[0] == "\\" and body[1] in CHAR_ESCAPES:
        return ord(CHAR_ESCAPES[body[1]])
    if len(body) == 4 and body[:2] == "\\x" and all(char in HEX_DIGITS for char in body[2:]):
        return int(body[2:], 16)
    errors.add_error(file, line, "unsupported character literal")
    return None


def parse_number(token: str, file: str, line: int, errors: ErrorCollector) -> Optional[int]:
    """Parse an integer literal, returning None for non-numeric text."""
    text = token.strip()
    if not text:
        return None
    negative = False
    if text[0] in "+-":
        negative = text[0] == "-"
        text = text[1:]
    if not text:
        errors.add_error(file, line, "invalid number")
        return None
    value: Optional[int]
    if text[0] == "'":
        value = parse_char_literal(text, file, line, errors)
    elif text[0].isdigit():
        lowered = text.lower()
        if lowered.startswith("0x"):
            digits, base = text[2:], 16
            valid = "0123456789abcdefABCDEF"
        elif lowered.startswith("0b"):
            digits, base = text[2:], 2
            valid = "01"
        else:
            digits, base = text, 10
            valid = "0123456789"
        if not digits or any(char not in valid for char in digits):
            errors.add_error(file, line, f"invalid number: {token}")
            return None
        value = int(digits, base)
    else:
        return None
    if value is None:
        return None
    return -value if negative else value


def tokenize(text: str, file: str, line: int, errors: ErrorCollector) -> List[Token]:
    """Split expression text into numbers, symbols, operators, and punctuation."""
    tokens: List[Token] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char.isdigit():
            start = index
            while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                index += 1
            word = text[start:index]
            if is_numeric_local_reference(word):
                tokens.append(Token("symbol", word))
            else:
                value = parse_number(word, file, line, errors)
                if value is not None:
                    tokens.append(Token("number", value))
            continue
        if char == "'":
            start = index
            index += 1
            while index < len(text):
                if text[index] == "\\" and index + 1 < len(text):
                    index += 2
                    continue
                if text[index] == "'":
                    index += 1
                    break
                index += 1
            value = parse_number(text[start:index], file, line, errors)
            if value is not None:
                tokens.append(Token("number", value))
            continue
        if char == ".":
            if index + 1 < len(text) and is_symbol_continue(text[index + 1]):
                start = index
                index += 1
                while index < len(text) and is_symbol_continue(text[index]):
                    index += 1
                tokens.append(Token("symbol", text[start:index]))
            else:
                tokens.append(Token("dot", "."))
                index += 1
            continue
        if is_symbol_start(char):
            start = index
            index += 1
            while index < len(text) and is_symbol_continue(text[index]):
                index += 1
            tokens.append(Token("symbol", text[start:index]))
            continue
        if char in "+-*|&":
            tokens.append(Token("op", char))
            index += 1
            continue
        if char == "<" and index + 1 < len(text) and text[index + 1] == "<":
            tokens.append(Token("op", "<<"))
            index += 2
            continue
        if char == ">" and index + 1 < len(text) and text[index + 1] == ">":
            tokens.append(Token("op", ">>"))
            index += 2
            continue
        if char == "(":
            tokens.append(Token("lparen", char))
            index += 1
            continue
        if char == ")":
            tokens.append(Token("rparen", char))
            index += 1
            continue
        errors.add_error(file, line, f"invalid character in expression: {char}")
        index += 1
    tokens.append(Token("end", ""))
    return tokens


def contains_symbol(text: str) -> bool:
    """Return True if the expression text mentions any symbol."""
    ignored = ErrorCollector()
    return any(token.kind == "symbol" for token in tokenize(text, "", 0, ignored))


class _Parser:
    """Recursive-descent parser over a token list."""

    def __init__(
        self,
        tokens: List[Token],
        dot: int,
        resolve: Callable[[str], int],
        file: str,
        line: int,
        errors: ErrorCollector,
    ) -> None:
        """Store parser state and the callback used to resolve symbols."""
        self.tokens = tokens
        self.dot = dot
        self.resolve = resolve
        self.file = file
        self.line = line
        self.errors = errors
        self.index = 0

    def peek(self) -> Token:
        """Return the current token without consuming it."""
        return self.tokens[self.index]

    def advance(self) -> Token:
        """Return the current token and move to the next one."""
        token = self.tokens[self.index]
        self.index += 1
        return token

    def accept(self, *operators: str) -> bool:
        """Consume the current token if it is one of the given operators."""
        if self.peek().kind == "op" and self.peek().value in operators:
            self.advance()
            return True
        return False

    def parse(self) -> int:
        """Parse the whole expression and return its integer value."""
        return self.parse_bit_or()

    def parse_bit_or(self) -> int:
        """Parse bitwise OR expressions."""
        value = self.parse_bit_and()
        while self.accept("|"):
            value |= self.parse_bit_and()
        return value

    def parse_bit_and(self) -> int:
        """Parse bitwise AND expressions."""
        value = self.parse_shift()
        while self.accept("&"):
            value &= self.parse_shift()
        return value

    def parse_shift(self) -> int:
        """Parse left and right shift expressions."""
        value = self.parse_additive()
        while self.peek().kind == "op" and self.peek().value in ("<<", ">>"):
            operator = self.advance().value
            amount = self.parse_additive()
            value = value << amount if operator == "<<" else value >> amount
        return value

    def parse_additive(self) -> int:
        """Parse addition and subtraction expressions."""
        value = self.parse_multiplicative()
        while self.peek().kind == "op" and self.peek().value in ("+", "-"):
            operator = self.advance().value
            term = self.parse_multiplicative()
            value = value + term if operator == "+" else value - term
        return value

    def parse_multiplicative(self) -> int:
        """Parse multiplication expressions."""
        value = self.parse_unary()
        while self.accept("*"):
            value *= self.parse_unary()
        return value

    def parse_unary(self) -> int:
        """Parse unary plus and minus."""
        if self.accept("+"):
            return self.parse_unary()
        if self.accept("-"):
            return -self.parse_unary()
        return self.parse_primary()

    def parse_primary(self) -> int:
        """Parse a number, symbol, location counter, or parenthesized expression."""
        token = self.peek()
        if token.kind == "number":
            self.advance()
            return int(token.value)
        if token.kind == "dot":
            self.advance()
            return self.dot
        if token.kind == "symbol":
            self.advance()
            value = self.resolve(str(token.value))
            if value is None:
                self.errors.add_error(self.file, self.line, f"undefined symbol: {token.value}")
                return 0
            return value
        if token.kind == "lparen":
            self.advance()
            value = self.parse_bit_or()
            if self.peek().kind != "rparen":
                raise ExpressionError("missing closing parenthesis")
            self.advance()
            return value
        raise ExpressionError("expected a value")


def evaluate(
    text: str,
    dot: int,
    resolve: Callable[[str], int],
    file: str,
    line: int,
    errors: ErrorCollector,
) -> int:
    """Evaluate expression text using the supplied symbol resolver."""
    before = len(errors.errors)
    tokens = tokenize(text, file, line, errors)
    if len(errors.errors) > before:
        return 0
    parser = _Parser(tokens, dot, resolve, file, line, errors)
    try:
        value = parser.parse()
    except ExpressionError:
        errors.add_error(file, line, "invalid expression")
        return 0
    if parser.peek().kind != "end":
        errors.add_error(file, line, "unexpected text at end of expression")
        return 0
    return value
