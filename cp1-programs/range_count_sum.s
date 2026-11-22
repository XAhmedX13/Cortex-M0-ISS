    @ assumptions: the user can enter a positive step in an ascending range,
    @ and a negative step in a descending range. The user inputs integers.
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

    movs r0, r4             @ r0 = first
    movs r1, r5             @ r1 = last
    movs r2, r6             @ r2 = step
    bl calc_range           @ returns r0 = count, r1 = sum

    movs r4, r0             @ r4 = count
    movs r5, r1             @ r5 = sum

    @ Print Count
    ldr r0, =out_count
    svc #0x11
    movs r0, r4
    svc #0x12               @ PUTINT

    @ Print Sum
    ldr r0, =out_sum
    svc #0x11
    movs r0, r5
    svc #0x12

    @ Exit program
    movs r0, #0
    svc #0x00               @ EXIT

    @ Function: calc_range
    @ Arguments: r0 = first, r1 = last, r2 = step
    @ Returns:   r0 = count, r1 = sum
    .thumb_func
calc_range:
    push {r4}               @ save r4 (callee-saved); it holds count
    movs r3, #0             @ r3 = sum = 0
    movs r4, #0             @ r4 = count = 0

    cmp r2, #0
    bgt posloop             @ if step > 0, go to posloop
    blt negloop             @ if step < 0, go to negloop
    b done                  @ if step == 0, exit immediately

posloop:
    cmp r0, r1
    bgt done                @ if current > last, done
    adds r4, #1             @ count++
    adds r3, r3, r0         @ sum += current
    adds r0, r0, r2         @ current += step
    b posloop

negloop:
    cmp r0, r1
    blt done                @ if current < last, done
    adds r4, #1             @ count++
    adds r3, r3, r0         @ sum += current
    adds r0, r0, r2         @ current += step
    b negloop

done:
    movs r0, r4             @ r0 = count
    movs r1, r3             @ r1 = sum
    pop {r4}                @ restore r4
    bx lr                   @ return to caller

    .section .rodata
msg1:      .asciz "Enter the first value in a range:\n"
msg2:      .asciz "Enter the last value in the range:\n"
msg3:      .asciz "Enter the step of the range:\n"
out_count: .asciz "Count: "
out_sum:   .asciz "\nSum: "