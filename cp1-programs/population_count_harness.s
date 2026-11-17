@ Standalone image for population_count: enters at _start, exits with the
@ number of set bits in the test value as the exit status.
        .syntax unified
        .cpu cortex-m0
        .thumb

        .section .vectors,"a"
        .word   0x20040000              @ initial SP
        .word   _start                  @ reset vector

        .text
        .thumb_func
        .global _start
_start: ldr     r0, =0xDEADBEEF         @ r0 = value to test (popcount = 24)
        bl      popcount                @ r0 = result
        svc     #0x00                   @ EXIT (refiss reports exit status = r0 & 0xFF)

        .thumb_func
        .global popcount
popcount:
        movs    r1, #0                  @ count = 0
        movs    r2, #1                  @ mask for lowest bit

loop:
        cmp     r0, #0                  @ check if val == 0
        beq     done                    @ exit loop if zero

        mov     r3, r0                  @ r3 = val
        ands    r3, r2                  @ extract lowest bit (val & 1)
        adds    r1, r1, r3              @ add bit to count

        lsrs    r0, r0, #1              @ logical shift right by 1
        b       loop                    @ repeat

done:
        mov     r0, r1                  @ return count in r0
        bx      lr                      @ return to caller
        .balign 4
        .ltorg                          @ literal pool: .word 0xDEADBEEF lands here
