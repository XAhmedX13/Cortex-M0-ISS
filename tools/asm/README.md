# Thumb assembler (Python 3, standard library only)

`tools/asm/asm.py` assembles the GNU-style ARMv6-M Thumb subset used by this
course into a `readelf -x`-style dump that the simulator loader can read.

## Run

```
python3 tools/asm/asm.py INPUT.s -o OUTPUT.dump
python3 tools/asm/asm.py INPUT.s -o OUTPUT.dump --listing OUTPUT.lst --no-ascii
python3 tools/asm/asm.py INPUT.s -o OUTPUT.dump --section-addr .text=0x200
```

Errors are printed as `file:line: error: message` and no output file is written
when assembly fails. Warnings use the same shape with `warning` in place of
`error`.

## Tests

```
python3 -m unittest discover tools/asm/tests
```

The tests cover the section 11.1 encoding table, the section 11.2 factorial
golden program, local labels, literal pools, section overrides, output formats
and the in-scope negative cases.

## Implemented scope

This delivery covers milestones M1–M4: lexing, expressions, symbols, sections,
data directives, dump/listing output, the M2 data-processing instructions, M3
branches and `push`/`pop`, and M4 literal pools. The factorial golden program
from the handout assembles byte-for-byte as shown in section 11.2.

A few encodings from later milestone tables are also implemented early because
the M4 golden program or the section 11.1 table requires them: `lsls` (immediate),
`muls`, `adr`, and the section 7.4 load/store forms. The remaining M5
instructions are rejected with `instruction not implemented in M1-M4` instead of
being silently mis-encoded.

## Notes on deviations from the plan

- The dump writer emits one leading space before each `0x` address, as stated in
  section 9.1. The checked-in GNU `readelf` examples have two; the simulator
  strips leading whitespace, so both are accepted.
- Section 11.3 lists `ands r0, r1` as a missing-`s` case. Since `ands` already has
  the required suffix, this assembler reports the missing-suffix hint for
  `and r0, r1` and reports `ands` as an M5 instruction that is not implemented.
- Optional milestones M6 and M7 are not implemented.
