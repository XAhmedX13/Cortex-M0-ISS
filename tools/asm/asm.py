"""Command-line entry point for the Thumb assembler."""

import argparse
from pathlib import Path
import sys

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

if __package__:
    from . import dump, encode, layout, lexer
    from .errors import AsmError, Diagnostics
else:
    from asm import dump, encode, layout, lexer
    from asm.errors import AsmError, Diagnostics


def parse_section_address(text: str):
    """Parse one ``NAME=ADDR`` command-line section override."""
    if "=" not in text:
        raise argparse.ArgumentTypeError("expected NAME=ADDR")
    name, address_text = text.split("=", 1)
    if not name:
        raise argparse.ArgumentTypeError("section name must not be empty")
    try:
        address = int(address_text, 0)
    except ValueError:
        raise argparse.ArgumentTypeError("bad address: " + address_text)
    return name, address


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Assemble a small Thumb (ARMv6-M) source file into a readelf-style dump.")
    parser.add_argument("input", type=Path, help="assembly source file")
    parser.add_argument("-o", "--output", type=Path,
                        help="dump output file (default: input name with .dump)")
    parser.add_argument("--listing", type=Path, help="optional listing output file")
    parser.add_argument("--no-ascii", action="store_true",
                        help="omit the ASCII column from dump lines")
    parser.add_argument("--section-addr", action="append", default=[],
                        type=parse_section_address, metavar="NAME=ADDR",
                        help="override a section base address")
    parser.add_argument("--quiet", action="store_true",
                        help="do not print the output file name on success")
    return parser


def assemble_source(source_text: str, filename: str, diagnostics: Diagnostics,
                    section_overrides=None) -> layout.Program:
    """Run lexing, pass one, base assignment and pass two."""
    statements = lexer.lex_source(source_text, filename, diagnostics)
    program = layout.Program(diagnostics, section_overrides)
    for statement in statements:
        try:
            program.layout_statement(statement)
        except AsmError as error:
            diagnostics.add_error(error)
        if program.stop:
            break
    try:
        program.finish_layout()
        program.assign_base_addresses()
    except AsmError as error:
        diagnostics.add_error(error)
    if not diagnostics.has_errors():
        encode.encode_program(program, diagnostics)
        program.check_vector_warning()
    return program


def main(argv=None) -> int:
    """Assemble one file, returning a shell exit status."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    source_path = arguments.input
    if not source_path.is_file():
        parser.error("source file does not exist: " + str(source_path))
    try:
        source_text = source_path.read_text(encoding="utf-8")
    except OSError as error:
        print("error: cannot read " + str(source_path) + ": " + str(error),
              file=sys.stderr)
        return 1
    diagnostics = Diagnostics()
    program = assemble_source(source_text, str(source_path), diagnostics,
                              dict(arguments.section_addr))
    diagnostics.print_all(sys.stderr)
    if diagnostics.has_errors():
        return 1
    output_path = arguments.output or source_path.with_suffix(".dump")
    dump_text = dump.write_dump(program, not arguments.no_ascii)
    listing_text = dump.write_listing(program) if arguments.listing else None
    try:
        output_path.write_text(dump_text, encoding="utf-8")
        if listing_text is not None:
            arguments.listing.write_text(listing_text, encoding="utf-8")
    except OSError as error:
        print("error: cannot write output: " + str(error), file=sys.stderr)
        return 1
    if not arguments.quiet:
        print(output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
