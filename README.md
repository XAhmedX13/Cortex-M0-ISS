# Cortex-M0 Instruction Set Simulator

CSCE 2303 project in C. The simulator loads readelf section dumps, decodes the
43-instruction course subset, disassembles programs, and implements the Core SVC
services through CP3.

## Build and run

```sh
cc -std=c11 -O2 -Wall -Wextra -Werror -o iss iss.c decoder.c disassembler.c
./iss --disasm public-tests/cp1/allinsn/prog.dump
./iss --trace trace.txt public-tests/cp2/fact/prog.dump
python3 public-tests/run_tests.py --iss ./iss cp1 cp2 cp3
bash tests/read-boundary/run.sh ./iss
```

Verified on Ubuntu/WSL on November 28, 2026: all 3 CP1, 9 CP2, and 26 CP3 public
tests pass (38/38), as do both original READ-boundary tests. This does not prove
coverage of every required encoding or hidden-test correctness. Final extensions
remain separate work. See [RUNTIME.md](RUNTIME.md) for runtime interfaces.

## Our Thumb programs

Thumb sources, RV32I counterparts, and program dumps are in `cp1-programs/`.
The standalone population-count harness is
`cp1-programs/population_count_harness.s`, with its matching `.dump`.

To rebuild it with the Arm toolchain installed:

```sh
python3 tools/build_dump.py cp1-programs/population_count_harness.s
```

See [BUILDING.md](BUILDING.md) for Compiler Explorer and offline build instructions.
Homework-port refiss checks and same-input RARS comparisons remain to be recorded;
the READ-boundary reference checks below do not establish those comparisons.

## READ-boundary tests

[tests/read-boundary/README.md](tests/read-boundary/README.md) describes the sources,
dumps, exact inputs, expected outputs/statuses, and shell runner.

- `valid-boundary`: zero-byte requests, a short read ending at RAM's final byte,
  and EOF with invalid buffers. Input is exactly `AB`; expected exit status is 0.
- `out-boundary`: actual input exceeds the writable destination. Input is exactly
  `ABC`; expected status is 255 with `FAULT BUS at pc=0x00000106` on stderr.

On November 28, 2026, user-provided refiss v1.1 results reported those exit statuses.
The reference traces (44 and 3 retired instructions respectively) are saved as
`*.expected.trace` and match fresh simulator traces line for line. The simulator's
stdout/stderr also match the expected files; refiss stdout/stderr were not
separately supplied in the verification record.

## Submission checklist

Include sources, dumps, tests, build/run instructions, and
[CONTRIBUTIONS.md](CONTRIBUTIONS.md) in each checkpoint tag. Review teammates' code,
record the remaining reference comparisons, and submit the repository URL and
checkpoint tag through Canvas. The current checkout has no `cp3` tag.

The full project requires at least twelve original tests, at least four per
member. Ali's READ-boundary pair accounts for two programs; two more remain for
his individual minimum. Final extensions, the team comparison report, and each
member's reflection are separate deliverables.
