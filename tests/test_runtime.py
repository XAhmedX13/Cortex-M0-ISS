"""Infrastructure regressions; run: python3 -m unittest discover -s tests -v.

Small encoded fixtures use only the starter MOVS/B/SVC instructions so these
checks focus on runtime behavior while using the integrated executor.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def section(name, address, data):
    lines = [f"Hex dump of section '{name}':"]
    for offset in range(0, len(data), 16):
        chunk = data[offset:offset + 16]
        words = ' '.join(chunk[i:i + 4].hex() for i in range(0, len(chunk), 4))
        lines.append(f'  0x{address + offset:08x} {words:<35} deadbeef ASCII ignored')
    return '\n'.join(lines) + '\n'


def dump(halfwords, sp=0x20040003, vector=0x101):
    return section('.vectors', 0, sp.to_bytes(4, 'little') + vector.to_bytes(4, 'little')) + section(
        '.text', 0x100, b''.join(h.to_bytes(2, 'little') for h in halfwords))


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.iss = Path(cls.build.name) / 'iss'
        subprocess.run([os.environ.get('CC', 'gcc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-O2', '-o', str(cls.iss), str(ROOT / 'iss.c'),
                        str(ROOT / 'decoder.c'), str(ROOT / 'disassembler.c')], check=True)
        # Inspect reset state directly without needing additional instructions.
        harness = Path(cls.build.name) / 'reset.c'
        harness.write_text('#define main simulator_main\n#include "' +
                           (ROOT / 'iss.c').as_posix() +
                           '"\n#undef main\nint main(void) {\n'
                           'rom[0]=3; rom[2]=4; rom[3]=0x20; rom[4]=1; rom[5]=1;\n'
                           'r[0]=7; N=Z=C=V=1; instret=9; reset();\n'
                           'return r[13]!=0x20040000u || r[15]!=0x100u || '
                           'r[14]!=0xffffffffu || r[0] || N || Z || C || V || instret; }\n')
        cls.reset_check = Path(cls.build.name) / 'reset'
        subprocess.run(['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-o',
                        str(cls.reset_check), str(harness), str(ROOT / 'decoder.c'),
                        str(ROOT / 'disassembler.c')], check=True)

        memory_source = Path(cls.build.name) / 'memory.c'
        memory_source.write_text('#define main simulator_main\n#include "' +
                                 (ROOT / 'iss.c').as_posix() +
                                 '"\n#undef main\n' + r'''
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    r[15] = 0x100;
    switch (argv[1][0]) {
    case 'r': (void)read_mem(0x100001, 4); break;
    case 'w': write_mem(1, 0, 4); break;
    case 'b': write_mem(0, 0, 4); break;
    case 'f': (void)fetch_halfword(0x100000); break;
    case 't': {
        uint32_t before[15] = {0};
        trace_file = stdout;
        recording_writes = 1;
        write_mem(RAM_BASE + 4, 0x12345678, 4);
        write_mem(RAM_BASE, 0xabcdef, 1);
        recording_writes = 0;
        write_mem(RAM_BASE + 8, 42, 1);
        r[13] = RAM_BASE; r[14] = UINT32_MAX; r[15] = 0x999;
        trace_instruction(0x100, 0xf000, 0xf800, 1, before);
        return 0;
    }
    default: return 2;
    }
    return 1;
}
''')
        cls.memory_check = Path(cls.build.name) / 'memory'
        subprocess.run(['gcc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-o',
                        str(cls.memory_check), str(memory_source), str(ROOT / 'decoder.c'),
                        str(ROOT / 'disassembler.c')], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def run_iss(self, contents, *args, stdin=b''):
        with tempfile.TemporaryDirectory() as directory:
            program = Path(directory) / 'program.dump'
            trace = Path(directory) / 'trace'
            program.write_text(contents)
            result = subprocess.run([str(self.iss), *args, '--trace', str(trace), str(program)],
                                    input=stdin, capture_output=True, timeout=5)
            return result, trace.read_text() if trace.exists() else None

    def test_exit_retires_and_traces(self):
        result, trace = self.run_iss(dump([0x202a, 0xdf00]))
        self.assertEqual(result.returncode, 42)
        self.assertEqual(trace.splitlines(), ['00000100 202a r0=0000002a NZCV=0000',
                                             '00000102 df00 NZCV=0000'])

    def test_disassembly_skips_reset_and_execution(self):
        result, trace = self.run_iss(dump([0x202a, 0xdf00], vector=0), '--disasm')
        self.assertEqual(result.returncode, 0)
        self.assertIn(b'00000100: 202a movs r0, #42', result.stdout)
        self.assertIsNone(trace)

    def test_getint_wraps_and_leaves_delimiter(self):
        result, _ = self.run_iss(dump([0xdf15, 0xdf13, 0xdf14, 0xdf10, 0x2000, 0xdf00]),
                                 stdin=b' \t-4294967297!')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b'0xFFFFFFFF!')

    def test_getint_preserves_sign_without_digits(self):
        result, _ = self.run_iss(dump([0xdf15, 0xdf12, 0xdf14, 0xdf10, 0xdf14,
                                      0xdf10, 0x2000, 0xdf00]), stdin=b' +x')
        self.assertEqual(result.stdout, b'0+x')
        self.assertEqual(result.returncode, 0)

    def test_getchar_eof(self):
        result, _ = self.run_iss(dump([0xdf14, 0xdf13, 0x2000, 0xdf00]))
        self.assertEqual(result.stdout, b'0xFFFFFFFF')
        self.assertEqual(result.returncode, 0)

    def test_instruction_limit(self):
        result, trace = self.run_iss(dump([0xe7fe]), '--max-instr', '2')
        self.assertEqual(result.returncode, 254)
        self.assertEqual(result.stderr, b'LIMIT at pc=0x00000100\n')
        self.assertEqual(len(trace.splitlines()), 2)

    def test_invalid_reset_vector(self):
        result, trace = self.run_iss(dump([0xdf00], vector=0x102))
        self.assertEqual(result.returncode, 255)
        self.assertEqual(result.stderr, b'FAULT INVSTATE at pc=0x00000102\n')
        self.assertEqual(trace, '')

    def test_faulting_svc_has_no_trace(self):
        result, trace = self.run_iss(dump([0x2001, 0xdf99]))
        self.assertEqual(result.returncode, 255)
        self.assertEqual(result.stderr, b'FAULT UNDEFINED at pc=0x00000102\n')
        self.assertEqual(len(trace.splitlines()), 1)

    def test_bad_loads(self):
        for contents in ['', 'headings only\n', '  0x00000100 gg\n',
                         section('.text', 0x100000, b'\x00'),
                         section('.text', 0x20040000, b'\x00')]:
            with self.subTest(contents=contents):
                result, _ = self.run_iss(contents)
                self.assertEqual(result.returncode, 253)
                self.assertIn(b'load error:', result.stderr)

    def test_memory_fault_priority_and_fetch_address(self):
        for mode, fault in [('r', 'UNALIGNED at pc=0x00000100'),
                            ('w', 'UNALIGNED at pc=0x00000100'),
                            ('b', 'BUS at pc=0x00000100'),
                            ('f', 'BUS at pc=0x00100000')]:
            with self.subTest(mode=mode):
                result = subprocess.run([str(self.memory_check), mode], capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 255)
                self.assertEqual(result.stderr.decode(), f'FAULT {fault}\n')

    def test_trace_orders_writes_masks_values_and_excludes_pc(self):
        result = subprocess.run([str(self.memory_check), 't'], capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout,
                         b'00000100 f000f800 sp=20000000 lr=ffffffff '
                         b'[20000000]=ef [20000004]=12345678 NZCV=0000\n')

    def test_invalid_limit(self):
        for limit in ['-1', '1x', '18446744073709551616']:
            result, _ = self.run_iss(dump([0xdf00]), '--max-instr', limit)
            self.assertEqual(result.returncode, 2)

    def test_reset_clears_state_and_aligns_sp(self):
        self.assertEqual(subprocess.run([str(self.reset_check)], timeout=5).returncode, 0)


if __name__ == '__main__':
    unittest.main()
