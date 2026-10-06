# A109 集中正确性验证前汇报

原同一次课程Windows native测量已完成，IPC=1.115262691835、Fmax=321.608040201MHz、含SRAM面积=35891.672317998um²，六性能答案通过。原PID103132已结束，serial timing/performance均rc0；所有源/工具/输入冻结绑定，结果并未重跑或覆盖。

现在只复用同一个CPU exe（SHA256 5a3ac16a6917157dd6d0dc2baa7f0b2c1bb7fe71baf504a2842edc3e09cdef42）、同一个source manifest/config与latency10，集中执行19项官方correctness程序（max_cycles10000000）及4项原有冻结边界程序（max_cycles200000）。不构建CPU、不综合/STA、不重跑六perf、不重生成/汇编边界程序。四项为arithmetic_edges_2、memory_low、memory_ram_top、control_alignment_0，涵盖原官方程序缺少的DIVU/MULH/MULHSU/MULHU及既有除零/溢出、RAM顶端、自然对齐、JALR边界。只包装原image为原OJ stdin协议，期望来自已冻结独立解释器；compare_output调用课程原函数，不忽略额外非空输出。

新输出独立保存于F:\CPU2026CourseRuns\ER1_A109_closing_20261006，不改原成功测量文件。全部23项跑完后，仍需关键参数/源架构审阅及将已验证A109采用到主源；有限程序不能证明任意参数/所有ISA输入。A110/A111未测，保留独立源候选，不混入此次验证。先在对话汇报此集中验证再启动。
