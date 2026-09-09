# 项目进度与跨对话接续

更新时间：2026-09-09。后续对话应先读本文件，再读 `instructions.md` 和
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
- 已按 `docs/area_optimization_strategy_2026-09-08.md` 开始单发射面积优化。当前已完成
  P0 面积审计、固定 completion producer、LSQ 32-bit/4-byte 相对数据重构、LSQ 重复
  转发扫描合并、completion FIFO 深度参数化，以及从 RS 到 ROB/LSQ 的 store payload
  全链路 32-bit/4-byte 收窄，并以 free bitmap 替代环形 free-list 与恢复压缩网络；结果
  和未决限制见下节。

## 面积优化执行批次（2026-09-08）

统一实验配置为 `FE=1/BE=1/PHYS=48/ROB=16/RS=4/LSQ=4`，使用 `make synth-bb`。
因为网表仍含 `$mem_v2`、`$_MUX_`、`$_NOT_` 等未定价单元，以下面积都是
`known_standard_cell_um2`，只能做同流程趋势对比，不能当作完整 `A_total`。

| 批次 | 改动 | 已知面积 µm² | 未定价实例 | `$mem` bits |
| --- | --- | ---: | ---: | ---: |
| Stage A | 审计基线 | 15864.57090 | 21094 | 66300 |
| P1 | 固定 ALU/MDU/LSQ producer 位置 | 15708.69612 | 21094 | 66300 |
| P2 | PRF data 不复位 | 15822.42012 | 19654 | 66300 |
| P3b | LSQ 相对 32/4-bit 状态 + 单次转发合并 | 15054.19992 | 19371 | 65436 |
| P4 | completion 深度按 BE=1/2/4 取 4/8/16 | 15027.34356 | 19367 | 62388 |
| P5 | RS→ALU→completion→ROB/LSQ store payload 收窄为 32/4 bit | 13513.23972 | 15623 | 61620 |
| P7 | free bitmap + 恢复 reserved bitmap，删除 free-list 动态压缩 | 9525.31812 | 15684 | 61236 |

与 Stage A 相比，P7 的已知面积下降 `6339.25278 µm²`（`39.96%`），未定价实例减少
5410 个，manifest 中的存储位减少 5064 bit。P7 相对 P5 单步下降
`3987.92160 µm²`（`29.51%`）；未定价实例增加 61 个，但少了一个高端口 `$mem_v2`，
存储位减少 384 bit。P5 相对 P4 单步下降 `1514.10384 µm²`（`10.08%`）。
P2 单独看已知面积上升，但同时减少了
1472 个未定价 mux；在 generic cell 全部合法化前，PRF data 不复位只标为“物理方向合理、
完整面积待确认”，不把它记成已证实的面积收益。

实现细节和验证：

- `tools/audit_synth.py` 将所有未知面积 cell 和 `$mem*` 列入 JSON；存在任一未知项时
  状态为 `INCOMPLETE` 且总面积为 null。`tools/test_audit_synth.py` 的 2 项测试通过。
- completion producer 固定为 `[ALU lanes][MDU][LSQ]`，删除动态 rank/压缩网络；该步
  后端局部已知面积从 5396.30586 降至 5240.43108 µm²。
- LSQ 每项 store/forward payload 从 `128+16+128+16=288 bit` 降至
  `32+4+32+4=72 bit`；资格阶段不再搬运数据，只有最终选中的 load 做一次 4-byte
  最近 store 优先合并，缓存边界才展开为 128/16 bit。
- P5 将 store payload 在 RS、ALU、completion FIFO、ROB 和 LSQ 的内部契约统一成
  access-relative `32-bit data + 4-bit mask`；只有 ROB commit 与 LSQ D-cache 边界展开
  为 128/16 bit。分模块已知面积相对 P4：ROB `-735.37`、LSQ `-621.90`、ALU
  `-90.78`、RS `-33.90`、completion `-34.99 µm²`，joint 胶水约 `+2.83 µm²`。
  B-03 还直接检查了地址偏移 0 和 4 时，ROB 边界输出能分别展开为正确的
  128-bit line data 与 16-bit byte mask。
- B-08 新增多 store 字节合并、最近 store 覆盖和 halfword 符号扩展测试；B-08 的
  BE=1/2、B-09、JOIN-03 均通过。P5 后 B-03/04/05/07/08/09、lint、JOIN-03、
  JOIN-04 均通过；1/1 四程序周期保持
  2558/1288/1288/2083，没有观察到性能回退。
- P3 的中间版本曾在每次扫描中重建 128-bit line，已知面积升至 16119.96876 µm²；
  该结构已被 P3b 替代，保留这条记录用于避免以后重复引入宽可变移位网络。
- P6 曾尝试把 joint 中按 ROB 深度保存的 imm/prediction/memory metadata 迁到 RS，并
  随 ALU 结果携带分支预测元数据。该实验存储位降到 60284 bit，但已知面积升至
  `13728.80502 µm²`、未定价实例升至 16026，分别比 P5 增加 `215.56530 µm²` 和
  403 个；已回退，不在当前 RTL 中。后续若继续消除元数据重复，应优先做窄 lookup
  或改变所有权接口，而不是把整组字段搬进 RS/ALU。
- P7 把 `PHYS_REGS-1` 项、每项 PAW 位的环形 free-list 改为 `PHYS_REGS` 位 bitmap。
  rename 分配按 lane 依次执行 priority select + mask，commit 直接置回 old-phys bit；
  branch recovery 从 checkpoint RAT、分支自身映射和幸存 ROB old-phys 得到 reserved
  bitmap，取反后直接恢复，不再动态压缩空闲号。已知面积中 rename 增加 `30.72006`
  µm²，但 backend joint 减少 `4018.64166 µm²`，净收益显著。B-02 的三组 BE/PHYS
  参数、B-09、lint、JOIN-03、JOIN-04、JOIN-05 均通过；1/1 周期保持不变。宽配置周期
  明显下降，但尚未用 stall/mispredict 计数器完成归因，不能先验地全部记为 bitmap 收益。

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
| FE2/BE2/P64/ROB32 | 2017/422 | 989/147 | 1001/147 | 1827/106 |
| FE4/BE4/P96/ROB64 | 1496/422 | 959/147 | 981/147 | 1749/106 |

JOIN-05 关键 cycles（完整结果见 JSON）：

| FE/BE | accumulate | vvadd | vmul |
| --- | ---: | ---: | ---: |
| 1/1 | 2558 | 1288 | 1288 |
| 2/1 | 2017 | 1028 | 1100 |
| 2/2 | 2017 | 989 | 1001 |
| 4/1 | 1497 | 1036 | 1113 |
| 4/2 | 1496 | 992 | 1009 |
| 4/4 | 1496 | 959 | 981 |

`FE=1` 时 BE 增宽没有收益，说明前端是明确瓶颈。相对 1/1，2/2 在三个短程序上的
speedup 约为 1.27/1.30/1.29；4/4 约为 1.71/1.34/1.31。P7 后控制流密集的
accumulate 在 FE4 下不再退化，但需要进一步采集 free-list stall、mispredict/rollback
周期确认原因。是否满足“面积约翻倍时性能至少 1.3x”的最终门槛仍必须使用完整面积和
固定 benchmark 集合判定，不能只由当前三个短程序得出。

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
2. 继续面积计划：P7 free bitmap 已完成并保留；下一步优先让 ROB 提供窄 lookup，逐项
   消除 joint 重复元数据，或优化 Cache hit pipeline。继续沿用统一配置做独立 A/B，并
   避免重复采用已被 P6 证伪的“整组元数据搬入 RS/ALU”方案。
3. 继续 JOIN-06：补跑 4/4，并对至少 1/1、2/2、4/4 运行 `make synth`，提取
   ASAP7 面积、ABC delay，并把 cycles/IPC、预测率、Cache 命中率、stall 和面积合并
   为 Pareto/performance-area 报告。
4. 针对前端控制流瓶颈优化：检查多 lane 预测、bundle 内首个 taken branch 截断、
   redirect 后 fetch queue 利用率，再用同一程序矩阵确认收益而不是只优化单点。
5. 补齐 C++ reference 的逐条 CommitRecord 差分、宽配置性能计数器导出，以及发布级
   日志/哈希索引。若 PPA 不达标，再根据综合层级报告选择 RS/ROB/PRF/Wallace 结构优化。

常用入口：`make doctor`、`make lint unit matrix`、`make b06 b09`、`make join03`、
`make join04`、`make join05`、`make join02-vlt-fast`、`make synth`、`make synth-bb`。
