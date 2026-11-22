# a0 = base address of str
# a1 = target char

count_char:
    add t0, zero, zero          # t0 = count = 0
loop:
    lbu t1, 0(a0)               # t1 = str[i]
    beq t1, zero, return        # if str[i] == '\0': return
    bne t1, a1, next            # if str[i] != target: skip
    addi t0, t0, 1              # count++
next:
    addi a0, a0, 1              # increment the pointer
    jal zero, loop              # reiterate
return:
    add a0, t0, 0               # a0 = count
    jalr zero, ra, 0            # return