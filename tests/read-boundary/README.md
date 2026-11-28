# READ boundary tests

These programs test SVC READ (0x22), using the supplied vector-table startup.
Input files deliberately have no trailing newline.

| Test | Input | Expected stdout | Exit |
| --- | --- | --- | --- |
| valid-boundary | AB | `0\n0\n2\nAB\n0\n0\n` | 0 |
| out-boundary | ABC | Empty | 255 |

The valid test covers zero-byte requests into ROM and unmapped memory, a short
read into RAM's final two bytes with a requested count of eight, and positive-count
reads at EOF with ROM/unmapped buffers. Neither zero-byte request may consume input.

The overflow test has three actual input bytes but only two writable destination
bytes. It must report exactly `FAULT BUS at pc=0x00000106` followed by a newline
on stderr. The valid test must produce no stderr.

## Build and run the simulator

From the repository root:

```sh
gcc -std=c11 -O2 -Wall -Wextra -Werror -o /tmp/read-boundary-iss iss.c decoder.c disassembler.c
bash tests/read-boundary/run.sh /tmp/read-boundary-iss
```

The shell runner checks exact stdout/stderr, exit status, absence of READ writes
in traces, EXIT tracing, and omission of the faulting READ. It returns nonzero
if either case fails. It requires no additional Python test suite.

## Rebuild the dumps

With GNU ARM binutils installed, run from the repository root. Set `arm_bin` to
its bin directory if the tools are elsewhere; the default is `/usr/bin`.

```sh
arm_bin=${arm_bin:-/usr/bin}
for name in valid-boundary out-boundary; do
    "$arm_bin/arm-none-eabi-as" -mcpu=cortex-m0 -mthumb -o "/tmp/$name.o" "tests/read-boundary/$name.asm"
    "$arm_bin/arm-none-eabi-ld" --section-start=.vectors=0 -Ttext=0x100 -Tdata=0x20000000 -e _start -o "/tmp/$name.elf" "/tmp/$name.o"
    "$arm_bin/arm-none-eabi-readelf" -x .vectors -x .text "/tmp/$name.elf" > "tests/read-boundary/$name.dump"
done
```

The checked-in dumps were built with GNU binutils 2.42. Intermediate object and
ELF files are not needed to run the tests and are not included.

## Verification status

Both cases have been checked on the team simulator. Refiss verification is still
pending because browser policy blocked local reference-page access. Open the
supplied refiss HTML manually, load each dump, use exactly AB or ABC without a
newline, and compare output/status and the trace rules above. These expectations
come from the handout, not an unverified simulator trace.
