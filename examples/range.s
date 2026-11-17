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
_start:
    ldr r0, =msg1
    svc #0x11               @ PUTS
    svc #0x15               @ GETINT -> r0
    movs r4, r0             @ r4 = first value

    ldr r0, =msg2
    svc #0x11
    svc #0x15
    movs r5, r0             @ r5 = last value

    ldr r0, =msg3
    svc #0x11
    svc #0x15
    movs r6, r0             @ r6 = step

    movs r0, r4             @ a0 = first
    movs r1, r5             @ a1 = last
    movs r2, r6             @ a2 = step
    bl calc_range           @ returns r0 = count, r1 = sum

    movs r4, r0             @ r4 = count
    movs r5, r1             @ r5 = sum

    ldr r0, =out_count
    svc #0x11
    movs r0, r4
    svc #0x12               @ PUTINT
    ldr r0, =out_sum
    svc #0x11
    movs r0, r5
    svc #0x12

    movs r0, #0
    svc #0x00               @ EXIT

    .thumb_func
calc_range:                 @ r0 = first, r1 = last, r2 = step
    push {r4}               @ r4 is callee-saved; it holds count
    movs r3, #0             @ sum = 0
    movs r4, #0             @ count = 0
    cmp r2, #0
    bgt posloop             @ step > 0
    blt negloop             @ step < 0
    b done                  @ step == 0

posloop:
    cmp r0, r1
    bgt done                @ current > last
    adds r4, #1             @ count++
    adds r3, r3, r0         @ sum += current
    adds r0, r0, r2         @ current += step
    b posloop

negloop:
    cmp r0, r1
    blt done                @ current < last
    adds r4, #1
    adds r3, r3, r0
    adds r0, r0, r2
    b negloop

done:
    movs r0, r4             @ r0 = count
    movs r1, r3             @ r1 = sum
    pop {r4}
    bx lr

    .section .rodata
msg1:      .asciz "Enter the first value in a range:\n"
msg2:      .asciz "Enter the last value in the range:\n"
msg3:      .asciz "Enter the step of the range:\n"
out_count: .asciz "Count: "
out_sum:   .asciz "\nSum: "