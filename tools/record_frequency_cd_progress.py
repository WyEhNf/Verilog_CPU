"""Record CD source batch and its premeasurement report; never invoke EDA."""
import json
import re
from pathlib import Path


ROOT=Path('E:/Verilog_cpu')
record=json.loads((ROOT/'build/cpu2026/active_frequency_implementation_20261004.json').read_text(encoding='utf-8'))
if record['tests_started'] or Path(record['frozen_run']).name!='architecture_CD_20261004':
    raise ValueError('Record only the newly frozen, untested CD source')

rows='''
| frontend BV | prefix/count 影响宽 bundle 数据，响应 word 用可变 shift 查询 | raw lane 数据并行构成，count 决定接受；四 word 有界读、逐 lane next-PC、公开 fetch packet 16 位 mask | 不增级/数据位；跨 line index 保留 3 位，不回绕 |
| frontend/dispatch BW | PC/epoch 与 chain PC 的集中宽写入，dispatch live 动态查询 | PC/epoch 原边沿 word owner；chain PC 分组；count 收窄至 0..FE_WIDTH；dispatch ROB live/gen 四行一域 | PC reset=0 保留；不增级/数据位 |
| one-hot BX | 已独热的 grant 再计算 last-event prefix | 11 处有显式唯一选择证明的路由使用 PRIORITY=0；真正可重叠写入保留默认 PRIORITY=1 | 不增级/数据位 |
| physical wake BY1 | 每个 RS source 用 17 位 ROB producer tag，需要 PRF→producer-tag 查表 | source/wake 独立 SOURCE_TAG_WIDTH；当前用物理编号+valid 共 7 位；完整 ROB tag 继续过滤结果生命周期 | RS 源标签逻辑宽度少 240 位；producer-tag 表不再消费，映射剪除待测 |
| RS operand write BZ | 最终 operand 写入与 allocation/wake 选择仍驱动 32 位 | 每个 operand 两个 16 位数据选择与 hold owner；allocation 优先于 wake | 不增级/数据位；原 ready/kill/flush 时刻 |
| direct producer wake CA | 生产者与其 CDB 副本重复唤醒，CDB 仲裁串回 RS | 当前直接完成模式只广播 6 个独立 live producer，原为 10 路；独立物理目标使 match 独热，无 first/last prefix，数据只选一次 | 不增级/数据位；queued/legacy 模式保留原总线和优先级 |
| predictor rows CB | BHT/BTB 集中动态写入和宽 reset/update，表读复用大 mux | BHT 与 BTB 行拥有原状态，四行一域查询/反馈；BTB payload hold 16 位；统计计数的 reset/write 分组 | 原弱 taken reset、饱和、trained、BTB 同拍更新保持 |
| prediction/RAS CC | predictor opcode 宽目标选择，RAS 宽 reset/动态写，return override 驱动整字 | 4 个互斥目标类；RAS 行 payload owner，count=0 屏蔽无效旧值；word query 与 return target 覆盖有界 | 不增级/数据位；RAS full overwrite 与 pop 规则保持 |
| outer prediction CD | bank rotation 的动态 32 位目标 mux，RAS 返回 PC 先选再 +4 | 38 位 bank packet 分组读；每 lane PC+4*(lane+1) 并行，首个 accepted call 的地址 16 位选择 | 不增级/数据位；FE_WIDTH 1/2/4 的 bank 路由保持 |
'''

proof='''## 本批 BV→CD 的源码依据

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
'''

p=ROOT/'reports/frequency_rtl_restructure_2026-10-04.md'
t=p.read_text(encoding='utf-8')
t=t.replace('当前工作树已更新为 BU 候选，21 个文件并入','当前工作树已更新为 CD 候选，23 个文件并入',1)
t=t.replace('[architecture_BU_20261004](F:/CPU2026CourseRuns/architecture_BU_20261004/source_manifest.json)',
            '[architecture_CD_20261004](F:/CPU2026CourseRuns/architecture_CD_20261004/source_manifest.json)',1)
t=t.replace('[pre_BU_worktree_20261004](F:/CPU2026Candidates/pre_BU_worktree_20261004/backup.json)',
            '[pre_CD_worktree_20261004](F:/CPU2026Candidates/pre_CD_worktree_20261004/backup.json)',1)
t=t.replace('不能作为 BU 的结果','不能作为 CD 的结果',1)
anchor='\nIcache 响应数据的单独 owner Q'
if anchor not in t: raise ValueError('Missing implemented table anchor')
t=t.replace(anchor,'\n'+rows+anchor,1)
start=t.index('## 仍在研究，因此暂不启动新测试')
t=t[:start]+proof
t=re.sub(r'(\|[^\n]*\|)\n(?:[ \t]*\n)+(?=\|)',r'\1\n',t)
p.write_text(t,encoding='utf-8')

pretest='''# CD 统一后台测试前汇报

本报告先于测量启动落盘。当前工作树采用 CD；本批 BV→CD 九项和此前 S→BU 的全部结构改动共同冻结于 [architecture_CD_20261004](F:/CPU2026CourseRuns/architecture_CD_20261004/source_manifest.json)，23 个实现文件、157 个课程输入，原工作树版本保留在 [备份](F:/CPU2026Candidates/pre_CD_worktree_20261004/backup.json)。

已完成的主要变化是：保持十级，RS physical wake tag 17→7 位、wake source 10→6 路，移除 CDB 仲裁到 RS 的重复唤醒路径及 first/last 选择；frontend 宽包/PC/count/dispatch 查询缩短；预测器 BHT/BTB/RAS 行拥有原边沿状态，目标与跨 bank 路由按 16 位分组。之前已有恢复 preview/apply、dispatch/issue 边界、相对年龄、CSA 乘法器末级、并行除法准备、LSQ/cache/AXI 控制与宽数据重构。完整解释见 [实现记录](E:/Verilog_cpu/reports/frequency_rtl_restructure_2026-10-04.md)。

质变判断依据是跨级组合依赖被切断、唤醒身份和总线规模直接缩小、原高负载控制分散到最终消费者；没有数值证据保证已经达到 300 MHz。当前没有新的频率、IPC 或面积结果。统一测量用于确认这个完整候选的收益与合法性，不为每项改动运行测试。

## 一次测量的范围

- 只在 Windows 当前环境用固定课程版本；不用 WSL。框架 54fc150ffc290f52aa024209ffb9a29d43856f6d，测试库 29f980727f7d99a1842a58f34091c7579ba3fe85，Yosys 0.63、ABC 8e40154、OpenSTA 3.1.0、Verilator 5.020，固定 ASAP7 库。
- 对同一冻结源码并行进行一次课程综合/STA 与一次原生 CPU 构建。综合使用原脚本 opt/2 ns 约束，最终频率取其 STA 最小周期，不将约束值当成实测频率。
- 构建后一次运行官方六项 perf，内存延迟 10，动态指令分子来自原 metrics.json，IPC 取精确几何平均；随后一次运行官方 19 项 correctness。
- 总面积按原课程 SRAM/FakeRAM 规则计入 SRAM。比较同规范基线的 Fmax、IPC、面积；频率优先，同时报告 ±10% 范围和 Tier3 的 36000 µm²/1.0985/300 MHz 是否达成。
- 后台隐藏窗口执行，冻结输入不再改动；运行期间继续整理优化方向，不重复启动测量。先完成本批验证，再根据实际最慢路径决定后续实现。

## 必须验证的风险

此前 L1 correctness 为 16/19，pi/qsort/tak 达到 million-cycle 上限；本批没有证据证明已修好。AM 的 redirect 仲裁修正和后续全部结构需共同验证。优先关注 warm reset、分支恢复后物理编号重用、持有生产者反压、同束 RAW、store/load 顺序、RAS overflow/pop、frontend line 边界与合法 ADDI。普通 RTL 层次控制分发是否通过原课程 SRAM 白名单、ABC 是否保留并改善负载也需实际综合。任何编译/映射失败都保留日志，不宣称有频率结果。

最后完整同规范基线为 Fmax 32.39788654411997 MHz、IPC 0.9801279406499007、总面积 46309.69349394434 µm²。L1 IPC 0.8004591469676289，综合被拒，没有 Fmax/面积；它们都不是 CD 的结果。
'''
(ROOT/'reports/frequency_batch_CD_pretest_2026-10-04.md').write_text(pretest,encoding='utf-8')

for name in ['frequency_dispatch_stage_design_2026-10-04.md','frequency_batch_measurement_2026-10-04.md']:
    p=ROOT/'reports'/name
    t=p.read_text(encoding='utf-8')
    t=t.replace('当前 BU 已继承','当前 CD 已继承',1)
    t=t.replace('[architecture_BU_20261004](F:/CPU2026CourseRuns/architecture_BU_20261004/source_manifest.json)',
                '[architecture_CD_20261004](F:/CPU2026CourseRuns/architecture_CD_20261004/source_manifest.json)',1)
    t=t.replace('主工作树随后继续更新到独立 **BU 未测试实现**','主工作树随后继续更新到独立 **CD 未测试实现**',1)
    t=t.replace('BU 未启动硬件工具，不能将 L1 IPC 或基线频率视为 BU 的结果。',
                'CD 测试启动前不能将 L1 IPC 或基线频率视为 CD 的结果；具体统一范围见 [CD 测试前报告](E:/Verilog_cpu/reports/frequency_batch_CD_pretest_2026-10-04.md)。',1)
    p.write_text(t,encoding='utf-8')

p=ROOT/'reports/frequency_control_budget_2026-10-04.json'
budget=json.loads(p.read_text(encoding='utf-8'))
budget['adopted_candidate']=record['candidate']
budget['new_source_grouping'].update(RS_source_tag_bits=7,RS_wake_sources=6,
    RS_operand_write_mux_and_hold_bits=16,predictor_feedback_rows_per_domain=4,
    prediction_target_mask_bits=16,RAS_return_address_mask_bits=16,
    statement='RTL grouping and comparator inventory only; no mapped fanout/capacitance/slew measurement')
p.write_text(json.dumps(budget,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'CD_SOURCE_AND_PRETEST_REPORT_RECORDED','tests_started':False,
                  'implemented_files':len(record['implemented_files']),'run':record['frozen_run']},ensure_ascii=False))
