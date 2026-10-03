"""Update source-only progress documentation; never invoke hardware tools."""
import json
import hashlib
from pathlib import Path

ROOT=Path('E:/Verilog_cpu')
NAME='AW1'
record=json.loads((ROOT/'build/cpu2026/active_frequency_implementation_20261004.json').read_text(encoding='utf-8'))
if record['tests_started'] or Path(record['frozen_run']).name!='architecture_AW1_20261004':
    raise ValueError('Preserve active implementation identity')

p=ROOT/'reports/frequency_rtl_restructure_2026-10-04.md'
t=p.read_text(encoding='utf-8')
t=t.replace('当前工作树已更新为 AM 候选，17 个文件并入','当前工作树已更新为 AW1 候选，18 个文件并入',1)
t=t.replace('[architecture_AM_20261004](F:/CPU2026CourseRuns/architecture_AM_20261004/source_manifest.json)',
            '[architecture_AW1_20261004](F:/CPU2026CourseRuns/architecture_AW1_20261004/source_manifest.json)',1)
t=t.replace('[pre_AM_worktree_20261004](F:/CPU2026Candidates/pre_AM_worktree_20261004/backup.json)',
            '[pre_AW1_worktree_20261004](F:/CPU2026Candidates/pre_AW1_worktree_20261004/backup.json)',1)
anchor='\nIcache 响应数据的单独 owner Q'
rows='''
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
'''
if anchor not in t: raise ValueError('Missing source table insertion anchor')
t=t.replace(anchor,'\n'+rows+anchor,1)
t=t.replace('AH/AI/AJ/AL 本身不增加寄存位；','AH/AI/AJ/AL 及 AN→AW1 不增加数据寄存位或流水级；',1)
old='此次只读取库文本，没有运行任何 EDA。'
new='''此次只读取库文本，没有运行任何 EDA。继续读到 NAND2x1 的 A/B 输入电容约为 0.990183/0.990331 fF：32 个该类输入为 31.685856/31.690592 fF，超过弱 INV 的 23.04 fF 上限；16 个为 15.842928/15.845296 fF。这是 AT1 收紧分组的具体库依据。其他映射单元、极性共享、实际消费者数及寄生仍未知，不能据此宣称网表已满足负载。只读数值记录见 [控制负载预算](E:/Verilog_cpu/reports/frequency_control_budget_2026-10-04.json)。'''
t=t.replace(old,new,1)
t=t.replace('结果只属于 L1 快照，不能作为 AM 的结果。AM 的仲裁修复也未被证明是旧超时的根因或修复。',
            '结果只属于 L1 快照，不能作为 AW1 的结果。继承的 AM 仲裁修复也未被证明是旧超时的根因或修复。',1)
start=t.index('## 仍在研究，因此暂不启动新测试')
t=t[:start]+'''## 仍在研究，因此暂不启动新测试

1. **Dcache 剩余 MSHR/waiter 字段。**缓存数据字节和 metadata reset 已拆分；地址、LSQ tag、victim payload 与 waiter 状态仍需逐个确定完整初始化、partial merge、response/ACK 与重用的所有权，然后决定哪些宽复位与公共 action 选择可以移除。
2. **branch_pending 捕获与后端映射读。**恢复已存在保存/应用边界，但捕获 tag/PC/value/physical 的条件仍可能共享宽控制；ROB→LSQ 表的动态读也需继续检查查询驱动、选择负载及与代数检查的连接。
3. **执行端 PRF 读取/快速唤醒架构。**[BOOM Register Files and Bypass Network](https://docs.boom-core.org/en/latest/sections/reg-file-bypass-network.html)把读取端口与发射端口相连，旁路位于 register-read 末端；这是一条有价值的大改方向。当前 RS 保存操作数值，不能照搬早置 ready 而让数据晚到。需要明确反压、重发与取消规则，评估额外阶段和依赖链代价。AU1 只改广播/选择，不宣称实现 fast wakeup。
4. **取指 lookahead 与恢复域推进。**现有 frontend 的 response 同拍 chain request 已存在，不再重复实施；独立 lookahead 仍需预测和事务身份。恢复期间允许旧操作推进必须有年龄过滤，并避免把新比较器放回 issue 关键链。上述方向仍有待源码设计，不能称作已经穷尽方案。

AD 派发边界及本轮 AN→AW1 都已经并入主工作树；普通整数主路径仍为十级。本轮采用的主要 payload 控制预算为 16 位，不能把所有标志/query 引脚也统称为 16 个物理消费者。源码迁移中人工审查发现的跨行 prefetch_next_line 赋值遗漏已在 AW1 准备时移除，旧 AW 未并入；这仍不是编译或验证通过。

下一次测试前会另行提交明确的最终候选、改动/取舍、待核对路径和后台测量范围。保持课程固定的原生 Windows Yosys/ABC/OpenSTA/Verilator、库和约束，计入全部 SRAM；不使用 WSL。当前不是测试前通知，尚未启动 AW1 的硬件工具。
'''
p.write_text(t,encoding='utf-8')

p=ROOT/'reports/frequency_dispatch_stage_design_2026-10-04.md'
t=p.read_text(encoding='utf-8').replace('当前 AM 已继承','当前 AW1 已继承',1)
t=t.replace('[architecture_AM_20261004](F:/CPU2026CourseRuns/architecture_AM_20261004/source_manifest.json)',
            '[architecture_AW1_20261004](F:/CPU2026CourseRuns/architecture_AW1_20261004/source_manifest.json)',1)
p.write_text(t,encoding='utf-8')

p=ROOT/'reports/frequency_batch_measurement_2026-10-04.md'
t=p.read_text(encoding='utf-8').replace('主工作树随后继续更新到独立 **AM 未测试实现**','主工作树随后继续更新到独立 **AW1 未测试实现**',1)
t=t.replace('AM 未启动硬件工具，不能将 L1 IPC 或基线频率视为 AM 的结果。',
            'AW1 未启动硬件工具，不能将 L1 IPC 或基线频率视为 AW1 的结果。',1)
p.write_text(t,encoding='utf-8')

lib=Path('F:/CPU2026CourseTools/win54fc150/asap7/lib')
budget={'status':'LIBRARY_TEXT_READ_ONLY_NOT_MAPPED_TIMING','tests_started':False,
        'units':{'capacitance':'fF','time':'ps'},'weak_inverter_max_capacitance_fF':23.04,
        'library_sha256':{n:hashlib.sha256((lib/n).read_bytes()).hexdigest() for n in [
            'asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib','asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib']},
        'NAND2x1_ASAP7_75t_R':{pin:{'input_capacitance_fF':cap,'load_32_fF':32*cap,'load_16_fF':16*cap} for pin,cap in [('A',0.990183),('B',0.990331)]},
        'assumption_limit':'Counts are RTL grouping budgets, not actual mapped pin counts/capacitance/slew or a frequency/area result',
        'adopted_candidate':record['candidate']}
(ROOT/'reports/frequency_control_budget_2026-10-04.json').write_text(json.dumps(budget,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'SOURCE_PROGRESS_UPDATED','active':record['candidate'],'tests_started':False},ensure_ascii=False))
