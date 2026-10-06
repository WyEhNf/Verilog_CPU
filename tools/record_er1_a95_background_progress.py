"""Bind independent A95 source progress to the original live A94 measurement."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a94_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A95_store_class_compare')
PROOF = ROOT/'build/cpu2026/er1_a95_background_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A95_direct_store_class_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    state = read(STATE)
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    phase = read(RUN/'serial_phase_identity.json')
    assert dispatch['process_id'] == phase['supervisor_pid'] == state['measurement_process_id'] == 84416
    assert live(84416)
    assert phase['status'] in ['SERIAL_TIMING_IN_PROGRESS','SERIAL_PERFORMANCE_IN_PROGRESS']
    assert state['active_measurement_candidate'] == 'A94_localparam_dependency_order'
    assert state['current_source_candidate'] == 'A94_localparam_dependency_order'
    assert sha(CANDIDATE/'candidate.json') == '7b5654aa0f7887e8282ad14ba2d3025ce4aeb17c30881528815c2dc16bab3a3e'
    candidate = read(CANDIDATE/'candidate.json')
    parent = Path(candidate['parent_candidate'])
    assert parent.name == 'A94_localparam_dependency_order'
    assert sha(parent/'candidate.json') == candidate['parent_candidate_sha256'] == plan['candidate_sha256']
    preparer = ROOT/'tools/prepare_er1_store_class_compare.py'
    assert sha(preparer) == candidate['preparation_script_sha256']
    for path,digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE/path) == digest, path
    changed = sorted(path for path in candidate['source_sha256'] if (CANDIDATE/path).read_bytes() != (parent/path).read_bytes())
    assert changed == sorted(candidate['changed_from_parent_files']) and len(changed) == 5
    assert not candidate['tests_started'] and not candidate['adopted']
    assert candidate['candidate_ipc'] is candidate['candidate_area_um2'] is candidate['candidate_frequency_mhz'] is None
    review = Path(candidate['source_review'])
    assert read(review)['candidate_sha256'] == sha(CANDIDATE/'candidate.json')
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == plan['main_active_manifest_sha256']
    for path,digest in read(active)['source_sha256'].items():
        assert sha(ROOT/path) == digest, path
    helper = (CANDIDATE/'rtl/common/rv32_asap7_fanout.v').read_text(encoding='utf-8')
    original = (parent/'rtl/common/rv32_asap7_fanout.v').read_text(encoding='utf-8')
    marker = '    wire [2:0] generate_stage [0:2];'
    old_body = original[original.index(marker):original.index('    endgenerate\nendmodule',original.index(marker))+len('    endgenerate')]
    assert old_body in helper
    assert 'wire middle_ones=ones_prefix[5][15];' in helper
    assert 'wire middle_zero=zeros_prefix[5][15];' in helper
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256']
    REPORT.write_text('''# A95：保存存储地址的直接RAM分类

A94原监督PID84416在记录时仍存在，课程原生综合/STA→复用综合六性能IPC任务继续。A94测量源157文件、116课程依赖、配置、管理器、11份审阅/准备脚本、预报和已有进度证明均通过冻结检查；没有修改运行快照/重启任务。新A95只在独立F盘候选生成，未启动HDL/lint/形式/仿真/综合/STA/单元作业。

此前A83实测链经过PRF WB存储地址高位分类（2.292ns→2.755ns）；A94已移走WB值依赖，但保存基址分类仍先生成完整地址再检查高4位。继续阅读发现原simm12加法器已经有低12位进位和高20位前缀，不需要第二个低12位加法器。A95复用这些中间量，提前比较RAM条件，让最后进位只选择一个布尔结果。

令H=base[31:12]、L=base[11:0]、U=imm[11:0]、s=imm[11]、c=floor((L+U)/4096)。完整32位环绕地址的高20位严格为(H+c-s) mod2^20。

| c | s | 高20位 | RAM条件 |
|---|---|---|---|
| 0 | 0 | H | base高4位=0 |
| 1 | 1 | H | base高4位=0 |
| 1 | 0 | H+1 | 若base[27:12]全1则高4位=F，否则高4位=0 |
| 0 | 1 | H-1 | 若base[27:12]全0则高4位=1，否则高4位=0 |

四种互斥情况完整覆盖所有32位基址/12位偏移，包括正负偏移、0x0fffffff/0x10000000 RAM边界和32位上溢/下溢，未假定地址不会环绕。c复用原3×4bit carry prefix，两个middle16条件复用原ones_prefix[5][15]/zeros_prefix[5][15]；高位/符号条件提前准备carry0/carry1的RAM布尔值，最终c选择一个bit。半字/字对齐仍用原sum[1:0]，完整原加法主体逐字保留。

新FAST_STORE_CLASS_COMPARE默认core/backend为0、课程top为1，仅在原保存快存储profile激活时传给PRF。PRF新STORE_CLASS_COMPARE与加法器CLASS_COMPARE默认0，关闭时保存flag仍原sum[31:28]比较。其他所有调用的原sum、WB候选地址flag/优先级、公开read_data/read_ready、PRF更新和所有LSQ/ROB/RS/cache/completion/rename文件逐字不变。原快存储资格/实际分配、canonical immediate、RAM/对齐/op、保存基址且无当前WB、数据ready/合法WB、explicit-data覆盖、全部GEN、恢复/顺序存储副作用均保持。没有新增FF/SRAM/普通流水沿/端口容量。

这改变分类计算的串行结构，保持同输入资格与快路径机会；不声称已量出IPC/频率/面积，也不以源级代数作为完整正确性测试。当前瓶颈可能已迁移，增加carry扇出/高位谓词可能抵消收益，组合面积仍需整批映射。没有再次测试A95，也没有将A83或A94指标借给它。

主E EU40文件通过旧manifest哈希检查，没有采用新RTL。目标严格>300MHz/IPC≥1.1/含SRAM≤36000μm²与完整RV32IM/OoO/顺序提交/MMIO/参数化仍未证实。下一步读取同一A94原PID的终态数值与路径，继续考虑有证据的优化；未来新批次测试先汇报，采用前集中验证完整19正确性及M/恢复/GEN/MMIO/参数覆盖。
''',encoding='utf-8')
    classification = 'PROGRESS_A94_ORIGINAL_MEASUREMENT_LIVE_A95_DIRECT_SIGNED12_STORE_CLASS_RTL_NO_TESTS'
    artifacts = [RUN/'measurement_plan.json',RUN/'source_manifest.json',RUN/'course_windows_config.json',
        RUN/'dispatch_identity.json',review,preparer,CANDIDATE/'candidate.json',REPORT]
    proof = dict(status=classification,classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        original_a94_pid=84416,original_a94_pid_alive_at_record=True,original_a94_phase_observed=phase['status'],
        original_a94_source_manifest_sha256=plan['source_manifest_sha256'],original_a94_frozen_source_check_passed=True,
        candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),source_file_count=41,
        candidate_source_hashes_valid=True,changed_files=changed,review_sha256=sha(review),preparation_script_sha256=sha(preparer),
        source_arithmetic_derivation='High20=(H+c-s) mod2^20; exhaustive four sign/carry cases; original prefix/full sum retained',
        additional_tests_started=False,candidate_metrics=None,artifacts_sha256={str(p):sha(p) for p in artifacts},
        main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        pending_source_candidate=str(CANDIDATE),adopted_to_main=False,goal_complete=False)
    write(PROOF,proof)
    state.update(current_source_candidate=CANDIDATE.name,current_prepared_candidate=CANDIDATE.name,
        candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),
        pending_source_candidate=str(CANDIDATE),pending_source_candidate_sha256=sha(CANDIDATE/'candidate.json'),
        pending_source_candidate_tests_started=False,pending_source_candidate_has_measured_metrics=False,
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,
        candidates_adopted=False,goal_complete=False,
        next_work='Continue exact original A94 PID84416 serial measurement. Keep frozen source/tools/results immutable. A95 direct store RAM classification is untested pending source; inspect A94 terminal metrics/paths before another coherent pre-reported batch and complete full correctness before adoption.')
    write(STATE,state)
    print(dict(status=classification,a94_original_pid_alive=True,a95_tests_started=False,proof=str(PROOF),
        proof_sha256=sha(PROOF),candidate_sha256=sha(CANDIDATE/'candidate.json'),goal_complete=False))


if __name__ == '__main__':
    main()
