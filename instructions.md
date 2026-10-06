一个乱序的能够参数化的多发射CPU
Use Verilog
顺/乱序发射不需要参数化
因为顺/乱序的执行模型不一样，相当于重写代码
参数化
前端宽度/后端宽度：1/2/4生成不同的发射宽度的CPU
物理寄存器大小：不同的物理寄存器大小产生重命名空间
RoB大小
指令集：RV32IM: 最基础的RISCV指令集
我觉得理论上
csr*和fence是不需要的
lw是需要的但是lh/lb是不需要的
我觉得系统课的乐趣在于折腾
一个向量乘法
https://github.com/ucb-bar/riscv-benchmarks/blob/4d46f673ae42a321e35f5b40b2f5c8f498bc1d9d/multiply/multiply_main.c#L35-L40
一个向量加法
https://github.com/ucb-bar/riscv-benchmarks/blob/master/vvadd/vvadd_main.c#L26-L31


程序都都要
把c代码粘出来
用riscv-gnu-toolchain-gcc编译出来.o
https://github.com/riscv-collab/riscv-gnu-toolchain
把对应函数的binaries给抽出来
喂给cpu来跑

用YoSys + ASAP7工艺库综合面积
一个顺序单发射的CPU核心面积在1000 um2这个量级
Reference: UCB Sodor
理论上单发射乱序的面积应该在1500-2000 um2这个量级
然后要按照performance / area来算每次面积增加对于性能的影响
面积翻倍性能至少要多出来1.3×
每达到一个多给5分(也就是至少要在这个性能比例要求下翻倍三次)

代码资源
Driver
https://github.com/Synthesys-Lab/assassyn/blob/master/python/ci-tests/test_driver.py
两级流水
https://github.com/Synthesys-Lab/assassyn/blob/master/python/ci-tests/test_async_call.py
Downstream
https://github.com/Synthesys-Lab/assassyn/blob/master/python/ci-tests/test_downstream.py


