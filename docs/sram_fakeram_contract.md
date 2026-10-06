# 框架片上 SRAM 规范

来源：用户提供的 `sram_fakeram` 文档（2026-09-26）。用于片上存储，独立于仿真平台外部256MiB AXI4-Lite主存。

## 参数与接口

- DEPTH默认256，合法范围1..1,048,576。
- WIDTH默认32，合法范围1..4,096。
- WRITE_GRANULARITY默认WIDTH，合法范围1..WIDTH，必须整除WIDTH。
- 单实例DEPTH×WIDTH不超过16,777,216 bit。
- 输入clk/en/we为1bit，addr宽度为max(1,ceil(log2(DEPTH)))，wdata宽度为WIDTH，wmask宽度为WIDTH/WRITE_GRANULARITY；输出rdata宽度为WIDTH。
- addr为字索引，en有效时必须满足0<=addr<DEPTH。

## 必须保持的行为

- 同步单端口1RW：每周期只能读一次或写一次，不能同周期读写，也不能同时写两个地址。
- clk上升沿en=1/we=0采样读地址，沿后rdata有效，作为下一周期数据使用。
- clk上升沿en=1/we=1按wmask更新相应写通道；全零掩码不改变内容。
- 写周期和禁用周期rdata未定义，不依赖保留的旧输出。
- 无全局复位，初始内容不保证为零。需要有效位或显式逐项初始化；不能给SRAM数组加整表复位。

## 框架接入约束

- 使用框架原文件 `scripts/ram/sram_fakeram.sv`。
- 不把此文件加入框架 `verilog/filelist.f`，框架构建/综合脚本自动引入。
- 独立仿真应将框架原文件与设计一起编译。
- 不自行创建同名空桩或实现；`sram_fakeram`、`sram_fakeram_`和`fakeram_asap7_`前缀是框架保留名。
- 当前项目使用独立 `rtl/filelist.f`/自定义综合脚本，不假设它具有框架自动引入机制。接入时需核对真实框架文件和脚本。

## 面积计算边界

2026-09-30已克隆课程框架至 `.deps/RISC-V-CPU-2026`，冻结读取版本 `54fc150ffc290f52aa024209ffb9a29d43856f6d`。框架原模块、宏生成器和面积/时序汇总脚本现已取得。原接口文档未给数值，准确计算规则来自该版本 `scripts/fakeram.py`、`scripts/synth.py`、`scripts/synth_report.py`，不是通用SRAM位密度假设。

### 官方框架面积规则

模型名称 `fakeram-asap7-v1`，系数 `0.0419904 µm²/bit`。设深度D、总位宽W、写粒度G，通道数L=W/G。框架把一个实例拆成L个D×G窄宏，每个宏面积为 `round(D × G × 0.0419904, 6)`，单位µm²；实例面积为L个已舍入宏面积之和。没有另外添加固定宏外围面积项；每通道访问使能 `en & (~we | wmask[lane])` 等包装电路按实际综合的标准单元计价。

以下通过直接调用克隆框架的 `Shape` 对象验证，为指定形状的单个1RW实例价格，不表示当前CPU已经使用这些宏：

| D×W | G | 窄宏数 | SRAM面积µm² | 单宏clk→Q ns |
|---|---:|---:|---:|---:|
| 1024×32 | 8 | 4 | 1,375.941428 | 0.098324704 |
| 1024×128 | 8 | 16 | 5,503.765712 | 0.098324704 |
| 1024×19 | 19 | 1 | 816.965222 | 0.112000498 |
| 64×128 | 128 | 1 | 343.985357 | 0.231468304 |
| 64×23 | 23 | 1 | 61.809869 | 0.100926634 |

宏生成器按合法整数参数生成wrapper和Liberty。`synth_report.area_report`递归遍历实际叶实例，逐个累加宏area和ASAP7标准单元area；同类型宏被实例化多次时重复计入，父模块与子模块的汇总面积不重复相加。遇到未映射或未声明黑盒会报错。

### 官方框架时序规则

每个窄宏的 `clk→Q = 0.071262 + 0.0000167155 × D + 0.001243254 × G` ns。必须用G而非包装总位宽W。setup=hold=0.050ns，min_period=0.157ns；生成的Liberty时间单位为ns，电容单位为pF。这是课程框架规定的估算模型。

官方OpenSTA流程同时读取标准单元库及生成的SRAM库，统一命令时间单位ns/负载单位fF，时钟不确定度0.05ns，输入/输出预算各0.2ns，输出负载5fF；对setup、最小周期和脉宽约束进行周期搜索，再以1000/最小周期(ns)计算MHz。现有本地逻辑边界分析的约305.19MHz不等同于该完整流程。

### 普通RTL数组的计价

`prepare_memories`仅替换实际例化的 `sram_fakeram` 参数特化模块；普通Verilog数组没有自动享受SRAM价格。官方随后调用 `synth -top student_top -noabc`，普通数组会继续按Yosys综合流程映射为逻辑，最终纳入标准单元面积。全FF参考版本没有 `sram_fakeram` 实例，完整面积为148,169.833200µm²。2026-09-30后续实现已将非阻塞D-cache数据阵列实际迁移到课程原版同步1RW模块；不能把其它逻辑存储黑盒直接乘官方位密度并宣布正式总面积。

正式总面积仍为实际综合的组合/时序标准单元面积（含实际适配逻辑）加框架估算的实际实例化SRAM宏面积。外部主存不计。逻辑数组尚未绑定为合法宏时，不得直接套用1RW宏价格。

## 当前RTL的不匹配与计算次序

1. 非阻塞D-cache data已迁移到1024×128、G=8的真实1RW实例。refill优先于命中读/写和脏victim快照；掩码store直接写，不再读改写。同步读结果与响应元数据对齐，并在下一沿捕获以承受SRAM idle/write输出未定义和响应背压；victim旁路/捕获保持首周期回写可用。命中延迟仍为一周期。16组hash/容量/ways/prefetch随机测试、定向四态协议测试和完整整机回归通过；其它cache实现尚未迁移。
2. D-cache tag目前1024×19、5R1W，I-cache tag64×23、6R1W；需打包同set的ways并处理需求查询、预取和victim查询的端口占用。同步读流水改变后的性能必须重测。
3. I-cache data目前64×128、1R1W；即使逻辑端口较少，也须保证读与refill写互斥及同步读响应对齐，不能仅凭端口计数宣称兼容。
4. 当前BTB payload每bank单独tag/target/kind数组为组合读1R1W；可打包为58bit字，但仍需解决预测查询/反馈写冲突和一周期读延迟。valid/BHT复位与更新不能直接搬入无复位单端口宏。
5. PRF等多读多写阵列必须决定合法物理实现；用标准单元实现者实际综合并计价，不能用单端口宏面积代替。

下一步计算已具备官方模型输入。剩余工作是将目标片上存储实际接入合法1RW宏，对其它数组执行完整逻辑映射，并以同一设计重新综合和测评。无需再等待用户提供SRAM面积公式。

## 实际绑定和完整测评入口

`tools/build_join02_verilator.ps1`、Makefile及GUI在独立仿真中自动引入克隆框架的原版 `scripts/ram/sram_fakeram.sv`，不修改 `rtl/filelist.f`，不编写保留名称stub。

`tools/run_course_sram_area.py --build-manifest <冻结构建清单> --outdir <新目录>` 使用课程原版 `prepare_memories`、宏Liberty及 `area_report`，默认复用课程opt/flatten流程和默认ABC脚本。完整展开所有非SRAM数组，并独立核对叶面积和实例数；不接受缺失定价。`--abc-script classic-area` 是明确标注的备用映射，不能混称默认课程成绩。配置直接来自已验证的仿真构建清单，外部RAM不进入CPU综合顶层。

完整时序入口为 `tools/run_course_full_timing.py <面积目录>`，使用项目WSL OpenSTA 3.1.0、同一完整网表、全部标准单元与SRAM库以及课程原版 `timing.tcl`。真实 `cpu_core` 端口为 `clk/reset`，reset按课程约束固定为0；真实 AXI `student_top` 端口为 `clock/reset`，需传入 `--clock-port clock`。`clk_i/reset_i` 仅属于工具测试 fixture，不是 CPU 端口。不沿用此前忽略存储边界的局部频率。
