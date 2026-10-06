"""Record adopted source-only BI progress. Never invoke hardware tools."""
import json
from pathlib import Path


ROOT=Path('E:/Verilog_cpu')
record=json.loads((ROOT/'build/cpu2026/active_frequency_implementation_20261004.json').read_text(encoding='utf-8'))
if record['tests_started'] or Path(record['frozen_run']).name!='architecture_BI_20261004':
    raise ValueError('Preserve adopted untested source identity')

p=ROOT/'reports/frequency_rtl_restructure_2026-10-04.md'
t=p.read_text(encoding='utf-8')
t=t.replace('当前工作树已更新为 AW1 候选，18 个文件并入','当前工作树已更新为 BI 候选，18 个文件并入',1)
t=t.replace('[architecture_AW1_20261004](F:/CPU2026CourseRuns/architecture_AW1_20261004/source_manifest.json)',
            '[architecture_BI_20261004](F:/CPU2026CourseRuns/architecture_BI_20261004/source_manifest.json)',1)
t=t.replace('[pre_AW1_worktree_20261004](F:/CPU2026Candidates/pre_AW1_worktree_20261004/backup.json)',
            '[pre_BI_worktree_20261004](F:/CPU2026Candidates/pre_BI_worktree_20261004/backup.json)',1)
t=t.replace('\n\n\n| 后端映射 AN','\n| 后端映射 AN',1)
anchor='\nIcache 响应数据的单独 owner Q'
rows='''
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
'''
if anchor not in t: raise ValueError('Missing implementation table insertion point')
t=t.replace(anchor,'\n'+rows+anchor,1)
t=t.replace('AN→AW1 不增加数据寄存位或流水级','AN→BI 不增加数据寄存位或流水级',1)
t=t.replace('不能作为 AW1 的结果','不能作为 BI 的结果',1)
start=t.index('## 仍在研究，因此暂不启动新测试')
t=t[:start]+'''## 本轮源码推理

AX 的匹配条件包含 !reset、!flush、!branch_pending、ALU valid/ready、ROB generation live 与 redirect。最低编号匹配获得 one-hot grant，因此与旧 ordered capture loop 选择同一分支；包与 pending 在原时钟边沿一起保存。已删除 source PC/kind/taken/prediction 等无消费者的 pending 字段，它们旧版也会被综合剪除，不能作为已节省的映射面积。

MSHR demand/mask/victim 字段在 new demand 或 prefetch 分配时完整初始化。promote 只修改旧实现允许修改的 demand 字段，store merge 只合并 mask/data；victim 的同步 SRAM 捕获仍可在下一拍完成，发送仍有原 victim_from_sram 旁路。waiter allocation 初始化 descriptor/error 并清 ready，line 在 fill 置 ready 的同一边沿写入；valid/ready 为消费门槛。上述说明针对合法事务，无效总线数据不要求归零，仍须后续统一验证所有消费点。

BE 二叉节点合并左右区的前两项：第一项取左第一项（存在时），第二项依次取左第二项、右第一项（左恰有一项时）、右第二项（左为空时）。索引区间天然按大小排序，因此递归合并得到原最低两个空槽。send_locked 保持最高选择优先级；此推理不是仿真/形式证明。

BD 不改变 RV32 算术结果：原操作码选择的两个加数，改为对应固定网络的加数，取低 32 位；SUB 仍为 src1+~src2+1，JALR 仍清 bit0，branch compare 与预测纠正条件不变。[Ibex 官方集成说明](https://ibex-core.readthedocs.io/en/latest/02_user/integration.html)提供独立 branch target ALU 的设计实例。该资料讨论其分支性能作用；当前项目将它用于移除前置 operand mux 的频率推断，不能引用 Ibex 的结果证明本项目收益。

BH 保持所有旧 completion 输出值：正常模式沿用同编号 CDB；恢复 lane0 送 pending branch；其他可用 lane k 送 accepted source k−1，未接受的 shifted packet 为零；越界 slot 保持 tag/value 而清旧实现规定的 store/error 字段。PRF 分支 link 只占 CDB_WIDTH−1 的旧保留写口。

BI 保持 SRAM copy 早于同拍 forwarding；forward 的基底仍是 query_data_from_sram 为真时的原始 bank_rdata，否则是旧 bank_hold。只转换 payload 的读写所有权，query valid/deferred 状态边沿不变。8 位 memory ID 全部进入查询比较，不以低 3 位别名到一个活跃 MSHR。

准备工具的源文本审查曾发现 AZ 的残留赋值判断误匹配外围数组写、BF 的字段替换可能误改 legacy 字段名；已分别修正为 AZ1、BF1，再继承到 BI。旧失败/被舍弃目录未并入工作树。人工查文本与 SHA 一致性不能替代 RTL 编译、正确性和 STA。

## 仍在研究，因此暂不启动新测试

1. **后端剩余 ROB 状态查询。**完成错误/访存 size、producer/branch generation live 仍有动态 slot 查询，需考虑共享、局部查询译码和 16 位选择，而不把新比较器加回 ready 反馈链。
2. **存储接口控制与算术选择。**继续核对 AXI/内存桥、MDU 选择和 Dcache/LSQ 最终输出是否还有公共条件控制宽数据；优先处理源码上明确的大负载。
3. **执行端 PRF/快速唤醒的架构取舍。**[BOOM Register Files and Bypass Network](https://docs.boom-core.org/en/latest/sections/reg-file-bypass-network.html)提供寄存器读取/旁路分界，[BOOM Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)说明 fast wakeup 与及时旁路值的关系。当前 RS 存 operand value，issue FIFO 可变驻留，不能直接提前 ready。需要决定是移动已有边界还是增加级，以及 stall/reissue/kill 规则；尚未认定这条大改会提高当前候选频率。
4. **lookahead 与恢复期间推进。**现有 frontend response 同拍 chain request 已存在，预取也已有独立 MSHR；新 lookahead 需要预测和请求身份。恢复期间放开旧执行需要年龄过滤，commit 推进还会改变 head/occupancy/RAT checkpoint 的冻结假设。继续作取舍，不宣称已穷尽所有方案。

AD 派发边界及 AN→BI 均已经并入主工作树，普通整数主路径仍为十级；本轮 AX→BI 没有增加数据寄存位或流水级。保持原课程固定版本 Windows 原生 Yosys/ABC/OpenSTA/Verilator、库、脚本与约束，全部 SRAM 计入面积，不使用 WSL。18 个实现文件、157 个冻结课程输入只是源码身份，不是正确性或性能认证。

下一次测试前会单独汇报最终候选、改动及组合面积/IPC取舍、需要核对的路径和后台测量范围。当前仍是源码进展记录，不是测试启动通知；BI 的 Fmax、IPC、总面积均未知。
'''
p.write_text(t,encoding='utf-8')

p=ROOT/'reports/frequency_dispatch_stage_design_2026-10-04.md'
t=p.read_text(encoding='utf-8').replace('当前 AW1 已继承','当前 BI 已继承',1)
t=t.replace('[architecture_AW1_20261004](F:/CPU2026CourseRuns/architecture_AW1_20261004/source_manifest.json)',
            '[architecture_BI_20261004](F:/CPU2026CourseRuns/architecture_BI_20261004/source_manifest.json)',1)
p.write_text(t,encoding='utf-8')

p=ROOT/'reports/frequency_batch_measurement_2026-10-04.md'
t=p.read_text(encoding='utf-8').replace('主工作树随后继续更新到独立 **AW1 未测试实现**','主工作树随后继续更新到独立 **BI 未测试实现**',1)
t=t.replace('AW1 未启动硬件工具，不能将 L1 IPC 或基线频率视为 AW1 的结果。',
            'BI 未启动硬件工具，不能将 L1 IPC 或基线频率视为 BI 的结果。',1)
p.write_text(t,encoding='utf-8')

p=ROOT/'reports/frequency_control_budget_2026-10-04.json'
budget=json.loads(p.read_text(encoding='utf-8'))
budget['adopted_candidate']=record['candidate']
p.write_text(json.dumps(budget,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'SOURCE_PROGRESS_UPDATED','active':record['candidate'],'tests_started':False},ensure_ascii=False))
