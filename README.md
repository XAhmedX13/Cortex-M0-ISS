# Cortex-M0 Instruction Set Simulator

CSCE 2303 project in C. The simulator loads readelf section dumps, decodes the
43-instruction course subset, disassembles programs, and executes CP2 programs.

## Build and run

```sh
cc -std=c11 -O2 -Wall -Wextra -o iss iss.c decoder.c disassembler.c
./iss --disasm public-tests/cp1/allinsn/prog.dump
./iss --trace trace.txt public-tests/cp2/fact/prog.dump
python3 public-tests/run_tests.py --iss ./iss cp1 cp2
```

A fresh build of main passed all 3 CP1 and 9 CP2 public tests. This does not prove
coverage of every required encoding. Linux build verification remains pending.

## Our Thumb programs

Runnable source/dump pairs are in `cp1-programs/`: `sum_even_harness` (exit 30)
and `count_char_harness` (exit 6). Both produce no stdout. `population_count.s`
still needs a runnable harness, dump, and recorded expected result.

To rebuild a dump with the Arm toolchain installed:

```sh
python3 tools/build_dump.py cp1-programs/sum_even_harness.s
```

See [BUILDING.md](BUILDING.md) for Compiler Explorer and offline build instructions.
To check against refiss, open `refiss-v1.1.html` in a browser, load the same dump
and input, run it, and compare stdout, exit status, and trace. Paste our trace into
its Compare box. Refiss checks and same-input RARS comparisons for all three
homework ports remain to be recorded; no reference verification is claimed here.

## Submission checklist

Complete the third runnable port, record all three RARS/refiss comparisons, and
review instruction coverage. Include sources, dumps, tests, build instructions,
and [CONTRIBUTIONS.md](CONTRIBUTIONS.md) in each checkpoint tag. No `cp1` or `cp2`
tag was found during this audit. Submit the repository URL and tag on Canvas.
The full project also requires twelve original tests, at least four per member.
