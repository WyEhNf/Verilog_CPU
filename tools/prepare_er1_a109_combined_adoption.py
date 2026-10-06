"""Prepare the two-attempt evidence join and source adoption without running a CPU."""
import ast
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a109_closing import check as check_original, OUT as ORIGINAL, PLAN as ORIGINAL_PLAN
from manage_er1_a109_pi_budget_followup import check as check_pi, OUT as PI, PLAN as PI_PLAN
from manage_er1_a109_measurement import RUN, live

OUT = ROOT/'build/cpu2026/er1_a109_combined_adoption_preparation_20261006.json'
REPORT = ROOT/'reports/ER1_A109_combined_closing_adoption_preparation_2026-10-06.md'
STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'


def main():
    assert not OUT.exists() and not REPORT.exists(), 'Preserve the first successful preparation'
    original_plan, pi_plan = check_original(), check_pi()
    dispatch = read(ORIGINAL/'dispatch_identity.json')
    original = read(ORIGINAL/'closing_result.json')
    assert not live(dispatch['process_id']) and original['status'] == 'CLOSING_CORRECTNESS_COMPLETE'
    assert original['official_passed_count'] == 18 and original['official_failed_count'] == 1
    assert original['official_returncode'] == 1 and original['edge_all_passed'] and not original['all_23_passed']
    pi_dispatch = read(PI/'dispatch_identity.json')
    pi_live = live(pi_dispatch['process_id'])
    assert pi_live or (PI/'followup_result.json').exists()
    for key in ['source_manifest_sha256','executable_sha256','config_sha256','candidate_sha256']:
        assert original_plan[key] == pi_plan[key]
    old_path = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(old_path) == 'b6a3b95f37c0ac207706c28ddc9caa17d5665d5527beade404033bb08fd147d1'
    old = read(old_path)['source_sha256']
    candidate = Path('F:/CPU2026Candidates/tier3_er1_20261005/A109_rob_occupancy_distribution')
    source = read(candidate/'candidate.json')['source_sha256']
    assert len(old) == 40 and len(source) == 41 and set(source)-set(old) == {'rv32im_defs.vh'}
    for name,digest in old.items():
        assert sha(ROOT/name) == digest, name
    for name,digest in source.items():
        assert sha(candidate/name) == sha(RUN/'source'/name) == digest, name
    assert not (ROOT/'rv32im_defs.vh').exists()
    changed = [name for name in old if old[name] != source[name]]
    assert len(changed) == 20
    scripts = [ROOT/'tools'/name for name in ['record_er1_a109_combined_closing.py',
        'adopt_er1_a109_combined_verified.py','audit_er1_a109_combined_adopted_current_state.py',
        'finalize_er1_a109_verified_goal_evidence.py']]
    for path in scripts:
        ast.parse(path.read_text(encoding='utf-8'),filename=str(path))
    assert not Path('F:/CPU2026Candidates/er1_before_a109_adoption_20261006').exists()
    assert not (ROOT/'build/cpu2026/active_er1_a109_implementation_20261006.json').exists()
    text = (ORIGINAL/'official_stdout.log').read_text(encoding='utf-8')
    matches = list(re.finditer(r'^\[(correctness_[^\]]+)\]$',text,re.MULTILINE))
    rows = []
    for i,match in enumerate(matches):
        body = text[match.end():matches[i+1].start() if i+1<len(matches) else len(text)]
        cycles = re.findall(r'^PASS cycles=(\d+)$',body,re.MULTILINE)
        if match[1]=='correctness_pi':
            assert not cycles
        else:
            assert len(cycles)==1
            rows.append(dict(name=match[1],cycles=int(cycles[0]),max_cycles=10000000))
    assert len(rows)==18 and len({row['name'] for row in rows})==18
    result = read(RUN/'result/result.json')
    REPORT.write_text(f'''# A109 两次运行的正确性汇总与采用流程准备

本次仅准备和只读核对，未执行汇总记录器、源码采用器、采用后核对器或最终记录器，没有新增CPU测试、构建或综合。

原集中验证已经结束：18个官方用例PASS，Pi在10,000,000周期timeout，进程返回1；四个冻结边界用例全部PASS。原结果及错误日志保留。Pi单项补测使用相同exe/source/config、官方testcase.py、原Golden112、latency10与48,000,000周期上限，目前完成与否仍须读取实际终态，不从本文件推定。

后续按顺序执行：先确认既有Pi补测进程退出且官方严格答案通过；记录原18项、补测Pi和四边界，逐用例列周期、预算、输入与答案SHA和来源；完整备份当前40源；仅采用已测A109的20份变化源与课程头文件alias；独立逐字核对当前41源、备份40源、157份测量快照、实际93个SRAM合计、六IPC原始日志、两个正确性运行日志、四边界及架构/参数证据；最后记录完成证据。任一项缺失或失败即不采用或不宣布完成。

原本假定单次19项全通过的旧采用器和旧等待会话已不适用，不重启。新脚本不更改原成功manager、生成器、结果或报告。新最终报告将明确披露原18/1失败与Pi补测，避免将两次结果表述成原10M单次通过。

同一测量的数值保持IPC{result['ipc']:.12f}、含SRAM总面积{result['area_um2']:.6f}um²、综合STA估算Fmax{result['fmax_mhz']:.6f}MHz。主工作区目前仍为原40源，采用尚未执行；A110/A111未測、不采用。
''',encoding='utf-8')
    paths = scripts+[Path(__file__),REPORT,old_path,candidate/'candidate.json',ORIGINAL_PLAN,
        ORIGINAL/'closing_result.json',ORIGINAL/'phase.json',ORIGINAL/'dispatch_identity.json',
        ORIGINAL/'official_stdout.log',ORIGINAL/'official_stderr.log',PI_PLAN,PI/'dispatch_identity.json',
        PI/'cycle_bound_analysis.json',RUN/'source_manifest.json',RUN/'result/result.json']
    proof = dict(status='PREPARED_COMBINED_CLOSING_ADOPTION_NOT_EXECUTED',prepared_at=datetime.now(timezone.utc).isoformat(),
        original_correctness_passed=18,original_correctness_failed=1,original_returncode=1,
        original_pi_10m_timeout_preserved=True,original_official_pass_rows=rows,four_boundary_passed=True,
        pi_followup_process_id=pi_dispatch['process_id'],pi_followup_process_alive_at_preparation=pi_live,
        pi_followup_must_pass_before_adoption=True,current_main_old_40_hashes_verified=True,
        candidate_41_measured_source_hashes_verified=True,changed_main_files=changed,
        scripts_ast_valid=True,combined_recorder_executed=False,adopter_executed=False,
        independent_auditor_executed=False,finalizer_executed=False,new_hardware_tests_started=False,
        goal_complete=False,source_adopted=False,evidence_sha256={str(path):sha(path) for path in paths})
    write(OUT,proof)
    state=read(STATE)
    state.update(status='A109_COMBINED_ADOPTION_PREPARED_PI_FOLLOWUP_RUNNING',goal_complete=False,candidates_adopted=False,
        original_closing_observed_at=proof['prepared_at'],original_closing_observed_passed=18,
        original_closing_observed_phase='CLOSING_CORRECTNESS_COMPLETE',original_closing_process_alive=False,
        closing_measurement_process_alive=False,closing_measurement_completed=True,
        original_closing_pi_failed_timeout=True,original_closing_result_sha256=sha(ORIGINAL/'closing_result.json'),
        original_closing_failed_count=1,original_closing_returncode=1,pi_budget_followup_process_alive=pi_live,
        combined_adoption_preparation=str(OUT),combined_adoption_preparation_sha256=sha(OUT),
        combined_adoption_scripts={str(path):sha(path) for path in scripts},combined_adoption_executed=False,
        last_goal_turn_classification='PROGRESS_PREPARED_TRUTHFUL_COMBINED_CLOSING_AND_ADOPTION_WITH_ORIGINAL_FAILURE_PRESERVED',
        next_work='Wait actual Pi supervisor17616 exit; require exact official Pi112. Then combined recorder, new combined adopter, independent current-state auditor and finalizer in order. Preserve original18pass1timeout and4edges; no hardware reruns.')
    write(STATE,state)
    print(dict(status=proof['status'],main_adopted=False,pi_process_id=pi_dispatch['process_id'],pi_process_alive=pi_live,
        prepared_scripts=len(scripts),report=str(REPORT),proof=str(OUT),proof_sha256=sha(OUT)))


if __name__=='__main__':
    main()
