"""Line and operand lexing for the supported GNU-style Thumb assembly subset."""

from dataclasses import dataclass
from typing import List

try:
    from .errors import AsmError
except ImportError:
    from errors import AsmError


LABEL_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.$"
LABEL_START = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_.$"


@dataclass
class Statement:
    """One source line after comments have been removed and fields split."""

    file: str
    line: int
    source: str
    labels: List[str]
    kind: str
    mnemonic: str
    operands: List[str]
    seq: int = 0


def strip_comment(text: str, file: str, line: int) -> str:
    """Remove ``@`` and ``//`` comments while leaving quoted strings alone."""
    result = []
    index = 0
    in_string = False
    while index < len(text):
        char = text[index]
        if in_string:
            result.append(char)
            if char == "\\" and index + 1 < len(text):
                index += 1
                result.append(text[index])
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
            result.append(char)
        elif char == "@" or text.startswith("//", index):
            break
        else:
            result.append(char)
        index += 1
    if in_string:
        raise AsmError("unterminated string", file, line, text.strip())
    return "".join(result)


def parse_string(text: str, statement: Statement) -> bytes:
    """Decode one double-quoted assembler string into raw bytes."""
    stripped = text.strip()
    if len(stripped) < 2 or stripped[0] != '"' or stripped[-1] != '"':
        raise AsmError("expected a double-quoted string", statement.file,
                       statement.line, statement.source)
    body = stripped[1:-1]
    result = bytearray()
    index = 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            result.extend(char.encode("utf-8"))
            index += 1
            continue
        if index + 1 >= len(body):
            raise AsmError("unterminated escape sequence", statement.file,
                           statement.line, statement.source)
        escape = body[index + 1]
        simple = {"n": 10, "t": 9, "r": 13, "0": 0, "\\": 92, '"': 34}
        if escape in simple:
            result.append(simple[escape])
            index += 2
        elif escape == "x":
            digits = body[index + 2:index + 4]
            if len(digits) != 2 or any(c not in "0123456789abcdefABCDEF" for c in digits):
                raise AsmError("bad \\xHH string escape", statement.file,
                               statement.line, statement.source)
            result.append(int(digits, 16))
            index += 4
        else:
            raise AsmError("unsupported string escape: \\" + escape,
                           statement.file, statement.line, statement.source)
    return bytes(result)


def parse_character_literal(text: str, statement: Statement) -> int:
    """Decode a one-character literal such as ``'A'`` or ``'\\n'``."""
    stripped = text.strip()
    if len(stripped) < 3 or stripped[0] != "'" or stripped[-1] != "'":
        raise AsmError("bad character literal", statement.file,
                       statement.line, statement.source)
    body = stripped[1:-1]
    if body.startswith("\\"):
        if len(body) == 2 and body[1] in "ntr0\\\"'":
            return {"n": 10, "t": 9, "r": 13, "0": 0, "\\": 92, '"': 34, "'": 39}[body[1]]
        if len(body) == 4 and body[1] == "x":
            digits = body[2:]
            if all(c in "0123456789abcdefABCDEF" for c in digits):
                return int(digits, 16)
        raise AsmError("bad character escape", statement.file,
                       statement.line, statement.source)
    if len(body) != 1:
        raise AsmError("character literal must contain one character",
                       statement.file, statement.line, statement.source)
    return ord(body)


def split_operands(text: str, statement: Statement) -> List[str]:
    """Split operands on commas outside strings, brackets and braces."""
    if not text.strip():
        return []
    parts = []
    start = 0
    stack = []
    in_string = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            if char == "\\":
                index += 1
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            stack.append(char)
        elif char in "]}":
            if not stack:
                raise AsmError("unbalanced closing bracket", statement.file,
                               statement.line, statement.source)
            stack.pop()
        elif char == "," and not stack:
            parts.append(text[start:index].strip())
            start = index + 1
        index += 1
    if stack:
        raise AsmError("unbalanced opening bracket", statement.file,
                       statement.line, statement.source)
    parts.append(text[start:].strip())
    return parts


def validate_label(label: str, statement: Statement) -> None:
    """Check that a parsed label obeys the source-language naming rules."""
    if label.isdigit():
        return
    if label[0] in LABEL_START and all(char in LABEL_CHARS for char in label):
        return
    raise AsmError("invalid label: " + label, statement.file,
                   statement.line, statement.source)


def lex_line(raw_line: str, file: str, line: int, seq: int) -> Statement:
    """Split one source line into labels, a mnemonic and operand strings."""
    source = raw_line.strip()
    empty = Statement(file, line, source, [], "empty", "", [], seq)
    if not source:
        return empty
    text = strip_comment(source, file, line).strip()
    if not text:
        return empty
    labels = []
    while text:
        index = 0
        while index < len(text) and text[index].isspace():
            index += 1
        start = index
        while index < len(text) and text[index] in LABEL_CHARS:
            index += 1
        if index == start or index >= len(text) or text[index] != ":":
            break
        label = text[start:index]
        validate_label(label, empty)
        labels.append(label)
        text = text[index + 1:]
    text = text.strip()
    if not text:
        empty.labels = labels
        return empty
    pieces = text.split(None, 1)
    mnemonic = pieces[0].lower()
    operand_text = pieces[1] if len(pieces) == 2 else ""
    kind = "directive" if mnemonic.startswith(".") else "instruction"
    statement = Statement(file, line, source, labels, kind, mnemonic, [], seq)
    statement.operands = split_operands(operand_text, statement)
    return statement


def lex_source(text: str, file: str, diagnostics) -> List[Statement]:
    """Lex every line, recording lexical errors without losing later lines."""
    statements = []
    for index, line_text in enumerate(text.splitlines()):
        line_number = index + 1
        try:
            statement = lex_line(line_text, file, line_number, index)
        except AsmError as error:
            diagnostics.add_error(error)
            statement = Statement(file, line_number, line_text.strip(), [],
                                  "empty", "", [], index)
        statements.append(statement)
    return statements
