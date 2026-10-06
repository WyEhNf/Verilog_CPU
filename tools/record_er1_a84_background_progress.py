"""Bind independent A84 prefix admission to the live, immutable A83 run."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a83_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT/'build/cpu2026/er1_a84_background_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A84_store_prefix_admission_2026-10-06.md'
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A84_rob_store_prefix_admission')


def main():
    assert not PROOF.exists() and not REPORT.exists()
    state = read(STATE)
    assert state['current_source_candidate'] == 'A83_fast_store_identity_preselect'
    assert state['active_measurement_candidate'] == 'A83_fast_store_identity_preselect'
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    assert dispatch['process_id'] == state['measurement_process_id'] == 82452
    assert live(82452)
    assert dispatch['source_manifest_sha256'] == plan['source_manifest_sha256'] == state['active_measurement_source_manifest_sha256']
    assert sha(RUN/'dispatch_identity.json') == state['measurement_dispatch_sha256']
    phases = read(RUN/'serial_phase_identity.json')
    assert phases['supervisor_pid'] == 82452
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256'] == '96a7fd63a4459fe2501c3ba3907ace352cd3374192dfd7a9b0d2d73eec96f2ea'
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == read(previous)['main_active_manifest_sha256']
    for name, digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    candidate = read(CANDIDATE/'candidate.json')
    assert sha(CANDIDATE/'candidate.json') == '2b524c9472a3420c98290f9e9be6b8fcd5fd26731e3c84932f19dcf29270f880'
    parent = Path(candidate['parent_candidate'])
    assert parent.resolve() == Path(plan['candidate']).resolve()
    assert sha(parent/'candidate.json') == candidate['parent_candidate_sha256'] == plan['candidate_sha256']
    script = ROOT/'tools/prepare_er1_rob_store_prefix_admission.py'
    assert sha(script) == candidate['preparation_script_sha256']
    for name, digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE/name) == digest, name
    assert len(candidate['source_sha256']) == 41
    changed = sorted(name for name in candidate['source_sha256'] if (CANDIDATE/name).read_bytes() != (parent/name).read_bytes())
    assert changed == sorted(candidate['changed_from_parent_files'])
    review = Path(candidate['source_review'])
    assert read(review)['candidate_sha256'] == sha(CANDIDATE/'candidate.json')
    assert not candidate['tests_started'] and not candidate['adopted']
    assert candidate['candidate_ipc'] is candidate['candidate_area_um2'] is candidate['candidate_frequency_mhz'] is None
    # Original data/cache/LSQ/producer/recovery sources remain exact to A83.
    for name in ['rtl/backend/rv32_lsq.v','rtl/cache/rv32_dcache_nonblocking.v','rtl/backend/rv32_completion_network.v',
                 'rtl/backend/rv32_reservation_station.v','rtl/rv32i_alu.v','rtl/rv32_rename_unit.v']:
        assert (CANDIDATE/name).read_bytes() == (parent/name).read_bytes(), name
    rob = (CANDIDATE/'rtl/backend/rv32_rob.v').read_text(encoding='utf-8')
    old = (parent/'rtl/backend/rv32_rob.v').read_text(encoding='utf-8')
    assert rob[rob.index('    end else begin:g_legacy_field_commands'):] == old[old.index('    end else begin:g_legacy_field_commands'):]
    assert '                            else\n                                commit_valid_o[commit_lane] = 1\'b0;' in rob
    assert 'STORE_PREFIX_ADMISSION_ACTIVE!=0 && commit_ready_i &&' in rob
    classification = 'PROGRESS_A83_ORIGINAL_LIVE_A84_STORE_PREFIX_ADMISSION_RTL_NO_NEW_TESTS'
    REPORT.write_text('''# A84：存储授权与前缀退休重叠

正在测量的A83快照、管理器和157文件不修改；原监督PID82452在记录时确认存活。A84是F盘独立41文件候选，本轮没有为它启动任何HDL/lint/形式/仿真/综合/STA/单元测试。

源码审查确认，原ROB已启用存储缓冲退休，但一条存储必须先成为实际队首，然后用一拍获LSQ授权，再从注册store_sent状态退休。存储位于第二位置时，即使前面的整数指令已经就绪且当拍真实退休，仍不能授权它。连续已就绪存储理想退休上限因而只有每两拍一条。

A84允许在原提交循环已经通过全部更老有效/就绪指令、未遇到错误/终止/MMIO、且commit_ready为1的当拍，授权其后的第一条普通无错误存储进入原LSQ。更老前缀在同一边沿真实退休，授权存储随即成为下一拍实际队首；它自身仍必须从已经注册的store_sent状态退休，所有后续位置仍被这条存储阻断。没有根据LSQ-ready组合结果当拍退休新存储，因此没有新ready→head/count容量环路。

理想连续已就绪存储时序：原方案“授权S0；退休S0；授权S1；退休S1”。新方案“授权S0；退休S0同时授权S1；退休S1同时授权S2”。仍只有一个授权端口、一个原缓存请求通路，存储数据和外部副作用由原LSQ/缓存管理。实际程序可能受头阻塞、LSQ背压、缓存或分支限制，这不是已测IPC增益。

身份提前从保存的有效/存储/未授权队首字段选择，不依赖晚到的前缀退休资格。任何能在原循环中走到的发布存储，必定就是最早潜在未授权存储：否则更老未授权存储已经阻断循环。slot绕回和全部GEN来自原make_tag。实际LSQ全ROB标签匹配/地址数据就绪握手后，只将对应ROB行store_sent置位；其他写优先级、普通完成、快完成、GEN、恢复和确认不变。

MMIO终止、错误/halt存储仍只按原队首协议处理。任一更老指令未就绪、错误/终止、外部退休暂停或恢复/hold都会禁止年轻存储授权。BE1、参数0、非轻量/非分银行/非缓冲模式等继续原实现；legacy状态命令尾部完全一致。无新增FF/SRAM/流水边沿/端口。新的标签选择和行索引广播及前缀门控会改变映射面积和时序，三项指标未知。

后续集中验证需包含：连续存储、整数/加载/分支和存储混合、BE4长前缀、提交和LSQ-ready暂停、MMIO全掩码退出、错误/终止指令、已授权头、队首绕回/GEN复用、恢复、确认错误与分配/退休碰撞、选项0和所有支持参数。这里只进行了人工源码/调度/身份推导与哈希确认，不能替代完整正确性验证。

目标仍为频率严格大于300MHz、IPC至少1.1、含SRAM面积不超过36000μm²。现有实测A75仍1.05188539/299.24021MHz/35658.77140μm²，A83暂无结果。不得将A83未来结果赋予A84；A84不会逐改测试，继续积累有依据的同一批优化。
''',encoding='utf-8')
    proof = dict(status=classification,recorded_at=datetime.now(timezone.utc).isoformat(),new_tests_started=False,
        active_original_measurement=dict(run=str(RUN),process_id=82452,process_alive=True,phase=phases['status'],
            source_manifest_sha256=plan['source_manifest_sha256'],pretest_report_sha256=plan['pretest_report_sha256'],
            candidate_sha256=plan['candidate_sha256'],dispatch_sha256=sha(RUN/'dispatch_identity.json'),source_files_verified=157),
        candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),parent_candidate_sha256=candidate['parent_candidate_sha256'],
        source_file_count=41,source_hashes_valid=True,changed_files=changed,preparation_script_sha256=sha(script),
        source_review=str(review),source_review_sha256=sha(review),candidate_metrics=None,candidate_tests_started=False,
        main_active_manifest_sha256=sha(active),main_source_unchanged=True,adopted=False,goal_complete=False,
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),report=str(REPORT),report_sha256=sha(REPORT))
    write(PROOF,proof)
    state.update(status='ER1_A83_MEASUREMENT_WITH_A84_INDEPENDENT_SOURCE_PROGRESS',current_prepared_candidate=CANDIDATE.name,
        current_source_candidate=CANDIDATE.name,candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),pending_source_candidate=str(CANDIDATE),
        pending_source_candidate_sha256=sha(CANDIDATE/'candidate.json'),candidate_tests_started=False,pending_source_candidate_tests_started=False,
        candidate_ipc=None,candidate_fmax_mhz=None,candidate_area_um2=None,candidate_metrics_belong_to=None,
        candidate_correctness_not_run=True,candidate_correctness_passed=False,candidate_correctness_finished=False,
        last_prepared_measurement_run=str(RUN),last_prepared_measurement_source_manifest_sha256=plan['source_manifest_sha256'],
        prepared_run=None,prepared_source_manifest_sha256=None,candidate_pretest_report=None,candidate_pretest_report_sha256=None,
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),last_source_progress_proof=str(PROOF),
        last_source_progress_proof_sha256=sha(PROOF),last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        measurement_process_alive=True,goal_complete=False,candidates_adopted=False,
        next_work='Continue independent IPC/area/timing source work while original A83 PID82452 runs; A84 untested, no per-edit test or frozen-run mutation.')
    write(STATE,state)
    print(dict(status=classification,active_pid=82452,phase=phases['status'],pending=CANDIDATE.name,new_tests_started=False,
        proof=str(PROOF),proof_sha256=sha(PROOF),report=str(REPORT),goal_complete=False))


if __name__ == '__main__':
    main()
