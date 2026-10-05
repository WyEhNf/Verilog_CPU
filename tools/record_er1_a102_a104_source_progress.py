"""Bind the new recovery/admission batch and supersede A102's width assumption."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a99_measurement import check, live, RUN

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
CANDIDATE=BASE/'A104_lsq_alloc_fire_distribution'
STATE=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
REFERENCE=ROOT/'build/cpu2026/er1_a99_ppa_result_20261006.json'
PROOF=ROOT/'build/cpu2026/er1_a102_a104_source_progress_20261006.json'
REPORT=ROOT/'reports/ER1_A102_A104_recovery_and_admission_batch_2026-10-06.md'
PREPARERS={102:'prepare_er1_report_recovery_prequalification.py',103:'prepare_er1_report_recovery_age_width.py',104:'prepare_er1_lsq_alloc_fire_distribution.py'}


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan=check()
    assert not live(48248) and read(RUN/'serial_phase_identity.json')['status']=='SERIAL_TIMING_COMPLETE_PERFORMANCE_DEFERRED'
    assert sha(REFERENCE)=='c7a0983b6acfa224fb3def9a825f524b3b046d13db4ba5ec139c6c0aa9df7fad'
    state=read(STATE)
    assert state['current_source_candidate']=='A101_held_identity_row_query'
    assert state['active_measurement_candidate'] is None and not state['active_measurement_process_ids']
    assert not state['candidate_tests_started']
    previous=Path(state['last_source_progress_proof'])
    assert sha(previous)==state['last_source_progress_proof_sha256']==sha(REFERENCE)
    parent=BASE/'A101_held_identity_row_query';chain=[];artifacts=[REFERENCE]
    for number in range(102,105):
        review_path=BASE/f'A{number}_source_review.json';review=read(review_path)
        source=Path(review['candidate']);candidate=read(source/'candidate.json')
        assert sha(source/'candidate.json')==review['candidate_sha256']
        assert Path(candidate['parent_candidate']).resolve()==parent.resolve()
        assert sha(parent/'candidate.json')==candidate['parent_candidate_sha256']
        assert not candidate['tests_started'] and not candidate['adopted']
        for name,digest in candidate['source_sha256'].items():assert sha(source/name)==digest,name
        changed=sorted(n for n in candidate['source_sha256'] if (source/n).read_bytes()!=(parent/n).read_bytes())
        assert changed==sorted(candidate['changed_from_parent_files'])
        preparer=ROOT/'tools'/PREPARERS[number]
        assert sha(preparer)==candidate['preparation_script_sha256']
        chain.append(dict(candidate=source.name,candidate_sha256=sha(source/'candidate.json'),changed_files=changed,
            review_sha256=sha(review_path),preparer_sha256=sha(preparer),tests_started=False))
        artifacts += [source/'candidate.json',review_path,preparer];parent=source
    assert parent.resolve()==CANDIDATE.resolve()
    candidate=read(CANDIDATE/'candidate.json')
    top=(CANDIDATE/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key,value in candidate['parameter_overrides'].items():
        m=re.search(r'\b'+key+r'\s*=\s*(\d+)',top);assert m and int(m[1])==value,key
    assert candidate['parameter_overrides']['FAST_STORE_BATCH']==0
    assert candidate['parameter_overrides']['LSQ_HELD_LOAD_IDENTITY_QUERY']==0
    assert candidate['parameter_overrides']['LSQ_REPORT_RECOVERY_PREQUALIFY']==1
    assert candidate['parameter_overrides']['LSQ_ALLOC_FIRE_DISTRIBUTE']==1
    backend=(CANDIDATE/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    original=(BASE/'A101_held_identity_row_query/rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    for name in ['producer_recovery_age','producer_recovery_branch_age']:
        assert f'    reg [ROB_SLOT_WIDTH-1:0] {name};' in original
        assert f'    reg [ROB_SLOT_WIDTH-1:0] {name};' in backend
    assert 'wire [ROB_SLOT_WIDTH-1:0] age=slot-' in backend
    assert 'wire signed [31:0] age=slot-' not in backend
    active=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active)==plan['main_active_manifest_sha256']
    for name,digest in read(active)['source_sha256'].items():assert sha(ROOT/name)==digest,name
    assert state['last_measured_result']['ipc'] is None and state['last_measured_full_result']['ipc']>=1.1
    REPORT.write_text('''# 新恢复/入队关键路径批次：A102至A104源码记录

A99原任务终态为timing返回0、频率287.802136MHz、含SRAM面积35915.758478μm²、IPC未测；原PID48248已不存在。PPA门槛未过，CPU构建/性能仿真/完整正确性未运行。原157源/工具/脚本/报告冻结检查通过，不启动或重建旧任务。

新最慢五路径同为分支恢复→LSQ公开ROB标签→恢复资格→CDB/PRF→晚入队与LSQ行写，最大到达3.414ns。恢复预览0.6154ns、分布0.7736ns、LSQ标签bit5到completion data[79]1.823ns、CDB选择2.202ns、PRF旁路2.499ns、共同分配资格2.982ns、LSQ第5行写3.253ns。OAI21耗337ps/27.89fF，晚NAND3耗212ps/24.14fF。距300MHz周期需要缩短超过141.276ps，面积余量84.241522μm²。

## 有证据支持的新结构

A102对原私有保存/held与head身份分别计算恢复kill，最后原选择只选一个bool。实际恢复apply和实际producer-valid仍门控原target-live更新；原valid/allROBGEN、cancel/ready/data/公共包、ALU/MDU代码及下游状态保持。课程profile关闭A100/A101第三held查询，功能选项与源码保留，恢复A99两候选以控制面积。实际标签在晚头响应选择之后再算恢复年龄的串行依赖是该方向依据，不是假设新流水收益。

源码复查发现A102准备时类型假设有误：只有原slot临时变量是integer32，age与branch_age实际为unsigned ROB_SLOT_WIDTH regs。因此A102独立32位有符号表达式不能作等价配置，尚未测试或采用。A103单独修正为原槽位宽度、unsigned减法截断和比较。对于任何slot/head，原32位减法赋到SLOT_WIDTH寄存器取低位，等于新SLOT_WIDTH直接减法；branch_age同宽同位域，两个比较保持原无符号扩展。A102的源审阅第2项错误已明确被A103替代，旧成功源/脚本/证明不改写。

A104把原actual alloc_fire_o送入原功能控制树，分发给每组最多四行的metadata/payload分配匹配。课程16行分4组，每lane的两类行选择各由本组叶驱动。所有view位仍为原fire，原公共valid/ready/fire/count/ticket、容量/计划槽、完整GEN/数据/写优先级/回收/状态保持；没有新事件、信用借用或comb反馈。晚资格相关高负载NAND3是该方向依据，映射别名到具体控制的一部分关联仍为推断。

本批不新增声明FF/SRAM/流水边沿，不缩ISA、GEN、窗口或缓存、不改测试/库/时序约束；新增完整候选的窄恢复比较和真实分发反相器会计入ASAP7面积/时序。实际频率/面积/IPC未知，84μm²余量很紧，不能把结构改善当必过。A103/A104保存原周期行为的依据是上述精确函数选择/位宽以及逐位控制等式。

仅源级阅读、推导、哈希冻结，没有HDL/lint/形式/仿真/综合/STA/单元测试，也没有新CPU构建。A10441文件已校验，主E EU40文件不变，完整RV32IM/OoO/顺序提交/MMIO/参数化保持。当前没有新测量在运行。

后续先查尚有直接收益依据的同路径控制问题，完成整批后对话汇报，再原生Windows集中PPA；通过Fmax>300/总面积≤36000后才测六IPC。三项实测全部达标才集中19官方正确性与四份已冻结补充字节程序（覆盖45类、8762解释器指令、除零/溢出/RAM边界/分支/JALR），复用同一CPU，不重综合/构建或六perf。有限测试不等于完整ISA形式证明，参数化仍需源级审阅。目标未完成，不采用候选。
''',encoding='utf-8')
    classification='PROGRESS_A99_NEW_RECOVERY_PATH_A103_EXACT_AGE_WIDTH_A104_ALLOCATION_FANOUT_NO_TESTS'
    artifacts.append(REPORT)
    proof=dict(status=classification,classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        original_a99_terminal_status='SERIAL_TIMING_COMPLETE_PERFORMANCE_DEFERRED',original_pid=48248,original_pid_alive=False,
        measured_reference=str(REFERENCE),measured_reference_sha256=sha(REFERENCE),source_chain=chain,
        candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),candidate_source_hashes_valid=True,
        source_file_count=41,candidate_metrics=None,new_tests_started=False,new_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        active_report_candidates=2,optional_third_held_query_disabled=True,original_age_width='unsignedROB_SLOT_WIDTH',
        a102_signed32_assumption_superseded_by_a103=True,allocation_fire_rows_per_domain=4,
        main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,
        artifacts_sha256={str(p):sha(p) for p in artifacts},previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        adopted_to_main=False,goal_complete=False)
    write(PROOF,proof)
    state.update(status='ER1_A99_PPA_COMPLETE_PENDING_A104_RECOVERY_ADMISSION_SOURCE',
        current_source_candidate=CANDIDATE.name,current_prepared_candidate=CANDIDATE.name,candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),
        pending_source_candidate=str(CANDIDATE),pending_source_candidate_sha256=sha(CANDIDATE/'candidate.json'),
        pending_source_candidate_tests_started=False,pending_source_candidate_has_measured_metrics=False,
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,
        candidates_adopted=False,goal_complete=False,
        next_work='Review remaining directly supported same recovery/admission path work, then pre-report one coherent A103/A104 native PPA batch. A102 agewidth assumption superseded, no tests. Optional A100/A101 held third query inactive. Keep frequency>300/IPC>=1.1/totalarea<=36000 goal and final19+minimal4edge/parameter coverage intact.')
    write(STATE,state)
    print(dict(status=classification,candidate_sha256=sha(CANDIDATE/'candidate.json'),proof=str(PROOF),proof_sha256=sha(PROOF),tests_started=False,goal_complete=False))


if __name__=='__main__':
    main()
