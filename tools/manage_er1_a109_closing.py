"""One closing batch on the completed, numerically qualifying A109 executable."""
import argparse
from collections import deque
from datetime import datetime, timezone
import importlib.util
import math
import os
from pathlib import Path
import re
import subprocess
import sys

from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from manage_er1_a109_measurement import check as check_measurement, live, RUN

OUT = Path('F:/CPU2026CourseRuns/ER1_A109_closing_20261006')
PLAN = OUT/'closing_plan.json'
COVERAGE = ROOT/'build/cpu2026/er1_minimal_closing_coverage_20261006.json'
REPORT = ROOT/'reports/ER1_A109_closing_pretest_2026-10-06.md'
STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'


def protocol_module(path):
    spec = importlib.util.spec_from_file_location('a109_original_oj_io',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check():
    original = check_measurement()
    plan = read(PLAN)
    assert plan['source_manifest_sha256'] == original['source_manifest_sha256']
    for name, digest in plan['frozen_sha256'].items():
        assert sha(Path(name)) == digest, name
    return plan


def prepare():
    assert os.name == 'nt' and not OUT.exists() and not REPORT.exists()
    original = check_measurement()
    assert not live(103132), 'Wait for original A109 supervisor to finish'
    phase_path = RUN/'serial_phase_identity.json'
    phase = read(phase_path)
    assert phase['supervisor_pid'] == 103132 and phase['status'] == 'SERIAL_CHARACTERIZATION_COMPLETE'
    assert [(p['phase'],p['returncode']) for p in phase['phases']] == [('timing',0),('performance',0)]
    result_path = RUN/'result/result.json'
    result = read(result_path)
    assert sha(result_path) == phase['result_sha256']
    assert result['status'] == 'COURSE_STANDARD_WINDOWS_MEASUREMENT_COMPLETE'
    assert result['ipc'] >= 1.1 and result['fmax_mhz'] > 300 and result['area_um2'] <= 36000
    assert result['official_perf_expected_results_passed'] and result['latency'] == 10
    assert result['thread_objective_numeric_requirements_met'] and result['official_correctness_suite_not_run']
    config_path = RUN/'course_windows_config.json'
    config = read(config_path)
    assert config['environment'] == 'WINDOWS_NATIVE' and not config['wsl_allowed'] and config['latency'] == 10
    manifest = Path(config['source_manifest'])
    assert sha(manifest) == original['source_manifest_sha256']
    build_path = Path(config['native_build_path'])/'build_identity.json'
    build = read(build_path)
    assert build['status'] == 'COMPLETE' and build['source_manifest_sha256'] == sha(manifest)
    executable = Path(build['executable'])
    assert sha(executable) == build['executable_sha256']
    identity_path = RUN/'result/measurement_identity.json'
    identity = read(identity_path)
    assert identity['status'] == 'COMPLETE' and identity['result_sha256'] == sha(result_path)
    assert identity['prebuilt_cpu']['executable_sha256'] == sha(executable)
    ipc_path = RUN/'result/ipc.json'
    ipc = read(ipc_path)
    assert ipc['status'] == 'COMPLETE' and len(ipc['results']) == 6
    assert identity['ipc_sha256'] == sha(ipc_path)
    assert abs(math.exp(sum(math.log(row['instructions']/row['cycles']) for row in ipc['results'])/6)-result['ipc']) < 1e-12
    assert sha(COVERAGE) == '4cba742b27f80df18db3884c8abc3023505de13e72e6d39f4226298ed7881000'
    coverage = read(COVERAGE)
    suite = Path(coverage['frozen_suite'])
    assert sha(suite) == coverage['frozen_suite_sha256']
    for name, digest in coverage['frozen_suite_input_sha256'].items():
        assert sha(Path(name)) == digest, name
    source = Path(config['source'])
    course = source/'.deps/RISC-V-CPU-2026'
    cases = sorted(path for path in (course/'testcases').glob('correctness_*') if path.is_dir())
    assert len(cases) == 19 and [p.name for p in cases] == [p['name'] for p in coverage['official_rows']]
    frozen = {str(path):sha(path) for path in [Path(__file__),COVERAGE,suite,manifest,config_path,
        result_path,ipc_path,phase_path,build_path,identity_path,executable,REPORT.parent/'ER1_minimal_closing_coverage_2026-10-06.md']}
    for old_name, digest in coverage['official_program_artifacts_sha256'].items():
        old = Path(old_name)
        path = course/'testcases'/old.parent.name/old.name
        assert sha(path) == digest, path
        frozen[str(path)] = digest
    for name, digest in coverage['frozen_suite_input_sha256'].items():
        frozen[name] = digest
    for name in ['testcase.py','oj_io.py','sim.cpp']:
        path = course/'scripts'/name
        if path.exists():
            frozen[str(path)] = sha(path)
    oj = protocol_module(course/'scripts/oj_io.py')
    OUT.mkdir(parents=True)
    edge_cases = []
    for row in coverage['selected_existing_cases']:
        image = Path(row['image'])
        text = image.read_text(encoding='utf-8')
        oj.validate_image(text)
        input_path = OUT/(row['name']+'.in')
        answer_path = OUT/(row['name']+'.ans')
        input_path.write_text(f'CPU2026-OJ 1\n200000 10\n{text.rstrip()}\n',encoding='utf-8')
        answer_path.write_text(f"{row['expected_u32']}\n",encoding='utf-8')
        frozen[str(input_path)] = sha(input_path)
        frozen[str(answer_path)] = sha(answer_path)
        edge_cases.append(dict(name=row['name'],image=str(image),input=str(input_path),answer=str(answer_path),
            expected_u32=row['expected_u32'],max_cycles=200000,oracle_trace_sha256=row['trace_sha256']))
    command = [sys.executable,str(course/'scripts/testcase.py'),'--kind','correctness',
        '--testcases',str(course/'testcases'),'--sim',str(executable),'--latency','10','--max-cycles','10000000']
    REPORT.write_text(f'''# A109 集中正确性验证前汇报

原同一次课程Windows native测量已完成，IPC={result['ipc']:.12f}、Fmax={result['fmax_mhz']:.9f}MHz、含SRAM面积={result['area_um2']:.9f}um²，六性能答案通过。原PID103132已结束，serial timing/performance均rc0；所有源/工具/输入冻结绑定，结果并未重跑或覆盖。

现在只复用同一个CPU exe（SHA256 {sha(executable)}）、同一个source manifest/config与latency10，集中执行19项官方correctness程序（max_cycles10000000）及4项原有冻结边界程序（max_cycles200000）。不构建CPU、不综合/STA、不重跑六perf、不重生成/汇编边界程序。四项为arithmetic_edges_2、memory_low、memory_ram_top、control_alignment_0，涵盖原官方程序缺少的DIVU/MULH/MULHSU/MULHU及既有除零/溢出、RAM顶端、自然对齐、JALR边界。只包装原image为原OJ stdin协议，期望来自已冻结独立解释器；compare_output调用课程原函数，不忽略额外非空输出。

新输出独立保存于{OUT}，不改原成功测量文件。全部23项跑完后，仍需关键参数/源架构审阅及将已验证A109采用到主源；有限程序不能证明任意参数/所有ISA输入。A110/A111未测，保留独立源候选，不混入此次验证。先在对话汇报此集中验证再启动。
''',encoding='utf-8')
    frozen[str(REPORT)] = sha(REPORT)
    plan = dict(status='PREPARED_NOT_RUN',prepared_at=datetime.now(timezone.utc).isoformat(),
        original_run=str(RUN),candidate='A109_rob_occupancy_distribution',
        candidate_sha256=original['candidate_sha256'],source_manifest_sha256=sha(manifest),
        config_sha256=sha(config_path),executable=str(executable),executable_sha256=sha(executable),
        original_result_sha256=sha(result_path),ipc=result['ipc'],fmax_mhz=result['fmax_mhz'],
        area_um2=result['area_um2'],official_command=command,official_cases=[p.name for p in cases],
        edge_cases=edge_cases,latency=10,environment='WINDOWS_NATIVE',runtime_bin=config['runtime_bin'],
        build_bin=config['build_bin'],working_directory=str(source),oj_io=str(course/'scripts/oj_io.py'),
        frozen_sha256=frozen,pretest_report=str(REPORT),pretest_report_sha256=sha(REPORT),
        additional_cpu_builds=0,additional_synthesis_runs=0,performance_repeats=0,
        tests_started=False,goal_complete=False)
    write(PLAN,plan)
    print(dict(status=plan['status'],ipc=plan['ipc'],fmax_mhz=plan['fmax_mhz'],area_um2=plan['area_um2'],
        official_cases=19,edge_cases=4,executable_sha256=plan['executable_sha256'],pretest_report=str(REPORT)))


def start():
    check()
    assert not (OUT/'dispatch_identity.json').exists() and not (OUT/'phase.json').exists()
    with (OUT/'supervisor_stdout.log').open('w',encoding='utf-8') as stdout, (OUT/'supervisor_stderr.log').open('w',encoding='utf-8') as stderr:
        process = subprocess.Popen([sys.executable,'-u',str(Path(__file__).resolve()),'run'],cwd=ROOT,
            stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)
    dispatch = dict(started_at=datetime.now(timezone.utc).isoformat(),process_id=process.pid,
        plan_sha256=sha(PLAN),manager_sha256=sha(Path(__file__)),initial_process_alive=process.poll() is None)
    write(OUT/'dispatch_identity.json',dispatch)
    state = read(STATE)
    state.update(closing_measurement_run=str(OUT),closing_measurement_process_id=process.pid,
        closing_measurement_plan_sha256=sha(PLAN),closing_measurement_started=True,goal_complete=False)
    write(STATE,state)
    print(dispatch)


def run():
    plan = check()
    assert not (OUT/'phase.json').exists() and not (OUT/'closing_result.json').exists()
    phase = dict(status='OFFICIAL_CORRECTNESS_IN_PROGRESS',supervisor_pid=os.getpid(),
        started_at=datetime.now(timezone.utc).isoformat(),plan_sha256=sha(PLAN))
    write(OUT/'phase.json',phase)
    env = dict(os.environ)
    env['PATH'] = ';'.join([plan['runtime_bin'],plan['build_bin'],env['PATH']])
    env['PYTHONUNBUFFERED'] = '1'
    with (OUT/'official_stdout.log').open('w',encoding='utf-8') as stdout, (OUT/'official_stderr.log').open('w',encoding='utf-8') as stderr:
        official = subprocess.run(plan['official_command'],cwd=plan['working_directory'],env=env,
            stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
    text = (OUT/'official_stdout.log').read_text(encoding='utf-8')
    names = re.findall(r'^\[(correctness_[^\]]+)\]$',text,re.MULTILINE)
    pass_rows = re.findall(r'^PASS(?: cycles=(\d+))?$',text,re.MULTILINE)
    summary = re.search(r'^Results: (\d+) passed, (\d+) failed$',text,re.MULTILINE)
    official_ok = (official.returncode == 0 and names == plan['official_cases'] and
        len(pass_rows) == 19 and summary is not None and summary.groups() == ('19','0'))
    phase.update(status='FROZEN_EDGE_CORRECTNESS_IN_PROGRESS',official_returncode=official.returncode,
        official_passed=official_ok,official_observed_cases=names)
    write(OUT/'phase.json',phase)
    oj = protocol_module(Path(plan['oj_io']))
    edges = []
    for case in plan['edge_cases']:
        check()
        begin = datetime.now(timezone.utc).isoformat()
        output = subprocess.run([plan['executable']],input=Path(case['input']).read_text(encoding='utf-8'),
            text=True,capture_output=True,cwd=plan['working_directory'],env=env,
            creationflags=subprocess.CREATE_NO_WINDOW)
        stdout_path = OUT/(case['name']+'.stdout.log')
        stderr_path = OUT/(case['name']+'.stderr.log')
        stdout_path.write_text(output.stdout,encoding='utf-8')
        stderr_path.write_text(output.stderr,encoding='utf-8')
        error = oj.compare_output(output.stdout,Path(case['answer']).read_text(encoding='utf-8'))
        cycles = re.findall(r'^CPU2026 cycles=(\d+)$',output.stderr,re.MULTILINE)
        valid_cycles = len(cycles) == 1 and 0 < int(cycles[0]) <= case['max_cycles']
        passed = output.returncode == 0 and error is None and valid_cycles
        row = dict(name=case['name'],passed=passed,returncode=output.returncode,error=error,
            cycles=int(cycles[0]) if len(cycles) == 1 else None,started_at=begin,
            completed_at=datetime.now(timezone.utc).isoformat(),expected_u32=case['expected_u32'],
            stdout_sha256=sha(stdout_path),stderr_sha256=sha(stderr_path))
        edges.append(row)
        phase['completed_edge_rows'] = edges
        write(OUT/'phase.json',phase)
        print(row,flush=True)
    check()
    result = dict(status='CLOSING_CORRECTNESS_COMPLETE',completed_at=datetime.now(timezone.utc).isoformat(),
        plan_sha256=sha(PLAN),source_manifest_sha256=plan['source_manifest_sha256'],
        candidate_sha256=plan['candidate_sha256'],executable_sha256=plan['executable_sha256'],
        original_result_sha256=plan['original_result_sha256'],official_returncode=official.returncode,
        official_expected_cases=plan['official_cases'],official_observed_cases=names,
        official_passed_count=int(summary[1]) if summary else None,
        official_failed_count=int(summary[2]) if summary else None,official_all_passed=official_ok,
        official_stdout_sha256=sha(OUT/'official_stdout.log'),official_stderr_sha256=sha(OUT/'official_stderr.log'),
        edge_rows=edges,edge_all_passed=all(row['passed'] for row in edges),
        all_23_passed=official_ok and len(edges) == 4 and all(row['passed'] for row in edges),
        latency=10,additional_cpu_builds=0,additional_synthesis_runs=0,performance_repeats=0,
        arbitrary_parameter_dynamic_coverage_claimed=False,full_isa_formal_proof_claimed=False,goal_complete=False)
    write(OUT/'closing_result.json',result)
    phase.update(status='CLOSING_CORRECTNESS_COMPLETE',result_sha256=sha(OUT/'closing_result.json'),
        all_23_passed=result['all_23_passed'])
    write(OUT/'phase.json',phase)
    print(result,flush=True)
    if not result['all_23_passed']:
        raise SystemExit(1)


def observe():
    check()
    dispatch = read(OUT/'dispatch_identity.json')
    phase = optional(OUT/'phase.json')
    result = optional(OUT/'closing_result.json')
    observation = dict(observed_at=datetime.now(timezone.utc).isoformat(),process_id=dispatch['process_id'],
        process_alive=live(dispatch['process_id']),phase=phase,
        result=({key:result.get(key) for key in ['status','official_all_passed','edge_all_passed','all_23_passed']} if result else None))
    for name in ['official_stdout.log','official_stderr.log','supervisor_stderr.log']:
        path = OUT/name
        if path.exists():
            with path.open(encoding='utf-8',errors='replace') as stream:
                observation[name] = list(deque(stream,maxlen=4))
    print(observation)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','start','run','observe'])
    args = parser.parse_args()
    assert os.name == 'nt'
    if args.action == 'run':
        try:
            run()
        except Exception as error:
            failure = dict(status='CLOSING_FAILED',process_id=os.getpid(),
                failed_at=datetime.now(timezone.utc).isoformat(),error=repr(error))
            write(OUT/'failure.json',failure)
            phase = optional(OUT/'phase.json') or {}
            phase.update(status='CLOSING_FAILED',failure_sha256=sha(OUT/'failure.json'))
            write(OUT/'phase.json',phase)
            raise
    else:
        {'prepare':prepare,'start':start,'observe':observe}[args.action]()
