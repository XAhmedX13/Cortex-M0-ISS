popcount: 
    li   
    t0, 0           
    loop: 
    # t0 = count 
    beq  a0, x0, done    # if val == 0, finish 
    andi t1, a0, 1       
    add  t0, t0, t1      
    srli a0, a0, 1       
    j  loop             
done:
    mv   a0, t0          
    ret