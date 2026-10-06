# MinorCPU 项目导读

## 1. 先看结论

`MinorCPU` 是一个面向 FPGA 和仿真的 RV32I 处理器实现。它的核心并不是手写 Verilog，而是用 **Scala + Chisel** 描述硬件，再由 Chisel 生成 Verilog；外围的顶层封装、RAM、UART、串口调试接口和 FPGA 引脚约束使用 Verilog。

项目的核心思路是：

> 取指阶段持续提出指令请求；指令进入队列后，带着 ROB 编号在后端等待操作数；操作数就绪的指令可以乱序送入 ALU 或内存系统执行；结果通过广播网络唤醒后继指令；最后由 ROB 按程序顺序提交。

因此它实现的是 **乱序执行、顺序提交**，属于一个简化的 Tomasulo 风格处理器，而不是经典的五级顺序流水线。

从仓库内容可以确认的主要优化机制有：

- 乱序执行（Out-of-Order）
- 指令缓存和数据缓存（Cache）
- 两级局部历史分支预测（Branch Prediction）
- 返回地址栈（RAS）辅助预测 `jalr`
- MMIO（内存映射 I/O）和 UART 输出

## 2. 目录与职责

| 路径 | 作用 |
| --- | --- |
| `src/main/scala/` | Chisel/Scala 编写的 CPU 核心模块 |
| `src/main/scala/CPU.scala` | 顶层 Chisel 模块，实例化并连接所有核心部件 |
| `src/test/scala/` | ChiselTest 单模块和小系统测试 |
| `src/cpu.v` | 作业要求的 CPU 外壳，暴露时钟、复位、内存总线和调试接口 |
| `src/riscv_top.v` | FPGA/仿真顶层，连接 CPU、RAM、HCI 和 UART |
| `src/hci.v` | 主机通信接口：串口下载、调试、程序停止和 MMIO 处理 |
| `src/common/` | 单口 RAM、FIFO、UART 等通用 Verilog 模块 |
| `src/Basys-3-Master.xdc` | Basys-3 FPGA 的时钟、LED、UART 等引脚约束 |
| `sim/testbench.v` | iverilog/Verilator 使用的仿真顶层 |
| `sim/main.cpp` | 可选的 Verilator C++ 仿真驱动 |
| `Makefile` | 生成、编译和运行仿真/FPGA 测试的脚本 |
| `build.sbt` | Scala、Chisel 和 ChiselTest 的构建依赖 |
| `README.md` | 项目说明、架构解释和性能记录 |

`Interpreter.scala` 是早期的解释器原型，只实现了少量 R 型指令，且没有被 `CPU.scala` 实例化；阅读主 CPU 时可以先忽略它。

## 3. 从指令到提交：一条指令如何运行

### 3.1 前端

1. **IF（Instruction Fetcher，`IF.scala`）**

   - 保存当前 PC，持续向 ICache 请求 32 位指令。
   - 按 RISC-V 的 `opcode/funct3/funct7/rs1/rs2/rd` 字段解码。
   - 计算立即数，并为分支、`jal`、`jalr` 选择下一条 PC。
   - 条件分支查询 `Predictor`；`jalr` 查询 `RAS`。
   - 预测错误时接受 ROB 给出的 `modified_pc`，丢弃当前错误路径上的指令。

2. **ICache（`ICache.scala`）**

   - 直接映射、单路结构（README 称为 1-way）。
   - 默认有 `2^8 = 256` 个 32 位字，容量约 1 KiB。
   - 用 `valid + tag + data` 判断命中；未命中时向 MA 请求一个 32 位字。

3. **IQ（Instruction Queue，`IQ.scala`）**

   - 32 项环形指令队列，吸收取指和后端处理速度差异。
   - 从队头一次发射一条指令到 ROB、RS；load/store 同时进入 LSQ。
   - 发射时通知 RF 为目的寄存器记录一个新的 ROB 依赖标签。

4. **Predictor 和 RAS**

   - `Predictor.scala` 为 64 个 PC 索引保存 2 位局部历史。
   - 用 `PC(7,2) + history` 索引 256 个 2 位饱和计数器，计数器最高位决定 taken/not-taken。
   - 分支在 ROB 提交时才用真实结果更新预测器。
   - `RAS.scala` 是 32 项返回地址栈：`jal` 入栈 `PC+4`，`jalr` 使用栈顶并弹栈。

### 3.2 后端

1. **RF（Register File，`RF.scala`）**

   - 保存 32 个 32 位架构寄存器。
   - 每个寄存器额外保存“当前生产者 ROB 编号”，用它表示数据依赖。
   - ROB 提交后写回寄存器，并在生产者仍是该 ROB 时清除依赖。
   - 这是简化的寄存器重命名/记分牌机制，并没有独立的物理寄存器文件。

2. **RS（Reservation Station，`RS.scala`）**

   - 32 个保留站项保存操作码、两个操作数、依赖 ROB 编号和立即数。
   - 新指令进来时读取 RF；如果值还没有产生，就保存依赖标签。
   - ALU、LSQ、WB 都会广播结果，RS 监听广播并唤醒等待项。
   - 每周期选出一个“忙且两个操作数都有效”的项送入 ALU。

3. **ALU（`ALU.scala`）**

   - 实现整数加减、逻辑运算、移位、有/无符号比较和分支比较。
   - 同时计算 load/store 的有效地址。
   - 结果分别广播给 RS、ROB、LSQ。
   - 对 load 地址检查高位 MMIO 区域，并把 MMIO 状态传递给 ROB/LSQ。

4. **LSQ（Load Store Queue，`LSQ.scala`）**

   - 32 项队列保存 load/store 的地址、数据和 ROB 编号。
   - 地址由 ALU 计算，数据依赖可以由 ROB 广播补齐。
   - load 只从队头按顺序访问内存，避免破坏内存顺序；访问前要求 WB 为空。
   - store 在地址和值就绪后先进入 WB，只有 ROB 到达队头时才允许真正写出。
   - 对 `lb/lh` 做符号扩展，对 `lbu/lhu` 保持零扩展。

5. **RoB（Reorder Buffer，`RoB.scala`）**

   - 32 项环形 ROB，为每条指令保存指令信息、结果、地址和 ready 状态。
   - 执行可以乱序完成，但提交严格按照 head 顺序进行。
   - 普通算术指令提交到 RF；store 提交到 LSQ/WB；分支在此处检查预测是否正确。
   - 分支或 `jalr` 预测错误时产生 `modified_pc`，同时通知 IF、IQ、RS、LSQ、Cache 和 MA 清空错误路径状态。
   - MMIO load 先被标记为“地址已算出”，等 WB 返回实际 I/O 数据后才算真正提交。

6. **WB（Write Buffer，`WB.scala`）**

   - 8 项小型队列，串行向数据缓存或 MMIO 发送 store 请求。
   - MMIO 读完成后把数据广播给 RS 和 ROB。
   - 普通 store 不需要把结果广播回寄存器，但必须等待内存请求完成。

### 3.3 内存系统

1. **DCache（`DCache.scala`）**

   - 与 ICache 类似，也是默认 256 项、直接映射的 32 位字缓存。
   - 支持 `lb/lh/lw` 和 `sb/sh/sw`，维护 valid、tag 和 dirty/write-back 标志。
   - 写命中时在缓存中修改；替换脏行时先写回旧字，再读取新字。
   - `0x30000` 和 `0x30004` 被定义为特殊 I/O 地址，不进入缓存，直接交给外部接口。

2. **MA（Memory Arbiter，`MA.scala`）**

   - ICache 和 DCache 共用一个外部字节内存端口。
   - 用状态机把 4 次字节读写拼成一个 32 位结果。
   - 空闲时优先处理 DCache 请求，再处理 ICache 请求。
   - 对外只暴露 `mem_a`、`mem_din`、`mem_dout`、`mem_wr` 四个作业接口。

## 4. 分支错误和 MMIO 是怎样闭环的

### 分支预测错误

```text
IF 预测下一条 PC
  -> 指令进入 IQ/ROB/RS
  -> ALU 计算真实分支结果
  -> ROB 到队头时比较预测值和真实值
  -> 不一致：产生 modified_pc，并广播 predict_failed
  -> 清空错误路径状态，IF 从正确 PC 重新取指
  -> 用真实结果更新 Predictor
```

这种设计把“执行”和“是否允许对外生效”分开：错误路径可以提前执行，但只有 ROB 顺序提交后才能改变架构状态。

### MMIO

顶层用地址的 `mem_a[17:16] == 2'b11` 区分 I/O 区域：

- `0x30000` 读：读取 UART 输入 FIFO；写：输出一个字符。
- `0x30004` 读：读取 CPU 周期计数器；写：通知程序结束。
- `hci.v` 在仿真时通过 `$write` 输出字符，在 FPGA 上通过 UART 发送。
- HCI 下载或调试时会拉低 CPU 的 `rdy_in`，让 CPU 暂停，避免和主机访问 RAM 冲突。

## 5. 使用了哪些语言、工具和技术

| 类别 | 项目中的实际使用 |
| --- | --- |
| 硬件描述 | Chisel 3.6.1、Scala 2.13.14；生成 synthesizable Verilog |
| Chisel 构建 | sbt、`chisel3-plugin`；`sbt run` 生成 `generated/CPU.v` 等模块 |
| 模块测试 | ChiselTest 0.6.2 + ScalaTest 风格测试 |
| Verilog 仿真 | Icarus Verilog（Makefile 默认路径） |
| 可选仿真 | Verilator + `sim/main.cpp`，Makefile 中的 Verilator 命令目前被注释 |
| FPGA | Vivado 综合/实现/下载，目标板是 Basys-3；约束见 `.xdc` |
| 外设 | Verilog UART、FIFO、同步 RAM、串口 HCI |
| 测试程序 | README/原始作业文档要求使用 RISC-V GCC 交叉工具链把 C 程序编译成机器码/ELF |
| 软件脚本 | GNU Make；Makefile 负责复制测试文件、编译仿真器和启动运行 |

## 6. 从源码到运行的工作流

### 第一步：生成核心 Verilog

在 `MinorCPU` 目录执行：

```bash
sbt run
```

`CPU.scala` 的 `Main` 会生成 `CPU.v`，并额外生成 ALU、IF、IQ、LSQ、MA、Predictor、RAS、RF、RoB、WB 等模块到 `generated/`。`src/cpu.v` 再把生成的核心包成作业规定的 `cpu` 端口。

### 第二步：运行单元测试

```bash
sbt test
```

重点测试文件包括：

- `FESpec.scala`：IF + ICache + MA 的取指链路和重新取指。
- `DCacheSpec.scala`：缓存命中、未命中、读写和字节拼接。
- `LSQSpec.scala`：load/store 顺序、广播、预测失败清空和满队列。
- `MASpec.scala`：外部字节内存读写和仲裁状态机。
- `PredictorSpec.scala`：局部历史 + 饱和计数器模型。
- `RFSpec.scala`：寄存器值和 ROB 依赖的建立/清除。
- `RSSpec.scala`：保留站基础接口测试，目前覆盖较少。

这些测试直接驱动 Chisel 模块的 IO，按时钟周期 `poke/expect/step`，因此适合验证状态机和握手时序。

### 第三步：运行整机仿真

```bash
make run_sim name=<测试用例名>
```

Makefile 的默认流程是：准备测试文件，使用 iverilog 编译 `sim/testbench.v`、所有 Verilog 外围模块和 `generated/CPU.v`，然后启动仿真。同步 RAM 会从 `test.data` 初始化，测试程序通过 `0x30000/0x30004` 完成输入、输出和结束。

### 第四步：上 FPGA

Vivado 使用 `src/riscv_top.v` 作为顶层，加入 `src/common/`、生成后的 CPU Verilog 和 `Basys-3-Master.xdc`，完成综合、实现并生成 bitstream。串口 HCI 可把程序写入板上 RAM、启动 CPU 并读取调试信息。

## 7. 如何理解“已经完成”

README 中给出的性能记录说明作者确实做了端到端运行，而不只是连接模块：

| 场景 | 结果 | 说明 |
| --- | --- | --- |
| 数组加法/循环访存 | 9409 cycles，3.920 CPI | 访存和 store 是主要瓶颈，DCache 优势不明显 |
| 前缀和循环 | 13144 cycles，1.826 CPI | DCache 和乱序执行带来明显收益 |

代码层面形成了完整闭环：取指、解码、依赖跟踪、乱序执行、结果广播、内存访问、顺序提交、分支恢复、MMIO 和 FPGA 外设都已连接到 `CPU.scala` 的顶层。

但阅读时要注意几个边界：

1. README 明确写的是 RV32I；当前 IF 按固定 32 位指令解码，没有看到 RISC-V C（压缩指令）解码逻辑。原始作业说明中的 RV32IC 不能直接等同于 MinorCPU 已实现的能力。
2. 这是“乱序执行”而不是“多发射”：IQ、RS、ROB 每周期的核心路径都以一条指令为主，提交也按 ROB head 一条一条进行。
3. 当前目录是源代码快照，没有 `generated/`、`testcase/` 和 `fpga/` 目录；因此文档中的 `sbt run` 和 `make run_sim` 需要先生成 Verilog，并补齐外部测试用例/工具链后才能完整执行。
4. `Interpreter.scala` 未完成，也不参与最终 CPU 数据通路；不要把它当作 CPU 的第二个实现。

## 8. 推荐的阅读顺序

1. 先读 `src/cpu.v`，理解作业规定的外部端口、内存时序和 MMIO 地址。
2. 再读 `src/riscv_top.v`，看 CPU、RAM、HCI、UART 如何连接。
3. 读 `src/main/scala/CPU.scala`，只关注模块实例和连线，不要一开始钻进每个状态机。
4. 沿一条算术指令阅读：`IF -> IQ -> RF/RS -> ALU -> ROB -> RF`。
5. 沿一条 load/store 阅读：`RS -> ALU -> LSQ -> DCache -> MA -> ROB/WB`。
6. 最后阅读 `Predictor.scala`、`RAS.scala` 和 ROB 的 `modified_pc` 逻辑，理解分支恢复。
7. 用对应的 `src/test/scala/*Spec.scala` 对照每个模块的时序。

如果只记住一个总图，可以记成：

```text
                +---------------- Predictor / RAS
                |
Memory <-> MA <-> ICache <-> IF -> IQ
   ^                  ^             |
   |                  |             +--> RF / RS / ROB
   |                  |                         |
   +------ DCache <-- LSQ <-- WB <--------------+-- ALU
```

其中 ROB 是“按顺序提交”的控制中心，RS/LSQ/WB 的广播网络负责把乱序执行结果重新传播给等待中的指令。

## 9. 和当前任务的关系

`MinorCPU` 适合作为上一年度项目的架构参考，不应被当成当前任务的直接模板。根目录的 `instructions.md` 强调了参数化多发射、物理寄存器重命名和 RV32IM 等要求，而 `MinorCPU` 的实现更偏向固定规模的单发射乱序核心：

- IQ、RS、RoB、LSQ 固定为 32 项，WB 固定为 8 项，`CPU` 没有把这些规模做成参数。
- 每周期的发射、RS 选择和 ROB 提交都以一条指令为主，不是前端/后端宽度可配置的 1/2/4 路多发射。
- RF 使用 ROB 编号作为依赖标签，没有独立的物理寄存器文件和可配置重命名空间。
- README 声明支持 RV32I；代码中没有明显的乘除法（M 扩展）或 CSR 数据通路。
- 它额外实现了字节/半字 load-store、缓存、预测和 MMIO，这些内容对理解系统级 CPU 很有价值，但不代表当前任务的全部接口要求。

因此，阅读这个项目时可以复用它的模块划分、ROB/广播/恢复思路和 Chisel 测试方法；真正实现当前任务时，仍要重新检查发射宽度、参数化接口、物理寄存器、指令集和综合约束。

## 10. README 中记录的分工

项目 README 将贡献大致分为两部分：

- `livandan`：DCache、MA、Predictor、`lb/lbu/lh/lhu` 支持、主要单元测试、Interpreter 和部分 MMIO。
- `sword`：IF、IQ、ICache、RF、RoB、RS、ALU、LSQ、WB、RAS 和部分 MMIO。

这也解释了为什么代码同时包含“核心数据通路”和“外围总线/缓存”的两组风格：前者主要用 Chisel 组织，后者需要适应题目提供的 Verilog 接口和 FPGA 平台。
