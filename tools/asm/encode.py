"""Instruction encoding dispatch for the Thumb assembler."""

from tools.asm.directives import write_item as write_data_item
from tools.asm.layout import Assembler, Item


def write_item(asm: Assembler, item: Item) -> None:
    """Write final bytes for one item during pass 2."""
    if item.kind == "instr":
        asm.errors.add_error(
            asm.file,
            item.line,
            "instruction encoding not implemented until M2",
        )
        return
    write_data_item(asm, item)
