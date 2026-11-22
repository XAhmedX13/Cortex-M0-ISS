sum_even:
    addi t0, x0, 0 # sum = 0
    addi t1, x0, 0 # i = 0
loop:
    bge t1, a1, done # if i >= length, exit
    lw t2, 0(a0) # t2 = arr[i]
    andi t3, t2, 1 # t3 = LSB
    bne t3, x0, skip # if odd, skip
    add t0, t0, t2 # sum += arr[i]
skip:
    addi a0, a0, 4 # arr++
    addi t1, t1, 1 # i++
    j loop
done:
    addi a0, t0, 0 # return sum
    jalr x0, 0(ra)