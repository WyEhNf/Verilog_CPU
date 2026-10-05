"""Record the unmeasured parallel add/sub source and observe original A109."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from manage_er1_a109_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A111_alu_parallel_add_sub')
PROOF = ROOT/'build/cpu2026/er1_a111_background_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A111_parallel_integer_arithmetic_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    assert dispatch['process_id'] == 103132
    phase = read(RUN/'serial_phase_identity.json')
    assert phase['supervisor_pid'] == 103132
    alive = live(103132)
    if not alive:
        assert phase['status'] in ['SERIAL_TIMING_COMPLETE_PERFORMANCE_DEFERRED',
            'SERIAL_CHARACTERIZATION_COMPLETE','SERIAL_TIMING_FAILED','SERIAL_PERFORMANCE_FAILED']
    state = read(STATE)
    assert state['current_source_candidate'] == 'A110_lsq_wake_identity_precompare'
    assert state['active_measurement_candidate'] == 'A109_rob_occupancy_distribution'
    assert sha(CANDIDATE/'candidate.json') == 'eed6b8e99fac4f3134547b76214812571a375c3a33f9a2d6ee7cd58ca26058fc'
    candidate = read(CANDIDATE/'candidate.json')
    parent = Path(candidate['parent_candidate'])
    assert parent.name == 'A110_lsq_wake_identity_precompare'
    assert sha(parent/'candidate.json') == candidate['parent_candidate_sha256']
    preparer = ROOT/'tools/prepare_er1_alu_parallel_add_sub.py'
    assert sha(preparer) == candidate['preparation_script_sha256']
    for name, digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE/name) == digest, name
    changed = sorted(name for name in candidate['source_sha256']
                     if (CANDIDATE/name).read_bytes() != (parent/name).read_bytes())
    assert changed == sorted(candidate['changed_from_parent_files']) and len(changed) == 4
    assert not candidate['tests_started'] and not candidate['adopted']
    assert candidate['candidate_ipc'] is candidate['candidate_area_um2'] is candidate['candidate_frequency_mhz'] is None
    top = (CANDIDATE/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key, value in candidate['parameter_overrides'].items():
        match = re.search(r'\b'+key+r'\s*=\s*(\d+)',top)
        assert match and int(match[1]) == value, key
    alu = (CANDIDATE/'rtl/rv32i_alu.v').read_text(encoding='utf-8')
    old = (parent/'rtl/rv32i_alu.v').read_text(encoding='utf-8')
    marker = '    wire [31:0] address_sum='
    assert alu[alu.index(marker):] == old[old.index(marker):]
    assert '    parameter integer PARALLEL_ADD_SUB = 0,' in alu
    assert 'fast_add_carry(issue_src1_value_i,issue_src2_value_i,1\'b0)' in alu
    assert 'fast_add_carry(issue_src1_value_i,~issue_src2_value_i,1\'b1)' in alu
    assert '.PARALLEL_ADD_SUB(ALU_PARALLEL_ADD_SUB)' in (CANDIDATE/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    review = Path(candidate['source_review'])
    assert read(review)['candidate_sha256'] == sha(CANDIDATE/'candidate.json')
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == plan['main_active_manifest_sha256']
    for name, digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256']
    timing = optional(RUN/'result/timing_only.json')
    result = optional(RUN/'result/result.json')
    observation = dict(observed_at=datetime.now(timezone.utc).isoformat(),run=str(RUN),
        process_id=103132,process_alive=alive,phase=phase['status'],
        timing=({key:timing.get(key) for key in ['status','fmax_mhz','area_um2']} if timing else None),
        result=({key:result.get(key) for key in ['status','ipc','fmax_mhz','area_um2',
                'official_perf_expected_results_passed']} if result else None))
    REPORT.write_text('''# A111：操作码选择移到加减结果之后

本轮延续完整目标：Fmax>300MHz、IPC>=1.1、总面积含SRAM<=36000um²，以及原完整RV32IM/OoO/inordercommit/MMIO/参数化。上一轮属于已核实等待，原A109 PID103132仍在运行；本轮新增独立A111源候选与源级代数审阅，属于实际进展。A109原157文件冻结集合、工具、源、配置、报告检查保持，通过同一个原PID观察，不改源/重启/并行测试。

需要纠正旧描述：原ALU fast_add_carry的八个四位chunk及prefix层均为组合逻辑，只有原执行结果寄存器；课程ISSUE_PIPELINE=0。因此“九级架构”的描述不能证明唤醒→RS选择→ALU路径之间存在八到十个时钟边界，更不能把进位层叫做流水线。保留旧冻结文件，这份源级核对替代此前不准确的算术流水级解释。

A105实际慢路径在2.427ns完成RS payload选择，2.595/2.631ns到达SUB控制树/叶，3.586ns到ALU结果FF。原SUB解码要先反转32位rhs并给carry_in，再经过完整进位与sum网络。A111让F(a,b,0)与F(a,~b,1)并行，与操作码无关，然后由原同一个SUB谓词选择32位结果，原控制树两叶各负责16位。F为原未修改的fast_add_carry。

对任意二值操作码和操作数，原F(a,b XOR {32{S}},S)在S=0/1时分别正好等于这两个预计算值。这是完全相同的函数展开，包含无效op/空issue字段，且不依赖RS选择onehot或年龄矩阵不变量。原address_sum之后整个ALU文件后缀逐字相同：AGU/branch/compare/shift/resultclass/所有状态寄存器及accept/hold/reset/recovery/cancel均不变。没有增加时钟边沿、FF、SRAM、read port或completion source。默认flag0保留原表达式；课程top1，经core/backend传入ALU。

候选四文件改变，独立41文件manifest。增加每个有效ALU的一份组合整数算术及结果选择，综合可能分享/裁掉逻辑，但面积增益没有测量依据。A94仅约201.03um²面积余量，A105已超56.02um²；A110额外tag比较也需计入。新候选三项均未知，零新增周期不等于已经证明IPC1.115，不能继承A94或A109的数字。移除SUB控制到完整算术的串联具有明确结构收益，但实际operand路径/其他控制路径可能成为瓶颈。

未运行A110/A111的HDL/lint/形式/仿真/综合/STA/单元测试或CPU构建，未采用到主E源。原A109继续完成；根据其实际PPA与路径决定下一批的算术面积取舍，继续完成结构优化后才向用户汇报并整批测量。原冻结工具和已成功生成的proof/报告不编辑或重跑。目标未完成。
''',encoding='utf-8')
    classification = 'PROGRESS_A111_OPCODE_INDEPENDENT_INTEGER_ADD_SUB_SOURCE_NO_NEW_TESTS'
    proof = dict(status=classification,classification='PROGRESS',
        previous_goal_turn_classification='VERIFIED_WAIT_A109_ORIGINAL_PID103132_CONFIRMED_LIVE',
        recorded_at=datetime.now(timezone.utc).isoformat(),original_a109_observation=observation,
        original_a109_source_manifest_sha256=plan['source_manifest_sha256'],
        original_a109_frozen_source_check_passed=True,candidate=str(CANDIDATE),
        candidate_sha256=sha(CANDIDATE/'candidate.json'),source_file_count=41,changed_files=changed,
        source_hashes_valid=True,review_sha256=sha(review),preparer_sha256=sha(preparer),
        arithmetic_and_clocked_state_suffix_byte_identical=True,
        arithmetic_pipeline_claim_correction=read(review)['arithmetic_pipeline_claim_correction'],
        new_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,candidate_metrics=None,
        additional_tests_started=False,main_active_manifest_sha256=sha(active),main_e_source_unchanged=True,
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        artifacts_sha256={str(path):sha(path) for path in [RUN/'measurement_plan.json',
            RUN/'source_manifest.json',RUN/'course_windows_config.json',RUN/'dispatch_identity.json',
            CANDIDATE/'candidate.json',review,preparer,REPORT]},adopted_to_main=False,goal_complete=False)
    write(PROOF,proof)
    state.update(current_source_candidate=CANDIDATE.name,current_prepared_candidate=CANDIDATE.name,
        candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),pending_source_candidate=str(CANDIDATE),
        pending_source_candidate_sha256=sha(CANDIDATE/'candidate.json'),pending_source_candidate_tests_started=False,
        pending_source_candidate_has_measured_metrics=False,last_source_progress_proof=str(PROOF),
        last_source_progress_proof_sha256=sha(PROOF),last_background_progress=str(PROOF),
        last_background_progress_sha256=sha(PROOF),previous_goal_turn_classification=state['last_goal_turn_classification'],
        last_goal_turn_classification=classification,measurement_process_alive=alive,
        measurement_last_observed_at=observation['observed_at'],measurement_last_observation=observation,
        candidates_adopted=False,goal_complete=False,
        next_work='Continue original frozen A109 PID103132 native course measurement. Pending A111 includes A110 pre-choice physical wake matching and opcode-independent parallel integer add/sub, source algebra unchanged and no new FF/edge. Check A109 actual gates/paths before deciding coherent next batch/area tradeoff; complete structural work and pre-report before measurement. If A109 meets numerical gates, close sameCPU19+4 correctness and architecture/parameter audit/adoption.')
    write(STATE,state)
    print(dict(status=classification,original_a109_observation=observation,
        a111_tests_started=False,proof=str(PROOF),proof_sha256=sha(PROOF),goal_complete=False))


if __name__ == '__main__':
    main()
