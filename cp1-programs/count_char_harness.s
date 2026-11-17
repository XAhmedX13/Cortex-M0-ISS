@ Standalone image for count_char: enters at _start, exits with the number of
@ occurrences of the target character as the exit status.
        .syntax unified
        .cpu cortex-m0
        .thumb

        .section .vectors,"a"
        .word   0x20040000              @ initial SP
        .word   _start                  @ reset vector

        .text
        .thumb_func
        .global _start
_start: ldr     r0, =str                @ r0 = string to scan
        movs    r1, #'a'                @ r1 = target char
        bl      count_char              @ r0 = result
        svc     #0x00                   @ EXIT (refiss reports exit status = r0 & 0xFF)

        .thumb_func
        .global count_char
count_char:
        movs    r2, #0                  @ count = 0

count_loop:
        ldrb    r3, [r0]                @ r3 = *str
        cmp     r3, #0                  @ if (*str == '\0')
        beq     done                    @ exit loop

        cmp     r3, r1                  @ if (*str != target)
        bne     skip                    @ skip count++

        adds    r2, r2, #1              @ count++

skip:
        adds    r0, r0, #1              @ str++
        b       count_loop

done:
        mov     r0, r2                  @ return count
        bx      lr

        .section .rodata
str:    .asciz  "ananas compote, banana split"
