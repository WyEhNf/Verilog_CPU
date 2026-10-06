# 参数化多发射 RV32IM 乱序 CPU 实施计划

## 0. 计划边界与依据

本计划以根目录 `instructions.md` 和 `VerilogCPU/SPEC.md` 为验收约束，以
`RISC-V-CPU-Simulator` 为 Tomasulo 语义参考，以 `MinorCPU` 为缓存、取指和 FPGA
系统连接的参考。三者的角色不同：

- `instructions.md`：当前项目的硬性要求，优先级最高。
- `RISC-V-CPU-Simulator`：单发射、无 Cache 的 C++ Tomasulo 模型。重点借鉴它的
  ROB/RS/LSQ、generation tag、`evaluate -> arbitrate -> latch` 时序和单元测试方法，
  不直接照搬它的单发射和三周期无 Cache 内存模型。
- `MinorCPU`：上一年度的 Chisel/Verilog CPU。重点参考 I/D Cache、访存仲裁、预测
  错误恢复和 MMIO 的系统级连接，但它是固定规模、单发射、没有 RV32M 的核心，不能
  直接作为当前 CPU 的实现。
- `VerilogCPU`：本年度未完成 RTL。已有 decoder、整数 ALU、三周期乘法器、迭代除法器、
  物理寄存器文件和 rename unit，可先审计后复用；缺少完整前端、ROB/RS/LSQ、Cache、
  顶层和回归链路的部分必须独立设计。

向量乘法和向量加法指的是 C 程序中的标量循环，不要求 RISC-V V 扩展。`CSR`、`FENCE`
不列入首轮验收，且转储文件中的 `.comment`、调试段出现的 CSR/FPU 助记符不应被误判为
待执行指令。

### TEST-01 实际验收数据、停机语义和结果表

本项目的程序验收集是 `RISC-V-CPU-Simulator/testcases/`，而不是一个抽象的 “SORA
用例”。该目录的 18 份 `.data` 是必须直接加载并跑完的输入；`.c` 用于理解算法和后续由
本项目工具链重新编译，`.dump` 用于核对反汇编，不能把其中的非代码段当作 ISA 需求。

| 程序 | 期望返回值 | 主要压力 |
| --- | ---: | --- |
| `array_test1` | 123 | 数组、函数调用、字节/字访存 |
| `array_test2` | 43 | 数组和控制流 |
| `basicopt1` | 88 | 大量循环和数组 |
| `bulgarian` | 159 | 分支和整数算术 |
| `expr` | 58 | 表达式、函数调用 |
| `gcd` | 178 | 递归、除余数软件例程 |
| `hanoi` | 20 | 深递归、栈访存 |
| `lvalue2` | 175 | 地址计算和写回 |
| `magic` | 106 | 长循环和分支 |
| `manyarguments` | 40 | 调用约定、栈 |
| `multiarray` | 115 | 二维数组 |
| `naive` | 94 | 最小控制流 |
| `pi` | 137 | 极长循环、密集 load/store |
| `qsort` | 105 | 递归、数组和分支 |
| `queens` | 171 | 回溯、栈和分支 |
| `statement_test` | 50 | 语句和分支组合 |
| `superloop` | 134 | 高分支密度循环 |
| `tak` | 186 | 深递归和调用返回 |

镜像是小端的稀疏 byte image：`@xxxxxxxx` 设定后续字节地址，随后每个两位十六进制数为
一个字节；程序入口为地址 `0x00000000`。testbench 必须支持离散段（现有镜像会跳到
`0x00001000` 及以后），不能把文件当成连续 word 列表。所有段必须落在 1 MiB 内；该容量
覆盖现有最高使用地址（`qsort` 约 `0x0000b0b0`）。

`0x0ff00513` 是验收运行环境的结束哨兵：只有当这条指令到达 **ROB head 并提交** 时才令
`halted=1`，返回其提交前架构 `a0[7:0]`，不得在取指、译码或执行该条 `addi` 时提前停止。
每项回归以表中值、无 `error`、有序退休 trace 和 watchdog 未触发共同判定通过；周期数只
记录性能，不能与 C++ 模型逐周期相等。`pi`、`qsort`、`tak` 等长程序使用各自可配置的硬
上限，另设“连续 N 周期无退休”看门狗，避免短上限误杀正确程序或无限等待掩盖死锁。

### TEST-02 从真实镜像得到的 ISA 范围

根 `instructions.md` 提到理论上不需要 `lb/lh`，但实际 18 份可执行代码包含
`LB`、`LBU`、`LW`、`SB`、`SW`。因此下表中的“必须”以真实验收优先；若不实现字节
访存，程序会在到达算法主体前就行为错误。

| 类别 | 本轮硬件要求 | 依据与处理 |
| --- | --- | --- |
| 整数/立即数 | `ADD/SUB/AND/OR/XOR/SLL/SRL/SRA/SLT/SLTU` 及对应 I 型、`LUI/AUIPC` | 18 个镜像的可执行 `.text` 使用；ALU 和译码必须全部覆盖。 |
| 控制流 | 六种条件分支、`JAL`、`JALR` | 递归、调用/返回和密集循环必需；`JALR` 目标 bit 0 清零。 |
| 访存基线 | `LB/LBU/LW/SB/SW` | 作为 LSQ、D-Cache、byte enable 与 load 符号扩展的最低实现集。 |
| 半字访存 | `LH/LHU/SH` | 当前镜像未观察到，且根指令说明不要求；接口从第一天保留 `size/sign/mask`，在主回归通过后补齐，补齐后才可宣称完整 RV32I 访存子集。 |
| M 扩展 | `MUL/MULH/MULHSU/MULHU/DIV/DIVU/REM/REMU` | `instructions.md` 的 RV32IM 与乘/除单元要求；旧 `.data` 常以 `__mulsi3/__divsi3/__modsi3` 软件例程实现，不能据此证明硬件 M 已测试。 |
| 不在首轮 | CSR、FENCE、浮点、V 扩展 | 不因 `.dump` 的注释/调试段而实现；译码给 `legal=0`，并在精确提交点报错。 |

伪助记符 `ret`、`j`、`mv`、`li`、`beqz` 等只是上述真实 RV32I 编码的汇编别名。除 18 个
镜像外，必须用本项目的 `rv32im` 编译链重新构建“0 到 100 累加、向量加、向量乘”，并在
反汇编中确认 `MUL/DIV/REM` 的机器码确实出现；其中向量程序也要保留可比较的内存输出和
返回值。

### TEST-03 自行编译程序和 M 扩展覆盖

在 `VerilogCPU/tests/programs/` 保存可审计的 C 源、启动代码、链接脚本、Make 规则、ELF、
objdump、稀疏镜像和 manifest。外部向量程序链接中的 C 主体应保留来源 URL/commit；不把
网络下载结果或手工抄写的机器码当作唯一输入。建议固定以下工件：

| 工件 | 源码与编译策略 | 验收重点 |
| --- | --- | --- |
| `sum100` | C 循环累加 `0..100`，`-march=rv32i` | 基础算术/循环；退出低 8 位应为 `5050 & 255 = 186`。 |
| `vvadd` | 取所给 vvadd C 主体或等价的固定长度标量数组循环，`-march=rv32i` | load/store、分支、Cache 数据正确；host checker 比较数组 checksum 与返回值。 |
| `vmul` | 取所给 multiply C 主体或等价固定长度标量数组乘法，`-march=rv32im -O2`，操作数避免编译期常量折叠 | objdump 和 CommitRecord 均需出现 `MUL`；检查数组 checksum。 |
| `m_isa_smoke` | C + 小段内联汇编或独立 `.S`，`-march=rv32im` | 逐一覆盖 `MULH/MULHSU/MULHU/DIV/DIVU/REM/REMU`、除零与 `INT_MIN/-1`。 |

所有程序使用同一 `startup.S`：设置栈、调用 `main`，并在返回后放置 `.word 0x0ff00513`；
链接脚本使入口位于 `0x0`、text/data/stack 均在 1 MiB 模型内。构建链固定为
`$RISCV_PREFIX-gcc -march=<rv32i|rv32im> -mabi=ilp32 -ffreestanding -nostdlib`，随后由
`objdump` 审查、`objcopy` 和 `make_image.py` 生成 `@address` 镜像。每次重编译的期望
checksum 由 host checker 用同一 C 算法独立计算并写入 manifest；CPU 不得把这个值硬编码在
testbench 中。

### GAP-01 C++ 模型可借鉴处与必须独立完成的硬件部分

`RISC-V-CPU-Simulator` 是正确性参考，不是可综合实现。它已经提供 Tomasulo 的单发射
语义（ROB/RS/LSQ、CDB 仲裁、generation tag、未知老 store 阻塞 load、最近匹配 store
转发），但没有 Cache，且其固定三周期访存不能代表目标硬件。

| 范围 | C++ 模型可作为参考 | 本项目必须在 Verilog 中独立完成 |
| --- | --- | --- |
| 周期语义 | `evaluate -> arbitrate -> latch` 的旧状态/新状态分离 | 时钟、同步 reset、寄存器使能、valid/ready、反压和无 X 的真实时序。 |
| 发射与完成 | 单发射 Tomasulo、tag 生命周期和 CDB 概念 | 1/2/4 lane bundle、同 bundle rename 旁路、多端口 PRF、完成 FIFO 与 `BE_WIDTH` 写回仲裁。 |
| 访存 | LSQ 顺序/转发算法、固定延迟请求模型 | 独立 I/D 端口、三周期流水 L1、miss 状态机、50 周期 line 主存、writeback/refill、byte lane。 |
| 前端 | 简单预测的行为可比对 | PC/Fetch Queue、Bimodal + BTB、预测元数据、epoch、取指反压和跨 line 边界。 |
| 恢复 | tag 有效性和提交语义 | 分支 checkpoint/recovery、RS/LSQ/完成缓冲清除、旧 I/D 响应屏蔽、精确 HALT/error。 |
| 验证与交付 | 18 项返回值和退休结果的黄金参考 | 镜像加载器、RTL testbench、断言/trace/watchdog、参数矩阵、Yosys + ASAP7 综合及 PPA 报告。 |

因此，C++ 模型只用于退休状态差分和局部算法交叉验证；不能复制其单发射调度、瞬时容器
操作或三周期“内存”来代替 RTL 中的缓存、主存协议和时序闭环。

`RISC-V-CPU-Simulator` 保持只读。若要逐条对拍，在 `VerilogCPU/tools/` 新建外置
`reference_trace.cpp`：仅 include 参考仓库公开的 `simulator.h/module_io.h`，在其
`evaluate -> CDB -> latch` 的状态更新前记录公开 `CycleWires.commit`，输出 PC、指令、
rd/value 和 store 信息到独立文件。该适配器不写入参考仓库；如果参考版本导致适配器不能
编译，18 项返回值和 RTL CommitRecord 断言仍是硬门，逐条差分降为可选诊断而非阻塞实现。

## 1. 环境、语言和技术栈

### ENV-01 语言和 RTL 约束

- RTL 使用 **Verilog-2005**，源文件为 `.v`，不依赖 SystemVerilog 特性。
- 跨模块的多 lane 接口统一压平成 packed bus；不在端口中使用 unpacked array。
- RTL 注释遵守 `VerilogCPU/AGENTS.md`：只写必要的 ASCII 英文；中文设计说明写在
  `docs/*.md`。
- C++ 参考模型和测试工具使用 C++20；Python 只用于镜像生成、随机向量和报表脚本。

### ENV-02 编译和仿真工具

- **Icarus Verilog**：`-g2005`，用于快速单元仿真和基础回归。
- **Verilator**：`--language 1364-2005`，用于更快的整机仿真、lint 和波形导出。
- **GTKWave/FST/VCD**：查看单元和整机波形。
- **CMake 3.22+、C++20 编译器**：构建和运行 `RISC-V-CPU-Simulator` 参考模型；
  目标 CPU 不依赖它才能综合，但使用它做差分对拍。
- **GNU Make、Git、PowerShell 或 Bash**：统一入口、超时、回归和结果保存。

### ENV-03 RISC-V 程序工具链

- `riscv64-elf-gcc`/Binutils，使用 `-march=rv32i -mabi=ilp32` 或
  `-march=rv32im -mabi=ilp32`。
- 程序流水线为 `C -> .o -> ELF -> objdump -> 稀疏 @address byte image`；保留 `.o`
  便于检查编译结果，使用 `objdump` 确认验收程序实际包含 M 指令。
- 启动代码、链接脚本、最小 runtime 和镜像转换脚本放在 `tools/`，不要手工复制二进制。

### ENV-04 综合和面积

- 使用 **Yosys + ASAP7** 进行综合和面积/延迟报告。
- Cache 数据阵列和 tag 阵列先按 SRAM blackbox 统计主指标，再提供按寄存器综合的面积上界；
  两种口径必须分开报告。
- 每次综合固定库版本、约束和脚本，产物放入 `build/` 或 `reports/`，不提交生成文件。

### ENV-05 环境检查和超时

建立 `make doctor` 检查 Verilog 工具、Verilator、Yosys、RISC-V multilib、Python、
ASAP7 路径和只读的 `RISC-V-CPU-Simulator/testcases` 路径。所有单元、整机和综合命令都设置墙钟 timeout；整机另加
“周期数上限 + 无退休进度 watchdog”，防止错误设计无限运行。

### ENV-06 额外参考资料

`instructions.md` 列出的 Assassyn 代码可分别参考 driver、两级流水和 downstream 的
测试组织方式：

- [test_driver.py](https://github.com/Synthesys-Lab/assassyn/blob/master/python/ci-tests/test_driver.py)
- [test_async_call.py](https://github.com/Synthesys-Lab/assassyn/blob/master/python/ci-tests/test_async_call.py)
- [test_downstream.py](https://github.com/Synthesys-Lab/assassyn/blob/master/python/ci-tests/test_downstream.py)

它们只用于理解测试驱动和模块边界，不作为 RTL 的直接实现来源；本地的
`RISC-V-CPU-Simulator` 同样保持只读。

## 2. 项目骨架和目录树

### TREE-01 目标目录

保持 `VerilogCPU` 现有仓库为实现仓库，先不大规模移动已有文件；新增模块可以按功能子目录
组织，Makefile 统一递归收集。目标树如下：

```text
VerilogCPU/
├── rtl/                              # 可综合 Verilog-2005
│   ├── rv32im_defs.vh                # 操作码、类、参数和公共位宽
│   ├── rv32im_decoder.v              # 已有：RV32IM 译码，需审计/补测试
│   ├── rv32i_alu.v                   # 已有：整数 ALU，需接入分支/AGU
│   ├── rv32m_multiplier.v            # 已有：三级 Booth-Wallace 乘法器
│   ├── rv32m_divider.v               # 已有：迭代除法器
│   ├── rv32_physical_register_file.v # 已有：参数化 PRF
│   ├── rv32_rename_unit.v            # 已有：RAT/RRAT/free list 原型
│   ├── cpu_core.v                    # 最终顶层和时钟控制
│   ├── common/                       # FIFO、tag、打包/解包和断言辅助
│   ├── frontend/                     # PC、Fetch Queue、取指、解码/dispatch
│   ├── predictor/                    # Bimodal、BTB 和预测反馈
│   ├── backend/                      # ROB、整数/MDU RS、完成网络、提交恢复
│   ├── memory/                       # LSQ、主存协议和内存请求状态机
│   └── cache/                        # 独立 L1 I-Cache/D-Cache
├── tb/
│   ├── unit/                         # 每个 RTL 单元的 testbench
│   ├── integration/                  # 单发射、双发射、四发射整机测试
│   └── models/                       # 50 周期主存、镜像加载和参考检查器
├── tests/
│   ├── programs/                     # 累加、向量加、向量乘和最小程序
│   ├── simulator_cases/              # 从 RISC-V-CPU-Simulator/testcases 只读导入/校验的镜像
│   ├── vectors/                      # decoder/ALU/MUL/DIV/Cache 随机向量
│   └── manifest                       # 测试名、期望值、镜像 hash 与 timeout 配置
├── tools/
│   ├── make_image.py                 # C 到稀疏机器码镜像
│   ├── startup.S、runtime.c、link.ld
│   └── regression/                   # 回归、差分、性能报表脚本
├── docs/                             # 每个已完成元件的中文设计文档（含 interfaces.md）
├── synth/                            # Yosys/ASAP7 脚本和约束
├── build/                            # 忽略的仿真、镜像和综合中间产物
├── reports/                          # 正确性、性能、面积和波形索引
└── third_party/                      # 许可证和固定外部依赖说明
```

### TREE-02 现有代码的处理方式

- `rtl/rv32im_decoder.v`、`rtl/rv32i_alu.v`、`rtl/rv32m_multiplier.v`、
  `rtl/rv32m_divider.v`、`rtl/rv32_physical_register_file.v`、
  `rtl/rv32_rename_unit.v` 作为候选基础，不默认它们已经满足整机协议。
- `docs/decoder.md`、`docs/alu.md`、`docs/multiplier.md`、`docs/divider.md`、
  `docs/prf.md`、`docs/rename.md` 作为设计意图和端口说明；发现 RTL 与文档不一致时，
  先写测试确定行为，再修正文档/RTL。
- `RISC-V-CPU-Simulator` 只读，尤其不修改它的测试或数据；通过 `SIM_TESTCASES_DIR` 或复制到
  `tests/simulator_cases/` 的受控校验脚本使用它。18 项的名称和值以 `TEST-01` 为唯一清单。

## 3. CPU 总体架构

### ARCH-01 宏流水和数据流

采用五级宏流水，级间都有显式 valid/ready 或队列边界：

1. **Fetch**：PC、分支预测、I-Cache 请求和 Fetch Queue 入队。
2. **Decode/Rename**：译码、源寄存器映射、物理寄存器分配、同 bundle 旁路。
3. **Dispatch/Issue**：按程序顺序分配 ROB/RS/LSQ；就绪项由 Tomasulo 选择。
4. **Execute/Memory**：整数 ALU、分支、AGU、MUL、DIV、LSQ 和 D-Cache。
5. **Writeback/Commit**：完成仲裁、PRF/ROB 写回、顺序提交和错误恢复。

```text
                 +---------------- Bimodal + BTB
                 |
PC -> I-Cache -> Fetch Queue -> Decode/Rename -> Dispatch
                                      |             |
                                      |       +-----+-----+
                                      |       | ROB / RS  |
                                      |       |  / LSQ    |
                                      |       +-----+-----+
                                      |             |
                                PRF/RAT      ALU/MUL/DIV
                                                    |
                         +--------------------------+
                         | Completion / Writeback  |
                         +------------+-------------+
                                      |
                              ROB in-order Commit
                                      |
                         LSQ -> D-Cache -> 50-cycle Mem
```

### ARCH-02 乱序语义和时序原则

- 取指和 dispatch 保持程序顺序；RS 中操作数就绪的指令可乱序执行。
- 所有结果带完整生产者 tag；旧 tag 在 ROB slot 回绕后不能唤醒新指令。
- store 的地址和值可以提前计算，但只有到达 ROB/LSQ head 后才能发出 `store_commit` 给
  D-Cache；entry 在 D-Cache acknowledge 前保持 ROB head，ack 后才真正退休。write-back
  Cache 的脏 line 可在以后写主存，但对 CPU 的可见性从该 D-Cache ack 开始。
- branch 在执行阶段得到真实结果和目标；若与预测不符，立刻以该 branch 的 checkpoint 恢复
  RAT/free list/RS/LSQ 尾部、清除严格年轻项并 redirect，不能等到它成为 ROB head 才继续
  取指。预测元数据随指令保留至 ROB 提交时才训练 Bimodal/BTB，因此错误路径不会训练预测器。
- 用“本周期旧状态生成 wire，下一个时钟沿统一写入新状态”的方式设计每个状态单元，禁止一
  个模块读取另一个模块在同周期刚写出的寄存器。
- branch mispredict 在执行期恢复，优先于普通 issue/dispatch；非法指令、越界/非对齐 fault
  和 HALT 则必须等到相应 ROB head 提交才停止并丢弃其年轻项，不能让一个年轻异常阻塞更老
  completion 或提前改变架构状态。

### ARCH-03 必须参数化的范围

顺序/乱序执行模型不做参数化：当前仓库只实现乱序 Tomasulo 核心；如果以后需要顺序核，
应作为另一套执行控制逻辑重写，而不是在同一套状态机中加一个模式位。

| 参数 | 合法值/默认值 | 影响 |
| --- | --- | --- |
| `FE_WIDTH` | 1、2、4 | 每周期最多取指、译码和送入 Fetch Queue 的连续指令数 |
| `BE_WIDTH` | 1、2、4 | 每周期最多 dispatch、issue、完成仲裁和 ROB commit 数 |
| `PHYS_REGS` | 至少 33，默认 64 | 物理寄存器地址宽度、free list 容量和重命名空间 |
| `ROB_ENTRIES` | 2 的幂，默认 32 | ROB 指针、slot tag 和 generation 回绕 |
| `INT_RS_ENTRIES` | 2 的幂 | 整数/分支保留站容量 |
| `MUL_RS_ENTRIES`、`DIV_RS_ENTRIES` | 2 的幂 | 多周期单元前的等待容量 |
| `LSQ_ENTRIES` | 2 的幂 | load/store 顺序跟踪容量 |

非法参数在 elaboration 或仿真开始时明确报错。Cache 容量先固定为 I-Cache 1 KiB、D-Cache
4 KiB、16-byte line；Cache 内部容量参数化放在基础功能通过之后，避免同时扩大验证空间。

### ARCH-04 顶层接口

`cpu_core` 至少包含：

- `clk`、同步 `reset`；
- 独立 I/D 侧 ready/valid 主存 line 请求与响应，line 宽度 128 bit（16 byte）；
- D 侧 write、byte enable、line 地址和写数据；
- `halted`、`error`、`return_value`；
- `cycles`、`instret`、branch/mispredict、I/D hit/miss、stall 计数器；
- 按 `BE_WIDTH` 压平的退休 trace：valid、PC、原始指令、逻辑 rd、写回值。

testbench 提供 1 MiB、小端、从地址 0 开始的 byte memory，I/D 事务可以同时在途；主存
请求接受后固定 50 个周期返回。`0x0ff00513` 作为 `TEST-01` 约定的 HALT 编码：它进入 ROB，
在 head 提交时读取已经提交的 `a0[7:0]`，不得先执行该条 `addi`。

### ARCH-05 参考模型的对应关系

把 C++ 模拟器中的 `IssueOutput`、`ExecuteOutput`、`MemoryRequest`、`MemoryOutput`、
`CommitOutput`、`CDBOutput` 和 `CycleWires` 映射成 RTL valid/ready 总线。每个周期逻辑上
分为：

1. 各模块只读取旧状态并产生候选输出；
2. 完成网络解决资源冲突；
3. 各模块在时钟沿按解析后的总线更新自己的状态。

这保留 Tomasulo 的模块可交换性质；硬件实现不依赖仿真器调用顺序，也不依赖全局内存的
瞬时值。

## 4. 各单元实现细节

下面的 ID 同时用于任务、文件名、测试和提交说明。`A`、`B` 表示两条可以并行推进的
工作流，`S` 表示两人共同维护的接口或集成门。

### 4.1 硬件地基、公共协议和工具

下面的 `H-*` 是所有功能单元的前置条件。它们不是软件模拟器已有的能力，必须先用
Verilog-2005 和 testbench 把时钟、协议、存储层次和观察点搭起来；A/B 不得绕过这些
接口直接互连内部寄存器。

#### H-00 构建配置、文件清单和参数检查（共同）

- 建立唯一的 RTL filelist、`Makefile` 目标和默认配置：
  `FE_WIDTH=1`、`BE_WIDTH=1`、`PHYS_REGS=64`、`ROB_ENTRIES=32`。单元仿真、整机仿真、
  lint、镜像生成、回归和综合必须都从同一份参数来源展开，禁止 testbench 私自覆盖位宽。
- 在 `rv32im_defs.vh` 和顶层的 `initial` 参数检查中拒绝非 `1/2/4` 宽度、
  `PHYS_REGS < 33`、非二幂 ROB/RS/LSQ 容量、地址/标签位宽不足和 Cache line 非 16 byte。
  报错必须指出参数名和取值；不能让截断后的地址静默运行。
- 最低命令入口为 `make doctor`、`make lint`、`make unit NAME=<id>`、
  `make run TEST=<case> CFG=<cfg>`、`make regression` 和 `make synth CFG=<cfg>`；每个目标
  有墙钟 timeout，并将 VCD/FST、日志和镜像放在 `build/<cfg>/<test>/`。
- **接口/状态/时序**：本项不产生 CPU 数据通路状态，只冻结编译宏、filelist、顶层名和
  时钟/复位极性。所有状态模块采用 `posedge clk`、同步高有效 `reset`；组合块必须有默认
  赋值，避免 latch/X。
- **测试/依赖/责任**：Icarus 用 `-g2005`、Verilator 用 Verilog-2005 lint 编译现有六个
  RTL 单元和一个空 `cpu_core` stub；`H-00` 无依赖，A/B 共同完成，未通过前不得开始跨模块
  集成。

#### H-01 冻结 packed bus 与握手契约（共同，A 写前端/Cache 字段，B 写后端字段）

- 每条流接口以 `valid/ready` 传输：只在时钟沿前 `valid && ready` 时转移一个 lane；
  `valid=1 && ready=0` 时，发送方必须保持该 lane 的全部 payload 和 tag 不变。多 lane
  bundle 只允许连续有效前缀，禁止 `lane 0` 无效而后续 lane 有效。
- `FetchPacket` 固定为 `pc[31:0]`、`inst[31:0]`、`pred_taken`、`pred_target[31:0]`、
  `pred_kind`、`btb_hit`、`epoch`；`DecodedInst` 增加 op、`rd/rs1/rs2`、立即数、源使用位、
  写回位、load/store `size/sign` 和 `byte_mask`。这些字段从 Fetch Queue 一直保留到 ROB。
- `Rename/IssuePacket` 固定携带完整 `rob_tag`、逻辑/物理 rd、两个源的
  `{ready,value}` 或 `{not_ready,producer_tag}`、PC、操作和内存/预测信息；不能只携带 ROB
  slot。`ExecResult`/`Completion` 固定携带 `rob_tag`、`phys_rd`、`wb_en`、value、地址、
  分支真实结果和异常位。
- `DCacheRequest` 固定携带 `valid, is_load, is_store, addr, size, sign, wdata, byte_mask,
  rob_tag, lsq_tag`；`DCacheResponse` 回传 `rob_tag, lsq_tag, rdata, error`。I-Cache 请求/响应
  额外携带 `pc, epoch`。主存只处理 16-byte 对齐 line：`mem_read/mem_write, line_addr,
  line_wdata[127:0], line_wmask[15:0], transaction_id`，响应原样带回 ID 和 error。
- `flush_valid` 携带“保留至”的完整 branch `rob_tag`、`redirect_pc` 和新 `epoch`；任何
  RS、LSQ、completion FIFO、MSHR 或响应只有在 tag/epoch 仍 live 时才可写状态。复位、
  HALT/error、flush、普通握手的优先级写入接口文档和断言，顶层不得临时改写。
- **内部状态/时序/测试/依赖**：本项状态仅为常量编码和 pack/unpack helper；在 `H-00` 后
  用 A/B 双方的 producer/consumer stub 做 backpressure、全 lane、tag 回绕和 flush 传输
  测试。完成物是 `docs/interfaces.md` 与可被所有 `.v` include 的单一 `rv32im_defs.vh`。

#### H-02 时序原语、队列和资源计数（共同，B 主责实现，A 复核）

- 实现并单测同步 FIFO、环形指针/occupancy 计数器、`valid+slot+generation` tag 比较器、
  ready/valid skid buffer、优先编码器和连续前缀分配器。ROB、RS、LSQ、Fetch Queue、
  completion FIFO、free list 只能复用这些经过测试的语义，不各自手写边界条件。
- 每个 FIFO 规定输入 `push_count/push_payload`、输出 `pop_count/pop_payload`、`free_count`
  与 `flush_tail`；同周期 pop/push 使用“旧状态计算可用空间、时钟沿同时更新”的规则，
  不允许 occupancy 下溢或超过容量。仲裁器只输出 grant，不直接删除未获 grant 的完成项。
- `flush` 在时钟沿后删除严格年轻项；如果同周期收到旧 epoch/load 的结果，tag 校验必须在
  写入前失败。同步 reset 后所有 valid、busy、ready scoreboard、队列计数和性能计数器为
  已知值，x0 对应的物理寄存器永远 ready 且为 0。
- **测试/依赖/责任**：枚举 empty/full、wrap、同周期 push/pop、1/2/4 lane、flush 与旧 tag
  响应相撞、无 ready 下的 payload 稳定性；`H-02` 依赖 `H-00/H-01`，是 ROB/RS/LSQ/Cache
  MSHR 的共同前置。

#### H-03 稀疏镜像加载器和双端口 50 周期主存（A 主责，B 复核）

- 在 `tb/models/` 实现非综合模型：解析 `@xxxxxxxx` 与十六进制 byte，按小端写入 1 MiB
  byte array，越界、未对齐 line、非法字符或缺少结束哨兵立即报错。它不依赖 C++ 模拟器的
  内存类，也不改写 `RISC-V-CPU-Simulator/testcases/`。
- I 与 D 各有独立请求槽和 `ready/valid`；请求在第 N 个上升沿被接受后，响应第一次允许
  在第 N+50 个上升沿前有效。请求期间 payload 被模型锁存，不能因为上游后续改变 wire 而
  改变事务。D 的 line write 在对应响应完成时才写入 byte array，读返回接受请求时的 line
  快照；这使 testbench 不会把“请求”误作“已提交的内存可见性”。
- 地址按 16-byte line 对齐，line 内 byte 以 `8*i +: 8` 映射；D 写使用 16 位 mask。I/D
  端口可以并行在途，模型记录各自 transaction ID，响应不能串到另一端。现阶段声明不支持
  自修改代码；若将来需要，必须增加 I/D Cache 一致性/失效协议，不能暗中依赖测试顺序。
- **测试/依赖/责任**：加载两个不连续段、端序、读写 mask、并行 I/D、精确 50 周期、地址
  错误和 `TEST-01` 的 18 个镜像 smoke；依赖 `H-00/H-01`，是 A-03/A-05 与 B-08 的共同
  可替换底座。

#### H-04 退休 trace、断言、watchdog 和回归驱动（共同，A 主责驱动，B 主责架构断言）

- `CommitRecord` 是唯一的架构比较出口，逐 lane 输出 `valid, pc, inst, rd, rd_we, value,
  is_store, store_addr, store_mask, store_data`；只记录真正提交的连续前缀，绝不记录 issue
  或 speculative writeback。回归首先比较返回值，再按 trace 的 PC/指令/寄存器写回对拍；
  C++ trace 只能由本仓库的只读外置 `reference_trace.cpp` 生成，不能修改参考仓库加入日志。
- 在 testbench/可选 `ifndef SYNTHESIS` 断言：P0/x0 恒零、ROB tag 必须 live 才能完成、
  store 在 commit 前未到 D-Cache、无效 lane 无副作用、flush 后年轻 tag 不再退休、I-Cache
  响应 epoch 匹配、请求数与响应数平衡。断言信息要包含 cycle、配置、测试名和 tag。
- watchdog 同时检查全局最大周期和连续无退休周期；长基准的上限通过 `tests/manifest` 按
  程序配置，不能以一个很小的全局常数限制 `pi`。失败自动保留首错 trace 窗口与 VCD/FST。
- **测试/依赖/责任**：先以人工 CommitRecord 验证检查器会拒绝错误值/错误顺序，再跑 18
  项期望表；依赖 `H-00` 到 `H-03`，是所有 A/B 单元接入顶层前的验收门。

#### S-01 公共定义与参数包（两人共同）

- 在 `rv32im_defs.vh` 统一定义 RV32I/M op/class、ALU/MEM 操作码、参数合法性、
  `PHYS_REG_ADDR_WIDTH`、`ROB_SLOT_WIDTH`、`ROB_TAG_WIDTH` 和 packed bus 宽度。
- ROB tag 至少包含 `valid/kind/slot/generation`；比较必须同时比较 slot 和 generation。
- 定义 `FetchPacket`、`DecodedInst`、`RenamePacket`、`IssuePacket`、`ExecResult`、
  `MemoryRequest/Response`、`CommitRecord` 的字段顺序，所有未使用 lane 的 valid 清零。
- 明确 flush、redirect、commit、writeback、store visibility 的同周期优先级。

**完成门**：所有单元只引用这一份定义；单元 testbench 可以用同一组 pack/unpack 任务。

#### S-02 程序镜像和主存模型（共同，A 主责脚本，B 复核）

- `tools/make_image.py` 保留 `source.o`、ELF、objdump 和稀疏 image；检查入口为 0、所有段
  落在 `[0, 1 MiB)`，并保留结束哨兵。`RISC-V-CPU-Simulator/testcases/*.data` 则作为外部
  只读输入直接解析，不能先“重新生成”而改变验收镜像。
- `tests/manifest` 固定 `TEST-01` 的测试名、期望返回值、推荐最大周期和是否为长回归；
  回归脚本以 manifest 逐项加载 `.data`，不能只跑一个代表程序后宣称全部通过。
- 主存模型的精确 I/D 两端口、50 周期、端序与 store 可见性以 `H-03` 为准；本项只负责
  镜像产物、hash、manifest 和对可重编译 RV32I/RV32IM 程序的统一入口。

#### S-05 统一回归入口和失败产物（共同，A 主责实现，B 主责检查条件）

- `make regression CFG=<cfg>` 必须依次运行 18 项外部镜像、累加、向量加和向量乘；短冒烟、
  全量回归与参数矩阵分为不同目标，避免开发时每次等待 `pi`，但发布门只接受全量通过。
- 每次运行保存配置、git revision、镜像 hash、期望/实际返回值、结束原因、周期数、退休数、
  I/D hit/miss 和 branch/mispredict；失败保留首个断言、最近 trace 和波形路径。
- 成功判据固定为 `halted=1 && error=0 && return_value==expected`，且 watchdog/timeout
  未触发；仿真器进程退出码、日志匹配和 manifest 条目数也必须纳入检查。

### 4.2 A 线：前端、预测和缓存/内存

#### A-01 RV32IM decoder（部分已有，A 主责）

- 审计 `rv32im_decoder.v` 对 R/I/S/B/U/J、load/store、M 扩展和非法编码的判断。
- 重点验证 B/S/J 立即数重排、I 型符号扩展、移位 `funct7`、JALR bit0 清零以及
  MUL/DIV 四类操作码；未知/保留编码必须给 `legal=0`，不能静默当 NOP。
- 按 lane 输出 `rd/rs1/rs2`、是否使用源、是否写 rd、立即数、内存宽度、load 符号属性、
  branch/jump/serialize 类别。`LB/LBU/LW/SB/SW` 必须分别产生正确的 `size/sign/byte_mask`；
  `LH/LHU/SH` 先保留编码位置和显式 `legal` 策略，不能与 byte/word 编码混淆。
- CSR/FENCE 在本项目首轮返回不支持/非法状态；如果后续测试明确要求，再单独扩展。

**测试**：逐类定向向量 + 随机 raw instruction + 与 C++ `dec::decode` 对拍；另对每一种
byte/word load/store 检查地址低位、mask、符号扩展和非法 `funct3`。

#### A-02 分支预测器和 BTB（A 主责）

- 64 项 2-bit Bimodal 表，按 `PC >> 2` 索引，初始为弱 taken 或按测试契约统一初始化。
- 16 项直接映射 BTB，记录 conditional branch/JALR 的 `valid/tag/target/kind`；JAL 的立即数
  目标直接计算并预测 taken。conditional branch 只有 Bimodal 预测 taken 且 BTB tag 命中时
  才预测跳转，BTB miss 保守预测 not-taken，避免拿到错误目标。
- 预测输出携带 `taken、target、prediction metadata`；ROB 保存快照，branch 执行计算真实
  taken/target，提交时更新计数器和命中统计。
- redirect 时增加 frontend epoch；旧 epoch 的 I-Cache 响应不得重新写入 Fetch Queue。

**接口/状态/时序/恢复**：输入是 Fetch PC 和提交的真实 branch feedback，输出是当周期的
prediction metadata；内部状态只有 BHT/BTB/统计计数器。BHT/BTB 在 branch 提交沿更新，
flush 不回滚它们，因为错误路径 branch 不能提交；epoch 属于前端流而不是预测表内容。

**测试**：全 taken、全 not-taken、交替、alias、BTB miss/hit、JAL/JALR 和错误恢复。

#### A-03 I-Cache（A 主责，独立设计）

- 1 KiB、直接映射、16-byte line；每项保存 valid、tag 和 128-bit data。
- 命中流水分为 request/tag-read、compare、response 三个寄存阶段：命中延迟严格 3 周期，
  流水线充满后每周期可接受一个无冲突请求。
- miss 使用一个 MSHR 保存 line 地址、请求 PC、epoch 和 refill 状态；主存固定 50 周期返回，
  refill 完成后再向 Fetch Queue 产生响应。
- 处理跨 line 的 FE bundle：在第一条预测控制流处截断，line 尾部不足的指令等待下一 line。
- redirect/flush 只杀死旧 epoch 的响应，不误删已经提交的指令流。

**接口/状态/时序/恢复**：输入为 `if_req_valid, pc, epoch` 与主存 line 响应，输出为
`if_req_ready` 和带原 PC/epoch 的 FetchPacket。状态为每 line 的 valid/tag/data、三级命中
流水寄存器和一个 MSHR；请求在上升沿 N 接受时，hit 响应最早在 N+3 交付。flush 不丢弃可能
服务正确路径的 refill，但使 MSHR/流水中 epoch 不符的响应无效；MSHR 满时只反压新 miss，
不凭组合读绕开三级流水。

**测试**：连续命中吞吐、首访问 miss、同 set 冲突、line 边界、backpressure、redirect 后
旧响应和多个 `FE_WIDTH` 配置。

#### A-04 Fetch PC、Fetch Queue 和前端控制（A 主责）

- PC 从 0 开始；每次从 I-Cache 接受最多 `FE_WIDTH` 条连续 32-bit 指令。
- Fetch Queue 保存 raw instruction、PC、预测 taken/target 和 epoch，按序出队；后端资源
  不足时通过 ready 反压，不能丢弃 bundle 中间 lane。
- 第一个预测 taken 的 branch/JAL/JALR 截断当前 bundle；预测 not-taken 则顺序取 `PC+4`。
- 将 redirect、flush、HALT/error freeze 和普通 PC+4 更新集中在一个前端控制器，固定优先级。
- Decode/Rename 只接受连续有效前缀；同 bundle 内后一 lane 可以看到前一 lane 新产生的 RAT 映射。

**接口/状态/时序/恢复**：输入是 I-Cache response、后端 `fetch_ready`、`redirect_pc/epoch`
和 stop/error；输出是 I-Cache request 和连续前缀 FetchPacket。状态仅为当前 PC、Fetch Queue
和 epoch；每次时钟沿按 `HALT/error freeze > redirect > response prediction > 顺序 PC` 的
优先级更新。flush 清空旧 epoch FQ 项且不改变已提交架构状态；依赖 H-01、A-02、A-03。

**测试**：FE_WIDTH=1/2/4、预测跳转截断、跨 line、队列 full/empty、后端 backpressure 和
redirect 后无 stale issue。

#### A-05 D-Cache（A 主责，独立设计）

- 4 KiB、直接映射、16-byte line，维护 valid/tag/dirty/data；采用 write-back + write-allocate。
- load 命中走三周期流水；store 只有 ROB/LSQ 提交后才到达 D-Cache，写命中支持 byte enable。
- miss 只允许一个 MSHR：脏 victim 先按完整 line 写回主存，再以 50 周期 refill；未命中读到
  line 后才向 LSQ 返回目标 word。
- 首版即支持 `LB/LBU/LW/SB/SW`：load 在 Cache 返回 32-bit 对齐 word 后按地址低位选取
  byte 并完成零/符号扩展；store 按 `byte_mask` 合并 line 内字节。`LH/LHU/SH` 复用同一
  对齐、mask 和 extraction 路径，留作 `TEST-02` 后续兼容项。
- D-Cache 请求携带 ROB/LSQ tag，flush 时取消未提交 load 的响应；store 不可在提交前写 cache。

**接口/状态/时序/恢复**：输入是 B-08 的请求和 H-03 的 line 响应，输出是同 tag 的 load
response 或 store acknowledge；状态为 data/tag/valid/dirty 阵列、三级命中流水和一个
MSHR/writeback 状态机。请求在 N 接受后的 hit response/ack 最早在 N+3 交付；miss 先完成
可能的 50-cycle writeback，再发起 50-cycle refill。flush 只丢弃未提交 load 的等待结果，
不撤销已由 ROB commit 发出的 store，也不以 flush 清空 dirty line。

**测试**：三周期连续 hit、read miss、write allocate、dirty eviction、同 set 冲突、byte
enable、`LB/LBU` 符号差异、`SB` 与同 word `LW` 合并、主存延迟、flush 和随机
cache/memory 一致性。

#### A-06 主存桥和 Cache 统计（A 主责）

- 为 I/D Cache 分别提供 ready/valid line 端口，不把主存瞬时数组读直接暴露给 CPU。
- 统计 I/D request、hit、miss、refill、writeback 和 stall；计数器只在定义的握手点增加。
- 主存 bridge 处理 line 地址、128-bit data、16-bit byte enable 和响应 epoch/tag；异常地址
  返回 error，不产生 X 或死锁。

**接口/状态/时序/恢复**：桥输入为各 Cache 的 line read/write 请求，输出为 `ready` 和
原 transaction ID 的 line response；仲裁状态记录被接受而尚未响应的 I/D 事务，不能改变
payload。Cache 统计在 CPU/Cache 握手沿加一，主存统计在 bridge/主存握手沿加一；flush 仅
影响携带的 I epoch/D live tag，已接受的 line 事务仍必须被正确消耗或标记丢弃。

#### A-07 前端、I/D Cache 联合门（A 主责）

- 使用 `H-03` 的真实 50 周期模型把 A-01 至 A-06 连接到 stub：前端 stub 按需消费
  FetchPacket，LSQ stub 产生读/写/flush 请求。此门验证的是硬件握手和时序，不等待真实
  rename/ROB 才暴露 Cache bug。
- 记录每个请求的接受周期、三周期 hit 响应、miss/refill/writeback 周期、epoch/tag 和
  line 地址；同一请求不得产生两次响应，flush 后旧 I 响应不得进入 Fetch Queue，D load
  响应必须原样返回给发起 LSQ tag。
- **依赖/测试/责任**：依赖 `H-00` 到 `H-04` 与 A-01 至 A-06；跑 18 个镜像的取指 smoke、
  缓存冲突随机测试、I/D 并发和 backpressure。本项的成功是 A 线对 S-03 的交付门。

### 4.3 B 线：重命名、乱序后端和执行

#### B-01 物理寄存器文件（已有，B 主责审计）

- 保留 `rv32_physical_register_file.v` 的参数化方向：`2*BE_WIDTH` 读端口、`BE_WIDTH`
  写端口、同周期写回旁路、x0 固定为零。
- 检查 `PHYS_REGS` 非 2 的幂时地址边界、非法参数和多写同地址的优先级；读到 reset 中的
  无效物理寄存器必须给确定值。
- PRF 只保存数据和 ready；生产者关系由 RAT/tag 保存，不让 PRF 充当 ROB。

**接口/状态/时序/恢复**：输入为 `2*BE_WIDTH` 个物理源号和最多 `BE_WIDTH` 个 CDB 写回，
输出为源 `{value,ready}`。状态为 `PHYS_REGS` 份 value/ready；读可组合产生，但同周期 CDB
写必须显式旁路，所有写在时钟沿生效。flush 不回滚已写 PRF 值，RAT/ROB tag 决定哪些值可达；
reset 只保证 P0 ready/value=0，其余 ready=0。

**测试**：1/2/4 路读写、同周期 RAW bypass、x0、写端口冲突、参数矩阵和 reset。

#### B-02 RAT、RRAT、free list 和 rename（已有，B 主责审计/补全）

- `RAT` 是推测映射，`RRAT` 是已提交映射；free list 提供非零物理寄存器，phys-ready
  scoreboard 表示值是否可读。
- rename bundle 按程序顺序处理：同一 bundle 的后 lane 必须看到前 lane 的新映射，处理
  lane 内 RAW/WAW；资源不足时只接受连续前缀。
- 每个写 rd 的 ROB entry 保存 `old_phys/new_phys`；提交释放 old phys，squash 释放年轻
  new phys 并恢复 RAT。x0 永远固定到 P0。
- 现有 `rv32_rename_unit.v` 先与 PRF/ROB 端口逐项核对，不能只因单元 testbench 通过就
  假设可以处理多周期 recovery。

**接口/状态/时序/恢复**：输入为连续 DecodedInst 前缀、ROB/RS/LSQ free count、commit
release 和 `B-03` checkpoint restore；输出是连续 RenamePacket 与各资源分配请求。状态为
32 项 RAT、32 项 RRAT、free-list 环和临时 bundle RAT。rename 在一个组合选择阶段只接受
资源足够的最长前缀、在 N 沿写入推测 RAT/free-list；commit 在 N 沿更新 RRAT 并释放
old phys；mispredict 由 checkpoint 在单一沿恢复，期间 input ready=0，避免半个 bundle
写入。

**测试**：free list 满/空、物理寄存器回绕、同 bundle 依赖、WAW、commit release、branch
rollback、不同 PHYS_REGS 和 BE_WIDTH。

#### B-03 ROB（B 主责，新建）

- 环形 ROB 保存 PC、raw、decoded op、逻辑 rd、old/new phys、ready、结果、地址、branch
  prediction、LSQ slot、HALT/error 标志。
- 每周期最多分配/完成/提交 `BE_WIDTH` 条；提交只看 head 连续 ready 项，store 和 branch
  的可见效果在提交点产生。store 的“地址/数据 ready”与“已完成提交写”分开：它成为 head
  后向 LSQ 发一次 commit 许可，等 D-Cache ack 才 pop，不能把尚未写入 Cache 的 store 越过。
- slot 复用时 generation 非零递增，完成、CDB、LSQ 和 flush 均比较完整 tag；旧响应不能写
  新一代 entry。
- 每个可能 redirect 的 branch/JALR 在 rename 后保存 checkpoint：至少含 RAT 映射、free-list
  分配指针、RS/LSQ 分配尾指针和 branch 后的 ROB tail。mispredict 在执行期到达时恢复该
  checkpoint、将 ROB tail 截到 branch 后、清空严格年轻的 RS/LSQ/completion 项并发出
  `redirect_pc/new_epoch`；checkpoint 可以是完整快照或等价的可验证 undo log，但不能依赖
  “等到提交后慢慢重建”。
- 同周期有多个已解析且 live 的 recovery request 时，完成网络只接受其中最老的 branch；
  一个尚未解析的更老 branch 不阻止年轻 branch 的先行 redirect，但若它随后 mispredict，
  会以自己的 checkpoint 覆盖年轻路径。被更老 flush 覆盖的结果因 tag/epoch 不 live 而丢弃。
  branch 仍按程序顺序提交，届时才训练预测器并释放 checkpoint。
- HALT 编码只在 head 提交时置 `halted` 并捕获 `a0[7:0]`；非法/越界/非对齐 error 也只在
  精确提交点对外可见。

**接口/状态/时序/恢复**：输入为 rename allocation、B-07 completion、store-ack、branch
recovery request 和 commit sideband；输出为资源分配 tag、连续 CommitRecord、store-commit
许可、checkpoint restore 和 HALT/error。状态为 head/tail/generation、entry payload/ready、
branch checkpoint 与未完成 store 标志。N 周期只从旧 head 选择最多 `BE_WIDTH` 条连续 ready
项，N 沿更新 head/RRAT/free-list release；branch recovery 和精确停机优先级遵循 ARCH-02，
所有写入都先校验完整 tag。

**测试**：多分配/多提交、head/tail 同周期、回绕、generation stale completion、store
顺序、branch flush、HALT 和所有宽度组合。

#### B-04 保留站和 issue 选择（B 主责，新建）

- 分离整数/分支、MUL、DIV 保留站；每项保存操作、PC、ROB tag、两个 value/tag、store
  data 和目标物理寄存器。
- CDB/PRF writeback 唤醒完整匹配的 tag；只有两个源 ready 且目标 ROB tag live 才能选择。
- 每个执行端口采用固定 oldest/lowest-slot 优先级；每周期最多接受 BE_WIDTH 条，受 ALU、
  MUL、DIV、LSU 端口和完成缓冲 backpressure 限制。
- 未获得完成网络许可的指令保持在 RS；被 flush 的项立即清除，不能再次发射。

**接口/状态/时序/恢复**：输入为 RenamePacket、CDB wakeup、执行端口 ready 和 flush，输出
为每类单元的 IssuePacket；状态为 entry valid、操作、两源 value/tag/ready 和 ROB tag。
CDB 在 N 沿写醒 entry，初版从 N+1 开始可被选择，保持 H-02 的旧状态模型；如后续加入
same-cycle wakeup-to-issue bypass，必须仍满足相同选择优先级和波形断言。issue 只有在执行端
口和 completion 容量均保证可接收时才移除 entry；flush 在同一更新点清除严格年轻项。

**测试**：RAW/WAR/WAW、同周期 wakeup、RS full、选择公平性、多 issue、backpressure 和
generation 唤醒。

#### B-05 整数 ALU、分支和 AGU（已有 ALU 接口，B 主责集成）

- 复用/审计 `rv32i_alu.v` 的 ADD/SUB/AND/OR/XOR/SLL/SRL/SRA/SLT/SLTU、立即数、LUI、
  AUIPC；移位量只取低 5 位。
- 分支比较输出 `taken` 和 `target`；JAL 产生 `PC+4` 和立即数目标，JALR 目标为
  `(rs1 + imm) & ~1`。
- load/store 只在 ALU/AGU 产生地址，不直接访问 Cache；LSQ 接收地址和 store data。
- 结果带 ROB tag、是否写 rd、是否 branch、是否 memory op 和 redirect 信息，交给完成网络。

**接口/状态/时序/恢复**：输入为 INT RS 的 IssuePacket，输出为带同一 `rob_tag` 的
ExecResult；ALU/AGU 采用一拍寄存执行，N 接受、N+1 产生 completion candidate，branch
mispredict 也在该时点请求 checkpoint recovery。它不保存推测架构状态；flush 后仍到达的
candidate 必须先经 live-tag 检查，不能写 PRF/ROB。

**测试**：立即数/符号、边界移位、signed/unsigned 比较、JAL/JALR bit0、分支目标和地址
溢出回绕。

#### B-06 三周期流水乘法器和迭代除法器（已有，B 主责集成）

- `rv32m_multiplier.v`：保留 radix-4 Booth、Wallace/CSA、最终加法三级寄存；支持
  MUL/MULH/MULHSU/MULHU，ready/valid 回压和 flush 清空所有年轻请求。
- `rv32m_divider.v`：保留 32 步恢复除法；覆盖 DIV/DIVU/REM/REMU、除零、最小负数除
  `-1`、符号组合，响应期间 request ready 为低。
- MDU 保留站按 tag 等待响应；完成端不能直接写 PRF/ROB，必须经过统一 completion bus。
- 优先验证现有单元自身，再接入多 issue，避免把算法错误和后端时序错误混在一起。

**接口/状态/时序/恢复**：MUL 在 N 接受后经过 Booth/部分和、Wallace/CSA、最终加法三段
寄存，最早在 N+3 给出可回压的结果；DIV 只接受一个请求，保存被除数/除数、商/余数、步数
和原 tag，特殊值同样走受控完成路径。二者的响应 valid 必须保持到 B-07 接受；flush 通过
tag/epoch 杀死年轻流水项或抑制响应，不能改变更老运算。

**测试**：随机 32 位模型比对、零/最大最小值、连续 MUL 吞吐、DIV 回压、flush 中止和
ROB tag 保持。

#### B-07 Completion/CDB/Writeback 网络（B 主责，新建）

- 汇集整数 ALU、MUL、DIV、load response 和 branch result；每个完成项保留 ROB tag、
  物理 rd、value、address、branch metadata。
- 每周期最多输出 BE_WIDTH 个 writeback lane；若来源多于 lane，使用确定优先级和完成 FIFO，
  不能覆盖未发送结果。
- writeback 同时更新 PRF ready/value、ROB ready/value 和 RS/LSQ wakeup；store 完成只更新
  ROB/LSQ 状态，不错误占用寄存器写口。
- flush 优先清除所有年轻完成缓冲；完整 tag 检查避免旧 load/MUL/DIV response 写新 ROB。

**接口/状态/时序/恢复**：输入为 ALU、branch、MUL、DIV、LSQ 的 completion producer，
输出为固定 `BE_WIDTH` 条 CDB、PRF 写口、ROB ready 写口和 wakeup。状态为每个 producer 的
ready/valid 保持寄存器与 completion FIFO；N 周期仲裁的是旧缓冲内容，获 grant 的项在 N 沿
写入，未获 grant 保持。flush 优先移除严格年轻结果，branch recovery/ROB tag 检查在 grant
前执行；CDB 不承担 store 的内存可见性。

**测试**：ALU/Load/MDU 同周期冲突、多写端口、CDB backpressure、flush、stale tag 和连续
多路完成。

#### B-08 LSQ 和访存顺序（B 主责，新建）

- load/store 按程序顺序分配 LSQ，保存 ROB tag、地址 ready、store data ready、宽度、请求
  pending、响应完成和 byte mask；访问宽度来自 `TEST-02` 的 `LB/LBU/LW/SB/SW`，而非默认
  把所有请求当作 word。
- load 不能越过地址未知的更老 store。地址已知时，从最近的更老 store 向前扫描目标 byte：
  data ready 的重叠字节覆盖缓存返回对应 byte；重叠但 data 未 ready 的 store 阻塞；所有
  目标 byte 均被覆盖时直接完成转发，否则把未覆盖 byte 与 D-Cache 返回 word 合并后再按
  `size/sign` 产生 load 值。该规则同时覆盖 `SB -> LB/LBU/LW` 和 `SW -> LB/LBU`，不能只
  对齐 word 转发。
- load 请求进入 D-Cache 后等待三周期 hit 或 miss/refill；在主存响应前不能直接读取数组。
- store 地址/数据可以提前计算；其 operand-ready 写入 ROB/LSQ 后，只有 ROB head 和
  LSQ head 同时允许时才向 D-Cache 发写。ROB 维持该 head 的 `store_commit_pending`，收到
  D-Cache store-ack 后才完成该条退休；Cache 的 write-back 到主存不阻塞此 ack。
- mispredict 时截断 tail、取消年轻 pending request；旧 response 按 ROB generation 丢弃。

**接口/状态/时序/恢复**：输入为 rename 的 LSQ allocation、AGU 地址/store data、CDB
wakeup、ROB store-commit 许可和 D-Cache response；输出为 DCacheRequest、load completion
与 store-ack。状态为程序顺序 entry、head/tail、地址/数据 ready、请求 tag、byte forwarding
mask 和等待 response 标志。一个 load 只能在所有更老未知地址消除后离开 LSQ；flush 在 N 沿
截断年轻 entry，并让其已在途响应因完整 tag 不 live 而被丢弃，已获 commit 的 store 不回滚。

**测试**：`SB -> LB/LBU/LW`、`SW -> LB/LBU`、多 store 最近值覆盖、未知/未就绪旧 store
阻塞、不同地址并行、store 顺序、Cache hit/miss、主存 50 周期、flush 和 LSQ full。

#### B-09 后端联合门（B 主责）

- 在不接真实前端的条件下，把 PRF、rename、ROB、RS、ALU/MDU、completion 与 LSQ 串成
  单发射闭环；输入使用 `DecodedInst` trace，D-Cache 使用 `G-INT-02` 的标准 responder，
  绝不另建一个字段不同的“后端专用内存”。
- 输出必须是 `CommitRecord` 而非内部 PRF snapshot。定向程序覆盖同 bundle 之前先用
  `BE_WIDTH=1` 验证 RAW/WAR/WAW、长延迟 DIV、MUL 与 load 同周期完成、checkpoint 恢复、
  字节转发及 store 精确提交；随后只替换为 2/4 lane 输入，不改变协议。
- **依赖/测试/责任**：依赖 `H-00` 至 `H-04`、B-01 至 B-08 与 `G-INT-02`；生成
  `docs/rename.md`、`docs/rob.md`、`docs/rs.md`、`docs/lsq.md`、`docs/writeback.md` 的
  一致版本，是 B 线向 S-03 交付的门。

### 4.4 S 线：顶层和横向控制

#### S-03 `cpu_core` 顶层连接（共同，B 负责后端接线，A 负责 Cache 接线）

- 连接 Fetch/Decode/Rename/ROB/RS/LSQ/执行单元/Completion/Cache/主存端口。
- 明确资源不足的反压链：Cache -> Fetch Queue -> rename -> ROB/RS/LSQ -> execution ->
  completion；只接受连续 valid 前缀。
- 将 reset、flush、redirect、HALT、error、cycle/instret 和退休 trace 接到单一控制点。
- 顶层不能重新实现模块内部状态；只负责 wire 汇合、仲裁和优先级。

#### S-04 分支恢复和精确停止（共同）

- 执行期的 mispredict 由 `B-03` checkpoint 立即触发 redirect；本周期停止接收新的
  Fetch/rename/dispatch，下一周期以新 epoch 从 `redirect_pc` 取指。commit head 只判断
  error/HALT、顺序寄存器提交、store 可见性和预测器训练，不能二次发起 branch redirect。
- recovery 期间清除 Fetch Queue、decode/rename/dispatch 的旧 epoch 项；执行单元和 Cache
  只保留能被当前 live tag 验证的响应。HALT/error 的精确提交优先于同周期的普通退休，
  但不得错误地取消一个更老 branch 的恢复请求。
- retirement trace 是唯一架构观察点；用于和 C++ reference 每条已提交指令后的 PRF/RRAT
  状态对拍。

## 5. 两人并行分工和依赖

### PAR-00 并行边界和冻结接口

两人可并行，但必须按下列交接门冻结接口，避免 A 的 Cache 改动 B 的 LSQ 假设，或 B 的
恢复逻辑绕过 A 的 epoch。每个门先用双方 stub 通过，再接入真实模块；接口字段变更必须
同步修改 `docs/interfaces.md`、pack/unpack testbench 和两侧测试，不能只改一侧 RTL。

| 交接门 | 接口所有者 | 冻结内容 | 合格证据 |
| --- | --- | --- | --- |
| `G-INT-01` | 共同（H-01/S-01） | lane 前缀、完整 ROB tag、flush 优先级、同步 reset | A/B producer-consumer stub 在 1/2/4 lane、backpressure、flush 下通过。 |
| `G-INT-02` | A 提供服务，B 定义请求 | `DCacheRequest/Response`、16-byte line 主存、3-cycle hit、50-cycle miss、字节 mask | B 的合成 LSQ 请求能驱动 A 的 D-Cache，tag、数据、错误和响应周期逐项对上。 |
| `G-INT-03` | B 产生，A 消费 | `redirect_pc/epoch`、branch metadata、I-Cache 旧响应丢弃 | 对同一 miss 注入 redirect，Fetch Queue 中只有新 epoch 指令。 |
| `G-INT-04` | B 产生，A 驱动测试 | `CommitRecord`、HALT/error、性能计数 | 人工 trace 能被 H-04 拒绝/接受；整机可判定 `TEST-01` 返回值。 |

### PAR-01 共同先行任务（不能跳过）

| ID | 共同产物 | 完成条件 |
| --- | --- | --- |
| H-00 | filelist、Makefile、默认参数和 elaboration 检查 | 现有 RTL + 空顶层在 Icarus/Verilator 均可编译 |
| H-01 / S-01 | 公共参数、tag、packed wire、flush 优先级 | `G-INT-01` 通过并生成接口文档 |
| H-02 | FIFO/tag/skid/连续前缀等时序原语 | wrap、flush、1/2/4 lane 单测全通过 |
| H-03 / S-02 | 镜像格式、双端口 50-cycle 主存、manifest | 最小 C 程序和一份真实 `.data` 可加载并精确响应 |
| H-04 / S-05 | trace、断言、watchdog、日志和回归入口 | 检查器能故意拒绝错误 trace，`make doctor/lint` 可运行 |

完成 `G-INT-01` 后两人可以使用相同端口协议并行开发；完成 `G-INT-02` 前不允许把真实
LSQ 直连 D-Cache。每个单元都先有独立 testbench，不要等顶层完成才开始验证。

### PAR-02 人员 A：前端、预测、Cache 和主存

| ID | 工作范围 | 可独立使用的 B 线 stub |
| --- | --- | --- |
| A-01 | decoder 审计、立即数和非法编码 | 固定 `rename_ready=1` 的 dispatch sink |
| A-02 | Bimodal + BTB、预测 metadata | 固定 branch feedback 的提交 stub |
| A-03 | I-Cache 三周期命中、MSHR、epoch | 假设 I-Cache response 的 Fetch Queue |
| A-04 | PC、Fetch Queue、bundle 截断和 redirect | 假设后端可接收任意连续前缀 |
| A-05 | D-Cache、主存桥、line refill/writeback | 合成 LSQ memory request 发生器 |
| A-06 | 镜像工具、I/D 主存 testbench 和 Cache 统计 | 使用 B 线定义的 MemoryRequest |
| A-07 | 前端/Cache 联合测试与 `docs/fetch/icache/dcache` | S-03 顶层之前完成单元门 |

A 线的集成出口是：能从 PC=0 连续取指、预测 redirect、正确返回三周期 Cache hit，
并能接受 B 线格式的 load/store 请求但不依赖真实 ROB。

### PAR-03 人员 B：重命名、Tomasulo 后端和执行

| ID | 工作范围 | 可独立使用的 A 线 stub |
| --- | --- | --- |
| B-01 | PRF 多端口、旁路和 ready scoreboard | 预设的 renamed issue bundle |
| B-02 | RAT/RRAT/free list、同 bundle rename 和 rollback | 预设 decoded bundle 与 ROB allocation stub |
| B-03 | ROB、generation tag、checkpoint、commit、HALT/recovery | 假设 branch/exec result 已按 tag 返回 |
| B-04 | INT/MUL/DIV RS 和 oldest-ready issue | 人工注入 CDB/PRF wakeup |
| B-05 | ALU/branch/AGU 接线 | 人工注入操作数、PC 与预测 metadata |
| B-06 | MUL/DIV 与 MDU RS 的 ready/valid/flush | 现有单元 testbench 和随机向量 |
| B-07 | Completion/CDB/writeback 多 lane 仲裁 | 人工注入 ALU/Load/MDU 完成组合 |
| B-08 | LSQ、字节转发、D-Cache 请求协议 | `G-INT-02` 的合成 Cache/50-cycle memory responder |
| B-09 | 后端联合测试、`docs/rename/rob/rs/lsq/writeback` | H-01 tag/wire 契约与 A 的 Cache stub |

B 线的集成出口是：用人工产生的 issue/完成 wire，完成 RAW/WAR/WAW、ROB 回绕、旧 tag
丢弃、执行期 branch squash、字节级 load forwarding 和按序 store commit；随后以
`G-INT-02` 的真实 Cache 响应替换 responder，接口字段不变。

### PAR-04 合并阶段

1. **JOIN-01：单发射闭环**。固定 `FE_WIDTH=BE_WIDTH=1`、`PHYS_REGS=64`、
   `ROB_ENTRIES=32`，连接 A/B 的真实模块，先跑定向算术、branch、`LB/LBU/LW/SB/SW`、
   字节转发、Cache hit/miss、50-cycle miss 和 HALT。
2. **JOIN-02：实际 18 项镜像回归与对拍**。运行
   `RISC-V-CPU-Simulator/testcases` 的全部 `.data`，按 `TEST-01` 检查返回值；逐条比较
   C++ reference 的退休 PC、寄存器写回和 store 记录，不比较周期数，也不先做性能优化。
3. **JOIN-03：RV32IM 验收程序**。加入 0 到 100 累加、向量加、向量乘，检查 dump 中
   确实出现 MUL/DIV/REM 等 M 指令并正确退休；向量乘不能因链接到软件 `__mulsi3` 而误判
   为硬件 MUL 测试。
4. **JOIN-04：开启双发射**。修复 bundle 内依赖、free list 多分配、完成冲突、ROB 多提交
   和 LSQ 同周期 pop/push。
5. **JOIN-05：开启四发射与参数矩阵**。验证 FE/BE 独立组合和不同 PHYS_REGS/ROB 配置。
6. **JOIN-06：综合、性能和面积**。所有功能回归通过后再运行 Yosys/ASAP7，生成 Pareto
   和 performance/area 报告。

## 6. 里程碑、测试门和交付顺序

### MILE-01 环境和公共协议

负责人：共同。完成 `ENV-*`、`S-01/S-02/S-05`，建立 `make doctor`、`make lint`、镜像
生成和主存模型。门槛是 `H-00` 至 `H-04`、`G-INT-01` 均已通过，decoder/ALU/PRF/rename
现有单元可以被统一 Makefile 编译，且任意错误 trace 会被 H-04 检查器拒绝。

### MILE-02 两条单元线并行

- A 完成 `A-01` 到 `A-07` 的单元测试和中文 docs。
- B 完成 `B-01` 到 `B-09` 的单元测试和中文 docs。
- `G-INT-02/G-INT-03/G-INT-04` 分别以 Cache/LSQ stub、redirect miss、人工 CommitRecord
  通过；此时才允许 `S-03` 顶层连接。
- 每个单元满足：reset 后无 X；参数非法时明确失败；有 timeout；有波形或错误定位信息。

### MILE-03 单发射整机

共同完成 `S-03/S-04` 和 `JOIN-01`。验收内容：

- 所有 RV32I 基础算术、分支、JAL/JALR、`LB/LBU/LW/SB/SW`；
- M 扩展四乘四除；
- Cache 命中/未命中、50 周期主存和 load/store 顺序；
- 预测错误恢复、HALT、x0 恒为 0、store 不早于提交；
- C++ reference 逐条退休对拍。

### MILE-04 程序回归

共同完成 `JOIN-02/JOIN-03`。`TEST-01` 的 18 个返回值必须全部通过，不能只报告汇总；
三个自行编译程序必须保留 C 源、`.o`、ELF、objdump、image 和对应 M 指令证据。每个程序
保存镜像、编译参数、周期数、返回值、预测率、I/D hit/miss、首个差异退休记录和波形命令。
任何超时都先定位无退休进度，不调大上限掩盖死锁。

### MILE-05 宽度和容量扩展

共同完成 `JOIN-04/JOIN-05`，最小矩阵为：

```text
FE_WIDTH x BE_WIDTH = {1,2,4} x {1,2,4}
PHYS_REGS             = {48,64,96}
ROB_ENTRIES           = {16,32,64}
```

先做 elaboration/lint，再对代表配置跑完整回归，最后对所有合法配置跑短程序和压力测试。

### MILE-06 面积和性能

共同完成 `JOIN-06`：以 `FE=1, BE=1, PHYS_REGS=64, ROB=32` 为基线，报告每个配置的
cycles/IPC、branch accuracy、Cache hit rate、stall、综合面积、ABC delay、面积倍数和
speedup。按照任务要求检查面积约翻倍时性能是否至少达到 1.3 倍，不在功能未通过前做
针对单个测试点的优化。

## 7. 重点风险和处理策略

### RISK-01 多发射同 bundle 依赖

原因：后 lane 不能只读取周期开始的 RAT。处理：rename 先按 lane 顺序生成工作映射，
每次写 rd 立即更新临时 RAT，所有源查询使用临时映射；单独覆盖 RAW/WAW 和资源不足时
连续前缀。

### RISK-02 ROB slot 回绕后的旧响应

原因：只比较 slot 会把旧 load/MUL/DIV 结果写进新指令。处理：tag 带 generation，ROB、
RS、LSQ、完成 FIFO、Cache MSHR 和 redirect epoch 都做完整校验。

### RISK-03 Cache 延迟和错误路径

原因：预测错误后旧 I-Cache response 或年轻 load response 仍可能返回。处理：I 请求带 epoch，
D 请求带 ROB generation；flush 时取消/标记无效，响应只对 live tag 生效。

### RISK-04 Store 提前可见

原因：LSQ 地址和值很早 ready，若直接写 D-Cache 会破坏精确提交。处理：store 仅在 ROB head
和 LSQ head 同时满足时发起写请求，D-Cache 写入并 acknowledge 后再退休 ROB entry；脏 line
以后写回主存不改变这一提交点。

### RISK-05 多来源完成覆盖

原因：ALU、load、MUL、DIV 可能同周期完成，简单 wire 会丢结果。处理：completion FIFO +
确定仲裁 + 每个 lane 独立 valid；未获 grant 的结果保持到下一周期。

### RISK-06 Reference 和目标 CPU 语义错位

原因：C++ 模型是单发射、无 Cache、固定三周期访存，而目标是多发射、三周期 Cache hit、
50 周期主存。处理：用 reference 对拍架构退休结果，不比较周期数；周期和性能只在目标
CPU 的独立 testbench 中统计。

### RISK-07 任务描述和参考测试的边界不一致

根指令说明排除 CSR/FENCE、弱化 LB/LH，但 `TEST-01` 的真实可执行镜像已使用
`LB/LBU/SB`。处理：把 `LB/LBU/LW/SB/SW` 定为第一阶段硬门；CSR/FENCE/浮点不因
`.dump` 的 `.comment` 或调试段出现而纳入执行范围；`LH/LHU/SH` 使用既有 size/mask
接口在完整回归后补齐。这样既不会因旧说明遗漏字节访存，也不会扩大到无证据的 ISA。

### RISK-08 长程序、Cache miss 与不当 timeout

原因：`pi`、`qsort`、`tak` 本身循环/递归量大，目标机又规定 50 周期主存；以 C++ 无 Cache
模型的周期数或一个小型 smoke timeout 作为上限都会产生误判。处理：`tests/manifest` 为
每个 case 配置独立上限，且只用无退休 watchdog 判定无进展；性能比较在所有程序正确结束后
用同一配置、同一镜像、同一计数口径进行。

### RISK-09 “M 扩展已测试”的假阳性

原因：现有 `.data` 来自 RV32I 风格编译，乘除常落入 `__mulsi3/__divsi3/__modsi3` 软件例程，
即使 18 项通过也不能证明 Booth-Wallace 或 divider 被执行。处理：`JOIN-03` 的三个程序以
`-march=rv32im` 编译，并在 objdump/trace 中断言至少覆盖 MUL、DIV、REM；MULH/MULHSU/MULHU
和 DIVU/REMU 用单元随机向量与专门微程序覆盖。

## 8. 每个提交必须留下的证据

每个单元完成时同时提交 RTL、testbench、中文 `docs`、执行命令和结果摘要。整机阶段必须
保存：

- `make doctor/lint/unit/smoke/regression/matrix/synth/report` 的日志；
- 编译器参数、`.o`、ELF、objdump 和最终 image 的哈希；
- 退休 trace、周期数、返回值、预测/Cache 统计；
- 失败 case 的参数、随机 seed、首个错误 cycle 和 VCD/FST 波形路径；
- Yosys/ASAP7 的库版本、约束、面积和延迟报告。

最终目标不是先做出一个能跑的单发射核，而是先用 `JOIN-01` 建立正确的 Tomasulo 闭环，
再以相同的 tag、状态更新和测试契约扩展到 2/4 路，最后用面积/性能矩阵验证参数化确实
带来可解释的收益。
