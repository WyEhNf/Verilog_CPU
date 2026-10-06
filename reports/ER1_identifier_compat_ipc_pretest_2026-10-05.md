# ER1 IPC 构建兼容修复与测量前汇报

第一次构建在程序运行前失败：Verilator5.020将 matches 识别为SystemVerilog保留字。
原ER1冻结源、综合结果、失败构建和日志全部保留。独立副本仅对LSQ局部信号做alpha重命名：
matches → response_query_matches，四行、五处标识符；反向字节替换与原文件完全一致，其他156文件逐一SHA256相同。
没有逻辑、参数、寄存器、时钟边界、握手或程序变化。这是兼容修复，不是架构优化。

构建修复后的副本并运行六个官方perf一次，latency10，原metrics指令数/GEOMEAN口径。
不再综合/STA，不运行额外回归。IPC明确记录为ER1标识符兼容副本结果，并引用原ER1综合身份；
不会伪造相同源码hash，也不会把当前EU的频率/面积混入基线。
Windows原生Verilator5.020/课程工具链，禁止WSL。CPU构建与六程序此时尚未启动；汇报后后台执行。
