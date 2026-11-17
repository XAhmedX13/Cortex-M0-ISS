
.syntax unified
.cpu cortex-m0
.thumb

.thumb_func
sum_even:
push {r4, r5, lr} @ Save registers
movs r2, #0       @ sum = 0
movs r3, #0       @ i = 0
movs r5, #1       @ Used to check odd or even
loop:
cmp r3, r1        @ Compare i with length
bge done          @ Exit if i >= length

ldr r4, [r0]      @ r4 = arr[i]
tst r4, r5        @ Check if odd
bne skip          @ Skip if odd
adds r2, r2, r4   @ sum += arr[i]

skip:
adds r0, #4       @ arr++
adds r3, #1       @ i++
b loop            @ Repeat

done:
movs r0, r2       @ Return sum in r0
pop {r4, r5, pc}  @ Restore registers and return