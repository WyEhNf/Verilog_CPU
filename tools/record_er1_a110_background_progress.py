"""Record A110 pre-choice wake matching while original A109 is running."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from manage_er1_a109_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A110_lsq_wake_identity_precompare')
PROOF = ROOT/'build/cpu2026/er1_a110_background_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A110_physical_wake_match_before_choice_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    assert dispatch['process_id'] == 103132
    alive = live(103132)
    phase = read(RUN/'serial_phase_identity.json')
    assert phase['supervisor_pid'] == 103132
    if not alive:
        assert phase['status'] in ['SERIAL_TIMING_COMPLETE_PERFORMANCE_DEFERRED','SERIAL_CHARACTERIZATION_COMPLETE','SERIAL_TIMING_FAILED','SERIAL_PERFORMANCE_FAILED']
    state = read(STATE)
    assert state['current_source_candidate'] == state['active_measurement_candidate'] == 'A109_rob_occupancy_distribution'
    assert sha(CANDIDATE/'candidate.json') == 'abe407fd2556c0c80fa95927b4ff0b653f3c452e97979a3400e853f001b0dd2f'
    candidate = read(CANDIDATE/'candidate.json')
    parent = Path(candidate['parent_candidate'])
    assert parent.name == 'A109_rob_occupancy_distribution'
    assert sha(parent/'candidate.json') == candidate['parent_candidate_sha256']
    preparer = ROOT/'tools/prepare_er1_lsq_wake_identity_precompare.py'
    assert sha(preparer) == candidate['preparation_script_sha256']
    for name, digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE/name) == digest,name
    changed = sorted(n for n in candidate['source_sha256'] if (CANDIDATE/n).read_bytes() != (parent/n).read_bytes())
    assert changed == sorted(candidate['changed_from_parent_files']) and len(changed) == 5
    assert not candidate['tests_started'] and not candidate['adopted']
    assert candidate['candidate_ipc'] is candidate['candidate_area_um2'] is candidate['candidate_frequency_mhz'] is None
    top = (CANDIDATE/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key, value in candidate['parameter_overrides'].items():
        match = re.search(r'\b'+key+r'\s*=\s*(\d+)',top)
        assert match and int(match[1]) == value,key
    rs = (CANDIDATE/'rtl/backend/rv32_reservation_station.v').read_text(encoding='utf-8')
    old = (parent/'rtl/backend/rv32_reservation_station.v').read_text(encoding='utf-8')
    marker = '                if(WAKE_UNIQUE_OWNER!=0) begin:g_unique_owner'
    assert rs[rs.index(marker):] == old[old.index(marker):]
    backend = (CANDIDATE/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    assert 'assign rs_base_wake_valid=producer_valid & producer_rd_we & producer_wake_live;' in backend
    assert 'assign phys=producer_phys[wake_identity_lane*PAW +: PAW];' in backend
    assert 'lsq_load_complete_unretired && lsq_load_complete_tag[0] && !lsq_wake_cancel;' in backend
    review = Path(candidate['source_review'])
    assert read(review)['candidate_sha256'] == sha(CANDIDATE/'candidate.json')
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == plan['main_active_manifest_sha256']
    for name, digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest,name
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256']
    observation = dict(observed_at=datetime.now(timezone.utc).isoformat(),run=str(RUN),process_id=103132,
        process_alive=alive,phase=phase['status'],timing=optional(RUN/'result/timing_only.json'),result=optional(RUN/'result/result.json'))
    REPORT.write_text('''# A110：先比较两份物理身份，再选择匹配结果

原A109独立课程运行源/157文件manifest/工具/脚本/报告已冻结检查，原PID103132当前观察附于JSON；未改源、未重启、未并行新测试。A110为独立41文件源候选，五文件改变，三项指标未知。

等待期间，继续对真实RS wake源码与BOOM原始文档核对。BOOM将ALU早唤醒和load/变延迟writeback唤醒分开，bypass位于register-read末端：[Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)、[Register Files and Bypass Network](https://docs.boom-core.org/en/latest/sections/reg-file-bypass-network.html)。这是架构思路，不能作为本CPU频率证据。

本设计原RS_DIRECT_WAKE已经把四rawproducer和独立cache-return送到RS；COMPLETION的source3 data72只是与LSQ public phys4和RS tagtree26共享的原载荷别名，不能据它的名称声称串行经过CDB仲裁。原路径的后续signal_i21是LSQ物理tag valid位（PAW6+valid1，column3从21开始），物理地址字段先晚mux，再执行phys!=0&&phys<56，随后RS等值比较与issue。因此早先CDB-tag选择后比较的表述被这次源级核对替代，数字/原节点证据不改。

A110导出原head_packet_metadata及saved_identity_tree中两份原物理地址，不新增存储/read port；backend分别执行原phys!=0&&phys<PHYS_REGS编码。各RS行的两个操作数分别提前比较这两份完整物理身份，再由同一个原head选择bool选匹配结果，仍与原实际local wake_valid相与。对任意h和tag：match(h?head:saved,t)=h?match(head,t):match(saved,t)，包含原tagvalid、src_tagvalid和range编码。公开报告packet不变，saved候选仍含原held选择，完整ROB/LSQGEN、unretired/localcancel/currentvalid实际门槛不改；无早唤醒/猜测事件。

只替换原LSQ rawproducer列的match，其他ALU/MDU/cache-return/legacyCDB列保留。原match向量逐bit等值，所以first/last duplicate priority、组合值旁路/时序捕获、issue选择/age矩阵、recover/kill/allocate和所有RS状态后缀逐字保持。默认flag0；实际启用还要求原headidentity、headpacket、directphysicalwake、parallelwakemux，其他配置保留原selectedtag比较。按四行域分布两份身份和原headbool，减少晚head值mux→物理valid编码→等值比较的串行深度。

RS8/两操作数使候选比较多16份，原selected-column比较和部分tag分发可能裁掉，但面积不保证减少；原wake_valid/值路由/issue链可能接替瓶颈。新增FF/SRAM/流水边沿0，目标窗口/cache/GEN/ISA/OoO/commit/MMIO/参数化不缩。未运行HDL/lint/形式/仿真/综合/STA/单元测试或CPU构建，不能借A94/A109指标。主E40源保持原状态。

先完成原A109同一个运行；按其原PPA/IPC/新路径判断是否需要A110或进一步结构工作。若A109三项达到目标，集中同CPU19课程+4冻结边界及参数/架构审阅后采用；若未达到，以实际数据组成下一批，先汇报再测，不能因为准备了A110就自动派发测试。
''',encoding='utf-8')
    classification = 'PROGRESS_A109_ORIGINAL_OBSERVED_A110_LSQ_PHYSICAL_WAKE_MATCH_BEFORE_CHOICE_NO_NEW_TESTS'
    proof = dict(status=classification,classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        original_a109_observation=observation,original_a109_source_manifest_sha256=plan['source_manifest_sha256'],
        original_a109_frozen_source_check_passed=True,candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),
        source_file_count=41,changed_files=changed,candidate_source_hashes_valid=True,review_sha256=sha(review),
        preparer_sha256=sha(preparer),rs_priority_values_issue_and_state_suffix_byte_identical=True,
        original_direct_producer_wake_source_mapping_confirmed=True,
        superseded_path_interpretation='completion source data is a raw producer alias; the direct RS wake path already avoids CDB arbitration',
        new_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,additional_tests_started=False,candidate_metrics=None,
        main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        artifacts_sha256={str(p):sha(p) for p in [RUN/'measurement_plan.json',RUN/'source_manifest.json',
            RUN/'course_windows_config.json',RUN/'dispatch_identity.json',CANDIDATE/'candidate.json',review,preparer,REPORT]},
        adopted_to_main=False,goal_complete=False)
    write(PROOF,proof)
    state.update(current_source_candidate=CANDIDATE.name,current_prepared_candidate=CANDIDATE.name,
        candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),pending_source_candidate=str(CANDIDATE),
        pending_source_candidate_sha256=sha(CANDIDATE/'candidate.json'),pending_source_candidate_tests_started=False,
        pending_source_candidate_has_measured_metrics=False,last_source_progress_proof=str(PROOF),
        last_source_progress_proof_sha256=sha(PROOF),last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,
        measurement_process_alive=alive,measurement_last_observed_at=observation['observed_at'],measurement_last_observation=observation,
        candidates_adopted=False,goal_complete=False,
        next_work='Continue original A109 PID103132 frozen native course PPA-gated batch without edits/restart. Pending A110 compares saved/head physical wake identities before original latechoice, preserving direct raw-producer wake/actualvalid/priority. No new tests/metrics. If A109 meets three numerical gates finish sameCPU correctness and architecture/parameter audit; otherwise inspect original paths and complete supported next batch then pre-report before measuring.')
    write(STATE,state)
    print(dict(status=classification,original_a109_observation=observation,a110_tests_started=False,
        proof=str(PROOF),proof_sha256=sha(PROOF),goal_complete=False))


if __name__ == '__main__':
    main()
