# 频率结构重构：当前实现与剩余工作

当前工作树已更新为 CD1 候选，23 个文件并入，157 个文件的课程输入单独冻结在 [architecture_CD1_20261004](F:/CPU2026CourseRuns/architecture_CD1_20261004/source_manifest.json)。覆盖前版本备份在 [pre_CD1_worktree_20261004](F:/CPU2026Candidates/pre_CD1_worktree_20261004/backup.json)。**CD 首次课程编译发现内部保留字错误；CD1 仅修复名称，尚无 IPC/Fmax/面积。源码准备、人工推理和文件散列核对不能证明频率收益或正确性。**

## 已完成的结构实现

| 项目 | 原结构的问题 | 当前实现 | 新增延迟/状态 |
|---|---|---|---|
| 合规控制分发 S | 外部 BUF 黑盒被课程拒绝；同名功能定义又与 Liberty 导入冲突 | 完整普通 RTL 反相器模块，保留功能层次及独立实例，最多四叉递归分发；由原 ABC 映射真实门 | 不加周期；映射尚未验证 |
| 宽数据控制 T | 一个选择/写入控制驱动 64–272 个数据位 | RS 分配选择、元数据写入、恢复描述符和 64 位部分积/完成数据按至多 32 位分组 | 不加周期，不增加逻辑数据寄存位 |
| LSQ 字段 U1 | 25 类字段集中修改，共享控制进入大量保持 mux | 普通 RTL 字段 owner，保留原 reset、恢复、提交、响应、分配及最后 NBA 优先级 | 不加周期；请求选择级保留 |
| PRF 字段 P（继承） | 写回数据、查询和最终写入负载集中 | 分组广播输入、每行拥有值与 ready，保留同拍 WB 优先于 busy 标记 | 不加周期 |
| 生产者标签 V | 多端口动态标签读与集中写 | 行拥有标签，分组查询、独热选择和二叉 OR 读树；完整写入和最高通道优先 | 至多 PHYS_REGS 个有效寄存位；不加周期 |
| ROB 字段 W1 | 分配/完成/恢复修改的保持 mux 集中 | 22 类字段的功能 owner；CHECKPOINT_IMPL=1 时明确排除未使用的完整 checkpoint 数组 | 不加周期；SRAM 接口不变 |
| 恢复年龄 W1/N | 32 位整数 subtract/wrap 链与恢复优先选择广播 | LSQ 的二次幂 ROB 使用 SLOT_WIDTH 无符号模减；非二次幂保留修正；RAT 恢复按八行组分别选 first-any/first-upper | 不加周期 |
| rename 状态 X/M（继承） | RAT 恢复/写入集中，候选搜索接在 rename 前面 | 行拥有 RAT、按字拥有 raw free bitmap；四项寄存候选池隔离搜索与使用，提交归还仍具有原优先级 | 普通指令不增级；池在 reset/恢复后有补充等待 |
| RS 空槽 Y | 四个通道按 cursor 依次遍历空槽 | 并行计算每行之前的空槽数和每通道之前的接受数；第 k 个接受通道获得第 k 个最低空槽 | 不加周期、不加寄存位 |
| 空闲池补充 Z | 四次最低编号选择和位图清除前后依赖 | 八位组计数、组前缀和组内前缀；同时产生第 0..3 个空闲编号，保持编号顺序和零哨兵 | 不加周期、不加寄存位 |
| 除法器 AA | 每拍两次恢复减法串联 | 同一试算余数并行减 D/2D/3D，选择最高合法商位；3D 在已有准备级捕获 | 加 34 个数据位；迭代数、准备/结束级和特殊结果不变 |
| 乘法器 AB | 第二段同时做四层 CSA 和 64 位最终加法 | 两条最终 carry-save 行先寄存，再做 CPA 和高/低半选择；每段独立保持、丢弃和反压 | 当前宽度加 159 个寄存位；MUL 类增加一拍，乘法器自身可每拍接收一项 |
| 剪除可见性 AC | 将整个状态 owner 保留层次会妨碍跨边界剪除未使用的调试字段/常数位 | ROB/LSQ/前端/译码状态 owner 允许 flatten；仍保留完整反相器的层次和独立实例，维持控制域 | 不增周期或寄存位；面积效果尚未测量 |
| 派发边界 AD | free pool/RAT 同束旁路之后又串 PRF/tag 查询、RS/LSQ 分配 | R 完成 rename/ROB/destination 分配，D 从单束寄存包读取操作数、写入 RS/LSQ；寄存额度扣除保留项；实际 LSQ 映射在 D 写入 | 普通路径新增一级，达到十级；当前配置增加 712 个逻辑寄存位 |
| 命令生成修复 AE | 自动拆分误将条件中的关系运算 <= 当成 NBA，且吞入部分单行 if guard | 按完整语句边界和配对括号提取赋值；从原快照重生成 ROB/LSQ。修复 ROB 恢复完成条件、error guard 和残留 ready 多写者 | LSQ 文本与 AD 相同；不是验证通过或频率优化收益 |
| 行控制 AF/AG | 上游公共 mode 和 completion/alloc select 仍进入宽 payload 选择 | ROB 每行判断 reset/recovery、代数、年龄及更新优先级；完成输入分域，最终独热选择每叶最多 32 位；分配 bank 使用并行独热选择、二叉 OR，排除未使用 checkpoint 位宽 | 不增加寄存位或周期；保留旧参数分支，实际负载与面积待测 |
| LSQ 宽字段 AH | 地址、数据、tag、结果、转发快照的选择共享 mode 和动态数组写译码 | 五类字段改为逐行事件选择，最后事件优先，树叶至多 32 位；保留早期地址 < 通道地址 < 分配、同通道 wake 晚于 data、恢复响应年龄过滤及 allocation 最后写入 | 不新增寄存位或周期；其他标志命令暂沿用原过程 |
| RS 发射数据 AI | 并行排名后的选择仍直接驱动整包 231 位数据 | ready/rank 完全沿用；选中信号按 32 位分发，数据以二叉 OR 汇合，仍包含同拍 CDB value 旁路 | 不新增寄存位或周期；不是提前唤醒 |
| 前端队列 AJ | 队头独热位跨四个读通道驱动全部 payload；写选择驱动 120 位 | 按读通道/字分发队头选择；读数据二叉 OR，写入使用有最后通道优先级的事件选择及逐字保持 | 不新增寄存位或周期；原响应同拍接续请求已存在，未重新作为优化宣称 |
| 译码队列 AK | 只有一束容量，容量公式含下游同拍消费量，传播 reverse ready | 容量变为两束，上游空位只取寄存 count；原 enqueue/dequeue 和有效性优先级保留；队头读按字选择 | 当前配置增加 776 个 payload 位及 3 个 pointer/count 位；不新增流水级 |
| ALU 生命周期 AL/AM | 宽结果/预测字段接受 reset/flush；无效旧 branch flag 可以占用 redirect 仲裁 | 有效位/shift 控制负责失效，数据只在原接受或移位边沿写入；逐字保持；空结果槽不参与 redirect 仲裁 | 不新增寄存位或执行周期；无效 payload 不再保证为零，接收端需遵守 valid |
| 后端映射 AN | R/D 的集中写入和 payload 复位重新汇聚控制；非当前参数下的字段混在一起 | R 元数据与 D 的 ROB→LSQ、LSQ→physical 表逐行拥有，分域广播、最后通道优先；当前 RS inline 模式只保存仍使用的 mem size，PREDICTOR_META=0 的历史恒零；load error 保留复位并增加 ROB 有效代数过滤 | 不增级或状态；无效 payload 不再保证复位为零 |
| LSQ 标志 AO | 五个宽字段以外的 20 类窄字段仍由一个全局命令过程控制 | 每行拆成静态分配、就绪、生命周期三组；mode/event 分发后判年龄/代数；保留 recovery 的 AGU/data/wakeup/ACK/旧响应、committed store 与 retired load 例外、pop 和分配最后写 | 不增级或寄存位；移除中央 metadata 写命令 |
| PRF 查询 AP | 读查询控制树只有一个出口，仍驱动 64 行译码；word select 同时控制 data/ready | 四个 word 查询域及独立 bypass 查询，data 与 ready 分开选择，显式二叉 OR；WB 仍最高通道优先并保持同拍旁路，P0 恒零/ready，越界结果沿用零/不就绪 | 不增级或寄存位 |
| Icache MSHR AQ | PC/line/epoch 的 reset 与更新选择控制整包数据 | payload 按 demand merge/new demand、sequential prefetch、control prefetch 事件拥有；merge 只更新 PC/demand epoch，不改变旧事务 line/txn epoch；scalar valid/sent/prefetch 原优先级保留 | 不增级或寄存位；owner 可 flatten 剪除常数位 |
| producer 数据 AR | producer valid 在 completion 选择之前再次驱动 57–151 位的清零 mux | retained tag/phys/value/address/target/store-data 直接跟随各源，valid/target-live/窄 metadata 沿用原仲裁与代数过滤；completion 与 wake 接收前检查有效位 | 不增级或寄存位；无效数据无需清零 |
| LSQ 上报/准入 AS | 以 head+scan 串行选择完成 load；store match 按 physical slot 串行编码 | 完成 load 以最小队列年龄做平衡选择，store admission 保留最低 physical slot 优先；report/ACK 的数据独热选择后二叉 OR；保留越过等待 committed store 的 load 上报与 head ACK/pop | 不增级或寄存位；无效输出仍为零 |
| 控制负载预算 AT1 | 每叶 32 个消费者并不保证弱驱动输出电容合规 | 公共 word/event owner、RS 分配/发射、ROB 分配/完成、completion、PRF、前端/译码、issue FIFO、free bitmap、LSQ report/ACK 和 Icache response 的主要 payload 组收紧到 16 位；RV32 数据宽度不变 | 不增级或数据寄存位；分发门数量增加，面积与实际 cap/slew 待测 |
| RS 唤醒 AU1 | 同一 wake data 位跨 12 行、两操作数的 first/last 选择广播 | 每个 wake 域最多四行，valid/tag/value 分域；四种 first/last mux 使用有界选择及二叉 OR；保留重复标签时 first 同拍旁路与 last 时钟写入的区别 | 不增级或寄存位；仍是结果到达时唤醒 |
| cache 状态 AV | Icache valid/LRU 集中复位；Dcache bank reset 和 MSHR 128 位清零仍过载 | Icache valid/LRU 逐行 reset/refill/hit 事件，refill 晚于 hit；Dcache row/set/query reset 分域，MSHR 按字节 zero>write>merge owner，保留 reset-to-zero | 不增级或寄存位；全部 SRAM 类型/容量/接口不变 |
| Icache 控制 AW1 | 响应 PC/line/epoch/error 与预取地址仍受集中复位和宽条件更新 | 原边沿的 payload owner：hit<memory response，step<new stream<control stream；valid/active 保留失效规则；prefetch_remaining 按参数范围用带符号窄计数，负参数保留 32 位行为 | 不增级或寄存位，部分计数位可剪除；无效响应 payload 需遵守 valid |
| 分支捕获 AX | 顺序扫描分支后，同一条件保存整个恢复包 | 并行判断 accepted/live redirect，显式最低通道优先，88 位当前有效恢复包逐字拥有；有预测历史时同拍捕获；无消费者的旧字段删除，不计为物理节省 | 不增周期/状态，invalid payload 不复位 |
| 映射读取 AY | ROB→LSQ/LSQ→physical 仍用动态数组读 | 查询最多四行一个域、16 位选择叶及二叉 OR；地址/数据更新共享读取 | 不增周期/状态，代数接收规则不变 |
| Dcache MSHR payload AZ1 | demand/mask/victim 字段受集中复位和动态写控制 | demand、16 位 mask、victim descriptor、128 位 victim data 原边沿事件 owner；保留提升、部分合并、分配及 deferred SRAM capture 的覆盖顺序 | 不增周期/状态；完整分配后 valid 才可消费 |
| Dcache waiter BA | 二级 miss 等待项的元数据和 128 位行数据集中修改 | 每行拥有 allocate/local fill/memory fill/consume 事件；数据、错误及 valid/ready 分开更新；未使用的 store waiter 标志恒零 | 不增周期/状态；memory response 仍为最后 writer |
| Dcache MSHR lifecycle BB | sent/valid/RFO offered/merge delay 控制与宽写入混在中央过程 | 逐行分域生命周期，保留 decrement<offer<promote<demand<prefetch<send<local fill<response；成功 victim writeback 只清 writeback、保留需求事务 | 不增周期/状态；旧 STATIC_UPDATES 分支保留 |
| Dcache 响应 BC | hit/forward/waiter/refill 公共事件选择整包数据 | metadata、160 位 line/word、deferred size 及 ACK 原边沿 owner；保留 SRAM copy<hit<forward<waiter<failed writeback/demand response 顺序 | 不增周期/状态，bypass/valid/backpressure 不变 |
| 独立加法器 BD | ALU 运算前先通过 opcode 选择 PC/src1、立即数/src2，再进行加法 | PC+imm 负责 branch/JAL/AUIPC，src1+imm 负责 AGU/JALR/ADDI，src1±src2 负责 ADD/SUB；SUB 极性分域；选择移到运算结果之后 | 不增周期/状态；当前四通道源码多八个 32 位加法网络，组合面积待测 |
| cache 选择 BE | MSHR/waiter 状态按编号串行扫描；第二空槽依赖之前找到的第一槽 | 二叉树同时合并每半区的前两项，发送/匹配/等待项使用相同的最低编号规则；send lock 最终覆盖新选择 | 不增周期/状态；原序号及锁定身份保持 |
| cache 数据读取 BF1 | 动态索引驱动宽数组 mux，发送有效和 victim bypass 再控制 128 位输出 | send/matching/local/response/waiter query 四行一域、16 位独热选择后二叉 OR；memory write data 和 line address 最终选择也分到 16 位 | 不增周期/状态；完整 response ID 不允许越界别名 |
| cache 输出 BG | hit/deferred SRAM/held response 选择信号直接驱动 line/word/tag/address | 最终响应和 ACK 按 16 位分发选择，保留 hit 优先、deferred size 身份及持有响应 | 不增周期/状态 |
| 后端恢复路由 BH | branch_pending 直接选择四通道 ROB completion 和分支 link PRF 数据 | 分通道及 16 位选择叶；lane0 恢复分支，其他 lane 顺移已接受 CDB 来源；保持旧零填充、error/mask 及有效值 | 不增周期/状态；正常 CDB 路由不变 |
| Dcache 查询 BI | query 入口仍是 32 位写组；SRAM 保存/同拍回填覆盖控制整行 | 入口 payload 与 index owner 16 位写组，hold copy<forward 事件逐 way 拥有；held/live lookup 及数据 way 选择也分域；response query 使用完整 8 位 ID | 不增周期/状态；same-edge byte merge/tag forwarding 与 deferred read 保持 |
| AXI payload BJ | 行事务与响应 FIFO 的集中宽写入 | read descriptor、128 位收数、184 位 write packet、FIFO 元数据/数据分别原边沿拥有；响应 push 按事件选择，队头读分组 | 不增周期/寄存位，counts/credits 保持 |
| AXI lifecycle BK1 | 动态 slot 写 valid/sent/received/error，与全局队列更新混合 | 原边沿逐行状态，alloc<send<return<reply 顺序；word queue slot/word payload owner；AW/W 对应关系保留 | 不增周期/寄存位，只复位有效性 |
| AXI arbitration BL | 从 cursor 开始逐项扫描，读写完成扫描依赖前一结果 | upper/wrap 同时最低编号查找；原 prefer_write、response slot space 与读写仲裁不变 | 不增周期/寄存位 |
| AXI query BM | 先选整条 write line，再可变 shift 取 word | issue/reply/return 分字段有界查询；直接按 slot+word 读 36 位 data/mask；输出按 16 位 mask，原 address 加法保持 | 不增周期/寄存位 |
| 内存与 MDU BN | 本地错误标志选择 128 位响应；按通道顺序选择 MDU 整包 | 错误记录原边沿拥有、响应 16 位选择；MDU 最低有效 lane 并行选择后有界路由 | 不增周期/寄存位 |
| ROB query BO | live/generation 与 completion metadata 多处重复动态查表 | 四行一域查询；ALU training 复用对应 producer live，LSQ error 复用其 live；normal/shifted CDB 共享 size/error | 不增周期/寄存位，raw tag 输入不依赖过滤结果 |
| store probe BP | 选完 store 后重复查找 RS，立即数又再匹配一次 | 在原 LSQ×RS 匹配矩阵并行得出每条 store 的最低 RS 编号；选择 store 时一起带出编号，基址/立即数共用 | 不增周期/寄存位，oldest eligible store/lowest RS 策略保持 |
| 分支反馈 BQ | accepted branch 逐通道选择宽反馈包 | 同一最低通道策略，宽数据 16 位叶；legacy 元数据与 history 查询仅在对应参数下生成 | 不增周期/寄存位，正常模式反馈值保持 |
| RS chronology BR | 缓存数字年龄结果，但分配仍需新旧年龄比较及计数器 | 直接在分配时更新相对入站顺序；当前复用 66 个关系位，数字年龄 96 位及 8 位计数器不再消费，可剪除；旧 0/1 模式保留 | 不增级；回绕/相等年龄时调度策略改变，IPC 待测 |
| barrel shift BS | 移位量及算术 fill 控制整组 mux | 五个组合级，每个 amount 叶最多 16 位；右移共享 logical/arithmetic 网络；immediate/register 仍分开，避免增加前置 amount mux | 不增执行周期/寄存位；逻辑网络变化，映射面积待测 |
| ALU result BT | opcode case 的结果、目标、地址与 store fallback 形成宽公共选择 | 互斥 opcode 类并行结果路由，branch target/next PC、AGU mask、store fallback 分到 16 位；互斥类不额外计算 last-event prefix | 不增执行周期/寄存位；公共事件 owner 的默认优先级保持 |
| RS final operand BU | wake 数据已分组，但 stored/first-wake 最后选择仍为 32 位公共条件 | 两个 16 位最终选择，ready OR 独立；同拍 first wake、时钟写入 last wake、legacy 参数路径保留 | 不增执行周期/寄存位 |
| frontend BV | prefix/count 影响宽 bundle 数据，响应 word 用可变 shift 查询 | raw lane 数据并行构成，count 决定接受；四 word 有界读、逐 lane next-PC、公开 fetch packet 16 位 mask | 不增级/数据位；跨 line index 保留 3 位，不回绕 |
| frontend/dispatch BW | PC/epoch 与 chain PC 的集中宽写入，dispatch live 动态查询 | PC/epoch 原边沿 word owner；chain PC 分组；count 收窄至 0..FE_WIDTH；dispatch ROB live/gen 四行一域 | PC reset=0 保留；不增级/数据位 |
| one-hot BX | 已独热的 grant 再计算 last-event prefix | 11 处有显式唯一选择证明的路由使用 PRIORITY=0；真正可重叠写入保留默认 PRIORITY=1 | 不增级/数据位 |
| physical wake BY1 | 每个 RS source 用 17 位 ROB producer tag，需要 PRF→producer-tag 查表 | source/wake 独立 SOURCE_TAG_WIDTH；当前用物理编号+valid 共 7 位；完整 ROB tag 继续过滤结果生命周期 | RS 源标签逻辑宽度少 240 位；producer-tag 表不再消费，映射剪除待测 |
| RS operand write BZ | 最终 operand 写入与 allocation/wake 选择仍驱动 32 位 | 每个 operand 两个 16 位数据选择与 hold owner；allocation 优先于 wake | 不增级/数据位；原 ready/kill/flush 时刻 |
| direct producer wake CA | 生产者与其 CDB 副本重复唤醒，CDB 仲裁串回 RS | 当前直接完成模式只广播 6 个独立 live producer，原为 10 路；独立物理目标使 match 独热，无 first/last prefix，数据只选一次 | 不增级/数据位；queued/legacy 模式保留原总线和优先级 |
| predictor rows CB | BHT/BTB 集中动态写入和宽 reset/update，表读复用大 mux | BHT 与 BTB 行拥有原状态，四行一域查询/反馈；BTB payload hold 16 位；统计计数的 reset/write 分组 | 原弱 taken reset、饱和、trained、BTB 同拍更新保持 |
| prediction/RAS CC | predictor opcode 宽目标选择，RAS 宽 reset/动态写，return override 驱动整字 | 4 个互斥目标类；RAS 行 payload owner，count=0 屏蔽无效旧值；word query 与 return target 覆盖有界 | 不增级/数据位；RAS full overwrite 与 pop 规则保持 |
| outer prediction CD | bank rotation 的动态 32 位目标 mux，RAS 返回 PC 先选再 +4 | 38 位 bank packet 分组读；每 lane PC+4*(lane+1) 并行，首个 accepted call 的地址 16 位选择 | 不增级/数据位；FE_WIDTH 1/2/4 的 bank 路由保持 |

Icache 响应数据的单独 owner Q 也已继承，保留 SRAM 上拍复制与当前活跃内存响应覆盖的优先级。当前没有采用 R 的空队列直通查询。普通整数主路径沿用之前的取指查询边界；S→AA 不新增普通流水级，AB 只增加乘法器内部级，AD 再增加 R→D 真实边界。

## 静态推理的边界

原课程脚本先读准备后的 RTL，再读 Liberty，所以直接定义 ASAP7 单元名不可行。当前反相器使用项目自身模块名、完整逻辑，没有 blackbox/whitebox、面积属性、伪 SRAM 或 `$` 外部单元。固定版本 Yosys 的 flatten 源码明确保留 `keep_hierarchy`，opt_merge 对两个具有 keep 的实例不合并。课程 area_report 会递归计入普通子模块里的实际 ASAP7 叶单元。对应 [Yosys 官方层次文档](https://yosyshq.readthedocs.io/projects/yosys/en/stable/cmd/index_passes_hierarchy.html)。这是选择实现方式的源码依据，不能替代最终网表检查。

RS 并行分配依据：空槽 i 前的空槽数为 k 时，它正是第 k 个空槽；通道之前已接受 k 项时，它应取得该槽。free_count/accepted-prefix 原协议保证有足够空槽。空闲池补充采用相同排名关系，分组相加不改变第 k 个最低编号。

除法器依据：正常迭代有 0≤R<D、D>0；令 X=4R+b，b 是接下来两位，则 0≤X<4D。最高的 q∈{0,1,2,3} 满足 X≥qD，且 0≤X−qD<D。因此三次试减可并行；35 位差的最高位表达借位。奇数有效位的最后一拍只处理一位，沿用 q∈{0,1}。除零、溢出、符号处理、缓存和事务取消沿用原协议。尚未运行验证。

面积尚未知。寄存位与源码实例数只是逻辑规模，不能代替剪除后标准单元及 SRAM 总面积；也不能保证面积/IPC ±10%。

AD 的单束派发包增加 712 个逻辑寄存位，AK 的额外译码容量增加 779 位。这两项合计 1491 位，尚未计算跨边界剪除。AH/AI/AJ/AL 及 AN→BI 不增加数据寄存位或流水级；控制分发会增加映射门，也会改变/删除原共享 mux 与 reset 逻辑，不能只按新增实例估算总面积。

直接阅读固定课程 INVBUF Liberty：INVxp33/INVxp67 最大输出电容均为 23.04 fF，INVx1 为 46.08 fF。若实际叶驱动选到前两者，则 32 个消费者的平均输入电容需不超过 0.72 fF 才符合该负载上限。源码限制消费者数只是设计预算，不能证明实际 cap/slew 或 ABC 选择的驱动规格；最终必须检查原课程映射网表和 STA。此次只读取库文本，没有运行任何 EDA。继续读到 NAND2x1 的 A/B 输入电容约为 0.990183/0.990331 fF：32 个该类输入为 31.685856/31.690592 fF，超过弱 INV 的 23.04 fF 上限；16 个为 15.842928/15.845296 fF。这是 AT1 收紧分组的具体库依据。其他映射单元、极性共享、实际消费者数及寄生仍未知，不能据此宣称网表已满足负载。只读数值记录见 [控制负载预算](E:/Verilog_cpu/reports/frequency_control_budget_2026-10-04.json)。

BOOM 的官方 issue 文档把 ALU 快速唤醒与可用旁路数据相联系，把 load/可变延迟完成视为慢唤醒。[BOOM Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)。当前 RS 保存 operand value，并直接从它执行；不能简单提前置 ready 而让值晚到一拍。后续若改元数据发射/PRF 读取，需要同步设计数据旁路、反压和取消规则。当前 AI 仅改宽数据选择，不宣称采用 BOOM 的快速唤醒。

## 有效实测与旧批次状态

唯一完整同规范基线仍是 **32.3978865441 MHz、IPC 0.98012794065、含 SRAM 面积 46309.6934939443 µm²**。

L1 六项原课程 perf 输出匹配，IPC **0.8004591469676289**，下降 **18.3312%**，不满足 ±10%。L1 综合在 RAM 检查被拒绝，**没有频率和面积结果**。原后台已经结束，19 项 correctness 最终 **16 passed / 3 failed**，pi/qsort/tak 均到百万周期上限；尚不能将超时直接定性为死锁。详细历史见 [测量记录](E:/Verilog_cpu/reports/frequency_batch_measurement_2026-10-04.md)。结果只属于 L1 快照，不能作为 CD 的结果。继承的 AM 仲裁修复也未被证明是旧超时的根因或修复。

## 本轮源码推理

AX 的匹配条件包含 !reset、!flush、!branch_pending、ALU valid/ready、ROB generation live 与 redirect。最低编号匹配获得 one-hot grant，因此与旧 ordered capture loop 选择同一分支；包与 pending 在原时钟边沿一起保存。已删除 source PC/kind/taken/prediction 等无消费者的 pending 字段，它们旧版也会被综合剪除，不能作为已节省的映射面积。

MSHR demand/mask/victim 字段在 new demand 或 prefetch 分配时完整初始化。promote 只修改旧实现允许修改的 demand 字段，store merge 只合并 mask/data；victim 的同步 SRAM 捕获仍可在下一拍完成，发送仍有原 victim_from_sram 旁路。waiter allocation 初始化 descriptor/error 并清 ready，line 在 fill 置 ready 的同一边沿写入；valid/ready 为消费门槛。上述说明针对合法事务，无效总线数据不要求归零，仍须后续统一验证所有消费点。

BE 二叉节点合并左右区的前两项：第一项取左第一项（存在时），第二项依次取左第二项、右第一项（左恰有一项时）、右第二项（左为空时）。索引区间天然按大小排序，因此递归合并得到原最低两个空槽。send_locked 保持最高选择优先级；此推理不是仿真/形式证明。

BD 不改变 RV32 算术结果：原操作码选择的两个加数，改为对应固定网络的加数，取低 32 位；SUB 仍为 src1+~src2+1，JALR 仍清 bit0，branch compare 与预测纠正条件不变。[Ibex 官方集成说明](https://ibex-core.readthedocs.io/en/latest/02_user/integration.html)提供独立 branch target ALU 的设计实例。该资料讨论其分支性能作用；当前项目将它用于移除前置 operand mux 的频率推断，不能引用 Ibex 的结果证明本项目收益。

BH 保持所有旧 completion 输出值：正常模式沿用同编号 CDB；恢复 lane0 送 pending branch；其他可用 lane k 送 accepted source k−1，未接受的 shifted packet 为零；越界 slot 保持 tag/value 而清旧实现规定的 store/error 字段。PRF 分支 link 只占 CDB_WIDTH−1 的旧保留写口。

BI 保持 SRAM copy 早于同拍 forwarding；forward 的基底仍是 query_data_from_sram 为真时的原始 bank_rdata，否则是旧 bank_hold。只转换 payload 的读写所有权，query valid/deferred 状态边沿不变。8 位 memory ID 全部进入查询比较，不以低 3 位别名到一个活跃 MSHR。

准备工具的源文本审查曾发现 AZ 的残留赋值判断误匹配外围数组写、BF 的字段替换可能误改 legacy 字段名；已分别修正为 AZ1、BF1，再继承到 BI。旧失败/被舍弃目录未并入工作树。人工查文本与 SHA 一致性不能替代 RTL 编译、正确性和 STA。

## 本批 BJ→BU 源码推理与取舍

本批没有新增流水级或数据寄存位，普通整数路径仍为十级。唯一主动改变调度策略的 BR 使用相对入站顺序；其他改动以保留原合法事务、接受边沿、反压和覆盖顺序为目标。源码目标不是等价验证结果。

AXI 保持 read/write allocation、每 word 发出/返回以及最终 response FIFO push 的时刻。read metadata 为 41 位，write packet 为 184 位，D response packet 为 169 位；FIFO head/tail/count 和 response space 未改变。发送仍先选 cursor 以上最低 eligible slot，再回绕；读写完成仍采用原 prefer_write 与各自容量规则。AW 和 W 必须同时完成才 push 对应 write word，两个通道独立完成标志保持原样。BK 初版文本提取器未处理嵌套 rq_slot[rq_head]，已以 BK1 修正后继承；失败目录未并入。没有新 RTL 编译。

BO 的 raw producer query 按 {LSQ,MDU,ALU} 排列，与原 [0..BE_WIDTH−1,MDU_SOURCE,LSQ_SOURCE] 对齐。valid/generation 读不经 producer qualification 输出再返回该组合过程；避免人为制造异步查询的过程依赖环。ALU training 复用同一 ALU query，error response 复用原 LSQ tag query，接受条件仍含原 tag valid、ROB valid/generation 与需要的 slot 范围判断。

BP 已有完整 store/RS tag 匹配矩阵。对每条 store 先得到最低 ready RS index，再随最老 eligible store 的 tag 一起选择；这与选 tag 后重新比较等价于选择同一合法匹配行。基址与立即数共享 selected RS，消除了重复比较的串行依赖。无效输出无需构成合法地址，shared_store_addr_valid 仍检查 reset/flush/pending/tag/ROB generation。

BR 对两个物理行 L<H 保留关系位 L precedes H：两行都不分配时保持；只分配 L 时写 0；只分配 H 时写 1；两行一起分配时写 1。静态分配把第 k 个 accepted lane 给第 k 个递增 free row，因此同束低行更早。对不同边沿，新行晚于所有仍有效旧行；flush/issue 只删除行，不改存活关系。新分配会覆盖与所有旧行的关系，所以两个有效行的关系已经初始化，pair bits 无需 reset；invalid row 的 ready=0 排除其关系。当前 12 行继续用 66 个关系位，旧 12×8+8=104 个逻辑年龄位已不再消费；综合是否全部剪除及物理面积仍未知。此方案保持真正入站时间顺序，主动放弃数字回绕后的旧 unsigned-age 优先级，不能宣称 IPC 等价或已经改善。

BS 第 s 个组合级选择位移 2^s，五级累加产生低五位 amount 的 0..31 位移。左边界填 0；右边界在每级填同一个 arithmetic sign 或 0，因此 logical/SRA 值保持 RV32 定义。immediate/register amount 未提前合并，SHIFT_IMPL=1 仍从原 src1 开始逐拍移位。源码每叶最多 16 个数据位，不等于已确认映射 pin 电容。

BT 16 个 value class 覆盖原 24 个 calc_value 赋值位置所定义的整数结果，其中 ADD/SUB、JAL/JALR、SRL/SRA 成组，SLT 家族只产生 bit0；load/store/conditional branch 结果值仍为零。branch target 为 conditional/JAL 的 PC+imm 或 JALR 的 (src1+imm)&~1，next PC 还包含 conditional not-taken 的 PC+4。redirect 条件、mem size/unsigned、store_data==0 时取 rs2 的约定保持。PRIORITY=0 仅用于已知互斥 opcode/branch-next 类，其他已有事件选择器仍默认最后事件优先；字段不再由同一过程写后经外部选择器读回。

BU 的 ready 为 stored_ready OR wake_match；只有 !stored_ready && wake_match 才取 wake_first value，否则取原 stored value，逐半字实现原选择。时钟更新仍取 wake_last；重复 tag 的旧 first/last 区别没有合并。

## 本批 BV→CD 的源码依据

仍为十级普通整数路径，本批九项没有增加执行或恢复周期。修改在 23 个实现文件中落盘，157 个课程输入已冻结。BY 的首次准备器源文本计数写为 63，人工核对正确库存为 51 后重新生成 BY1；失败的 BY 目录保留，未并入。此计数不是 RTL 编译或测试。

**物理寄存器身份。**rename 为每个仍存活的写指令保留不同物理目标；旧映射只能在替换它的指令顺序提交时回收。使用旧映射的更早读者此时已经提交，更晚读者使用新映射。恢复会删除年轻消费者；存活消费者的映射仍保留。ROB 完整代号的 valid/generation/age 过滤没有缩短，PAW+1 源身份仅用于 RS 唤醒，P0/out-of-range 有效位为 0。当前 12 行、每行 2 source，source tag 的逻辑位数由 12×2×17=408 缩到 12×2×7=168；64-row producer-tag 表不再被选中，但不把逻辑剪除当成实测 FF 或面积。

**直接生产者唤醒。**COMPLETION_BYPASS=1/2 的 CDB packet 是仍有效、持有直到接受的 producer 的组合视图；原总线同时包含这个 producer。删去 CDB 副本后，未选中的 live producer 继续像原逻辑一样唤醒，不依赖 completion_ready。ALU load 的地址结果不作为 rd value 广播，实际 load 由 LSQ 广播；MDU 由独立 producer 广播，redirect branch 的特殊完成路径按原规则排除。每个 live physical destination 只有一个真实 producer，所以物理模式 match 独热，first/last 选词可共用。当前比较器逻辑库存由 12×2×10=240 组 17 位比较，变成 12×2×6=144 组 7 位比较；这不是门数/时延测量。queued 模式仍接 CDB+producer，通用 RS 默认保留重复 tag 的 first/last 行为。需要统一验证寄存器回收、恢复与 held producer 反压下的一致性。

**预测器与 RAS。**BHT counter/训练位保留 reset=2'b10/0 与原饱和规则；BTB valid 复位且 payload 仅同一反馈边沿写入。59 位查询字段为 {valid,tag24,target32,kind2}。四个目标类覆盖 default PC+4、direct branch、JAL、BTB，conditional DIRECT=0/1/2 规则保持。RAS reset 只清 sp/count，count=0 时没有返回预测；count>0 的顶项已由 push 写入，overflow 仍写环形栈并保持 count=4。首个 call/return/taken 事件关闭同一 bundle prefix，call 的返回地址为原 PC+4*(lane+1)。预测器容量未缩小，没有追加预测周期。

这些是人工源码推理，不是仿真或形式验证结论。控制叶的 16 位/四行分组也不是已确认的 Liberty pin load、slew 或频率。

## 本批方案取舍与统一测量边界

当前直接可实施、且有明确逻辑缩短依据的方案已并入。没有再找到同样明确的新改动。仍保留以下条件架构方向；它们需要新的实际关键路径来选择，不能据旧基线猜测收益：

- **将 PRF 读移到发射端。**直接接在 issue FIFO 后会把 PRF read 与 ALU 串联；独立 read stage 会超过当前十级。若移动既有 D 边界并改 metadata-only RS，还要为早期 store probe 保留读取和处理未进 PRF 的 held-producer bypass、任意 FIFO 反压。当前不加入无明确缩短证明的整套 reissue/read 协议。
- **拆 INT/memory/MDU 队列或更换排序网络。**可减少每个分区负载，但当前只有 12 行，分区容量不均会增加 admission stall；新的 tournament 动态关系查询也未必短于已有 chronological pair/rank。先看缩窄后的 RS 是否仍是实际瓶颈。
- **增加流水级或寄存唤醒 ready。**会增加相关链、分支和 load 延迟，超过用户先前 8–10 级范围或进一步损失 IPC；本批没有采用。
- **lookahead fetch、恢复期间提交、左右移位共享。**已有同拍接续取指；新增 epoch/恢复提交需要改变 checkpoint 所有权。bit-reversal 共享 shifter 会增加前后 mux。这些方向不具备当前频率改动的确定依据。

参考原始资料：[BOOM Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)、[BOOM Register Files and Bypass Network](https://docs.boom-core.org/en/latest/sections/reg-file-bypass-network.html)。BOOM 的读寄存器旁路、分队列与动态端口重发射机制用于分析设计约束，不能推导本实现已经达标。

本报告落盘时尚未启动硬件工具。测试前的具体范围与风险见 [CD 测试前报告](E:/Verilog_cpu/reports/frequency_batch_CD_pretest_2026-10-04.md)。不会把旧 32.3979 MHz、L1 的 0.80046 IPC 或任一局部数字归到 CD。


## CD1：内部保留字修复与统一测量继续范围

CD 首次 Windows 原生 Verilator 编译在五个 RTL 文件报告 26 个语法错误，全部为内部名称 `matches` 与 SystemVerilog 保留字冲突。CPU 未生成，没有运行 perf/correctness；综合仍在前期处理时已停止，仅停止经 PID/command line 核对的 CD 进程树，保留 [build.log](F:/CPU2026CourseRuns/architecture_CD_20261004/native_build/build.log)、[synth.log](F:/CPU2026CourseRuns/architecture_CD_20261004/result/synth.log)和 [中断记录](F:/CPU2026CourseRuns/architecture_CD_20261004/interruption.json)。CD 没有 IPC、频率或面积结果。

CD1 只把 27 处完整内部标识符 `matches` 改为 `row_match_mask`，五个文件的端口、方程、状态、参数、边沿和架构均未改。它继续同一批测量范围，没有加入新优化或独立测试。新的 23-file 实现、157-file 冻结输入见 [architecture_CD1_20261004](F:/CPU2026CourseRuns/architecture_CD1_20261004/source_manifest.json)，源码前版本保留在 [pre_CD1](F:/CPU2026Candidates/pre_CD1_worktree_20261004/backup.json)。启动前的完整范围见 [CD1 测试前报告](E:/Verilog_cpu/reports/frequency_batch_CD1_pretest_2026-10-04.md)。
