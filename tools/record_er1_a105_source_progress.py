"""Record the completed coherent A103-A105 frequency source batch; no tests."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a99_measurement import check, live, RUN

STATE=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
CANDIDATE=BASE/'A105_rob_recovery_row_live'
PROOF=ROOT/'build/cpu2026/er1_a105_source_progress_20261006.json'
REPORT=ROOT/'reports/ER1_A105_recovery_row_live_batch_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan=check();assert not live(48248)
    assert read(RUN/'serial_phase_identity.json')['status']=='SERIAL_TIMING_COMPLETE_PERFORMANCE_DEFERRED'
    state=read(STATE)
    assert state['current_source_candidate']=='A104_lsq_alloc_fire_distribution'
    assert state['active_measurement_candidate'] is None and not state['active_measurement_process_ids']
    previous=Path(state['last_source_progress_proof'])
    assert sha(previous)==state['last_source_progress_proof_sha256']=='94d2044fda151163e40af764c0b09f3b505f5eb46d91e7e1fa351473d15764dd'
    assert sha(CANDIDATE/'candidate.json')=='7eb963391d62ecbd793d09b90d01a3210f5cbf94a5856575b49fe95d434f698d'
    candidate=read(CANDIDATE/'candidate.json');parent=Path(candidate['parent_candidate'])
    assert parent.name=='A104_lsq_alloc_fire_distribution' and sha(parent/'candidate.json')==candidate['parent_candidate_sha256']
    preparer=ROOT/'tools/prepare_er1_rob_recovery_row_live.py'
    assert sha(preparer)==candidate['preparation_script_sha256']
    assert not candidate['tests_started'] and not candidate['adopted']
    for name,digest in candidate['source_sha256'].items():assert sha(CANDIDATE/name)==digest,name
    changed=sorted(n for n in candidate['source_sha256'] if (CANDIDATE/n).read_bytes()!=(parent/n).read_bytes())
    assert changed==sorted(candidate['changed_from_parent_files']) and len(changed)==4
    review=Path(candidate['source_review']);assert read(review)['candidate_sha256']==sha(CANDIDATE/'candidate.json')
    top=(CANDIDATE/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key,value in candidate['parameter_overrides'].items():
        m=re.search(r'\b'+key+r'\s*=\s*(\d+)',top);assert m and int(m[1])==value,key
    assert candidate['parameter_overrides']['ROB_RECOVERY_ROW_LIVE_QUALIFY']==1
    assert candidate['parameter_overrides']['LSQ_HELD_LOAD_IDENTITY_QUERY']==0
    rob=(CANDIDATE/'rtl/backend/rv32_rob.v').read_text(encoding='utf-8')
    old=(parent/'rtl/backend/rv32_rob.v').read_text(encoding='utf-8')
    marker='    localparam integer STORE_PREFIX_ADMISSION_ACTIVE='
    helper='\n\n// Pure single-bit OR.'
    assert rob[rob.index(marker):rob.index(helper)]==old[old.index(marker):]
    backend=(CANDIDATE/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    assert 'wire [ROB_SLOT_WIDTH-1:0] age=slot-' in backend and 'wire signed [31:0] age=slot-' not in backend
    active=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active)==plan['main_active_manifest_sha256']
    for name,digest in read(active)['source_sha256'].items():assert sha(ROOT/name)==digest,name
    closing=Path(state['closing_coverage_plan']);assert sha(closing)==state['closing_coverage_plan_sha256']
    REPORT.write_text('''# A105：恢复路径起点、中段、末段的完整频率批次

A99原测量已终态、原PID48248不存在。Fmax287.802136MHz、含SRAM面积35915.758478μm²、IPC未测；仅一次综合/STA，按门槛跳过CPU构建和性能仿真。原源码/工具/报告冻结，主E EU40源不变。

本次A105在A103原位宽恢复资格前算与A104实际LSQ分配事件分组驱动之外，新增ROB每行完整GEN合法性预计算。原恢复候选先按槽位读取9位{valid,8GEN}再比较；新模式各行先比较全部GEN和当前valid，与完整slot匹配合并，然后二叉OR单bit资格。课程32行为8个四行域，候选slot+GEN13bit由原功能控制树分布。最后仍由原tagvalid门控同一个recovery_lane_live。

对任何合法槽位r，原9位读严格等于行r状态，原资格就是tagvalid&&valid[r]&&tagGEN==GEN[r]；新OR中只有slot==r一行能非零，因此相同。非法槽位没有命中，原valid读零、新OR零，均不合法。tagvalid0都不合法。此证明适用于所有二值tag/行状态、非2幂容量/填充行/entries1，不借用可达状态或一热私有query假设。完整GEN位数、原恢复valid/age/occupancy/最老选择/descriptor/checkpoint/redirect/epoch/回收/分配/提交逻辑保持；ROB原STORE_PREFIX_ADMISSION_ACTIVE之后到原endmodule逐字不变，追加单bitOR helper无状态。

A99起点段从保存分支tag到ROB行选0.2694/0.2935ns，再到recovery_preview0.6154ns；新每行GEN比较可与槽位资格并行，消除选中GEN读取后的比较。中段A103把原私有报告候选的恢复年龄资格前算，晚head选择只选bool；末段A104把原alloc_fire分布到四行域，控制晚NAND3的行负载。三项共同针对同一条3.414ns关键链，需要周期缩短超过141.276ps。

组合面积余量只有84.2415μm²。A105新增并行完整GEN比较及query分发，但消除9位32行读mux/其选择树，代价不能只数新增比较。二叉单bitOR保护层计入真实ASAP7面积/时序，无falsepath/假buffer/黑盒。实际净面积/频率未知，新瓶颈可能出现。声明FF/SRAM/流水边沿增量0，完整ISA/GEN/窗口/cache/预测容量不减，预计原周期行为相同而非借用旧IPC数值。

A102准备的错误32位年龄假设已被A103按原unsigned ROB_SLOT_WIDTH声明修正，未运行任何A102测试；旧快照不改。A100/A101第三held查询在当前课程profile关闭、源码功能保留，不追加其组合成本；本次仍两候选。

对剩余方向：再注册恢复/CDB/PRF会改变同周期唤醒/原子入队，并侵蚀仅1.37%IPC余量；扩窗口/预测器没有当前性能瓶颈依据且面积紧；缩GEN/省取消或范围门槛违背语义；CDB轮转/held仲裁改写风险与净收益尚无比本批更直接的证据。当前同路径有明确依据的起点/中段/末段修改已经完成，不宣称穷尽长期架构方案。

没有逐修改HDL/lint/形式/仿真/综合/STA/单元测试。A10541源码已冻结，三指标未知；下一步先对话汇报，再一次原生Windows课程PPA，只有Fmax>300且含SRAM面积≤36000才构建一次CPU、跑六perf。三项实测达标后集中原19正确性与四份既有冻结补充程序，共8762解释器指令覆盖45类及必要边界，复用同一个CPU，不重复综合构建/六perf；同时完成原参数维度源级审阅。目标完整RV32IM/OoO/顺序提交/MMIO/参数化和三数值条件未完成，未采用。
''',encoding='utf-8')
    classification='PROGRESS_A105_FULLGEN_ROW_RECOVERY_PLUS_A103_BOOL_PREQUAL_A104_ALLOCATION_FANOUT_NO_TESTS'
    proof=dict(status=classification,classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),source_file_count=41,changed_files=changed,
        candidate_source_hashes_valid=True,review_sha256=sha(review),preparer_sha256=sha(preparer),
        original_rob_state_and_control_suffix_byte_identical=True,original_unsigned_slot_age_retained=True,
        added_declared_ff_bits=0,added_sram_bits=0,added_pipeline_edges=0,new_tests_started=False,candidate_metrics=None,
        main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,closing_coverage_plan=str(closing),closing_coverage_plan_sha256=sha(closing),
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        artifacts_sha256={str(p):sha(p) for p in [RUN/'measurement_plan.json',RUN/'source_manifest.json',RUN/'course_windows_config.json',CANDIDATE/'candidate.json',review,preparer,REPORT,closing]},
        adopted_to_main=False,goal_complete=False)
    write(PROOF,proof)
    state.update(status='ER1_A99_PPA_COMPLETE_PENDING_A105_COHERENT_RECOVERY_BATCH',
        current_source_candidate=CANDIDATE.name,current_prepared_candidate=CANDIDATE.name,candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),
        pending_source_candidate=str(CANDIDATE),pending_source_candidate_sha256=sha(CANDIDATE/'candidate.json'),
        pending_source_candidate_tests_started=False,pending_source_candidate_has_measured_metrics=False,
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,candidates_adopted=False,goal_complete=False,
        next_work='Prepare/freeze/pre-report one coherent A103/A104/A105 native course PPA batch targeting root,middle,tail of A99 recoverypath. Gate perf by actual>300/area<=36000. Exactoriginalunsignedage retained; optionalheldquery0. Finalfullnumeric/19official+fourfrozenedges/parametercoverage beforeadoption; no oldrun restart.')
    write(STATE,state)
    print(dict(status=classification,proof=str(PROOF),proof_sha256=sha(PROOF),candidate_sha256=sha(CANDIDATE/'candidate.json'),tests_started=False))


if __name__=='__main__':
    main()
