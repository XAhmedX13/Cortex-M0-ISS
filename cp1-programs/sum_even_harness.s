@ Standalone image for sum_even: enters at _start, exits with the sum of the
@ even elements as the exit status.
        .syntax unified
        .cpu cortex-m0
        .thumb

        .section .vectors,"a"
        .word   0x20040000              @ initial SP
        .word   _start                  @ reset vector

        .text
        .thumb_func
        .global _start
_start: ldr     r0, =arr                @ r0 = array pointer
        movs    r1, #10                 @ r1 = element count
        bl      sum_even                @ r0 = result
        svc     #0x00                   @ EXIT (refiss reports exit status = r0 & 0xFF)

        .thumb_func
        .global sum_even
sum_even:
        push    {r4, r5, lr}            @ Save registers
        movs    r2, #0                  @ sum = 0
        movs    r3, #0                  @ i = 0
        movs    r5, #1                  @ Used to check odd or even
loop:
        cmp     r3, r1                  @ Compare i with length
        bge     done                    @ Exit if i >= length

        ldr     r4, [r0]                @ r4 = arr[i]
        tst     r4, r5                  @ Check if odd
        bne     skip                    @ Skip if odd
        adds    r2, r2, r4              @ sum += arr[i]

skip:
        adds    r0, #4                  @ arr++
        adds    r3, #1                  @ i++
        b       loop                    @ Repeat

done:
        movs    r0, r2                  @ Return sum in r0
        pop     {r4, r5, pc}            @ Restore registers and return

        .section .rodata
arr:    .word   1, 2, 3, 4, 5, 6, 7, 8, 9, 10
