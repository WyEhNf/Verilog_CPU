# 项目进度与跨对话接续

更新时间：2026-09-16。后续对话应先读本文件，再读 `instructions.md` 和
`plan.md`；本文件记录已经验证的事实、当前工作树和下一步，不替代验收要求。

## 当前冻结项

- `pi` 由用户于 2026-09-16 明确暂时冻结；当前回归、差分和优化筛选均不得运行它，
  也不得把跳过 `pi` 描述为 18/18 发布门完成。解除冻结后再补最终长程序验收。
- `LH/LHU/SH` 本轮不补链路，继续保持 decoder 显式 `legal=0`。当前功能声明限定为
  已验收的 RV32IM 算术/控制流以及 `LB/LBU/LW/SB/SW` 访存范围。

## 当前结论

- JOIN-03、JOIN-04、JOIN-05 的功能实现已经完成。自行编译的 RV32IM 程序、双/四
  发射代表配置和全部 9 组 `FE_WIDTH x BE_WIDTH` 组合均运行通过。
- 乘法器提供两种可参数化实现：`MUL_IMPL=0` 是显式部分积 + 3:2 CSA Wallace 三级
  流水吞吐档，`MUL_IMPL=1` 是 16-cycle radix-4 shift/add 面积档；DUT 中均没有行为级
  `*`，且都支持 `MUL/MULH/MULHSU/MULHU`、反压和 tag/物理寄存器元数据。
- 后端已经是真实的 `BE_WIDTH=1/2/4` 多发射实现，不只是接口变宽：每 lane 独立
  ALU，bundle 内 RAW rename 旁路，多分配 ROB/RS/LSQ，多路 completion/writeback，
  连续 ROB 多提交；MUL/DIV 共享一个 MDU，并按年龄选择。
- 2026-09-16 在当前多发射 RTL 上运行了排除 `pi` 的 JOIN-02 Verilator 回归，17/17
  镜像均以期望返回值停止；`pi` 因上述冻结未运行。C++ reference 已提供逐条
  CommitRecord 输出与 JSONL 比较工具，`naive` 在 FE_WIDTH=1/2/4 下各 18 条提交均完全
  一致；其余 16 个非 pi 镜像尚未逐条对拍，因此发布级完整差分仍未闭环。
- 目前处于 JOIN-05 功能收口完成、JOIN-06 PPA/性能分析进行中的状态。不能宣称
  整个项目最终完成：完整面积、真实时序和 performance/area 门尚未完成。
- 已按 `docs/area_optimization_strategy_2026-09-08.md` 开始单发射面积优化。当前已完成
  P0 面积审计、固定 completion producer、LSQ 32-bit/4-byte 相对数据重构、LSQ 重复
  转发扫描合并、completion FIFO 深度参数化，以及从 RS 到 ROB/LSQ 的 store payload
  全链路 32-bit/4-byte 收窄，并以 free bitmap 替代环形 free-list 与恢复压缩网络；P8
  又删除了 joint 与 ROB 重复的 phys/rd 元数据表，P10 将 ROB recovery lookup 改为
  tag-slot 直接索引。结果和未决限制见下节。

## 面积优化执行批次（2026-09-08 至 2026-09-09）

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
| P8 | ROB 直接提供提交 phys 元数据与恢复 reclaim bitmap，删除 joint 重复表 | 9314.03934 | 15682 | 61140 |
| P9 | 增加 radix-4 紧凑乘法档；同源码 Wallace→radix-4 | 8618.67540 | 14636 | 61140 |
| P10 | ROB recovery 从 tag 直接索引 slot，删除 BE×ROB 候选扫描 | 8549.18712 | 14636 | 61140 |

与 Stage A 相比，P8 的已知面积下降 `6550.53156 µm²`（`41.29%`），未定价实例减少
5412 个，manifest 中的存储位减少 5160 bit。P8 相对 P7 单步下降
`211.27878 µm²`（`2.22%`），未定价实例减少 2 个、存储位减少 96 bit。P7 相对 P5 单步下降
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
- P8 删除 backend joint 中与 ROB 重复的 `new_phys/old_phys/rd/rd_we` 四组按 ROB slot
  元数据。commit 的 old/new phys 直接由 ROB 输出；恢复时 ROB 输出分支自身目的映射，
  并扫描严格年轻的 live 项生成待回收物理寄存器 bitmap/count，rename 以当前 free
  bitmap 与 reclaim bitmap 的并集恢复。分模块已知面积相对 P7：ROB 增加
  `572.07546 µm²`，joint 减少 `783.35424 µm²`，净下降 `211.27878 µm²`；memory
  数量从 103 降至 101。B-03、B-09、lint、JOIN-03、JOIN-04、JOIN-05 均通过，
  9 组配置的周期与 P7 基线一致。P8 审计仍为 `INCOMPLETE`，不可当作完整芯片面积。
- P9 为 MDU 增加 `MUL_IMPL`：`0` 保留 Wallace 吞吐档，`1` 选择 16-cycle radix-4
  shift/add 面积档。为避免把 HALT 修复等后续源码变化混入收益，使用同一源码重新生成
  Wallace 基线 `9354.65922 µm² / 15682 unknown`；radix-4 为
  `8618.67540 µm² / 14636 unknown`，已知面积下降 `735.98382 µm²`（`7.87%`），未计价
  实例减少 1046，memory 保持 `101/61140`。JOIN-03 单发射四程序周期不变；宽配置只有
  `vmul` 回退，FE2/BE2 `1001→1069`（`6.8%`），FE4/BE4 `981→1079`（`10.0%`）。
- P10 利用 generation-qualified ROB tag 已编码 slot 的事实，只对 `BE_WIDTH` 个 recovery
  候选做 valid/generation/age 校验，不再让每个候选扫描全部 ROB 项。相对 P9 radix-4
  点，blackbox 已知面积从 `8618.67540` 降至 `8549.18712 µm²`（`-69.48828`，
  `-0.81%`），unknown 与 memory 保持 `14636` 和 `101/61140`；FF-reference 也从
  `57804.96150` 降至 `57728.91222 µm²`（`-76.04928`，`-0.13%`）。B-03、B-09、
  width matrix、radix-4 JOIN-03/04 均通过，代表程序周期不变。
- P10 的更激进版本曾把 completion 和 store ack 也改成 variable-index 写入。全量版本
  blackbox 降到 `7698.00672 µm²`，但使四组 16-entry ROB payload 重新推断为 1R1W
  memory，manifest 增加 1600 bit，FF-reference 反升至 `58849.64766 µm²`；单独保留
  store ack 直接索引时 FF-reference 也升到 `58824.81792 µm²`。两者均已回退，不能把
  黑盒中移入未计价 memory 的面积当作真实收益。
- cache stats 参数关闭实验的顶层面积前后均为 `9354.65922 µm²`。此前看到的
  `772.28802 µm²` 是未被顶层引用的独立模块统计，Yosys 原本已从 `cpu_core` 层次优化掉
  该实例；因此它不是实际面积机会。保留 `ENABLE_CACHE_STATS` 仅用于明确 production/profile
  配置，不能把它计入 P9 收益。
- P8b 曾进一步删除 joint 的 `rob_pc_mem`，改由 ROB 在恢复选择后输出 source PC。
  B-03/B-09 通过，memory/bits 从 P8 的 `101/61140` 降至 `100/60628`，但已知面积升至
  `9381.80718 µm²`，比 P8 增加 `67.76784 µm²`（`0.73%`）。该实验已回退；结论是当前
  综合口径下，恢复路径新增的 ROB PC 读取 mux 抵消了 512 bit 重复存储的收益。

### 2026-09-16 面积方向复核

P8 小配置的已知标准单元面积热点为：ROB `1811.23`、PRF `1731.59`、乘法器
`1086.02`、LSQ `1061.57`、D-Cache `1002.35 µm²`。cache stats 的 `772.29 µm²` 是独立
模块统计，不属于优化前的顶层面积。由于仍有
8518 个 `$_MUX_`、6817 个 `$_NOT_` 和 101 个 `$mem_v2` 未定价，这个排序只用于同流程
定位，不是 `A_total`。

当前价值排序：

1. 先补全综合账本并让最新 P8 的性能点、面积点使用同一源码；旧 JOIN-06 面积不可继续
   与最新周期结果混用。
2. P9 已完成 radix-4 紧凑乘法档：面积优先的单发射点用 `MUL_IMPL=1`，宽核或乘法吞吐
   优先点保留 Wallace；后续只在需要中间 Pareto 点时再研究 17x17 分解。
3. ROB 研究小型 branch checkpoint pool 或串行 rollback。该方向同时针对 `1811 µm²`
   已知逻辑和 3072 bit checkpoint 黑盒，但恢复语义风险高于前两项。P10 已先移除
   recovery lookup 的 BE×ROB 扫描；completion/store-ack 直接索引的 FF 实验已证伪。
4. 性能侧优先消除 D-Cache hit 路径 `pipeline_empty && outputs_free` 的全 drain；这比继续
   搬移 joint 元数据更可能让紧凑 2/2 配置越过 1.3x 周期性能门。
5. 宽核后续再做 issue/CDB/PRF 端口解耦或分簇。P6、P8b 已证明简单搬移元数据可能反增
   mux 面积，不再重复。

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
- `make b03 b06 b09`、随后 `make b07 b09`；P9 后再次运行 `make b03 b06 b09`：退出码
  0。B-06 现在分别运行 Wallace 与 radix-4 的边界值、反压、flush、四模式各 128 组随机
  操作数，以及两种 MDU RS 集成路径。
- `make join04`：双发射和四发射各 4 个程序全部通过。
- `make join05`：9 个配置、27 次整机执行全部通过。机器可读报告位于被忽略的
  `build/join05/report.json`，可随时重生成。
- P9 上 `make join03 MUL_IMPL=1` 与 `make join04 MUL_IMPL=1` 全部通过；默认 Wallace 的
  JOIN-03 也已复跑。`make join02-vlt-fast` 的 17 个非 pi 镜像全部通过，pi 保持冻结。
- JOIN-06 blackbox ASAP7 已有 1/1、2/2、4/4 三点报告，已知外围逻辑面积分别为
  26959.5135、37324.8、113312.8294 um2；对应四程序几何平均周期加速约为
  1.000x、1.248x、1.377x。但这些综合产物早于最新 P8 面积优化，且仍有
  104/105/107 个 `$mem_v2` 未计面积，也没有可用的真实 STA。它们只能证明旧版本宽度
  扩展趋势，不能与最新性能报告拼接成最终 Pareto 结论。

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

- 2026-09-16 已把此前未提交的多发射、面积优化、回归工具和文档整理为同一个可审计
  检查点。外部研究论文 PDF 只保留本地副本并由 `.gitignore` 排除，不作为项目源码提交。
- 本轮主要相关文件：`Makefile`、`rtl/cpu_core.v`、`rtl/rv32m_multiplier.v`、
  `rtl/backend/{rv32_backend_joint,rv32_rob,rv32_lsq,rv32_completion_network}.v`、
  `tb/integration/cpu_core_image_tb.v`、`tb/unit/rv32m_units_tb.v`、
  `tools/run_join03.py`、`tools/run_join05.py`、JOIN-03 C 源以及
  `docs/{multiplier,mdu,backend_joint}.md`。
- `RISC-V-CPU-Simulator` 和 `MinorCPU` 是只读参考仓库；不要修改。
- `build/` 中报告是生成物且通常被 gitignore；可审计状态必须以本文件和可重跑命令为准。

## 下一步执行顺序

1. 保持 `pi` 冻结，使用 17 项快速门和 JOIN-03/04/05 做当前迭代验证；Windows 下标准
   `make join02-vlt-build` / `make join02-vlt-fast` 已可直接构建运行，不再依赖手工归档。
2. 将现有 C++ reference CommitRecord 差分从 `naive` 扩展到其余 16 个非 pi 镜像，并补
   发布级日志/哈希索引；参考仓库保持只读。
3. 重新用最新 P8 源码对 1/1、2/2、4/4 生成同版本性能与综合报告。当前旧 JOIN-06
   面积不得与最新周期数据混用；完整结论仍需 SRAM 计价与真实 STA。
4. 面积优化近期优先级：先让综合面积账本完整；乘法器 Wallace/radix-4 双档已形成
   Pareto，下一项面积研究转向 ROB checkpoint pool/rollback。性能侧优先消除 D-Cache
   hit 路径的全流水 drain。cache stats、P8b 与 P6 已证伪的方向不重复尝试。
5. 完成宽配置性能计数器导出，再依据 frontend、ROB/RS/LSQ、MDU、Cache stall 数据决定
   是否做前端预测、容量缩减或 BE4 分簇，避免只按源码直觉优化。

常用入口：`make doctor`、`make lint unit matrix`、`make b06 b09`、`make join03`、
`make join04`、`make join05`、`make join02-vlt-fast`、`make synth`、`make synth-bb`。
