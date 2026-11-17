.syntax unified
.thumb

count_char:
    MOVS    r2, #0          @ count = 0

count_loop:
    LDRB    r3, [r0]        @ r3 = *str
    CMP     r3, #0          @ if (*str == '\0')
    BEQ     done            @ exit loop

    CMP     r3, r1          @ if (*str != target)
    BNE     skip            @ skip count++

    ADDS    r2, r2, #1      @ count++

skip:
    ADDS    r0, r0, #1      @ str++
    B       count_loop

done:
    MOV     r0, r2          @ return count
    BX      lr              @ return