# DD：统一频率结构优化，未测试

DD 将已经采用的 CY 与 CZ、DA、DB、DC、DD 合并。源码候选是 [DD_lsq_circular_hazards](F:/CPU2026Candidates/frequency_research_20261003/DD_lsq_circular_hazards/candidate.json)，冻结快照指定为 [architecture_DD_20261005](F:/CPU2026CourseRuns/architecture_DD_20261005/source_manifest.json)，采用前的 CY 工作树备份指定为 [pre_DD](F:/CPU2026Candidates/pre_DD_worktree_20261005/backup.json)。中间候选和所有旧测量均保留。

此批次只做源码阅读、代数推导、现成网表读取和文件身份核对，没有运行 HDL 编译、lint、仿真、综合、STA 或形式验证。下面的结构层数、行数和寄存器声明数不是测得的频率、面积或功能证明。

## 此次新增五组

| 组 | 改动 | 要缩短的依赖 | 状态及边界 |
|---|---|---|---|
| CZ | ALU 的 32 位加/减/地址/PC 相对加法，以及 MUL 的最终 64 位加法，预先形成每个四位块的 carry0/carry1 结果 | 后到的块进位直接选择结果，不再启动块内加法 | 无新增边沿/FF；原 Yosys `+` 的实际映射也可能很快，不能保证显式结构一定优于原映射 |
| DA | 33 位符号扩展、17 个 radix4 Booth digit 和一行补偿，替换原 36 行部分积；两段 CSA 分别为三层 | 原四层/四层压缩改为三层/三层，减少待压缩的行 | S1 声明从八个 64 位行变为六个，少声明 128 位；常量修剪使实际 FF 面积变化不一定等于 128 位。Booth 编码本身增加第一段逻辑 |
| DB | load report 携带同一行的 unretired 标志，结合本地恢复快照形成 wake 资格 | 去掉 LSQ report 后、早期 wake 前的 64-row ROB valid/generation 查询 | 正常 completion、PRF、ROB 的完整 valid/generation 检查保留；report 73→74 位仍五个 16 位组；无新 FF |
| DC | LSQ 请求、完成报告、恢复尾部定位的 oldest tournament，以及四个字节前递的 youngest tournament，传递一位 wrap key | 用固定子树的物理顺序代替每层完整年龄比较 | 当前 LSQ 16 项，四层树仍保留，比较项由四位年龄变为一位；资格、payload、握手、优先级不改 |
| DD | 固定行间 store/load 年龄关系直接化简为 wrap key 的 AND/OR；动态前递目标使用 wrap/slot 顺序 | 减少 16×16 行间年龄减法/比较依赖，以及 selected_age 后的前递年龄比较 | 不新增依赖 mask/年龄矩阵 FF；每个 hazard wrap leaf 至多服务四个对侧行，避免重建集中广播 |

普通整数流水仍为十级，MUL 的 req→S1→S2→OUT 三个算术阶段边沿仍相同。课程 39 项顶层设置、ROB/RS/PRF/LSQ/cache 容量、内存延迟 10 与 SRAM 形状不改。RS 文件本次相对 CY 只有注释修正（16 位分组），实际低排名逻辑来自 CW。

## 进位选择的代数

每块先算 `base=(lhs4+rhs4)` 的五位结果，保存 `sum0=base[3:0]` 和 `sum1=sum0+1 mod 16`。块 G 为 base[4]，P 为四个 XOR 的与。前缀合并为 `G=G_right | P_right*G_left`、`P=P_right*P_left`。ALU 八块用三层、64 位乘法末级十六块用四层前缀；最终 carry 只选择 sum0/sum1。ALU 原输入进位、SUB 的反相/加一和模 2^32 语义保留，MUL 末级为模 2^64。

不能把原 64 位 `+` 称为未经查看就确认的 ripple，也不能以源码前缀层数推算 MHz。增加局部双结果可能增加组合面积，必须由同一课程映射评价。

## Booth 与 CSA 的代数

MULH 的 A/B 都按有符号扩展；MULHSU 只将 A 按有符号扩展；MULHU 和 MUL 采用无符号扩展，后者只取低 32 位。A 为 33 位 `{sign,A32}`，B 的 recoding view 为 35 位 `{sign,sign,B32,0}`，digit j 读取位 `[2j +: 3]`。17 个 digit 同时覆盖无符号 B 的最高补偿位和有符号 B 的符号扩展。

`one=b0^b1`，`two=(b0==b1)&&(b2!=b1)`，`negative=b2&&(one||two)`，对应 0、±A、±2A。34 位 relative row 足以表示 33 位 A 的一次/两次量；非零负行先按位取反，再由共享补偿向量在位 2j 放入一。每个补偿位置不同，可以拼成一行。34 位行按符号扩展至 64 位后移 2j，保留模 2^64；不为每个负行添加串行二补码加法器。

压缩阶段是 `18→12→8→6 | register | 6→4→3→2 | register | CPA | output register`。每个三输入 CSA 保持 `sum3 + carry3 = a+b+c mod 2^64`，旁通余行也保留；因此所有行的总和在每层不变。S1 的数据使能由 33 个 leaf 调为 25 个（24 个数据组加一份 metadata）；S2 仍九个 leaf。恢复取消、反压、操作种类和目的身份继续使用 CY 的 stage owner，未提前丢弃未接受的结果。

[MIT 6.175 乘法器课程](https://csg.csail.mit.edu/6.175/labs/lab3-multipliers.html)给出 radix4 Booth 的三位编码和 n+1 位扩展处理 signed/unsigned 的依据。此实现的流水与分发是本项目自行重排，并非该课程电路的测试结果。

需检查 MULH 的最小负数、MULHSU 的负数乘最大 unsigned、MULHU 的高位补偿、MUL 的低半部，以及恢复/反压同拍的多段任务身份。人工推导没有代替这些硬件验证。

## load 唤醒的所有权

LSQ report 仍只从队列年龄范围内的有效 load、complete 且未 reported 行选择。新标志 `!retired_mem[row]` 与物理目的、值、错误和完整两个 tag 从同一行一起选择，避免选完后再串行读取 retired 表。

1. 普通 load 必须先由 LSQ 报告完成，ROB 才能退休它；尚未接受报告的 unretired 行仍拥有自己的 ROB 和物理目的。
2. report 接受边沿设置 reported；之后的 cache response 只更新完成/错误/等待状态，不清除 reported。retired 由完整 ROB tag 的 retire 匹配设置。
3. 只有 reset/flush、恢复 kill、出队和新分配会清 reported；出队同时清 valid，新分配同时建立新 generation/tag/物理目的、清 complete 和 retired，不产生旧有效 report。
4. cache response 必须通过 valid、slot、完整 LSQ generation 和 response_wait 检查。响应过期的旧 generation 不能填充新行。
5. 恢复 apply 当拍，报告完整 ROB tag 的年龄与已注册 head/occupancy/branch 边界比对；年轻或快照区间外结果不提供 wake，apply 边沿由原 LSQ kill 清除任务。保留的 retired load 也不提供 wake。
6. 全局 reset/flush 继续屏蔽 wake。正常 completion/PRF/ROB 的 ROB valid/generation/恢复检查没有删除，早期 wake 也仍与 producer_valid 和 rd_we 相与。

这些是依赖现有 CPU 分配、退休、恢复不变量的源码推导，没有形成形式证明。错误结果、恢复与完成同拍、受反压结果、迟到响应及物理编号复用仍是重点。默认未启用 issue pipeline 的 joint 配置继续使用原集中 wake 资格。

## 环形顺序的化简

定义 `wrap(i)=(i<head)`。对合法 head 和物理 slot，环形相对年龄顺序等于 `(wrap(i),i)` 的字典序：从 head 到队列末尾的行先于从零到 head 前的行，同一段中按物理 slot 升序。

对固定 i/j：

| 固定位置 | i 比 j 更老 |
|---|---|
| i<j | `!wrap(i) || wrap(j)` |
| i>j | `!wrap(i) && wrap(j)` |
| i==j | false |

平衡树的左右子树覆盖相邻且已知的物理区间。oldest 选择左的规则是 `left_valid && (!right_valid || !left_wrap || right_wrap)`；youngest 选择左的规则是 `left_valid && (!right_valid || left_wrap && !right_wrap)`。同段内 oldest 优先左，youngest 优先右；跨 head 时 wrap=0 的行更老。不同有效行没有年龄相同的情况，原有 tie 不受影响。

动态选中 slot 的前递年龄关系用 `(row_wrap==selected_wrap)?row<selected_slot:!row_wrap&&selected_wrap`。数据地址、byte mask、数据就绪检查及 unknown-store 阻塞没有变，仍逐字节选择最近的更老 store，未改为推测 load 或忽略未知 store。

原 LSQ 接口要求容量为 2 的幂。非填充的 pick/forward/recovery 树对非 2 的幂还保留原比较分支，不能据此声称原不支持的配置现已支持。报告树始终填充至 2 的幂，padding 叶仍无效。所有年龄区间资格和恢复 keep count 保留；本次没有删除 `age<occupancy` 防护。

这使当前 16 项配置的 256 个 pair order 项在 elaboration 时变为常量或两输入布尔表达式，并把 7 个 tournament 的每层四位比较变为一位选择。不能直接换算成门数或 Fmax：原映射可能已化简一部分表达式，新增分发也有成本。四态未知 payload 的逐位等价没有证明；有效已初始化任务的行为是本次保持的目标。

## 历史继承与未测状态

DD 继承 [CN 九组](E:/Verilog_cpu/reports/frequency_batch_CN_implementation_2026-10-04.md)、[CU1 七组](E:/Verilog_cpu/reports/frequency_batch_CU1_implementation_2026-10-04.md)、[CY 四组](E:/Verilog_cpu/reports/frequency_batch_CY_implementation_2026-10-04.md)。相对旧实测 CD1 是十三个 RTL 文件的组合修改，相对已采用的 CY 是六个文件。实际数量由冻结后的身份记录再次核对。

最近实测仍属于 CD1：Fmax 99.65936739659368 MHz，IPC 0.7823728642153719，总面积（含 SRAM）49851.29213392186 µm²，correctness 16/19，pi/qsort/tak 超时。DD 的四项全部未知，不能宣布达到 300 MHz 或 ±10%。本批不启动测试；完整采用/暂缓理由与拟定统一测量另见测试前报告。
