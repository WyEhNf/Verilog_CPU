"""Record source progress and frozen evidence; never execute HDL/EDA."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_er1_a16r2_measurement import check as check16
from manage_er1_a21_measurement import check as check21
from manage_frozen_baseline_programs import ROOT, read, sha, write
from wait_frequency_directed_native import live

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
NAMES=['A23_early_frontend_redirect','A24_sram_instruction_filter','A25_sram_axi_read_payload',
       'A26_compact_prediction_target','A27_compact_indirect_btb','A28_alloc_load_selection_bypass']
REPORT=ROOT/'reports/ER1_A23_A28_source_progress_2026-10-05.md'
OUT=ROOT/'build/cpu2026/er1_a23_a28_source_progress_20261005.json'
GOAL=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'


def main():
    assert not REPORT.exists() and not OUT.exists()
    check16();check21()
    measured=read(ROOT/'build/cpu2026/er1_a21_result_a22_source_progress_20261005.json')
    for key in ('a16r2','a21'):
        d=measured[key];run=Path(d['run'])
        assert not live(read(run/'dispatch_identity.json')['process_id'])
        assert sha(run/'result/result.json')==d['result_sha256']
        assert sha(run/'result/ipc.json')==d['ipc_sha256']
        assert sha(run/'result/synth/opt/report.json')==d['ppa_sha256']
    candidates=[]
    for name in NAMES:
        root=BASE/name;d=read(root/'candidate.json')
        assert d['status']=='PREPARED_UNTESTED_NOT_ADOPTED'
        assert not d['tests_started'] and not d['adopted']
        assert all(d[key] is None for key in ('candidate_ipc','candidate_area_um2','candidate_frequency_mhz'))
        assert sha(Path(d['parent_candidate'])/'candidate.json')==d['parent_candidate_sha256']
        for file,digest in d['source_sha256'].items():assert sha(root/file)==digest,file
        proof=BASE/(name.split('_',1)[0]+'_source_review.json')
        assert read(proof)['candidate_sha256']==sha(root/'candidate.json')
        candidates.append(dict(name=name,root=str(root),candidate_sha256=sha(root/'candidate.json'),
            source_review_sha256=sha(proof),changed_files=d['changed_from_parent_files'],tests_started=False))
    active=read(ROOT/'build/cpu2026/active_frequency_implementation_20261004.json')
    for file,digest in active['source_sha256'].items():assert sha(ROOT/file)==digest,file
    run=Path(measured['a21']['run'])
    frozen=read(run/'source_manifest.json')['snapshot_sha256']
    static=[]
    for case in sorted((run/'source/.deps/RISC-V-CPU-2026/testcases').glob('perf_*')):
        p=case/'program.S';assert sha(p)==frozen[p.relative_to(run/'source').as_posix()]
        pcs=[];section=None;jalr=[];cross_jal=[]
        for line in p.read_text(encoding='utf-8').splitlines():
            header=re.fullmatch(r'Disassembly of section (\S+):',line)
            if header:section=header[1];continue
            m=re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+',line)
            if not m or not section or not section.startswith('.text'):continue
            pc,ins=int(m[1],16),int(m[2],16);pcs.append(pc)
            if ins&127==103:jalr.append(pc)
            if ins&127==111:
                imm=((ins>>31)<<20)|(((ins>>12)&255)<<12)|(((ins>>20)&1)<<11)|(((ins>>21)&1023)<<1)
                if imm&(1<<20):imm-=1<<21
                target=(pc+imm)&0xffffffff
                if pc>>12!=target>>12:cross_jal.append(dict(pc=pc,target=target))
        assert pcs and {pc>>12 for pc in pcs}=={0}
        static.append(dict(case=case.name,disassembly_sha256=sha(p),static_instructions=len(pcs),
            min_pc=min(pcs),max_pc=max(pcs),text_pages=1,jalr_sites=len(jalr),cross_page_jal_sites=cross_jal))
    last=read(BASE/NAMES[-1]/'candidate.json')
    deleted_bits=2176+768+1216
    constant_bits=640
    removed_bits=deleted_bits+constant_bits
    ff_area=removed_bits*.2916
    sram_area=32*round(4*16*.0419904,6)+24*round(32*.0419904,6)
    REPORT.write_text(f'''# ER1 A23–A28源码进度（尚未测试）

严格目标仍为IPC≥1.1、Fmax>300MHz、总面积含SRAM≤36,000μm²。上一轮是实质进展：冻结实测结果、补齐A16R2全部25课程答案记录、修复记录脚本字段引用。本轮新增六个独立源码候选，全部未启动HDL/EDA测试，目标未完成。

|项目|同一源码的已测结果/源码变化|证据边界|
|---|---|---|
|当前最佳完整验证A16R2|IPC0.94636559、39,982.760814μm²、367.42016505MHz|6perf与19correctness答案全PASS|
|最新完整测量A21|IPC0.96158832、39,115.002954μm²、247.40275429MHz|频率不达门槛，不采用；19correctness未运行|
|A23前端提前重定向|已接收、完整ROB代际有效的分支直接重定向；省一拍前端等待|后台恢复描述符/应用/epoch更新原样；history模式保留原路|
|A24指令过滤缓存SRAM|16行容量不变，四个交错bank，命中仍一拍；删除2,176位数据FF|同bank填充/读冲突会等待；背压每拍重读符合FakeRAM输出语义|
|A25总线读行SRAM|前三字放SRAM、最后字保留FF，删除768位数据FF|AXI-Lite FIFO字序0/1/2/3保证完整行发布时点不变；错误/握手/生命周期原样|
|A26预测目标表示|只搬运JALR12位页内目标；直接分支/JAL省去目标副本|取指仍用完整地址；跨页JALR强制恢复，避免截断/页别名漏检|
|A27间接BTB表示|64项容量不变，58→39位，8位折叠tag+31位对齐target|预测允许tag别名；执行检查完整目标，模式0/2保留原格式|
|A28已就绪load分配直达请求候选|在原LSQ分配拍填充原请求选择寄存器，省一个等待|旧候选优先、无任何已存store及同束更早store；原全代际校验/请求/背压/恢复边界|

A22提前load唤醒与正式完成寄存边界分离继续保留；本轮没有在正式CDB/PRF/ROB完成路径重新启用返回直通。A23–A28不是各自单独测过的方案，A28才是当前组合源码；其IPC、频率、总面积均未知，不继承A16R2或A21数据。

面积结构依据：A24删除2,176位，A25删除768位，A27删除1,216位，共{deleted_bits:,}位显式FF数据状态。A26仍保留原32位接口/存储声明，只把高20位变为常量；按至少32份元数据副本计有{constant_bits}位预期可被综合剪除，不能称为声明本身已删除。合计约{removed_bits:,}位被删除或置为常量的数据位。参考已映射DFF单价0.2916μm²，对应FF组件约{ff_area:.6f}μm²；新增课程SRAM组件{sram_area:.6f}μm²，组件差约{ff_area-sram_area:.6f}μm²。A26副本数是源码下界，整体数字不是新映射面积：还需计入减少的保持mux/读写分发以及新增bank选择、hash和分配选择逻辑。不能据此宣称总面积已达36,000。A26候选早期记录中的removed_declared_ff_bits用词以本说明为准，已冻结候选不覆写。

六个冻结性能程序的静态.text均在page0，最大PC0x508，因此A26页内表示和A27折叠tag没有新增的静态文本跨页/别名。这个结论不证明运行时控制流被局限于该页，也不代替IPC/正确性测量。完整RV32IM任意地址仍需合法处理；跨页间接预测的恢复代价、tag别名、错误与背压都列入后续验证范围。

下一步先审查这一组合的控制扇出、分配到候选的新路径及同时恢复情形，再处理多分支训练等剩余IPC机会。当前仍有明确可实施方案，不启动A28独立硬件测试。下一次组合测试前先汇报；只有实测达到严格目标并完成相应RV32M/恢复/背压/地址别名验证后，才能采用并宣告完成。

课程工具/版本/依赖/答案/metrics/延迟计数保持冻结，Windows原生。EU主树源哈希不变，原A16R2/A21测量及所有历史候选均保留。

当前候选：{BASE/NAMES[-1]}
manifest SHA256：{sha(BASE/NAMES[-1]/'candidate.json')}
''',encoding='utf-8')
    proof=dict(status='PROGRESS_A23_TO_A28_SIX_SOURCE_CHANGES_UNTESTED',
        recorded_at=datetime.now(timezone.utc).isoformat(),candidates=candidates,
        perf_static_page_census=static,removed_declared_data_bits=deleted_bits,
        made_constant_prediction_data_bits_lower_bound=constant_bits,
        estimated_removed_or_constant_data_bits=removed_bits,
        removed_ff_area_component_um2=ff_area,added_sram_area_component_um2=sram_area,
        component_difference_um2=ff_area-sram_area,not_new_mapped_area=True,
        no_new_hdl_execution=True,no_new_synthesis=True,no_new_sta=True,no_new_cpu_tests=True,
        previous_turn_classification='PROGRESS_FROZEN_RESULTS_A16_ALL25_PASS_AND_STATE_RECORD',
        main_eu_source_changed=False,goal_complete=False,candidates_adopted=False,
        report=str(REPORT),report_sha256=sha(REPORT))
    write(OUT,proof)
    goal=read(GOAL)
    goal.update(status=proof['status'],current_prepared_candidate=NAMES[-1],
        pending_source_candidate=str(BASE/NAMES[-1]),
        pending_source_candidate_sha256=sha(BASE/NAMES[-1]/'candidate.json'),
        pending_source_candidate_tests_started=False,active_measurement_candidate=None,
        measurement_process_alive=False,active_measurement_process_ids=[],
        last_goal_turn_classification=proof['status'],last_background_progress=str(REPORT),
        last_background_progress_sha256=sha(REPORT),goal_complete=False,candidates_adopted=False,
        next_work=[
            'Review A28 combined source: allocated full LSQ generation, sparse lanes/earlier stores/wrap, selection drain, backpressure and recovery; audit all new bank/branch/metadata timing controls.',
            'Develop multi-bank branch feedback to avoid dropping a second same-cycle resolved branch; source analysis first, no per-edit tests.',
            'Finish architectural IPC and mapped-owner area opportunities and report before one coherent native course batch after material-gain evidence.',
            'Final adoption requires same-source IPC>=1.1, area including SRAM<=36000, Fmax>300 and relevant course/MDU/recovery/backpressure/alias coverage.'
        ])
    write(GOAL,goal)
    print({k:proof[k] for k in ('status','removed_declared_data_bits','component_difference_um2','no_new_cpu_tests','goal_complete')})


if __name__=='__main__':
    main()
