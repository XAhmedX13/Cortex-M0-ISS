# Member C runtime integration

Build from the repository root:

```sh
gcc -std=c11 -O2 -Wall -Wextra -o iss iss.c decoder.c disassembler.c
python3 public-tests/run_tests.py --iss ./iss cp1 cp2
python3 -m unittest discover -s tests -v
```

The root-level `iss.c` is the active simulator. The old C and Python skeletons
were removed on main.

## Interfaces for Members A and B

- `load_dump()` populates ROM/RAM. Private `text_start` and exclusive `text_end`
  describe the loaded `.text` extent. `--disasm` calls the existing `decode()`
  and `disassemble()` functions without resetting or executing the machine.
- During `step()`, `r[15]` is the current instruction address. PC operands must
  read that address plus four. Set local `next` for branches; update `r[15]`
  only at successful retirement.
- Use `read_mem(addr, size)` and `write_mem(addr, value, size)` for data accesses.
  Sizes are 1, 2, or 4. Helpers check alignment before mapping/protection.
  Writes through `write_mem` are captured for tracing, including unchanged values.
- Use `fetch_halfword()` for instruction fetches so failed fetch diagnostics
  report the attempted address. Use `fault(kind)` for instruction faults while
  `r[15]` still identifies the current instruction. Faults terminate with 255
  before retirement or trace output.
- Keep the shared end of `step()` for PC update, `instret`, and tracing.
  Never retire or trace inside an instruction implementation.
- `svc()` preserves flags. EXIT requests termination; `main()` returns its status
  after the shared retirement and trace path. SVC writes are excluded from the
  instruction write log. Future service memory accesses should use the same
  memory helpers while recording is disabled.
- The trace logs changed r0-r12, SP, LR, address-sorted memory writes, then NZCV.
  BL encodings must retain the first halfword first.

## Remaining team integration

`step()` combines the decoded instruction executor from main with Member C's
fetch diagnostics, service handling, retirement, and tracing. The second halfword
is fetched only for wide instructions, whose sequential PC advances by four bytes.
Instruction implementations still need to be validated against the public tests;
merging the executor does not establish that every instruction is correct.

The individual homework port requires choosing the original RARS program and
coordinating the team's three choices. Contribution attribution requires the
member's name. No homework choice, report evidence, or refiss verification is
invented by this infrastructure work.
