"""readelf-style dump and human-readable listing writers."""

try:
    from .expr import EvalContext
    from .symbols import Symbol
except ImportError:
    from expr import EvalContext
    from symbols import Symbol


def write_dump(program, include_ascii: bool = True) -> str:
    """Render all non-empty, byte-producing sections in address order."""
    lines = []
    for section in program.sorted_sections():
        if section.is_nobits or section.size == 0:
            continue
        data = section.byte_image()
        lines.append("")
        lines.append("Hex dump of section '" + section.name + "':")
        for offset in range(0, len(data), 16):
            lines.append(_format_dump_line(section.base + offset,
                                           data[offset:offset + 16], include_ascii))
        lines.append("")
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _format_dump_line(address: int, chunk: bytes, include_ascii: bool) -> str:
    """Format one 16-byte dump line with readelf's fixed hex column width."""
    groups = []
    for group_index in range(4):
        group = chunk[group_index * 4:group_index * 4 + 4]
        text = "".join("{:02x}".format(byte) for byte in group)
        groups.append(text.ljust(8))
    line = " 0x{:08x} ".format(address) + " ".join(groups)
    if not include_ascii:
        return line.rstrip()
    return line + " " + _ascii_column(chunk)


def _ascii_column(chunk: bytes) -> str:
    """Return printable bytes as characters and all other bytes as dots."""
    characters = []
    for byte in chunk:
        if 32 <= byte <= 126:
            characters.append(chr(byte))
        else:
            characters.append(".")
    return "".join(characters)


def write_listing(program) -> str:
    """Render one listing line per emitted item and append the symbol table."""
    lines = []
    for section in program.sorted_sections():
        for item in section.items:
            address = section.base + item.offset
            hex_bytes = item.encoded.hex()
            line_number = item.statement.line if item.statement is not None else 0
            source = item.statement.source if item.statement is not None else ""
            lines.append("0x{:08x}  {}  {}: {}".format(address, hex_bytes,
                                                       line_number, source))
    lines.append("")
    lines.append("Symbol table:")
    for symbol in program.symbols.iter_symbols():
        lines.append(_format_symbol(symbol, program.symbols))
    return "\n".join(lines) + "\n"


def _format_symbol(symbol: Symbol, symbols) -> str:
    """Format one symbol table row with its final value."""
    location = None
    if symbol.definition_section is not None and symbol.definition_section.base is not None:
        location = symbol.definition_section.base + symbol.definition_offset
    context = EvalContext(symbol.definition, location, "data")
    value = symbols.value(symbol.name, context)
    if symbol.is_thumb_func:
        value &= ~1
    text = "{:<16} 0x{:08x}".format(symbol.name, value)
    if symbol.is_thumb_func:
        text += " T"
    return text
