# Contributions — CP1, CP2 and CP3

Based on repository history; imported starter files and public tests are course material.

- **Ahmed Mostafa (XAhmedX13):** Decoder and disassembler (`1bce14f`);
  Thumb `sum_even` homework port (`c71b436`); branch integration.
- **Hazem Nasr (HazeMOONium):** Instruction execution in `iss.c`, including
  arithmetic, flags, branches, and memory operations (`414e38c`); Thumb
  `count_char` port (`64f8563`); assembly artifacts and runnable harnesses for
  both initial ports (`77709e4`, `085d416`).
- **Ali Hosny (Ali-Hosny):** Dump loader, memory checks, reset, console SVCs,
  command-line options, disassembly driver, and tracing (`f714c68`, merged as
  `594f4ba`); `population_count` port and MOV/MVN/shift execution fixes included
  in `594f4ba`.
- **Yusif (YUSIFABOOD):** Python Thumb assembler foundation in `tools/asm/`:
  error collection, lexer, expression parser, symbol table, layout and section
  placement, directives, dump/listing writers, and CLI (`5163a8f`, `78939dd`,
  `8688694`, `5bf2f71`, `ce33bf1`, `4de1040`, `2c289e3`, `661c8a5`,
  `283fe5c`); CP1 Thumb program added (`52058f4`).

## CP3

- **Ali Hosny (Ali-Hosny):** Implemented READ, WRITE, INSTRET, and DUMP_REGS
  (`9e8487a`). Corrected MOV/ADD writes to SP and PC, PC operand reads, and the
  extend/reverse source-register fields (`8220bd7`). Added two original
  READ-boundary programs with dumps, exact inputs, expected stdout/stderr and
  exit statuses, saved reference traces, and a shell runner (`271c54a`). Ran both
  programs on refiss v1.1 and supplied exit statuses and traces; those traces
  were checked against fresh simulator traces and matched exactly (44 and 3
  instructions). Refiss stdout/stderr confirmation is not separately recorded.
- A strict Linux/WSL build passed all 38 public CP1-CP3 tests and both original
  READ-boundary tests on November 28, 2026. Passing public tests does not
  establish complete encoding coverage or hidden-test correctness.

Outstanding team work: record homework-port RARS/refiss comparisons, complete the
original test-program minimum (Ali currently has two of his required four),
review remaining instruction coverage, and prepare the `cp3` checkpoint tag and
submission. Final extensions and comparison/reflection deliverables remain.
