"""Tests for milestones M1 through M4 of the Thumb assembler."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ASM_DIR = Path(__file__).resolve().parents[1]
TOOLS_DIR = ASM_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from asm import asm, dump
from asm.errors import Diagnostics


FACTORIAL_SOURCE = """
    @ main(void) is not used: entry is _start.
    .syntax unified
    .cpu cortex-m0
    .thumb
    .section .vectors, "a"
    .word 0x20040000        @ initial sp: top of RAM
    .word _start            @ reset vector
    .text
    .thumb_func
    .global _start
_start: ldr r0, =msg
    svc #0x11               @ PUTS
    movs r0, #10
    bl fact
    svc #0x12               @ PUTINT
    movs r0, #0
    svc #0x00               @ EXIT
    .thumb_func
fact: push {r4, lr}         @ r0 = n, returns n!
    movs r4, r0
    cmp r0, #1
    ble 1f
    subs r0, #1
    bl fact
    muls r0, r4, r0
    pop {r4, pc}
1:  movs r0, #1
    pop {r4, pc}
    .section .rodata
msg: .asciz "10! = "
"""


def assemble_text(source: str, overrides=None):
    """Assemble source text in memory and return the program and diagnostics."""
    diagnostics = Diagnostics()
    program = asm.assemble_source(source, "test.s", diagnostics, overrides or {})
    return program, diagnostics


def encoded_halfword(source: str) -> int:
    """Assemble one instruction at 0x100 and return its 16-bit encoding."""
    program, diagnostics = assemble_text(".text\n" + source + "\n")
    if diagnostics.errors:
        raise AssertionError("\n".join(diagnostics.errors))
    for item in program.sections[".text"].items:
        if item.kind == "instr":
            return int.from_bytes(item.encoded[:2], "little")
    raise AssertionError("no instruction was emitted")


class EncodingTableTests(unittest.TestCase):
    """Check the required one-line encodings from section 11.1."""

    def test_encoding_table(self):
        """Every listed one-line encoding matches the ARMv6-M table."""
        cases = [
            ("movs r0, #42", 0x202A), ("movs r0, #10", 0x200A),
            ("movs r4, r0", 0x0004), ("movs r0, r1", 0x0008),
            ("adds r0, r1, r2", 0x1888), ("adds r0, r1, #7", 0x1DC8),
            ("adds r0, #200", 0x30C8), ("subs r0, #1", 0x3801),
            ("cmp r0, #1", 0x2801), ("lsls r0, r1, #2", 0x0088),
            ("muls r0, r4, r0", 0x4360), ("mov r8, r0", 0x4680),
            ("bx lr", 0x4770), ("push {r4, lr}", 0xB510),
            ("pop {r4, pc}", 0xBD10), ("sub sp, #16", 0xB084),
            ("add sp, #16", 0xB004), ("ldr r0, [r1, #8]", 0x6888),
            ("ldr r0, [r1, r2]", 0x5888), ("str r0, [sp, #16]", 0x9004),
            ("svc #0x11", 0xDF11), ("svc 17", 0xDF11), ("nop", 0xBF00),
            ("ldr r0, [pc, #36]", 0x4809),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(expected, encoded_halfword(source))

    def test_register_list_ranges(self):
        """Register ranges expand into the same bitmap as explicit lists."""
        self.assertEqual(encoded_halfword("push {r4-r7, lr}"),
                         encoded_halfword("push {r4, r5, r6, r7, lr}"))

    def test_add_high_register_forms(self):
        """The documented high-register add examples encode correctly."""
        self.assertEqual(encoded_halfword("add r0, sp"), 0x4468)
        self.assertEqual(encoded_halfword("add sp, r1"), 0x448D)


class LayoutAndDirectiveTests(unittest.TestCase):
    """Check pass-one layout, expressions and directive bytes."""

    def test_data_directives_and_alignment(self):
        """Data directives emit exact little-endian bytes and ARM-style padding."""
        source = """
            .text
            .word 0x12345678, 0x90abcdef
            .byte 65, 0x42
            .hword 0x1234
            .asciz "A\\n"
            .space 2, 0xaa
            .align 2
        """
        program, diagnostics = assemble_text(source)
        self.assertEqual([], diagnostics.errors)
        expected = bytes.fromhex("78563412 efcdab90 4142 3412 410a00 aaaa 000000")
        self.assertEqual(expected, program.sections[".text"].byte_image())

    def test_equ_and_forward_reference(self):
        """Equates can use arithmetic and symbols defined later in the file."""
        source = """
            .equ DOUBLE, (1 << 3) + 2
            .text
            .word DOUBLE, LATER
        LATER: .word 7
        """
        program, diagnostics = assemble_text(source)
        self.assertEqual([], diagnostics.errors)
        self.assertEqual(bytes.fromhex("0a000000 08010000 07000000"),
                         program.sections[".text"].byte_image())

    def test_section_override(self):
        """A command-line override changes a section base address."""
        program, diagnostics = assemble_text(
            '.section .foo, "a"\n.byte 1\n', {".foo": 0x300})
        self.assertEqual([], diagnostics.errors)
        self.assertEqual(0x300, program.sections[".foo"].base)

    def test_numeric_local_labels(self):
        """Numeric local labels resolve to the next or previous definition."""
        source = """
            .text
            b 1f
            .space 4
        1:  nop
            b 1b
        """
        program, diagnostics = assemble_text(source)
        self.assertEqual([], diagnostics.errors)
        encodings = [int.from_bytes(item.encoded[:2], "little")
                     for item in program.sections[".text"].items
                     if item.kind == "instr"]
        self.assertEqual([0xE001, 0xBF00, 0xE7FD], encodings)


class LiteralPoolTests(unittest.TestCase):
    """Check pass-one pool placement, de-duplication and reach checks."""

    def test_pool_placement_and_deduplication(self):
        """Two identical ldr pseudo-instructions share one pool word."""
        source = """
            .text
            ldr r0, =0x12345678
            nop
            ldr r1, =0x12345678
            .ltorg
        """
        program, diagnostics = assemble_text(source)
        self.assertEqual([], diagnostics.errors)
        text = program.sections[".text"]
        pool_items = [item for item in text.items if item.kind == "pool_word"]
        self.assertEqual(1, len(pool_items))
        self.assertEqual(0x12345678, int.from_bytes(pool_items[0].encoded, "little"))
        self.assertEqual(8, pool_items[0].offset)

    def test_pool_reach_error(self):
        """A pool farther than 1020 bytes from its ldr is reported."""
        source = """
            .text
            ldr r0, =0x12345678
            .space 2000
            .ltorg
        """
        _, diagnostics = assemble_text(source)
        self.assertTrue(any("literal pool out of range" in error
                            for error in diagnostics.errors))


class GoldenFactorialTests(unittest.TestCase):
    """Check the complete factorial program from the course handout."""

    def test_full_program(self):
        """All section bytes, pool words and branch encodings match the golden dump."""
        program, diagnostics = assemble_text(FACTORIAL_SOURCE)
        self.assertEqual([], diagnostics.errors)
        self.assertEqual(0, program.sections[".vectors"].base)
        self.assertEqual(0x100, program.sections[".text"].base)
        self.assertEqual(0x12C, program.sections[".rodata"].base)
        self.assertEqual(bytes.fromhex("00000420 01010000"),
                         program.sections[".vectors"].byte_image())
        text_bytes = program.sections[".text"].byte_image()
        expected_text = ("094811df 0a2000f0 03f812df 002000df "
                         "10b50400 012804dd 0138fff7 f9ff6043 "
                         "10bd0120 10bd0000 2c010000")
        self.assertEqual(bytes.fromhex(expected_text), text_bytes)
        self.assertEqual(b"10! = \x00", program.sections[".rodata"].byte_image())

    def test_dump_first_text_line(self):
        """The .text dump line has the exact readelf-style layout."""
        program, diagnostics = assemble_text(FACTORIAL_SOURCE)
        self.assertEqual([], diagnostics.errors)
        lines = dump.write_dump(program).splitlines()
        header = "Hex dump of section '.text':"
        text_line = lines[lines.index(header) + 1]
        self.assertEqual(" 0x00000100 094811df 0a2000f0 03f812df 002000df .H... ....... ..",
                         text_line)

    def test_no_ascii_column(self):
        """The ASCII column can be omitted without changing the hex bytes."""
        program, diagnostics = assemble_text(FACTORIAL_SOURCE)
        self.assertEqual([], diagnostics.errors)
        text = dump.write_dump(program, include_ascii=False)
        self.assertNotIn(".H...", text)
        self.assertIn("0x00000100 094811df", text)


class NegativeTests(unittest.TestCase):
    """Check that unsupported or invalid operands fail without writing output."""

    CASES = [
        ("movs r0, #256", "immediate out of range"),
        ("adds r0, r1, #8", "imm3 out of range"),
        ("ldr r0, [r1, #3]", "word offset must be a multiple of 4"),
        ("ldr r8, [r1]", "high register r8"),
        (".text\nbeq far\n.space 300\nfar: nop", "conditional branch offset out of range"),
        ("b undefined", "undefined symbol"),
        ("x:\nx:\nnop", "duplicate label"),
        ("mov r0, #5", "use 'movs'"),
        ("and r0, r1", "use 'ands'"),
        ("ands r0, r1", "instruction not implemented in M1-M4"),
        ("wfi", "instruction not in the course subset"),
        ("ldm r0!, {r0, r1}", "ldm write-back rule violation"),
        (".text\nldr r0, =0x12345678\n.space 2000\n.ltorg", "literal pool out of range"),
    ]

    def test_negative_cases(self):
        """Every negative case reports a clear error and writes no dump file."""
        for source, expected in self.CASES:
            with self.subTest(source=source):
                with tempfile.TemporaryDirectory() as directory:
                    source_path = Path(directory) / "bad.s"
                    output_path = Path(directory) / "bad.dump"
                    source_path.write_text(".text\n" + source + "\n", encoding="utf-8")
                    result = subprocess.run(
                        [sys.executable, str(ASM_DIR / "asm.py"), str(source_path),
                         "-o", str(output_path), "--quiet"],
                        capture_output=True, text=True, check=False)
                    self.assertEqual(1, result.returncode)
                    self.assertIn(expected, result.stderr)
                    self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
