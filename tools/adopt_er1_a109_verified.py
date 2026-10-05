"""Adopt exactly the A109 source only after same-executable 19+4 closing passes."""
from datetime import datetime, timezone
import math
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a109_measurement import live, RUN
from manage_er1_a109_closing import check, OUT as CLOSING, PLAN as CLOSING_PLAN, protocol_module
from manage_er1_compatible_ipc import check as check_er1_baseline, RUN as ER1_BASELINE, ORIGINAL as ER1_ORIGINAL

CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A109_rob_occupancy_distribution')
BACKUP = Path('F:/CPU2026Candidates/er1_before_a109_adoption_20261006')
ACTIVE = ROOT/'build/cpu2026/active_er1_a109_implementation_20261006.json'
PROOF = ROOT/'build/cpu2026/er1_a109_goal_completion_audit_20261006.json'
REPORT = ROOT/'reports/ER1_A109_Tier3_verified_2026-10-06.md'
STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
AUDIT = ROOT/'build/cpu2026/er1_a109_architecture_source_audit_20261006.json'


def main():
    assert not BACKUP.exists() and not ACTIVE.exists() and not PROOF.exists() and not REPORT.exists()
    closing_plan = check()  # Verify the original measured snapshot before main-source adoption.
    dispatch = read(CLOSING/'dispatch_identity.json')
    assert not live(dispatch['process_id']) and not live(103132)
    phase = read(CLOSING/'phase.json')
    closing_path = CLOSING/'closing_result.json'
    closing = read(closing_path)
    assert phase['status'] == closing['status'] == 'CLOSING_CORRECTNESS_COMPLETE'
    assert phase['result_sha256'] == sha(closing_path)
    assert closing['plan_sha256'] == sha(CLOSING_PLAN) == dispatch['plan_sha256']
    assert closing['official_returncode'] == 0 and closing['official_passed_count'] == 19 and closing['official_failed_count'] == 0
    assert closing['official_all_passed'] and closing['edge_all_passed'] and closing['all_23_passed']
    stdout_path = CLOSING/'official_stdout.log'
    stderr_path = CLOSING/'official_stderr.log'
    assert sha(stdout_path) == closing['official_stdout_sha256'] and sha(stderr_path) == closing['official_stderr_sha256']
    text = stdout_path.read_text(encoding='utf-8')
    assert re.findall(r'^\[(correctness_[^\]]+)\]$',text,re.MULTILINE) == closing_plan['official_cases']
    assert len(re.findall(r'^PASS(?: cycles=\d+)?$',text,re.MULTILINE)) == 19
    assert 'Results: 19 passed, 0 failed' in text
    oj = protocol_module(Path(closing_plan['oj_io']))
    edges = {row['name']:row for row in closing['edge_rows']}
    assert len(edges) == 4
    for case in closing_plan['edge_cases']:
        row = edges[case['name']]
        stdout = CLOSING/(case['name']+'.stdout.log')
        stderr = CLOSING/(case['name']+'.stderr.log')
        assert row['passed'] and row['returncode'] == 0 and row['expected_u32'] == case['expected_u32']
        assert sha(stdout) == row['stdout_sha256'] and sha(stderr) == row['stderr_sha256']
        assert oj.compare_output(stdout.read_text(encoding='utf-8'),Path(case['answer']).read_text(encoding='utf-8')) is None
        assert re.findall(r'^CPU2026 cycles=(\d+)$',stderr.read_text(encoding='utf-8'),re.MULTILINE) == [str(row['cycles'])]
    result_path = RUN/'result/result.json'
    result = read(result_path)
    assert sha(result_path) == closing_plan['original_result_sha256'] == closing['original_result_sha256']
    assert result['ipc'] >= 1.1 and result['fmax_mhz'] > 300 and result['area_um2'] <= 36000
    assert result['official_perf_expected_results_passed'] and result['thread_objective_numeric_requirements_met']
    state_before_adoption = read(STATE)
    baseline_proof, _ = check_er1_baseline()  # Read-only original ER1 source/identifier audit.
    baseline = state_before_adoption['baseline']
    baseline_ipc_path = ER1_BASELINE/'result/ipc.json'
    baseline_ipc = read(baseline_ipc_path)
    assert sha(baseline_ipc_path) == baseline['ipc_report_sha256']
    assert baseline_ipc['geomean_ipc'] == baseline['ipc']
    assert baseline_ipc['official_perf_answers_passed'] and baseline_ipc['latency'] == 10
    assert baseline_ipc['compatibility_identity_sha256'] == sha(ER1_BASELINE/'compatibility_identity.json')
    assert baseline_proof['original_manifest_sha256'] == baseline['original_manifest_sha256']
    baseline_ipc_change_pct = (result['ipc']/baseline['ipc']-1)*100
    a94 = state_before_adoption['previous_measured_result']
    assert a94['candidate'] == 'A94_localparam_dependency_order'
    a94_result_path = Path(a94['run'])/'result/result.json'
    assert sha(a94_result_path) == a94['result_sha256']
    frequency_change_pct = (result['fmax_mhz']/a94['fmax_mhz']-1)*100
    area_change = result['area_um2']-a94['area_um2']
    ipc_path = RUN/'result/ipc.json'
    ipc = read(ipc_path)
    assert len(ipc['results']) == 6 and abs(math.exp(sum(math.log(row['instructions']/row['cycles']) for row in ipc['results'])/6)-result['ipc']) < 1e-12
    row_identity = lambda row:(row['name'],row['instructions'],row['cycles'])
    assert sorted(map(row_identity,ipc['results'])) == sorted(map(row_identity,a94['rows']))
    area = {key:result['area'][key] for key in ['combinational_area_um2','sequential_area_um2','sram_area_um2']}
    assert abs(sum(area.values())-result['area_um2']) < 1e-8
    sram_instances = result['area']['sram_instances']
    assert len(sram_instances) == 93 and len({row['instance'] for row in sram_instances}) == 93
    assert all(row['depth'] > 0 and row['width'] > 0 and row['area_um2'] > 0 for row in sram_instances)
    assert abs(sum(row['area_um2'] for row in sram_instances)-area['sram_area_um2']) < 1e-8
    audit = read(AUDIT)
    assert sha(AUDIT) == '05874e96427b7faca8f44b6b30b4364b2de2bc6d89664edade862dabd08babd6'
    assert audit['architecture_preservation_source_review_complete'] and audit['supported_parameter_limits_source_reviewed']
    assert len(audit['required_decoded_ops']) == 45
    old_manifest = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(old_manifest) == 'b6a3b95f37c0ac207706c28ddc9caa17d5665d5527beade404033bb08fd147d1'
    old = read(old_manifest)['source_sha256']
    assert len(old) == 40
    candidate_path = CANDIDATE/'candidate.json'
    candidate = read(candidate_path)
    assert sha(candidate_path) == closing_plan['candidate_sha256'] == audit['candidate_sha256']
    new = candidate['source_sha256']
    assert len(new) == 41 and set(new)-set(old) == {'rv32im_defs.vh'} and not set(old)-set(new)
    for name, digest in old.items():
        assert sha(ROOT/name) == digest, 'Preserve unrecognized main source edits: '+name
    for name, digest in new.items():
        assert sha(CANDIDATE/name) == digest == sha(RUN/'source'/name), name
    assert not (ROOT/'rv32im_defs.vh').exists(), 'Preserve an existing untracked alias'
    changed = [name for name in old if old[name] != new[name]]
    assert len(changed) == 20
    BACKUP.mkdir(parents=True)
    for name, digest in old.items():
        path = BACKUP/name
        path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,path)
        assert sha(path) == digest
    write(BACKUP/'backup_manifest.json',dict(created_at=datetime.now(timezone.utc).isoformat(),
        original_active_manifest=str(old_manifest),original_active_manifest_sha256=sha(old_manifest),
        source_sha256=old,root_header_alias_previously_absent=True,changed_files=changed))
    for name in changed+['rv32im_defs.vh']:
        destination = ROOT/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(CANDIDATE/name,destination)
    for name, digest in new.items():
        assert sha(ROOT/name) == digest, name
    active = dict(status='VERIFIED_A109_SOURCE_ADOPTED_NUMERIC_AND_23_CLOSING_PASS',
        adopted_at=datetime.now(timezone.utc).isoformat(),source_root=str(ROOT),candidate=str(CANDIDATE),
        candidate_manifest_sha256=sha(candidate_path),source_sha256=new,changed_files=changed,
        added_generated_course_header_alias='rv32im_defs.vh',previous_active_manifest=str(old_manifest),
        previous_active_manifest_sha256=sha(old_manifest),previous_source_backup=str(BACKUP),
        verified_run=str(RUN),source_manifest_sha256=closing_plan['source_manifest_sha256'],
        config_sha256=closing_plan['config_sha256'],executable_sha256=closing_plan['executable_sha256'],
        parameter_overrides=candidate['parameter_overrides'],materialized_top_defaults=audit['parameter_profile'],
        ipc=result['ipc'],fmax_mhz=result['fmax_mhz'],area_um2=result['area_um2'],
        official_perf_answers_passed=True,official_correctness_passed=19,frozen_boundary_passed=4,
        closing_result_sha256=sha(closing_path),adopter_sha256=sha(Path(__file__)))
    write(ACTIVE,active)
    rows = '\n'.join(f"| {row['name']} | {row['instructions']} | {row['cycles']} | {row['ipc']:.9f} |" for row in ipc['results'])
    REPORT.write_text(f'''# ER1 A109：Tier3与线程三项目标完成

同一课程固定工具链/配置/源/可执行文件实测IPC **{result['ipc']:.12f}**、总面积（含SRAM）**{result['area_um2']:.9f}um²**、综合/STA估算Fmax **{result['fmax_mhz']:.9f}MHz**。满足线程严格Fmax>300MHz、IPC>=1.1、总面积<=36000um²，并满足课程Tier3 IPC>=1.0985/频率>=300/面积<=36000。

| 指标 | 当前A109 | 线程目标 | 余量 |
|---|---:|---:|---:|
| 六perf IPC GEOMEAN | {result['ipc']:.9f} | >=1.1 | {result['ipc']-1.1:.9f} |
| 含SRAM面积/um² | {result['area_um2']:.6f} | <=36000 | {36000-result['area_um2']:.6f} |
| Fmax/MHz | {result['fmax_mhz']:.6f} | >300 | {result['fmax_mhz']-300:.6f} |

组合面积{area['combinational_area_um2']:.6f}、时序面积{area['sequential_area_um2']:.6f}、SRAM面积{area['sram_area_um2']:.6f}um²，三者相加等于总面积。课程报告中93个SRAM实例逐项面积求和与该SRAM合计一致，无重复实例或漏计。频率按课程ASAP7RVT TT/FakeRAM、ideal clock/no parasitics、50ps uncertainty与最低周期搜索得到；最低周期{result['minimum_period_ns']:.9f}ns，尚不是布局布线后硅片频率。

六perf原答案全部通过，IPC分子使用课程metrics.json的dynamic_instructions，分母为同一个官方sim报告cycles，latency10：

原ER1六perf IPC已先行实测确认：{baseline['ipc']:.12f}，A109相对提高{baseline_ipc_change_pct:.6f}%。ER1原源码因Verilator保留标识符只做局部名字替换，反向替换后的文件逐字还原，其他源码与课程输入不变；原IPC及兼容审阅保持冻结，没有为本次报告重复运行。

| 程序 | 课程动态指令数 | 仿真周期 | IPC |
|---|---:|---:|---:|
{rows}

随后复用原CPU，19/19官方correctness与4/4既有冻结RV32IM边界程序通过。额外四项为arithmetic_edges_2、memory_low、memory_ram_top、control_alignment_0，期望与输入来自原已冻结独立解释器，含全部45类操作/8个M操作、除零/溢出、x0、自然对齐存取、RAM顶部和JALR边界；它们补齐官方程序缺少的DIVU/MULH/MULHSU/MULHU。这是有限程序/签名覆盖加源级审阅，没有宣称整CPU形式化完整ISA证明或任意参数组合都经过动态验证。

源级审阅确认：保留完整RV32IM译码和原ALU/MDU/LSQ实现；RS只对ready行排序，可越过未ready的较老指令；ROB只提交实际head的连续ready前缀；MMIO word store以地址80000000、WSTRB1111和原32位WDATA送至外部AXI，普通cache不吸收退出。Icache高地址前缀按way完整保留并参与命中，变化会失效旧行，Dcache保持完整地址tag。

关键参数通过实际模块与数组维度：FE4、BE2、INT_ISSUE_WIDTH2、ROB32、PRF56、RS8、LSQ16、Icache128行2路（每行16B）、Dcache1024行2路（每行16B）。支持范围/依赖见[本次参数与架构审阅](E:/Verilog_cpu/reports/ER1_A109_architecture_parameter_source_audit_2026-10-06.md)。已有[参数敏感度](E:/Verilog_cpu/reports/parameter_sensitivity.md)记载历史单参数IPC实验，包括ROB32→64、PRF64→96、RS深度和CDB宽度等；[架构探索](E:/Verilog_cpu/reports/architecture_exploration.md)记录相应取舍。这些旧源码/latency20/旧工具数据仅作历史探索，不用作当前latency10课程成绩，不混成A109指标。

A109整批将原恢复/LSQ身份和分配的晚选择拆为先计算候选、后选择事件/小字段，并把原单份ROBoccupancy分发到局部消费者；该组合实测频率比A94提高{frequency_change_pct:.6f}%，IPC逐项周期与A94相同，面积仅增加{area_change:.6f}um²。A105整批曾退化到274.24MHz/36056.02um²，保留失败证据；不能从整批结果独立归因某个开关。A110先比较wake身份、A111并行加减已准备但没有测量，未混入或采用。

旧“九级算术流水”描述需要纠正：当前ALU四位chunk/prefix均是组合层，仍是原一周期结果寄存器，课程ISSUE_PIPELINE0未增加RS→ALU寄存级。本次达标通过组合路径与扇出重构得到，没有把算术组合层当作流水级。

已将20份改变的RTL及课程根目录头文件alias采用到E:/Verilog_cpu，41个主源文件逐字与本次已测源一致；原40源完整备份于{BACKUP}。旧成功生成器/manager/proof/report/结果均保留，不编辑或重跑；原A109结果和closing证据只读，原manager的check核对原测量快照，当前主工作区另外逐项核对41源SHA。本次没有重复CPU构建、综合或六perf，采用后的41源SHA一致替代重复测试。

课程框架54fc150ffc290f52aa024209ffb9a29d43856f6d、testcases29f980727f7d99a1842a58f34091c7579ba3fe85，Yosys0.63、固定ABC/OpenSTA3.1、Verilator5.020；整个测量与验证Windows native，无WSL。可执行文件SHA256：{closing_plan['executable_sha256']}；source manifest SHA256：{closing_plan['source_manifest_sha256']}。原测量、23项验证、架构审阅、当前41主源和备份证据由completion audit绑定。
''',encoding='utf-8')
    evidence = [ACTIVE,REPORT,Path(__file__),AUDIT,candidate_path,result_path,ipc_path,
        RUN/'source_manifest.json',RUN/'course_windows_config.json',RUN/'serial_phase_identity.json',
        RUN/'native_build/build_identity.json',Path(closing_plan['executable']),CLOSING_PLAN,
        closing_path,CLOSING/'phase.json',CLOSING/'dispatch_identity.json',stdout_path,stderr_path,
        BACKUP/'backup_manifest.json',ROOT/'build/cpu2026/er1_a109_complete_result_20261006.json',
        a94_result_path,ROOT/'docs/final_project_requirements.md',
        baseline_ipc_path,ER1_BASELINE/'compatibility_identity.json',ER1_BASELINE/'source_manifest.json',
        ER1_ORIGINAL/'source_manifest.json',ER1_ORIGINAL/'result/timing_only.json',
        ROOT/'reports/parameter_sensitivity.md',ROOT/'reports/architecture_exploration.md',
        Path('C:/Users/admin/.codex/attachments/81aa8947-b50a-458c-a1c6-d48e8f506208/goal-objective.md')]
    for case in closing_plan['edge_cases']:
        evidence += [CLOSING/(case['name']+'.stdout.log'),CLOSING/(case['name']+'.stderr.log')]
    proof = dict(status='ER1_A109_FULL_OBJECTIVE_VERIFIED_AND_SOURCE_ADOPTED',classification='PROGRESS',
        completed_at=datetime.now(timezone.utc).isoformat(),objective=dict(strict_fmax_mhz=300,
            minimum_ipc=1.1,maximum_total_area_including_sram_um2=36000),
        ipc=result['ipc'],fmax_mhz=result['fmax_mhz'],area_um2=result['area_um2'],area_components=area,
        total_sram_instances_counted=93,sram_instances_unique_and_summed=True,
        same_source_config_executable_three_metrics=True,official_six_perf_answers_passed=True,
        official_correctness_19_passed=True,four_frozen_boundary_cases_passed=True,
        full_required_rv32im_decode_execution_source_review_complete=True,
        ooo_inorder_commit_mmio_source_review_complete=True,key_parameterization_source_review_complete=True,
        historical_parameter_sensitivity_and_tradeoff_reports_preserved=True,
        current_main_41_source_sha256=new,backup_old_40_source_sha256=old,
        source_manifest_sha256=closing_plan['source_manifest_sha256'],
        executable_sha256=closing_plan['executable_sha256'],main_source_adopted=True,
        no_measurement_reruns_after_adoption=True,unmeasured_a110_a111_not_adopted=True,
        arbitrary_parameter_dynamic_proof_claimed=False,full_isa_formal_proof_claimed=False,
        requirement_evidence_sha256={str(path):sha(path) for path in evidence},goal_complete=True)
    write(PROOF,proof)
    state = read(STATE)
    measured = dict(state['last_measured_full_result'],full_correctness_not_run=False,
        full_correctness_passed=True,full_correctness_passed_count=19,boundary_correctness_passed_count=4,
        closing_result_sha256=sha(closing_path),adopted=True)
    state.update(status='ER1_A109_FULL_OBJECTIVE_VERIFIED_AND_SOURCE_ADOPTED',goal_complete=True,candidates_adopted=True,
        current_main_source_candidate=CANDIDATE.name,active_implementation_manifest=str(ACTIVE),
        active_implementation_manifest_sha256=sha(ACTIVE),goal_completion_audit=str(PROOF),
        goal_completion_audit_sha256=sha(PROOF),final_verified_report=str(REPORT),final_verified_report_sha256=sha(REPORT),
        best_verified_candidate=CANDIDATE.name,best_verified_result=measured,
        best_measured_combined_candidate=CANDIDATE.name,best_measured_combined_result=measured,
        last_measured_full_result=measured,last_measured_result=measured,
        candidate_correctness_not_run=False,candidate_correctness_passed=True,candidate_correctness_finished=True,
        candidate_correctness_failed=0,closing_measurement_completed=True,closing_measurement_process_alive=False,
        next_work='Thread goal verified complete; measured and23case-validated A109 source adopted. A110/A111 remain frozen unmeasured alternatives and are not active main source.')
    write(STATE,state)
    print(dict(status=proof['status'],ipc=result['ipc'],fmax_mhz=result['fmax_mhz'],area_um2=result['area_um2'],
        main_source_files=41,changed_main_files=20,added_alias=1,official_correctness_passed=19,
        boundary_passed=4,report=str(REPORT),proof=str(PROOF),proof_sha256=sha(PROOF)))


if __name__ == '__main__':
    main()
