.syntax unified
.cpu cortex-m0
.thumb

.global popcount
.thumb_func

popcount:
    MOVS R1, #0          @ count = 0
    MOVS R2, #1          @ mask for lowest bit

loop:
    CMP R0, #0           @ check if val == 0
    BEQ done             @ exit loop if zero 

    MOV R3, R0           @ R3 = val
    ANDS R3, R2          @ extract lowest bit (val & 1)
    ADDS R1, R1, R3      @ add bit to count

    LSRS R0, R0, #1      @ logical shift right by 1
    B loop               @ repeat

done:
    MOV R0, R1           @ return count in R0
    BX LR                @ return to caller