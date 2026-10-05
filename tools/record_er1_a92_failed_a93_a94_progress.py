"""Record terminal A92 frontend failure and independent A93/A94 sources."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a92_measurement import check, live, RUN

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT/'build/cpu2026/er1_a92_failed_a93_a94_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A92_frontend_failure_A93_A94_source_2026-10-06.md'
ITEMS = [
    ('A93_fast_store_wb_data','prepare_er1_fast_store_wb_data.py','13e00d4587ba34f677e9c328becc90802973c31eca1616350fcfec7fcb92f67b'),
    ('A94_localparam_dependency_order','prepare_er1_localparam_dependency_order.py','e36c9dc817c1c0ffa06add5261b2b212fc9ed2f26b441733f9c24ab2ded4d927'),
]


def main():
    assert not PROOF.exists() and not REPORT.exists()
    state = read(STATE)
    assert state['current_source_candidate'] == 'A92_load_response_source_query'
    assert state['active_measurement_candidate'] == 'A92_load_response_source_query'
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    phases = read(RUN/'serial_phase_identity.json')
    assert dispatch['process_id'] == phases['supervisor_pid'] == state['measurement_process_id'] == 97984
    assert not live(97984) and phases['status'] == 'SERIAL_TIMING_FAILED'
    assert len(phases['phases']) == 1 and phases['phases'][0]['phase'] == 'timing' and phases['phases'][0]['returncode'] == 1
    synth_log = RUN/'result/synth.log'
    error_line = next(line for line in synth_log.read_text(errors='replace').splitlines() if 'ERROR: Failed to detect width for parameter' in line)
    assert 'rv32_lsq.v:1215:' in error_line and 'HEAD_LOAD_PACKET_ACTIVE' in error_line
    assert not (RUN/'result/result.json').exists() and not (RUN/'result/timing_only.json').exists()
    assert not (RUN/'result/ipc.json').exists()
    previous_proof = Path(state['last_source_progress_proof'])
    assert sha(previous_proof) == state['last_source_progress_proof_sha256'] == '17ae46669c74fa0b784c934e4b25df7aedaf8cdb828f43ff7640b9ad5b89c870'
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == read(previous_proof)['main_active_manifest_sha256'] == plan['main_active_manifest_sha256']
    for path,digest in read(active)['source_sha256'].items():
        assert sha(ROOT/path) == digest, path
    previous = BASE/'A92_load_response_source_query'
    records = []
    for name,script,expected in ITEMS:
        root = BASE/name
        candidate = read(root/'candidate.json')
        assert sha(root/'candidate.json') == expected
        assert Path(candidate['parent_candidate']).resolve() == previous.resolve()
        assert sha(previous/'candidate.json') == candidate['parent_candidate_sha256']
        assert sha(ROOT/'tools'/script) == candidate['preparation_script_sha256']
        for path,digest in candidate['source_sha256'].items():
            assert sha(root/path) == digest, (name,path)
        changed = sorted(path for path in candidate['source_sha256'] if (root/path).read_bytes() != (previous/path).read_bytes())
        assert changed == sorted(candidate['changed_from_parent_files'])
        review = Path(candidate['source_review'])
        assert read(review)['candidate_sha256'] == expected
        assert not candidate['tests_started'] and not candidate['adopted']
        assert candidate['candidate_ipc'] is candidate['candidate_area_um2'] is candidate['candidate_frequency_mhz'] is None
        records.append(dict(candidate=name,candidate_sha256=expected,parent_candidate_sha256=candidate['parent_candidate_sha256'],
            source_file_count=41,source_hashes_valid=True,changed_files=changed,script=str(ROOT/'tools'/script),
            script_sha256=sha(ROOT/'tools'/script),review=str(review),review_sha256=sha(review),tests_started=False,metrics=None,adopted=False))
        previous = root
    lsq = (previous/'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8')
    backend = (previous/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    assert lsq.index('HEAD_STORE_ACK_ACTIVE=') < lsq.index('HEAD_LOAD_IDENTITY_ACTIVE=') < lsq.index('HEAD_LOAD_PACKET_ACTIVE=') < lsq.index('REPORT_IDENTITY_WIDTH=')
    assert backend.index('PARALLEL_STORE_ADDRESS=') < backend.index('FAST_STORE_SAVED_ACTIVE=')
    assert '(prf_read_stored_ready[2*ready_store_lane+1] ||' in backend
    assert '!prf_read_bypass_pending[2*ready_store_lane] && data_qualified)' in backend
    classification = 'PROGRESS_A92_TERMINAL_FRONTEND_ERROR_BOUND_A93_WB_DATA_A94_PARAMETER_ORDER_REPAIR_NO_ADDITIONAL_TESTS'
    REPORT.write_text(f'''# A92展开失败与A93/A94新源码

A92集中任务原PID97984已不存在，监督记录SERIAL_TIMING_FAILED，只有timing阶段返回1；尚未生成PPA、timing-only或IPC结果。错误来自原冻结synth.log：

`{error_line}`

原因是我新增A91常量HEAD_LOAD_PACKET_ACTIVE被更早的REPORT_IDENTITY_WIDTH宽度表达式引用，课程Yosys前端无法展开该前向常量依赖。这不是频率测量值，也不是工具/库版本不匹配。旧A92源码157文件、配置、管理器、审阅/准备脚本、预报与日志保持冻结，未修改或重启；记录绑定原PID/rc1/日志哈希。

A93独立新增数据WB快存储覆盖：基址仍须原保存ready且没有匹配WB，继续使用保存地址类别；数据ready允许原保存ready OR 合法匹配WB-ready，实际LSQ数据仍原PRF最高WB优先级。只拓宽当前数据就绪控制，不把WB data值恢复到地址加法/类别。原严格条件R&&!W蕴含新R||W；同输入下原快机会保留，整体IPC和映射时序未知。原explicit-data非零、MMIO/未就绪基址等保持RS路径，真实分配与顺序存储副作用/全GEN不变。

A94修正展开声明顺序：把原完整HEAD_STORE_ACK_ACTIVE→HEAD_LOAD_IDENTITY_ACTIVE→HEAD_LOAD_PACKET_ACTIVE声明块前移到REPORT_IDENTITY_WIDTH/SAVED_IDENTITY_QUERY_LSB之前；同时将PARALLEL_STORE_ADDRESS前移到新FAST_STORE_SAVED_ACTIVE之前，处理扫描发现的同类常量依赖。所有被移动声明表达式逐字不变，没有改变字段、参数值、算法、状态或握手。不是新增性能优化，也尚未确认重新编译通过。

当前待测源码A94，A93/A94无额外HDL/lint/形式/仿真/综合/STA/单元作业。主E EU40源码与原快照相同，工作在F盘，不用WSL。最新完整测量仍A83：IPC1.074413717/Fmax244.683393MHz/含SRAM35647.034498μm²，六项性能答案通过，19正确性未跑；不能借给新源码。目标严格>300MHz/IPC≥1.1/含SRAM≤36000μm²与完整RV32IM/OoO/顺序提交/MMIO/参数化仍未达成。

下一步用成功A83的冻结依赖/工具作参考，准备独立新运行表征整个修正后的批次；先在对话报告，再开始，保留旧失败任务。不增加逐改测试或自动重试旧PID。数值明确改善并采用前仍需完整19正确性及M/恢复/全GEN/MMIO/参数覆盖。
''',encoding='utf-8')
    artifacts = [RUN/'source_manifest.json',RUN/'course_windows_config.json',RUN/'measurement_plan.json',
        RUN/'dispatch_identity.json',RUN/'serial_phase_identity.json',RUN/'timing_stderr.log',synth_log,REPORT]
    proof = dict(status=classification,recorded_at=datetime.now(timezone.utc).isoformat(),classification='PROGRESS',
        original_a92_pid=97984,original_pid_absent=True,original_phase=phases,original_error_line=error_line,
        original_a92_source_manifest_sha256=plan['source_manifest_sha256'],original_a92_source_frozen=True,
        measurement_metrics=None,ppa_ipc_not_produced=True,additional_tests_started=False,candidates=records,
        artifacts_sha256={str(path):sha(path) for path in artifacts},main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,
        previous_source_progress_proof=str(previous_proof),previous_source_progress_proof_sha256=sha(previous_proof),
        pending_source_candidate=str(previous),pending_source_candidate_sha256=sha(previous/'candidate.json'),
        candidate_metrics=None,adopted_to_main=False,goal_complete=False)
    write(PROOF,proof)
    state.update(status='ER1_A92_FAILED_A94_PENDING_REPAIRED_SOURCE',current_source_candidate=previous.name,
        current_prepared_candidate=previous.name,candidate_manifest_sha256=sha(previous/'candidate.json'),
        pending_source_candidate=str(previous),pending_source_candidate_sha256=sha(previous/'candidate.json'),
        pending_source_candidate_tests_started=False,candidate_ipc=None,candidate_fmax_mhz=None,candidate_area_um2=None,
        candidate_metrics_belong_to=None,candidate_tests_started=False,candidate_correctness_passed=False,
        candidate_correctness_finished=False,candidate_correctness_not_run=True,
        active_measurement_candidate=None,active_measurement_process_ids=[],measurement_process_alive=False,
        active_measurement_source_manifest_sha256=None,last_failed_measurement_candidate='A92_load_response_source_query',
        last_failed_measurement_run=str(RUN),last_failed_measurement_process_id=97984,
        last_failed_measurement_proof=str(PROOF),last_failed_measurement_proof_sha256=sha(PROOF),
        last_prepared_measurement_run=str(RUN),prepared_run=None,prepared_source_manifest_sha256=None,
        candidate_pretest_report=None,candidate_pretest_report_sha256=None,
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,
        candidates_adopted=False,goal_complete=False,
        next_work='Keep failed A92 original artifacts/PID immutable. Freeze/report a fresh coherent A94 course-native run referenced to successful A83; no per-edit tests or old-source restart.')
    write(STATE,state)
    print(dict(status=classification,original_a92_pid_absent=True,ppa_ipc_not_produced=True,pending=previous.name,
        proof=str(PROOF),proof_sha256=sha(PROOF),additional_tests_started=False,goal_complete=False))


if __name__ == '__main__':
    main()
