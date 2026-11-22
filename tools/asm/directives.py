"""Directive handling for both assembler passes."""

from typing import List

from tools.asm.expr import evaluate
from tools.asm.layout import Assembler, Item
from tools.asm.lexer import Line, parse_quoted

IGNORED_DIRECTIVES = {
    ".syntax",
    ".cpu",
    ".arch",
    ".thumb",
    ".fpu",
    ".type",
    ".size",
    ".file",
    ".eabi_attribute",
}

DATA_WIDTH = {
    ".word": 4,
    ".long": 4,
    ".4byte": 4,
    ".hword": 2,
    ".short": 2,
    ".2byte": 2,
    ".byte": 1,
}

STRING_DIRECTIVES = {".ascii", ".asciz", ".string"}
SPACE_DIRECTIVES = {".space", ".skip", ".zero"}
ALIGN_DIRECTIVES = {".align", ".balign", ".p2align"}


def _evaluate_value(
    asm: Assembler, text: str, line_number: int, dot: int, as_data: bool
) -> int:
    """Evaluate expression text with a resolver bound to one source line."""
    resolver = asm.symbols.make_resolver(line_number, asm.file, asm.errors, as_data)
    return evaluate(text, dot, resolver, asm.file, line_number, asm.errors)


def _require_operands(asm: Assembler, line: Line, minimum: int) -> bool:
    """Report a wrong operand count and return whether enough were supplied."""
    if len(line.operands) < minimum:
        asm.errors.add_error(asm.file, line.number, "wrong operand count")
        return False
    return True


def _handle_section(asm: Assembler, line: Line) -> None:
    """Switch the current section, including NOBITS handling."""
    if not _require_operands(asm, line, 1):
        return
    name = line.operands[0]
    flags = [operand.lower() for operand in line.operands[1:]]
    is_nobits = name == ".bss" or "%nobits" in flags or "nobits" in flags
    asm.set_section(name, is_nobits)


def _handle_symbols(asm: Assembler, line: Line) -> None:
    """Handle .global, .globl, and .thumb_func."""
    if line.mnemonic == ".thumb_func":
        asm.symbols.set_pending_thumb_func()
        return
    for name in line.operands:
        asm.symbols.mark_global(name)


def _handle_equ(asm: Assembler, line: Line) -> None:
    """Define an absolute symbol from an expression."""
    if not _require_operands(asm, line, 2):
        return
    name = line.operands[0]
    expression = ",".join(line.operands[1:])
    value = _evaluate_value(asm, expression, line.number, asm.current_offset(), False)
    asm.symbols.define_absolute(name, value, asm.file, line.number, asm.errors)


def _decode_strings(asm: Assembler, line: Line) -> bytes:
    """Decode string operands and append a NUL for .asciz and .string."""
    payload = bytearray()
    for operand in line.operands:
        text = parse_quoted(operand, asm.file, line.number, asm.errors)
        payload.extend(text.encode("utf-8"))
    if line.mnemonic in (".asciz", ".string"):
        payload.append(0)
    return bytes(payload)


def _handle_space(asm: Assembler, line: Line) -> None:
    """Reserve a number of bytes with an optional fill value."""
    if not _require_operands(asm, line, 1):
        return
    count = _evaluate_value(asm, line.operands[0], line.number, asm.current_offset(), False)
    if count < 0:
        asm.errors.add_error(asm.file, line.number, "space count must not be negative")
        return
    fill = 0
    if len(line.operands) > 1:
        fill = _evaluate_value(asm, line.operands[1], line.number, asm.current_offset(), False)
    if fill < -128 or fill > 255:
        asm.errors.add_error(asm.file, line.number, "fill value out of range: -128..255")
    asm.emit(
        "bytes",
        count,
        line.number,
        line.mnemonic,
        payload=bytes([fill & 0xFF]),
    )


def _handle_align(asm: Assembler, line: Line) -> None:
    """Emit alignment padding using GNU ARM alignment meanings."""
    if not _require_operands(asm, line, 1):
        return
    amount = _evaluate_value(asm, line.operands[0], line.number, asm.current_offset(), False)
    if amount < 0 or (line.mnemonic != ".balign" and amount > 31):
        asm.errors.add_error(asm.file, line.number, "alignment out of range")
        return
    boundary = amount if line.mnemonic == ".balign" else 1 << amount
    if boundary < 1:
        asm.errors.add_error(asm.file, line.number, "alignment must be positive")
        return
    asm.align(boundary, line.number)


def _handle_data(asm: Assembler, line: Line) -> None:
    """Reserve bytes for numeric or string data directives."""
    if not _require_operands(asm, line, 1):
        return
    if line.mnemonic in STRING_DIRECTIVES:
        payload = _decode_strings(asm, line)
        asm.emit("bytes", len(payload), line.number, line.mnemonic, payload=payload)
        return
    if line.mnemonic in SPACE_DIRECTIVES:
        _handle_space(asm, line)
        return
    width = DATA_WIDTH[line.mnemonic]
    if width == 4 and asm.current_offset() % 4 != 0:
        asm.errors.add_warning(asm.file, line.number, "unaligned .word")
    asm.emit("bytes", width * len(line.operands), line.number, line.mnemonic, line.operands)


def handle(asm: Assembler, line: Line) -> None:
    """Handle one directive during pass 1."""
    mnemonic = line.mnemonic
    if mnemonic in IGNORED_DIRECTIVES:
        return
    if mnemonic == ".end":
        asm.stopped = True
        return
    if mnemonic in (".text", ".data", ".bss", ".section"):
        if mnemonic == ".section":
            _handle_section(asm, line)
        else:
            asm.set_section(mnemonic, mnemonic == ".bss")
        return
    if mnemonic in (".global", ".globl", ".thumb_func"):
        _handle_symbols(asm, line)
        return
    if mnemonic in (".equ", ".set"):
        _handle_equ(asm, line)
        return
    if mnemonic in DATA_WIDTH or mnemonic in STRING_DIRECTIVES or mnemonic in SPACE_DIRECTIVES:
        _handle_data(asm, line)
        return
    if mnemonic in ALIGN_DIRECTIVES:
        _handle_align(asm, line)
        return
    if mnemonic in (".ltorg", ".pool"):
        return
    asm.errors.add_error(asm.file, line.number, f"unsupported directive: {mnemonic}")


def _pack_value(asm: Assembler, item: Item, value: int, width: int) -> bytes:
    """Range-check and pack one data value as little-endian bytes."""
    bits = width * 8
    minimum = -(1 << (bits - 1))
    maximum = (1 << bits) - 1
    if value < minimum or value > maximum:
        asm.errors.add_error(
            asm.file,
            item.line,
            f"value out of range for {item.mnemonic}: {value} (range {minimum}..{maximum})",
        )
        return bytes(width)
    return (value & maximum).to_bytes(width, "little")


def write_item(asm: Assembler, item: Item) -> None:
    """Write a data item's final bytes during pass 2."""
    if item.kind != "bytes":
        return
    section = asm.sections[item.section]
    if item.mnemonic in STRING_DIRECTIVES:
        data = item.payload
    elif item.mnemonic in SPACE_DIRECTIVES:
        data = item.payload * item.size
    else:
        width = DATA_WIDTH[item.mnemonic]
        chunks: List[bytes] = []
        for offset, operand in enumerate(item.operands):
            dot = section.base + item.offset + offset * width
            value = _evaluate_value(asm, operand, item.line, dot, True)
            chunks.append(_pack_value(asm, item, value, width))
        data = b"".join(chunks)
    section.data[item.offset : item.offset + len(data)] = data
