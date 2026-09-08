# 项目进度与跨对话接续

更新时间：2026-09-08。后续对话应先读本文件，再读 `instructions.md` 和
`plan.md`；本文件记录已经验证的事实、当前工作树和下一步，不替代验收要求。

## 当前结论

- JOIN-03、JOIN-04、JOIN-05 的功能实现已经完成。自行编译的 RV32IM 程序、双/四
  发射代表配置和全部 9 组 `FE_WIDTH x BE_WIDTH` 组合均运行通过。
- 乘法器已经改为显式部分积 + 3:2 CSA（全加器形式的三进二出压缩器）Wallace
  归约树；DUT 中没有行为级 `*`。三级 ready/valid 流水支持
  `MUL/MULH/MULHSU/MULHU`、反压和 tag/物理寄存器元数据。
- 后端已经是真实的 `BE_WIDTH=1/2/4` 多发射实现，不只是接口变宽：每 lane 独立
  ALU，bundle 内 RAW rename 旁路，多分配 ROB/RS/LSQ，多路 completion/writeback，
  连续 ROB 多提交；MUL/DIV 共享一个 MDU，并按年龄选择。
- 目前处于 JOIN-05 功能收口完成、JOIN-06 PPA/性能分析已启动的状态。不能宣称
  整个项目最终完成：完整面积、时序和 performance/area 门尚未完成，最新多发射 RTL
  也尚未重跑 18 个历史镜像的发布级全量回归。

## 本轮实现

### JOIN-03 与 Wallace 乘法器

- 新增 `tests/programs/{vvadd,vmul,m_isa_smoke}.c`，修正 `accumulate.c` 以避免
  `-O2` 常量折叠；新增 `tests/join03_manifest.csv` 和 `tools/run_join03.py`。
- `vmul` 的反汇编必须出现硬件 `mul`；`m_isa_smoke` 必须同时出现八条 M 指令：
  `mul/mulh/mulhsu/mulhu/div/divu/rem/remu`。
- `rtl/rv32m_multiplier.v` 的部分积归约为：
  `32 -> 22 -> 15 -> 10 | reg | 10 -> 7 -> 5 -> 4 -> 3 -> 2 | reg |
  final CPA/sign/select`。
- `tb/unit/rv32m_units_tb.v` 对四种乘法模式分别覆盖边界值和 128 组伪随机操作数。

### JOIN-04/JOIN-05 多发射与容量参数化

- `rtl/backend/rv32_backend_joint.v` 和 `rtl/cpu_core.v` 的 decode、rename、dispatch、
  issue、completion、commit 以及 commit trace 都按 packed lane bundle 参数化。
- ROB tag 的 slot 位宽由 `ROB_ENTRIES` 推导；MDU、D-cache、LSQ 和 completion
  全路径传递动态 `TAG_WIDTH`，`PHYS_REGS=96` 时物理寄存器地址不再被截成 6 bit。
- ROB 暴露 slot valid/generation，所有 ALU/MDU/load producer 在入 completion 前
  检查真实 ROB 生命周期，防止 slot 回绕后的 stale response 写入新指令。
- 分支恢复保留严格更老的 ALU/MDU/LSQ 更新，杀死分支本身及年轻 completion；失效的
  producer 会被主动 drain，避免 completion FIFO 反压导致共享 MDU 永久堵塞。
- store 只允许真实 ROB head（commit lane 0）发出，ack 前保持 head；LSQ 支持稀疏
  多 lane 分配，并在恢复同拍保留更老 AGU 地址/数据更新。
- 新增 `tools/run_join05.py` 和 `make join05`，覆盖 9 组 FE/BE 独立组合以及
  `PHYS_REGS={48,64,96}`、`ROB_ENTRIES={16,32,64}`、RS/LSQ 容量变化。

## 已验证证据

本轮最终源代码上：

- `make lint`：退出码 0；本轮新增的组合逻辑 latch 告警已清除。仍有数组敏感列表、
  unused/empty pin 等非致命告警，不能把“lint 通过”解释为零告警。
- `make unit`、`make matrix`：退出码 0。
- `make b03 b06 b09`、随后 `make b07 b09`：退出码 0，覆盖 ROB、Wallace MUL/DIV、
  completion stale-result drain 和后端恢复路径。
- `make join04`：双发射和四发射各 4 个程序全部通过。
- `make join05`：9 个配置、27 次整机执行全部通过。机器可读报告位于被忽略的
  `build/join05/report.json`，可随时重生成。
- JOIN-06 blackbox ASAP7 已完成同容量的 1/1 与 2/2：外围逻辑面积分别为
  26959.5135 和 37324.8 um2，面积倍数约 1.384x。两份报告仍有 104 个 `$mem_v2`
  未计面积，且当前脚本没有输出可用的 ABC delay，因此这些数字只能按同口径比较，
  不能当作完整芯片面积/时序结论。

JOIN-04 代表配置结果（cycles/instret）：

| 配置 | accumulate | vvadd | vmul | m_isa_smoke |
| --- | ---: | ---: | ---: | ---: |
| FE2/BE2/P64/ROB32 | 2017/422 | 1021/147 | 1033/147 | 1827/106 |
| FE4/BE4/P96/ROB64 | 2329/422 | 991/147 | 1013/147 | 1749/106 |

JOIN-05 关键 cycles（完整结果见 JSON）：

| FE/BE | accumulate | vvadd | vmul |
| --- | ---: | ---: | ---: |
| 1/1 | 2558 | 1288 | 1288 |
| 2/1 | 2017 | 1048 | 1120 |
| 2/2 | 2017 | 1021 | 1033 |
| 4/1 | 2428 | 1049 | 1126 |
| 4/2 | 2329 | 1024 | 1041 |
| 4/4 | 2329 | 991 | 1013 |

`FE=1` 时 BE 增宽没有收益，说明前端是明确瓶颈。相对 1/1，2/2 在三个短程序上的
speedup 约为 1.27/1.26/1.25；4/4 约为 1.10/1.30/1.27。控制流密集的 accumulate
在 FE4 下反而退化，主要嫌疑是预测/redirect 仍偏向 lane 0 以及 bundle 遇控制流时的
浪费。因此目前没有证据满足“面积约翻倍时性能至少 1.3x”的最终门槛。

## 工作树注意事项

- 工作树原本就有未提交改动和未跟踪文档；不要 reset、checkout 或覆盖用户改动。
- 本轮主要相关文件：`Makefile`、`rtl/cpu_core.v`、`rtl/rv32m_multiplier.v`、
  `rtl/backend/{rv32_backend_joint,rv32_rob,rv32_lsq,rv32_completion_network}.v`、
  `tb/integration/cpu_core_image_tb.v`、`tb/unit/rv32m_units_tb.v`、
  `tools/run_join03.py`、`tools/run_join05.py`、JOIN-03 C 源以及
  `docs/{multiplier,mdu,backend_joint}.md`。
- `RISC-V-CPU-Simulator` 和 `MinorCPU` 是只读参考仓库；不要修改。
- `build/` 中报告是生成物且通常被 gitignore；可审计状态必须以本文件和可重跑命令为准。

## 下一步执行顺序

1. 在当前多发射源代码上跑 `make join02-vlt-fast`，再单独跑长耗时 `pi`，完成最新
   18/18 历史镜像发布门；随后重跑 `make join03 join04 join05` 固化同一版本证据。
2. 继续 JOIN-06：补跑 4/4，并对至少 1/1、2/2、4/4 运行 `make synth`，提取
   ASAP7 面积、ABC delay，并把 cycles/IPC、预测率、Cache 命中率、stall 和面积合并
   为 Pareto/performance-area 报告。
3. 针对前端控制流瓶颈优化：检查多 lane 预测、bundle 内首个 taken branch 截断、
   redirect 后 fetch queue 利用率，再用同一程序矩阵确认收益而不是只优化单点。
4. 补齐 C++ reference 的逐条 CommitRecord 差分、宽配置性能计数器导出，以及发布级
   日志/哈希索引。若 PPA 不达标，再根据综合层级报告选择 RS/ROB/PRF/Wallace 结构优化。

常用入口：`make doctor`、`make lint unit matrix`、`make b06 b09`、`make join03`、
`make join04`、`make join05`、`make join02-vlt-fast`、`make synth`、`make synth-bb`。
