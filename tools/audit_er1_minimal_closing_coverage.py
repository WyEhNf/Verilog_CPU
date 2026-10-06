"""Read existing programs to select a minimal closing batch; do not run a CPU."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a99_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT/'build/cpu2026/er1_minimal_closing_coverage_20261006.json'
REPORT = ROOT/'reports/ER1_minimal_closing_coverage_2026-10-06.md'
SUITE = Path('F:/CPU2026Proofs/rv32im_native_edges_suite_20261003/suite.json')
COMPARISON = Path('F:/CPU2026Proofs/rv32im_native_edges_comparison_20261003.json')
SELECTED = ['arithmetic_edges_2','memory_low','memory_ram_top','control_alignment_0']
MOPS = ['MUL','MULH','MULHSU','MULHU','DIV','DIVU','REM','REMU']


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    assert dispatch['process_id'] == 48248 and live(48248)
    state = read(STATE)
    pending = Path(state['pending_source_candidate'])
    assert pending.name == 'A101_held_identity_row_query'
    assert sha(pending/'candidate.json') == state['pending_source_candidate_sha256']
    for name,digest in read(pending/'candidate.json')['source_sha256'].items():
        assert sha(pending/name) == digest, name
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == plan['main_active_manifest_sha256']
    for name,digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    tests = RUN/'source/.deps/RISC-V-CPU-2026/testcases'
    rows=[]; total=Counter(); official_hashes={}
    for case in sorted(tests.glob('correctness_*')):
        words = re.findall(r'^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s+', (case/'program.S').read_text(encoding='utf-8'),re.M)
        counts=Counter()
        for h in words:
            word=int(h,16)
            if (word&0x7f)==0x33 and ((word>>25)&0x7f)==1:
                counts[MOPS[(word>>12)&7]]+=1
        total.update(counts)
        rows.append(dict(name=case.name,static_m_instructions=dict(counts),static_instruction_words=len(words)))
        for name in ['program.S','program.data','expected.txt','metrics.json']:
            official_hashes[str(case/name)] = sha(case/name)
    assert len(rows) == 19
    missing = sorted(set(MOPS)-set(total))
    assert missing == ['DIVU','MULH','MULHSU','MULHU']
    assert sha(SUITE) == '8189c2bfd0df8263d77b50036454d86b91204015849187621fcdb52e6522c2d2'
    assert read(COMPARISON)['input_sha256'][str(SUITE)] == sha(SUITE)
    suite = read(SUITE)
    assert suite['status'] == 'COMPLETE' and suite['instruction_types'] == 45
    for path,digest in suite['input_sha256'].items():
        assert sha(Path(path)) == digest, path
    by_name={c['name']:c for c in suite['cases']}
    selected=[by_name[n] for n in SELECTED]
    coverage=Counter();events=Counter()
    for case in selected:
        coverage.update(case['coverage']);events.update(case['events'])
        assert str(Path(case['image'])) in suite['input_sha256']
    assert set(coverage) == set(suite['coverage']) and len(coverage) == 45
    assert all(coverage[op.lower()] for op in MOPS)
    assert events['division_by_zero'] == 20 and events['signed_division_overflow'] == 2
    assert events['discard_x0_write'] and events['jalr_low_bit_cleared'] and events['jalr_rd_equals_rs1']
    for op in ['beq','bne','blt','bge','bltu','bgeu']:
        assert events[op+'_taken'] and events[op+'_not_taken']
    instruction_count=sum(c['instructions_through_exit_store'] for c in selected)
    assert instruction_count == 8762
    table='\n'.join(f"| {c['name']} | {c['instructions_through_exit_store']} | {c['expected_u32']} |" for c in selected)
    REPORT.write_text(f'''# 最终集中验证范围：19项课程程序 + 4项冻结补充程序

只读取现有课程程序与已冻结RV32IM字节/解释器结果，没有运行CPU、重新生成程序、汇编、构建、综合、STA或单元测试。A99原PID48248记录时仍存在；当前未测源码A101与原运行分开，主E EU源保持。

## 课程覆盖缺口

对原19份program.S的机器指令字静态译码，M opcode0x33/funct7=1的数量合计：{dict(total)}。没有DIVU、MULH、MULHSU、MULHU指令。静态出现不代表运行中执行，也不证明输入边界；六perf更不能单独证明完整M支持。因此不能把19程序通过写成全部RV32IM已验证。

## 最小补充集合

既有suite16项输入与生成器/独立字节译码器/汇编工具哈希均保持，suite哈希由旧双构建核验绑定。选四项可覆盖该有限套件中的全部45类RV32IM操作及相关边界，共{instruction_count}条解释器执行指令（至退出word store），无需重新生成，也无需重跑16项全套。

| 冻结程序 | 解释器指令数 | 独立期望退出签名 |
|---|---:|---:|
{table}

这四项解释器轨迹含全部8个M操作，20次除零、2次有符号除法溢出、49次x0丢弃写入、六种分支各两个方向、JALR目标bit0清除及rd==rs1，含自然对齐byte/half/word存取、RAM低地址与顶端附近、MMIO0x80000000 word签名退出。它们是有限签名/解释器覆盖，不是当前CPU通过记录或形式化完整ISA证明，也没有逐条RTL退休值观察。

## 执行门槛与身份

只有同一新候选实际Fmax>300MHz、含SRAM面积≤36000μm²、原六性能答案通过且IPC≥1.1，先在对话汇报后才集中运行19官方正确性与这四项。复用该同manifest/config/source工具下已完成的原生CPU可执行文件，latency10；官方正确性显式cycle上限10000000，补充有限程序200000，均只是超时上限。不得在旧成功结果目录覆盖measurement_identity/result/日志，不再综合、不再构建，也不重跑六perf。

官方testcase.py/oj_io.py保持字节相同，可用原stdin序列化和严格stdout签名比较跑现有补充image；新证据必须绑定原CPU exe/sourcemanifest SHA。若失败，保留记录并回到有依据的修复；不得缩减功能或删失败程序。参数化的关键维度及GEN/range/报告包/恢复/顺序提交仍需源级完成审阅；这些有限程序不能证明任意参数组合。

目标仍严格>300MHz、IPC≥1.1、含SRAM总面积≤36000μm²，并保留完整RV32IM/OoO/顺序提交/MMIO/参数化。当前未达成；此记录只让最终验证补齐实际缺口并减少重复工作。
''',encoding='utf-8')
    classification='PROGRESS_A99_LIVE_COURSE_M_COVERAGE_GAP_MINIMAL_FOUR_EXISTING_EDGE_PROGRAMS_NO_TESTS'
    proof=dict(status=classification,classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        original_a99_pid=48248,original_a99_pid_alive_at_record=True,source_manifest_sha256=plan['source_manifest_sha256'],
        official_correctness_case_count=19,official_static_m_counts=dict(total),official_static_m_missing=missing,
        official_rows=rows,official_program_artifacts_sha256=official_hashes,
        frozen_suite=str(SUITE),frozen_suite_sha256=sha(SUITE),frozen_suite_input_files_rechecked=len(suite['input_sha256']),
        frozen_suite_input_sha256=suite['input_sha256'],comparison=str(COMPARISON),comparison_sha256=sha(COMPARISON),
        selected_existing_cases=selected,selected_case_count=4,oracle_instruction_count=instruction_count,
        oracle_instruction_types=45,oracle_coverage=dict(coverage),oracle_events=dict(events),
        new_tests_started=False,new_programs_generated=False,current_cpu_passed=False,
        required_measurement_gate=dict(strict_fmax_mhz=300,ipc=1.1,total_area_um2=36000,perf_answers_passed=True),
        later_validation=dict(official_correctness_max_cycles=10000000,additional_max_cycles=200000,latency=10,
            reuse_same_executable=True,new_cpu_builds=0,new_synthesis_runs=0,performance_repeats=0),
        main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,pending_source_candidate=str(pending),
        pending_source_candidate_sha256=sha(pending/'candidate.json'),report=str(REPORT),report_sha256=sha(REPORT),
        audit_script_sha256=sha(Path(__file__)),goal_complete=False)
    write(PROOF,proof)
    state.update(closing_coverage_plan=str(PROOF),closing_coverage_plan_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,
        goal_complete=False,candidates_adopted=False)
    write(STATE,state)
    print(dict(status=classification,static_m_missing=missing,selected_existing_cases=SELECTED,
        oracle_types=45,oracle_instructions=instruction_count,new_tests_started=False,proof=str(PROOF),proof_sha256=sha(PROOF)))


if __name__ == '__main__':
    main()
