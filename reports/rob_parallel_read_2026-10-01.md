# ROB提交读口并行化：实现、验证与版本边界

## 完整时序依据

上一冻结版本的真实四发射AXI配置：ROB32/PRF48/RS8/LSQ8、TAG1/I128/D1024、store合并16、最新store ACK/tag-write重叠；完整默认ABC面积45,928.134894 µm²，IPC GEOMEAN0.9558133327368818，全部SRAM参与的最小周期42.4443359375 ns、23.560269654649 MHz。

对应网表 `d05ef13c3376d670d08be9b5e3b004d14ea80b843bfd6545be17d2d2925add9f`。timing.rpt起点 `_764847_` 的QN扇出1312，起始clk-Q2.2504 ns，后续反相器388扇出/3.7813 ns。按design.json的原cell及相同mapped.v引脚对应，再沿prepared.il反向追溯，起点确为ROB的head_o[0]；终点 `_757884_` 是AXI桥bus.d_resp_id[6]。不是沿用旧cache版的i_resp_id终点。

原cell名 `$auto$ff.cc:337:slice$688589` 的QN为 `$auto$dfflibmap.cc:468:dfflibmap$2941136`，prepared.il中反相器直接接 `core.g_ooo_backend.backend.rob.head_o[0]`；终点原cell `$auto$ff.cc:337:slice$681299` 的QN为 `$auto$dfflibmap.cc:468:dfflibmap$2927642`，反相器直接接 `bus.d_resp_id[6]`。证据目录 `D:/CPU2026AreaAudits/store_query_overlap_tagbanks_i128_r32p48rs8_standard_20261001`。

## 当前修改

`rtl/backend/rv32_rob.v`：

- 开放的第n个提交lane必然已接受前n个lane，因此它读取head+n；不再让可变pop_count参与后续lane的大数据读口地址。
- 共享head的one-hot行选择，各lane旋转行选择后掩码OR归并完整197-bit访问相对packet（该配置G=8、PAW=6）。不新增流水拍、不缩小ROB/PRF/RS，不改变四发射宽度。
- 所有可观察提交输出仍由原有ordered-prefix和ready控制。非首lane的store仍不能进入唯一store-admission端口；MMIO仍等待确认，HALT/error仍精确截断年轻lane。generation-qualified完成/恢复/回收逻辑保留。
- 顺序块的终止/返回值也使用同一已选择packet，避免重复动态读口；有效位清除和分配、指针更新、仲裁、恢复顺序不变。
- ROB深度小于lane数时使用原单次wrap读口fallback，不在本轮偷偷改变支持参数范围或修复另一类原有语义。

新ROB SHA256 `c6a971a9090c925a273916b115d21de148718a53563faf7fa545a68f50344369`。本轮与上一冻结RTL的唯一区别是ROB文件；上一轮PPA不再冒称当前改动后的结果。

## 已完成的功能验证

- `make b03`：BE=1/2/4通过；`make lint unit matrix`通过，日志 `build/rob_parallel_unit_matrix_20261001.log`。
- 新正式构建 `D:/CPU2026Builds/rob_parallel_tagbanks_i128_r32p48rs8_20261001`：benchmark6/6、basic5/5（含LH/LHU/SH与八条M操作）、simulator17/17、256MiB脏回写边界全部通过，pi冻结。
- 四份报告 `build/cpu2026/rob_parallel_tagbanks_i128_r32p48rs8_{benchmark,basic,simulator,boundary}_20261001.json`。六项周期和退休数与上一版逐项完全相等：总周期428254、总退休472599、IPC GEOMEAN **0.9558133327368818**。读口结构变化本身没有增加IPC。
- `tools/test_rob_read_equivalence.py` 对完整顺序ROB、全部模块输出和同名状态做equiv_simple/equiv_induct/equiv_status -assert。60组参数矩阵（BE1/2/4 × ROB2/4/8/16/32 × checkpoint0/1 × store-retire0/1，含小深度fallback）仍在实际运行；已通过的日志在 `D:/CPU2026Proofs/rob_parallel_read_20261001`，未完成前不宣称全矩阵证明。
- 当前实际BE4/ROB32/checkpoint1/store-retire1的优先完整证明已通过：12,083个equiv单元全部PROVEN，未证明0，equiv_status -assert成功。分别直接读取两份不可变整机面积快照，不重写gold参考算法；脚本/日志及指纹清单在 `D:/CPU2026Proofs/rob_parallel_current_20261001`。该结果不替代仍在运行的60组参数矩阵。

## 面积/频率核验与失败诊断

正式全局默认ABC、独立Decimal计价及完整STA均已完成：组合27,455.218920、时序10,513.054800、SRAM7,825.666854，总面积 **45,793.940574 µm²**；382,493个叶实例、37个宏，未计价/未展开0、最终check0。重新执行 `--require-current` VERIFIED、当前输入差异0。证据 `D:/CPU2026AreaAudits/rob_parallel_tagbanks_i128_r32p48rs8_standard_20261001`，与上述原驱动/latency20仿真冻结输入相同。

同一网表SHA `713d6245c0eb94162af54cffe85b13acd7ce392a36a960705b134e40e56ccf03`，全部SRAM参与/遗漏0，最小周期 **35.8095703125 ns**，估计Fmax **27.925495650277 MHz**。相对旧版面积减少134.194320 µm²（0.292183%），频率提高18.527912%，IPC精确不变。综合后理想时钟/无寄生STA不等于布局布线实测。

曾尝试保留全部端口的孤立ROB比较，但原冻结ROB在独立综合check-assert中报临时变量age的组合/时序多驱动；镜像课程proc/memory_collect分阶段流程后仍失败。两次均未产生可用面积/时序，没有放宽check或删除存储来拼成绩。失败脚本/日志保留在 `D:/CPU2026AreaAudits/rob_parallel_read_diagnostic_20261001/baseline` 和 `D:/CPU2026AreaAudits/rob_parallel_read_diagnostic_v2_20261001/baseline`；本轮新增而无有效用途的孤立审计入口已移除。正式CPU历史网表的最终check0及完整计价仍是其实际冻结结果，不以孤立失败替换。

## 目标与后续方向

Tier3仍要求**同一最终配置**面积≤36,000 µm²、IPC≥1.0985、完整Fmax≥300 MHz。当前45,793.940574/0.9558133327368818/27.925495650277三项均未达标，不能用局部改动代替三项验收。

前端已经实现response_can_chain，使响应可与下一请求同拍握手；不能把“尚未实现请求串接”当作已证实的低IPC原因，后续优化须检查实际cache握手与停顿证据。

进一步检查发现COMPLETION_BYPASS=1是旧单CDB最小面积模式，而非四路无延迟完成；它不能作为保留四路吞吐、达到1.0985 IPC的替代方案。本轮未将其打开或伪称四CDB优化。后续有价值的方向是保留参数化多CDB的直接完成通路，包含公平仲裁、背压时的来源锁定、generation-stale结果消耗及恢复取消；必须先实现和测量才能宣称收益。另需按完整路径检查ROB控制经D-cache响应仲裁到AXI寄存器的串联，评估真实弹性响应边界而不是仅全局加缓冲。
