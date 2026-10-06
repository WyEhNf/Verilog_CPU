# A109 Pi 周期预算核算与单项补测前汇报

原三项同配置实测仍为IPC1.115262691835、含SRAM面积35891.672318um²、估算Fmax321.608040MHz。原19+4集中验证仍继续；Pi已在10,000,000周期报告timeout，旧结果与错误日志完整保留，不能据此宣布正确性通过或采用源码。

Pi原汇编与program.data逐条编码核对。外层s3从5599每次减28直到-1，共200次；内层a2从2799每次外循环减14，到最后13，总计281200次。内层每次MUL×2、DIV×1、REM×1；外层额外MUL×1、DIV×2、REM×2，退出hash再REMU×1。因此MUL562600、DIV281600、REM281600、REMU1，共1,125,801条M指令。

当前MUL_IMPL2使用单份共享迭代器，busy阻止下一操作替换，step0..31每周期一轮，finishing与结果发布另占边沿。仅必需迭代的下界是1,125,801×32=36,025,632周期，尚未包括发射、发布、访存、分支或错误路径工作。10M预算不可能让功能正确的此实现完成Pi。A16旧独立Wallace乘法器、radix4/归一化/商余缓存除法器可6277118周期完成，不能把它的预算直接套到新的面积取舍。这是本次测试预算遗漏，不等于已证明CPU没有其他问题。

课程README-ZH.md明确演示make test MAX_CYCLES=5000000 LATENCY=10，Makefile/testcase.py直接提供可配置周期上限；config.mk也给出100000000示例。MAX_CYCLES是本地watchdog参数，用户提供的评分要求没有固定10M正确性门槛。sim.cpp中它只用于终止循环，不参与DUT输入或内存调度；内存latency仍10，所有原程序、Golden答案和工具版本保持同一冻结身份。六perf的原1M上限和已有三项指标不变。

现只用课程原testcase.py --kind correctness --case correctness_pi --max-cycles48000000 --latency10 --sim原exe。预算在36.03M必需迭代下界上给发射、发布和其他开销留余量；只有实际完整退出112与原答案匹配才算通过。复用同一exe/source/config，不构建CPU或重新测三项，不重复已通过程序。补测可与原其余case独立执行，输出写入F:\CPU2026CourseRuns\ER1_A109_pi_budget_20261006；原原19+4任务保留。最终必须同时核对原其余18项、四边界及此次Pi，再采用当前已测41源。

可执行文件SHA256：5a3ac16a6917157dd6d0dc2baa7f0b2c1bb7fe71baf504a2842edc3e09cdef42。补测前已在对话汇报该单项范围与预算原因。
