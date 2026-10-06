"""Record BU source implementation/research only; never run EDA."""
import json
from pathlib import Path


ROOT=Path('E:/Verilog_cpu')
record=json.loads((ROOT/'build/cpu2026/active_frequency_implementation_20261004.json').read_text(encoding='utf-8'))
if record['tests_started'] or Path(record['frozen_run']).name!='architecture_BU_20261004':
    raise ValueError('Preserve adopted untested source identity')

rows='''
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
'''

p=ROOT/'reports/frequency_rtl_restructure_2026-10-04.md'
t=p.read_text(encoding='utf-8')
for old,new in [
    ('当前工作树已更新为 BI 候选，18 个文件并入','当前工作树已更新为 BU 候选，21 个文件并入'),
    ('[architecture_BI_20261004](F:/CPU2026CourseRuns/architecture_BI_20261004/source_manifest.json)',
     '[architecture_BU_20261004](F:/CPU2026CourseRuns/architecture_BU_20261004/source_manifest.json)'),
    ('[pre_BI_worktree_20261004](F:/CPU2026Candidates/pre_BI_worktree_20261004/backup.json)',
     '[pre_BU_worktree_20261004](F:/CPU2026Candidates/pre_BU_worktree_20261004/backup.json)'),
    ('不能作为 BI 的结果','不能作为 BU 的结果'),
]:
    if old not in t: raise ValueError('Missing progress anchor: '+old)
    t=t.replace(old,new,1)
t=t.replace('|\n\n\n| 分支捕获 AX','|\n| 分支捕获 AX',1)
anchor='\nIcache 响应数据的单独 owner Q'
if anchor not in t: raise ValueError('Missing source table')
t=t.replace(anchor,'\n'+rows+anchor,1)
start=t.index('## 仍在研究，因此暂不启动新测试')
t=t[:start]+'''## 本批 BJ→BU 源码推理与取舍

本批没有新增流水级或数据寄存位，普通整数路径仍为十级。唯一主动改变调度策略的 BR 使用相对入站顺序；其他改动以保留原合法事务、接受边沿、反压和覆盖顺序为目标。源码目标不是等价验证结果。

AXI 保持 read/write allocation、每 word 发出/返回以及最终 response FIFO push 的时刻。read metadata 为 41 位，write packet 为 184 位，D response packet 为 169 位；FIFO head/tail/count 和 response space 未改变。发送仍先选 cursor 以上最低 eligible slot，再回绕；读写完成仍采用原 prefer_write 与各自容量规则。AW 和 W 必须同时完成才 push 对应 write word，两个通道独立完成标志保持原样。BK 初版文本提取器未处理嵌套 rq_slot[rq_head]，已以 BK1 修正后继承；失败目录未并入。没有新 RTL 编译。

BO 的 raw producer query 按 {LSQ,MDU,ALU} 排列，与原 [0..BE_WIDTH−1,MDU_SOURCE,LSQ_SOURCE] 对齐。valid/generation 读不经 producer qualification 输出再返回该组合过程；避免人为制造异步查询的过程依赖环。ALU training 复用同一 ALU query，error response 复用原 LSQ tag query，接受条件仍含原 tag valid、ROB valid/generation 与需要的 slot 范围判断。

BP 已有完整 store/RS tag 匹配矩阵。对每条 store 先得到最低 ready RS index，再随最老 eligible store 的 tag 一起选择；这与选 tag 后重新比较等价于选择同一合法匹配行。基址与立即数共享 selected RS，消除了重复比较的串行依赖。无效输出无需构成合法地址，shared_store_addr_valid 仍检查 reset/flush/pending/tag/ROB generation。

BR 对两个物理行 L<H 保留关系位 L precedes H：两行都不分配时保持；只分配 L 时写 0；只分配 H 时写 1；两行一起分配时写 1。静态分配把第 k 个 accepted lane 给第 k 个递增 free row，因此同束低行更早。对不同边沿，新行晚于所有仍有效旧行；flush/issue 只删除行，不改存活关系。新分配会覆盖与所有旧行的关系，所以两个有效行的关系已经初始化，pair bits 无需 reset；invalid row 的 ready=0 排除其关系。当前 12 行继续用 66 个关系位，旧 12×8+8=104 个逻辑年龄位已不再消费；综合是否全部剪除及物理面积仍未知。此方案保持真正入站时间顺序，主动放弃数字回绕后的旧 unsigned-age 优先级，不能宣称 IPC 等价或已经改善。

BS 第 s 个组合级选择位移 2^s，五级累加产生低五位 amount 的 0..31 位移。左边界填 0；右边界在每级填同一个 arithmetic sign 或 0，因此 logical/SRA 值保持 RV32 定义。immediate/register amount 未提前合并，SHIFT_IMPL=1 仍从原 src1 开始逐拍移位。源码每叶最多 16 个数据位，不等于已确认映射 pin 电容。

BT 16 个 value class 覆盖原 24 个 calc_value 赋值位置所定义的整数结果，其中 ADD/SUB、JAL/JALR、SRL/SRA 成组，SLT 家族只产生 bit0；load/store/conditional branch 结果值仍为零。branch target 为 conditional/JAL 的 PC+imm 或 JALR 的 (src1+imm)&~1，next PC 还包含 conditional not-taken 的 PC+4。redirect 条件、mem size/unsigned、store_data==0 时取 rs2 的约定保持。PRIORITY=0 仅用于已知互斥 opcode/branch-next 类，其他已有事件选择器仍默认最后事件优先；字段不再由同一过程写后经外部选择器读回。

BU 的 ready 为 stored_ready OR wake_match；只有 !stored_ready && wake_match 才取 wake_first value，否则取原 stored value，逐半字实现原选择。时钟更新仍取 wake_last；重复 tag 的旧 first/last 区别没有合并。

## 仍在研究，因此暂不启动新测试

1. **发射与 PRF 边界。**现在 allocation-side PRF/tag read 在 D 后写 RS，wake/rank/value select 后写 issue FIFO，之后 ALU 计算。移除 RS operand 存储可以降低写入和唤醒数据负载，但若直接把 PRF read 接到 FIFO 后，会与 ALU 串联；若增加一个 read stage，会成为第十一级并增加 dependency/branch 延迟。需要先给出能移动现有边界、保留同拍旁路与任意 backpressure 的方案，不能直接提前 ready。资料：[BOOM Register Files and Bypass Network](https://docs.boom-core.org/en/latest/sections/reg-file-bypass-network.html)、[BOOM Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)。
2. **独立调度队列/层次选择。**拆 INT、memory、MDU 队列能减少每类比较负载，但会引入 dispatch 端各队列资源保留与 issue lane 绑定，可能在当前 12-entry 配置形成 capacity imbalance。先比较能否缩短实际逻辑链，以及共享/分队列的 IPC 下限；未直接加入。
3. **顶层恢复分发与有效性。**已经切断恢复 preview/apply 和宽 payload reset，并处理最终 mux；继续审查是否在消费者处又汇聚为大的 valid/flush/readiness 控制。普通 counter/head 的分组并不自动证明所有 mapped load 都已合规。
4. **lookahead、恢复期间旧指令推进及 shifter 进一步共享。**frontend 同拍接续和 MSHR prefetch 已有；lookahead 新身份/epoch、commit 改动冻结 checkpoint 假设；带 bit-reversal 的统一左右移位器会增加前后选择级。后两类主要影响 IPC/面积，不因开源项目采用就断言提升本候选频率。继续依据数据和路径预算取舍。

当前 BU 是 21 个实现文件、157 个冻结输入的未测试源码。以上候选准备器只做文本变换、人工阅读和 SHA 身份核对，没有使用编译器、lint、仿真、形式、综合或 STA；没有作业正在测量 BU。Windows 原生课程固定 Yosys/ABC/OpenSTA/Verilator、库、约束和 SRAM 计价保持，不使用 WSL。

本记录不是测试启动报告，也不宣称已经想不出任何更多方案。仍有上面的架构边界需要取舍，所以本轮继续保持不测试。测试前将单独报告最终冻结候选、预期结构变化及风险，并说明统一后台测量范围；届时所有 SRAM 计入面积，Fmax/IPC/面积必须属于同一源码与课程工具身份。
'''
p.write_text(t,encoding='utf-8')

for name in ['frequency_dispatch_stage_design_2026-10-04.md','frequency_batch_measurement_2026-10-04.md']:
    p=ROOT/'reports'/name
    t=p.read_text(encoding='utf-8')
    t=t.replace('当前 BI 已继承','当前 BU 已继承',1)
    t=t.replace('[architecture_BI_20261004](F:/CPU2026CourseRuns/architecture_BI_20261004/source_manifest.json)',
                '[architecture_BU_20261004](F:/CPU2026CourseRuns/architecture_BU_20261004/source_manifest.json)',1)
    t=t.replace('主工作树随后继续更新到独立 **BI 未测试实现**','主工作树随后继续更新到独立 **BU 未测试实现**',1)
    t=t.replace('BI 未启动硬件工具，不能将 L1 IPC 或基线频率视为 BI 的结果。',
                'BU 未启动硬件工具，不能将 L1 IPC 或基线频率视为 BU 的结果。',1)
    p.write_text(t,encoding='utf-8')

p=ROOT/'reports/frequency_control_budget_2026-10-04.json'
budget=json.loads(p.read_text(encoding='utf-8'))
budget['adopted_candidate']=record['candidate']
budget['new_source_grouping']={'RS_order_peer_rows_per_domain':4,'barrel_mux_bits_per_amount_leaf':16,
    'ALU_result_bits_per_select_leaf':16,'RS_final_operand_bits_per_select_leaf':16,
    'statement':'RTL grouping only; no mapped fanout/capacitance/slew measurement'}
p.write_text(json.dumps(budget,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'SOURCE_PROGRESS_UPDATED','candidate':record['candidate'],
                  'implemented_files':len(record['implemented_files']),'tests_started':False},ensure_ascii=False))
