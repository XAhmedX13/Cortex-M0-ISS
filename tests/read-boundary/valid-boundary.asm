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
    @ Zero-byte read into ROM: no memory access or input consumption.
    movs r0, #0
    movs r1, #0
    movs r2, #0
    svc #0x22
    svc #0x12              @ Expected: 0
    movs r0, #10
    svc #0x10

    @ Zero-byte read into unmapped memory.
    movs r0, #0
    ldr  r1, =0x30000000
    movs r2, #0
    svc #0x22
    svc #0x12              @ Expected: 0
    movs r0, #10
    svc #0x10

    @ Request eight bytes, but stdin contains only two.
    @ Both actual bytes fit at RAM's last two addresses.
    movs r0, #0
    ldr  r1, =0x2003FFFE
    movs r2, #8
    svc #0x22
    svc #0x12              @ Expected: 2
    movs r0, #10
    svc #0x10

    @ Confirm the bytes were stored correctly.
    ldr  r1, =0x2003FFFE
    ldrb r0, [r1, #0]
    svc #0x10              @ Expected: A
    ldrb r0, [r1, #1]
    svc #0x10              @ Expected: B
    movs r0, #10
    svc #0x10

    @ At EOF, a positive count must not access a ROM buffer.
    movs r0, #0
    movs r1, #0
    movs r2, #8
    svc #0x22
    svc #0x12              @ Expected: 0
    movs r0, #10
    svc #0x10

    @ At EOF, an unmapped buffer must also remain unaccessed.
    movs r0, #0
    ldr  r1, =0x30000000
    movs r2, #8
    svc #0x22
    svc #0x12              @ Expected: 0
    movs r0, #10
    svc #0x10

    movs r0, #0
    svc #0x00
    .ltorg
