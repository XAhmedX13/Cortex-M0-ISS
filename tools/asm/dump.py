"""Dump and listing writers for the Thumb assembler."""

from tools.asm.layout import Assembler

PRINTABLE_MIN = 0x20
PRINTABLE_MAX = 0x7E


def _format_hex_field(data: bytes) -> str:
    """Format up to 16 bytes as four fixed-width groups of four bytes."""
    groups = []
    for index in range(4):
        chunk = data[index * 4 : index * 4 + 4]
        groups.append(chunk.hex().ljust(8) if chunk else " " * 8)
    return " ".join(groups)


def _ascii_column(data: bytes) -> str:
    """Render printable bytes as themselves and all others as dots."""
    return "".join(
        chr(byte) if PRINTABLE_MIN <= byte <= PRINTABLE_MAX else "."
        for byte in data
    )


def _format_data_line(address: int, data: bytes, include_ascii: bool) -> str:
    """Format one readelf-style dump data line."""
    line = f"  0x{address:08x} {_format_hex_field(data)}"
    if include_ascii:
        line += " " + _ascii_column(data)
    return line


def write_dump(asm: Assembler, include_ascii: bool = True) -> str:
    """Build the complete readelf-style dump text in memory."""
    lines = []
    sections = [
        section
        for section in asm.sections.values()
        if section.data and not section.is_nobits
    ]
    for section in sorted(sections, key=lambda item: item.base):
        lines.append("")
        lines.append(f"Hex dump of section '{section.name}':")
        for offset in range(0, len(section.data), 16):
            chunk = bytes(section.data[offset : offset + 16])
            lines.append(
                _format_data_line(section.base + offset, chunk, include_ascii)
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def write_listing(asm: Assembler) -> str:
    """Build the source listing and symbol table text in memory."""
    lines = []
    for address, hex_bytes, line_number in asm.listing:
        source = asm.source_lines.get(line_number, "").rstrip("\n")
        lines.append(f"{address:08x}  {hex_bytes:<34}  {line_number}: {source}")
    lines.append("")
    lines.append("Symbol table:")
    for name, symbol in sorted(asm.symbols.symbols.items()):
        if symbol.is_absolute:
            address = symbol.value
        else:
            address = asm.symbols.section_address(symbol.section, symbol.offset)
        marker = " T" if symbol.is_thumb_func else ""
        lines.append(f"{name:<16} 0x{address:08x}{marker}")
    return "\n".join(lines) + "\n"
