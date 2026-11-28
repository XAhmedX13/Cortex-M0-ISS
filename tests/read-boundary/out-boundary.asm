@ main(void) is not used: entry is _start.
.syntax unified
.cpu cortex-m0
.thumb

.section .vectors, "a"
.word 0x20040000
.word _start

.text
.thumb_func
.global _start
_start:
    ldr  r1, =0x2003FFFE
    movs r0, #0
    movs r2, #3
    svc #0x22              @ Third byte faults at this instruction.

    movs r0, #1            @ Must never reach this.
    svc #0x00
    .ltorg
