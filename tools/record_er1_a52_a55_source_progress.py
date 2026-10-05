"""Freeze source/program evidence and reconcile pending identity, without tests."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import read, sha, write
from manage_er1_a41_measurement import check as check_a41
from wait_frequency_directed_native import live

ROOT = Path('E:/Verilog_cpu')
BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
RUN = Path('F:/CPU2026CourseRuns/ER1_A41_tier3_20261005')
STATE = ROOT / 'build/cpu2026/tier3_er1_optimization_20261005.json'
REPORT = ROOT / 'reports/ER1_A52_A55_predictor_source_progress_2026-10-05.md'
PROOF = ROOT / 'build/cpu2026/er1_a52_a55_source_progress_20261005.json'


def static_program(folder, measured):
    """Parse frozen files and match disassembled words to official image bytes."""
    data = folder / 'program.data'
    assembly = folder / 'program.S'
    metrics = folder / 'metrics.json'
    assert sha(data) == measured['program_sha256']
    assert sha(metrics) == measured['metrics_sha256']
    memory = {}
    cursor = None
    for line in data.read_text(encoding='utf-8').splitlines():
        for token in line.split('#', 1)[0].split('//', 1)[0].split():
            if token.startswith('@'):
                cursor = int(token[1:], 16)
            else:
                assert cursor is not None and re.fullmatch(r'[0-9a-fA-F]{2}', token), token
                memory[cursor] = int(token, 16)
                cursor += 1
    words = []
    for line in assembly.read_text(encoding='utf-8').splitlines():
        match = re.match(r'^\s*([0-9a-fA-F]+):\s+([0-9a-fA-F]{8})\s+(\S+)', line)
        if match:
            pc, word = int(match[1], 16), int(match[2], 16)
            image_word = sum(memory[pc+byte] << (byte*8) for byte in range(4))
            assert image_word == word, (folder.name, hex(pc))
            words.append((pc, word))
    assert words
    branches = [pc for pc, word in words if (word & 127) == 0x63]
    grouped, chooser = {}, {}
    for pc in branches:
        grouped.setdefault(pc & ~15, []).append(pc)
        chooser.setdefault((pc >> 2) & 63, []).append(pc)
    return dict(case=folder.name, disassembly=str(assembly), disassembly_sha256=sha(assembly),
        program_data_sha256=sha(data), metrics_sha256=sha(metrics),
        expected_sha256=sha(folder / 'expected.txt'), disassembled_words_matched_to_image=len(words),
        static_instruction_count=len(words), static_conditional_count=len(branches),
        static_m_extension_count=sum((word & 127) == 0x33 and ((word >> 25) & 127) == 1
                                     for pc, word in words),
        multiple_conditional_lines={hex(line): [hex(pc) for pc in pcs]
                                    for line, pcs in grouped.items() if len(pcs) > 1},
        static_64_entry_chooser_collisions={str(index): [hex(pc) for pc in pcs]
                                          for index, pcs in chooser.items() if len(pcs) > 1},
        dynamic_execution_not_performed=True, dynamic_frequency_or_gain_not_inferred=True)


def main():
    assert not REPORT.exists() and not PROOF.exists()
    state = read(STATE)
    assert state['current_source_candidate'] == 'A51_predictor_narrow_direction_read'
    old_report, old_proof = Path(state['last_background_progress']), Path(state['last_source_progress_proof'])
    assert sha(old_report) == state['last_background_progress_sha256']
    assert sha(old_proof) == state['last_source_progress_proof_sha256']
    plan = check_a41()
    for relative, key in (('result/result.json', 'result_sha256'), ('result/ipc.json', 'ipc_sha256'),
                          ('result/synth/opt/report.json', 'ppa_sha256')):
        assert sha(RUN / relative) == state['last_measured_result'][key]
    measured = read(RUN / 'result/result.json')
    ipc = read(RUN / 'result/ipc.json')
    assert measured['status'] == 'COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert measured['official_perf_expected_results_passed'] and measured['official_correctness_suite_not_run']
    assert not measured['thread_objective_numeric_requirements_met']
    assert measured['ipc'] == ipc['geomean_ipc'] == state['last_measured_result']['ipc']
    assert measured['fmax_mhz'] == state['last_measured_result']['fmax_mhz']
    assert measured['area_um2'] == state['last_measured_result']['area_um2']
    assert not live(51000)
    candidates = []
    for name, digest, preparer in (
        ('A52_predictor_bank_pc_carry_select', 'f703927dd1c96f617f4e4f7b577ffb754d9728be4ad7a5942420f8140c82d584', 'prepare_er1_predictor_bank_pc_carry_select.py'),
        ('A53_predictor_prefix_query_history', '9f039ced879f8bdabeb292641d80849b612791d9eef532e56205247976f39797', 'prepare_er1_predictor_prefix_query_history.py'),
        ('A54_predictor_bank_local_instruction_read', 'b26fb5a1edd3d63966835fa29b97d2849186984db5a0695caa730adae0f2a0f0', 'prepare_er1_predictor_bank_local_instruction_read.py'),
        ('A55_predictor_bank_local_prefix_history', '63ccdf16996139e3f3a839b46af65b7192f358dc93512edc2e9553b5a867b984', 'prepare_er1_predictor_bank_local_prefix_history.py')):
        source = BASE / name
        c = read(source / 'candidate.json')
        review_path = BASE / (name.split('_', 1)[0] + '_source_review.json')
        review = read(review_path)
        assert sha(source / 'candidate.json') == digest == review['candidate_sha256']
        assert sha(ROOT / 'tools' / preparer) == c['preparation_script_sha256']
        assert not c['tests_started'] and not c['adopted']
        assert not review['tests_started'] and not review['adopted']
        assert review['added_ff_bits'] == review['added_sram_bits'] == review['added_pipeline_edges'] == 0
        parent = Path(c['parent_candidate'])
        parent_record = read(parent / 'candidate.json')
        assert sha(parent / 'candidate.json') == c['parent_candidate_sha256']
        assert len(c['source_sha256']) == 41
        for rel, source_digest in c['source_sha256'].items():
            assert sha(source / rel) == source_digest, (name, rel)
        for rel, source_digest in parent_record['source_sha256'].items():
            assert sha(parent / rel) == source_digest, (parent.name, rel)
        changed = [rel for rel, source_digest in c['source_sha256'].items()
                   if source_digest != parent_record['source_sha256'][rel]]
        assert set(changed) == set(c['changed_from_parent_files']) == set(review['changed_files'])
        candidates.append(dict(candidate=name, source_root=str(source), candidate_sha256=digest,
            source_files_checked=41, changed_files=changed, parent=str(parent),
            parent_candidate_sha256=c['parent_candidate_sha256'], source_review=str(review_path),
            source_review_sha256=sha(review_path), preparation_script_sha256=c['preparation_script_sha256'],
            added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
            tests_started=False, adopted=False, ipc=None, fmax_mhz=None, area_um2=None))
    active_path = ROOT / 'build/cpu2026/active_frequency_implementation_20261004.json'
    active = read(active_path)
    for rel, digest in active['source_sha256'].items():
        assert sha(ROOT / rel) == digest, rel
    assert len(ipc['results']) == 6
    programs = [static_program(RUN / 'source/.deps/RISC-V-CPU-2026/testcases' / row['name'], row)
                for row in ipc['results']]
    assert sum(bool(p['multiple_conditional_lines']) for p in programs) == 5
    assert all(p['static_m_extension_count'] == 0 for p in programs)
    rows = '\n'.join(f"|{p['case']}|{p['static_instruction_count']}|{p['static_conditional_count']}|"
                     f"{len(p['multiple_conditional_lines'])}|{p['static_m_extension_count']}|" for p in programs)
    report = f'''# ER1 A52–A55 预测前端源码进度（未测试）

目标保持 IPC≥1.1、含 SRAM 总面积≤36000 μm²、频率>300MHz，以及完整 RV32IM、OoO、顺序提交、MMIO 和参数化要求。

上一目标轮只汇报已有指标，归类为无实现进展；本轮重新读取实际状态与冻结源码后，完成 A53/A54/A55 并将此前已准备的 A52 纳入权威状态。当前累计候选为 A55。没有启动 HDL、lint、仿真、综合、STA、单元测试或新的课程测量，没有使用 WSL。主 E: 工作区 EU RTL 哈希保持原样。

## 当前已测结果

综合表现最好的已测候选仍为 A41：IPC **{measured['ipc']:.10f}**，总面积 **{measured['area_um2']:.5f} μm²**（SRAM **{measured['area']['sram_area_um2']:.5f} μm²**），课程综合时序估算频率 **{measured['fmax_mhz']:.5f} MHz**。6 项性能答案通过，完整正确性套件未运行。要达到 IPC1.1，需在当前基准上提高约 **{(1.1/measured['ipc']-1)*100:.5f}%**。旧 PID51000 已不存在，没有重启。A55 没有实测指标，目标尚未完成。

## 新增源码实现

|候选|变化|结构依据|
|---|---|---|
|A52 PC 高低位拆分|共享预计算28位行地址+1，晚到的字偏移只决定低位与是否选择下一行。|保留完整32位回绕、非对齐低2位和越界查询 PC；偏移不再进入高位增量加法。|
|A53 逐指令历史索引|统计当前行前缀中此前的条件分支，用常量左移形成各银行 gshare 历史。|被接收的后续指令之前，各条件分支必然预测不跳转，因此移入位均为0；无需串联前面方向表输出。|
|A54 银行所属指令字读取|FE4 固定读取银行字并保留越界零值；FE2 只选择该银行的两个字；FE1 原实现。|word_index & (FE_WIDTH-1) 恒为银行号；FE4 不需四选一读取，删除低位 PC→动态字选择依赖。|
|A55 固定银行前缀历史|FE4 以前缀中的固定字编号判断此前条件分支。|有效银行字号=B；无效银行起始W>B，固定此前字均<W，标志自然全0；避开偏移/字索引加法与比较。|

这四项均不新增 FF、SRAM 或流水边界。面积、频率、预测准确率与 IPC 的实际收益都未测量。A53 引入新的 opcode→计数→历史选择→方向表路径；A55 移除了其中字索引加法依赖，但不能凭源码断言一定超过300MHz。

A53 的低8位元数据仍保存实际查询索引，经原有 ROB/反馈所有权传到训练端。高位历史检查点推进、前缀终止、历史修复和反馈仲裁源代码保持原样。A53 会改变启用模式的预测方向与原始索引，包括终止之后未使用的查询；不能声称全部预测线等价。A54/A55 则保留各自父版本的内部指令字/历史值，包含越界查询。默认参数均为0并保留旧实现；课程顶层为1，A53 对串行后端关闭。

## 静态程序证据

从 A41 冻结的课程 program.S 解析每条32位指令，并逐条与同一 program.data 的小端字节匹配。源文件 SHA256、原 IPC 程序/metrics 身份及逐字匹配计数均存入证据 JSON。这是只读文件分析，不是新的程序仿真。

|程序|静态指令数|条件分支数|含多条件分支的16B行数|静态M指令数|
|---|---:|---:|---:|---:|
{rows}

5 个程序存在同一行多条条件分支，multiply 没有。median 的0xf0行包含0xf4/0xf8/0xfc三条条件分支；qsort 的0xb0行包含0xb0/0xbc，0x170行包含0x174/0x178。这证明优化所处理的指令布局在官方程序中存在，不证明这些分支动态经常同时进入同一束，也不证明新的历史提高准确率。

6 个性能镜像反汇编均没有 M 扩展指令，说明仅缩短 MDU 执行延迟不能解释这些性能程序的增益；完整 M 扩展实现和必要正确性范围仍保留。64项 chooser 的静态 PC 别名也存入证据，但没有动态冲突证据，暂不凭别名盲目扩表。

## 继续审查与测量前提

累计 A42–A55 已覆盖缓存并发与响应串行、加载选择空泡、恢复应用周期中的较老指令发射、混合方向预测和前端关键依赖。保留已有 A41/A36 动态与映射证据，不把互相重叠的计数相加，不将 A37–A41 联合结果归因为单一预测器变化。

接下来集中审查实际可实施的大结构方案与剩余控制依赖：额外流水级会影响 IPC 并增加状态；额外 MSHR、发射口或大表需给出面积和瓶颈依据；缓存已含合并请求和下一行预取；恢复与分配同拍、提前直接 ALU→前端重定向需先解决 ROB/RAT/RS/LSQ 代际所有权与路径预算。明确可实现方案的依据后，先提交整个批次的测试前汇报，再使用 Windows 原生课程工具链进行统一测量。当前尚未启动测量。

最终必要验证包括 FE1/2/4、全部银行/行起始字/越界字、0..3条此前条件分支、前缀跳转/RAS/哨兵/错误/背压、精确训练索引与恢复，同时保留缓存写读并发、加载转发与背压、恢复恰好一次发射、完整 RV32IM 和全部课程正确性。源码推导、哈希及静态反汇编不能替代这些证据。

证据：[A55 源码身份](F:/CPU2026Candidates/tier3_er1_20261005/A55_predictor_bank_local_prefix_history/candidate.json)；[A41 原始测量](F:/CPU2026CourseRuns/ER1_A41_tier3_20261005/result/result.json)。
'''
    REPORT.write_text(report, encoding='utf-8')
    next_work = [
        'Finish evidence-led architecture audit for cumulative A42-A55; inspect remaining actual control dependencies and ownership rather than adding ungrounded table/width/state growth.',
        'Complete one coherent pretest report after no further currently actionable material-gain option remains; do not execute HDL or course measurement before the report.',
        'Preserve strict IPC>=1.1, total area including SRAM<=36000um2, Fmax>300MHz, full RV32IM/OoO/in-order/MMIO/parameterization, and Windows-native course tools.']
    proof = dict(status='PROGRESS_A52_A55_PREDICTOR_SOURCE_UNTESTED', recorded_at=datetime.now(timezone.utc).isoformat(),
        previous_goal_turn_classification='NO_PROGRESS_METRICS_REPORT_ONLY_REVALIDATED',
        previous_recorded_goal_work_classification=state['last_goal_turn_classification'],
        this_goal_turn_classification='PROGRESS_NEW_A53_A54_A55_AND_A52_RECONCILED_STATIC_OFFICIAL_IMAGE_EVIDENCE',
        objective=dict(ipc_minimum=1.1, total_area_um2_maximum=36000, fmax_mhz_strictly_greater_than=300),
        last_measured_result=state['last_measured_result'], best_verified_result=state['best_verified_result'],
        frozen_host_scripts_sha256=plan['host_sha256'], candidates=candidates, official_static_program_evidence=programs,
        static_disassembly_all_words_matched_to_official_program_bytes=True,
        programs_with_multiple_conditional_lines=5, static_m_instruction_count=0,
        dynamic_profile_or_new_execution_performed=False, report=str(REPORT), report_sha256=sha(REPORT),
        previous_report=str(old_report), previous_report_sha256=sha(old_report),
        previous_proof=str(old_proof), previous_proof_sha256=sha(old_proof),
        tests_started_this_goal_turn=False, new_measurement_started=False, wsl_used=False,
        original_a41_pid_present=False, main_worktree_rtl_unchanged=True,
        main_worktree_candidate=active['candidate'], main_worktree_active_record_sha256=sha(active_path),
        candidate_metrics_measured=False, goal_complete=False, next_work=next_work)
    write(PROOF, proof)
    pending = candidates[-1]
    state.update(status='A41_COMPLETE_A55_PENDING_SOURCE_UNTESTED',
        current_prepared_candidate=pending['candidate'], current_source_candidate=pending['candidate'],
        candidate_manifest_sha256=pending['candidate_sha256'], candidate_tests_started=False,
        candidate_ipc=None, candidate_fmax_mhz=None, candidate_area_um2=None,
        candidate_metrics_belong_to=pending['candidate'], candidate_correctness_passed=None,
        candidate_correctness_failed=None, candidate_correctness_finished=False, candidate_correctness_not_run=True,
        pending_source_candidate=pending['source_root'], pending_source_candidate_sha256=pending['candidate_sha256'],
        pending_source_candidate_tests_started=False, prepared_run=None, prepared_source_manifest_sha256=None,
        candidate_pretest_report=None, candidate_pretest_report_sha256=None,
        active_measurement_candidate=None, active_measurement_process_ids=[], measurement_process_alive=False,
        active_measurement_source_manifest_sha256=None,
        last_background_progress=str(REPORT), last_background_progress_sha256=sha(REPORT),
        last_source_progress_proof=str(PROOF), last_source_progress_proof_sha256=sha(PROOF),
        last_goal_turn_classification=proof['this_goal_turn_classification'],
        previous_goal_turn_classification=proof['previous_goal_turn_classification'],
        previous_recorded_goal_work_classification=proof['previous_recorded_goal_work_classification'],
        candidates_adopted=False, goal_complete=False, next_work=next_work)
    write(STATE, state)
    print(dict(status=proof['status'], pending_candidate=pending['candidate'], report=str(REPORT),
        proof=str(PROOF), static_words_matched=sum(p['static_instruction_count'] for p in programs),
        new_measurement_started=False, goal_complete=False))


if __name__ == '__main__':
    main()
