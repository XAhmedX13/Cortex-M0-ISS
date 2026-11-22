"""Line-level lexer for GNU-style Thumb assembly source."""

from dataclasses import dataclass, field
from typing import List, Optional

from tools.asm.errors import ErrorCollector

LABEL_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.$"
ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", '"': '"'}
HEX_DIGITS = "0123456789abcdefABCDEF"


@dataclass
class Line:
    """One parsed source line with an optional label and statement."""

    number: int
    label: str = ""
    mnemonic: str = ""
    operands: List[str] = field(default_factory=list)


def strip_comment(text: str, file: str, line: int, errors: ErrorCollector) -> str:
    """Remove a trailing comment while preserving quoted strings."""
    kept: List[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            kept.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            kept.append(char)
            index += 1
            continue
        if char == "@":
            break
        if char == "/" and index + 1 < len(text) and text[index + 1] == "/":
            break
        kept.append(char)
        index += 1
    if in_string:
        errors.add_error(file, line, "unterminated string")
    return "".join(kept)


def find_label_colon(text: str) -> int:
    """Return the index of a leading label's colon, or -1 if none exists."""
    for index, char in enumerate(text):
        if char == ":":
            return index
        if char.isspace():
            return -1
    return -1


def is_valid_label(name: str) -> bool:
    """Accept ordinary labels and all-digit numeric local labels."""
    if name.isdigit():
        return True
    if not name or name[0].isdigit():
        return False
    return all(char in LABEL_CHARS for char in name)


def split_operands(text: str, file: str, line: int, errors: ErrorCollector) -> List[str]:
    """Split operands on commas outside strings, brackets, and braces."""
    if not text.strip():
        return []
    operands: List[str] = []
    current: List[str] = []
    bracket_depth = 0
    brace_depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            current.append(char)
            continue
        if char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
            if bracket_depth < 0:
                errors.add_error(file, line, "unbalanced ']' in operands")
        elif char == "{":
            brace_depth += 1
        elif char == "}":
            brace_depth -= 1
            if brace_depth < 0:
                errors.add_error(file, line, "unbalanced '}' in operands")
        if char == "," and bracket_depth == 0 and brace_depth == 0:
            operands.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if bracket_depth != 0:
        errors.add_error(file, line, "unbalanced '[' in operands")
    if brace_depth != 0:
        errors.add_error(file, line, "unbalanced '{' in operands")
    operands.append("".join(current).strip())
    return operands


def parse_quoted(token: str, file: str, line: int, errors: ErrorCollector) -> str:
    """Decode one double-quoted string token with assembly escapes."""
    if not token.startswith('"'):
        errors.add_error(file, line, "expected double-quoted string")
        return ""
    if len(token) < 2 or token[-1] != '"':
        return ""
    result: List[str] = []
    index = 1
    while index < len(token) - 1:
        char = token[index]
        if char == '"':
            errors.add_error(file, line, "unexpected character in string")
            return ""
        if char != "\\":
            result.append(char)
            index += 1
            continue
        if index + 1 >= len(token) - 1:
            errors.add_error(file, line, "bad escape at end of string")
            return ""
        escape = token[index + 1]
        if escape in ESCAPES:
            result.append(ESCAPES[escape])
            index += 2
            continue
        if escape == "x":
            digits = token[index + 2 : index + 4]
            if len(digits) == 2 and all(digit in HEX_DIGITS for digit in digits):
                result.append(chr(int(digits, 16)))
                index += 4
                continue
            errors.add_error(file, line, "bad \\x escape in string")
            return ""
        result.append(escape)
        index += 2
    return "".join(result)


def parse_line(number: int, text: str, file: str, errors: ErrorCollector) -> Optional[Line]:
    """Parse one source line into a label, mnemonic, and operand texts."""
    cleaned = strip_comment(text, file, number, errors)
    stripped = cleaned.strip()
    if not stripped:
        return None
    label = ""
    rest = stripped
    colon = find_label_colon(stripped)
    if colon >= 0:
        label = stripped[:colon].strip()
        rest = stripped[colon + 1 :].strip()
        if not is_valid_label(label):
            errors.add_error(file, number, "invalid label name")
            return None
    if not rest:
        return Line(number=number, label=label)
    parts = rest.split(None, 1)
    mnemonic = parts[0].lower()
    operand_text = parts[1].strip() if len(parts) > 1 else ""
    operands = split_operands(operand_text, file, number, errors)
    return Line(number=number, label=label, mnemonic=mnemonic, operands=operands)
