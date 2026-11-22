"""Command-line entry point for the Thumb assembler."""

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.asm import directives, dump, encode
from tools.asm.errors import ErrorCollector
from tools.asm.lexer import parse_line
from tools.asm.layout import Assembler


class AssemblerParser(argparse.ArgumentParser):
    """Argument parser that reports every failure with exit status 1."""

    def error(self, message: str) -> None:
        """Print usage and the error message, then exit with status 1."""
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def parse_section_addr(text: str) -> Tuple[str, int]:
    """Parse a --section-addr value of the form NAME=ADDR."""
    if "=" not in text:
        raise argparse.ArgumentTypeError("expected NAME=ADDR")
    name, address_text = text.split("=", 1)
    if not name:
        raise argparse.ArgumentTypeError("section name must not be empty")
    try:
        address = int(address_text, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid address: {address_text}")
    return name, address


def _write_outputs(outputs: List[Tuple[Path, str]], errors: ErrorCollector) -> bool:
    """Write all output files, removing any partial output on failure."""
    written: List[Path] = []
    for path, text in outputs:
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
            written.append(path)
        except OSError as exc:
            for completed in written:
                try:
                    completed.unlink(missing_ok=True)
                except OSError:
                    pass
            errors.add_error(str(path), 0, f"cannot write output file: {exc}")
            return False
    return True


def main(argv: Optional[List[str]] = None) -> int:
    """Run the full assemble pipeline and return the process exit status."""
    parser = AssemblerParser(
        description="Assemble GNU-style Thumb source into readelf-style section dumps."
    )
    parser.add_argument("source", type=Path, help="input assembly source file")
    parser.add_argument("-o", "--output", type=Path, help="output dump file")
    parser.add_argument("--listing", type=Path, help="optional listing file")
    parser.add_argument(
        "--no-ascii", action="store_true", help="omit the ASCII column from dump lines"
    )
    parser.add_argument(
        "--section-addr",
        action="append",
        default=[],
        type=parse_section_addr,
        metavar="NAME=ADDR",
        help="override a section base address",
    )
    args = parser.parse_args(argv)

    file = str(args.source)
    errors = ErrorCollector()
    if not args.source.is_file():
        errors.add_error(file, 0, "input file does not exist")
        errors.report()
        return 1
    try:
        source_text = args.source.read_text(encoding="utf-8")
    except OSError as exc:
        errors.add_error(file, 0, f"cannot read input file: {exc}")
        errors.report()
        return 1

    assembler = Assembler(file, errors, dict(args.section_addr))
    assembler.source_lines = {
        number: text for number, text in enumerate(source_text.splitlines(), 1)
    }
    parsed = []
    for number, text in assembler.source_lines.items():
        line = parse_line(number, text, file, errors)
        if line is not None:
            parsed.append(line)

    assembler.set_directive_handler(directives.handle)
    assembler.set_item_writer(encode.write_item)
    assembler.process_lines(parsed)
    assembler.assign_section_bases()
    assembler.fill_bytes()

    if errors.has_errors():
        errors.report()
        return 1

    dump_text = dump.write_dump(assembler, include_ascii=not args.no_ascii)
    outputs = [(args.output or args.source.with_suffix(".dump"), dump_text)]
    if args.listing is not None:
        outputs.append((args.listing, dump.write_listing(assembler)))
    if not _write_outputs(outputs, errors):
        errors.report()
        return 1

    errors.report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
