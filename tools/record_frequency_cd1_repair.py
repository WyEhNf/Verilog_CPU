"""Preserve CD compiler failure and record CD1 identifier-only continuation."""
import json
from pathlib import Path
from datetime import datetime,timezone


root=Path('E:/Verilog_cpu')
record=json.loads((root/'build/cpu2026/active_frequency_implementation_20261004.json').read_text(encoding='utf-8'))
if record['tests_started'] or Path(record['frozen_run']).name!='architecture_CD1_20261004':
    raise ValueError('Record repaired untested CD1 only')
old_run=Path('F:/CPU2026CourseRuns/architecture_CD_20261004')
interruption=dict(status='CPU_BUILD_FAILED_SYNTH_INTERRUPTED',recorded_at=datetime.now(timezone.utc).isoformat(),
    process_id=34148,reason='Native Verilator 5.020 rejects internal SystemVerilog keyword matches: 26 syntax errors in five RTL files; stop only verified CD process descendants, preserve partial logs; no IPC/Fmax/area result',
    replacement_run=record['frozen_run'],replacement_candidate=record['candidate'])
(old_run/'interruption.json').write_text(json.dumps(interruption,indent=2)+'\n',encoding='utf-8')
old_identity=old_run/'result/measurement_identity.json'
if old_identity.is_file():
    identity=json.loads(old_identity.read_text(encoding='utf-8'))
    identity.update(status=interruption['status'],interruption_record=str(old_run/'interruption.json'))
    old_identity.write_text(json.dumps(identity,indent=2)+'\n',encoding='utf-8')

repair='''\n\n## CD1：内部保留字修复与统一测量继续范围

CD 首次 Windows 原生 Verilator 编译在五个 RTL 文件报告 26 个语法错误，全部为内部名称 `matches` 与 SystemVerilog 保留字冲突。CPU 未生成，没有运行 perf/correctness；综合仍在前期处理时已停止，仅停止经 PID/command line 核对的 CD 进程树，保留 [build.log](F:/CPU2026CourseRuns/architecture_CD_20261004/native_build/build.log)、[synth.log](F:/CPU2026CourseRuns/architecture_CD_20261004/result/synth.log)和 [中断记录](F:/CPU2026CourseRuns/architecture_CD_20261004/interruption.json)。CD 没有 IPC、频率或面积结果。

CD1 只把 27 处完整内部标识符 `matches` 改为 `row_match_mask`，五个文件的端口、方程、状态、参数、边沿和架构均未改。它继续同一批测量范围，没有加入新优化或独立测试。新的 23-file 实现、157-file 冻结输入见 [architecture_CD1_20261004](F:/CPU2026CourseRuns/architecture_CD1_20261004/source_manifest.json)，源码前版本保留在 [pre_CD1](F:/CPU2026Candidates/pre_CD1_worktree_20261004/backup.json)。启动前的完整范围见 [CD1 测试前报告](E:/Verilog_cpu/reports/frequency_batch_CD1_pretest_2026-10-04.md)。
'''
p=root/'reports/frequency_rtl_restructure_2026-10-04.md'
t=p.read_text(encoding='utf-8')
t=t.replace('当前工作树已更新为 CD 候选','当前工作树已更新为 CD1 候选',1)
t=t.replace('[architecture_CD_20261004](F:/CPU2026CourseRuns/architecture_CD_20261004/source_manifest.json)',
            '[architecture_CD1_20261004](F:/CPU2026CourseRuns/architecture_CD1_20261004/source_manifest.json)',1)
t=t.replace('[pre_CD_worktree_20261004](F:/CPU2026Candidates/pre_CD_worktree_20261004/backup.json)',
            '[pre_CD1_worktree_20261004](F:/CPU2026Candidates/pre_CD1_worktree_20261004/backup.json)',1)
t=t.replace('**本轮没有启动新的编译、仿真、综合、STA 或形式验证。源码准备、人工推理和文件散列核对不能证明频率收益或正确性。**',
            '**CD 首次课程编译发现内部保留字错误；CD1 仅修复名称，尚无 IPC/Fmax/面积。源码准备、人工推理和文件散列核对不能证明频率收益或正确性。**',1)
t+=repair
p.write_text(t,encoding='utf-8')

p=root/'reports/frequency_batch_measurement_2026-10-04.md'
p.write_text(p.read_text(encoding='utf-8')+repair,encoding='utf-8')
p=root/'reports/frequency_dispatch_stage_design_2026-10-04.md'
t=p.read_text(encoding='utf-8').replace('当前 CD 已继承','当前 CD1 已继承',1)
t=t.replace('[architecture_CD_20261004](F:/CPU2026CourseRuns/architecture_CD_20261004/source_manifest.json)',
            '[architecture_CD1_20261004](F:/CPU2026CourseRuns/architecture_CD1_20261004/source_manifest.json)',1)
p.write_text(t,encoding='utf-8')

t=(root/'reports/frequency_batch_CD_pretest_2026-10-04.md').read_text(encoding='utf-8')
t=t.replace('# CD 统一后台测试前汇报','# CD1 统一后台测试前汇报',1)
t=t.replace('本报告先于测量启动落盘。当前工作树采用 CD；',
            '本报告先于 CD1 测量启动落盘。CD1 只修复 CD 的内部保留字：27 处 matches 改为 row_match_mask，不改逻辑、状态、时序或端口。CD 首次编译失败，没有运行 perf/correctness；其综合树已停止，日志保留。当前工作树采用 CD1；',1)
t=t.replace('architecture_CD_20261004','architecture_CD1_20261004').replace('pre_CD_worktree_20261004','pre_CD1_worktree_20261004')
(root/'reports/frequency_batch_CD1_pretest_2026-10-04.md').write_text(t,encoding='utf-8')

p=root/'reports/frequency_control_budget_2026-10-04.json'
budget=json.loads(p.read_text(encoding='utf-8'))
budget['adopted_candidate']=record['candidate']
p.write_text(json.dumps(budget,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'CD1_REPAIR_PRETEST_RECORDED','tests_started':False,'run':record['frozen_run']}))
