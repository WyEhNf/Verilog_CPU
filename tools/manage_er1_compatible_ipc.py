"""One native ER1 IPC build after a recorded identifier-only compatibility repair."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from wait_frequency_directed_native import live

ORIGINAL = Path('F:/CPU2026CourseRuns/architecture_ER1_20261005')
RUN = Path('F:/CPU2026CourseRuns/ER1_native_identifier_compat_20261005')


def check():
    proof = read(RUN/'compatibility_identity.json')
    original = read(ORIGINAL/'source_manifest.json')
    manifest = read(RUN/'source_manifest.json')
    assert proof['original_manifest_sha256'] == sha(ORIGINAL/'source_manifest.json')
    assert proof['compatible_manifest_sha256'] == sha(RUN/'source_manifest.json')
    assert proof['original_timing_sha256'] == sha(ORIGINAL/'result/timing_only.json')
    timing = read(ORIGINAL/'result/timing_only.json')
    assert timing['official_report_sha256'] == sha(ORIGINAL/'result/synth/opt/report.json')
    for name, expected in original['snapshot_sha256'].items():
        assert sha(ORIGINAL/'source'/name) == expected
        assert sha(RUN/'source'/name) == manifest['snapshot_sha256'][name]
        if name != proof['renamed_file']:
            assert expected == manifest['snapshot_sha256'][name], name
    changed = (RUN/'source'/proof['renamed_file']).read_bytes()
    assert changed.replace(b'response_query_matches', b'matches') == (ORIGINAL/'source'/proof['renamed_file']).read_bytes()
    assert sha(RUN/'course_windows_config.json') == proof['config_sha256']
    assert sha(proof['pretest_report']) == proof['pretest_report_sha256']
    assert proof['manager_sha256'] == sha(__file__)
    return proof, manifest


def run_programs():
    proof, manifest = check()
    config = read(RUN/'course_windows_config.json')
    out = RUN/'result'
    assert not out.exists()
    out.mkdir()
    env = dict(os.environ, PYTHONUNBUFFERED='1')
    env['PATH'] = config['runtime_bin']+';'+config['build_bin']+';'+env['PATH']
    build_command = [sys.executable, '-u', str(ROOT/'tools/prebuild_course_windows.py'),
                     '--config', str(RUN/'course_windows_config.json')]
    print('START native ER1 identifier-compatible build', flush=True)
    with (out/'build_host.log').open('w', encoding='utf-8') as stream:
        result = subprocess.run(build_command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        # Continue only the existing native make/link portability repair.
        log = (RUN/'native_build/build.log').read_text(errors='replace')
        known = any(s in log for s in ('ar: command not found', 'ar.exe', 'undefined reference to `sc_time_stamp', 'undefined reference to sc_time_stamp'))
        if known and (RUN/'native_build/obj/Vstudent_top.mk').is_file():
            with (out/'build_host_resume.log').open('w', encoding='utf-8') as stream:
                result = subprocess.run(build_command+['--resume-generated'], cwd=ROOT, env=env,
                                        stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            write(out/'failure.json', dict(phase='BUILD', returncode=result.returncode))
            raise SystemExit('Native build failed; preserve all generated files')
    build = read(RUN/'native_build/build_identity.json')
    assert build['status'] == 'COMPLETE' and build['source_manifest_sha256'] == sha(RUN/'source_manifest.json')
    assert build['executable_sha256'] == sha(build['executable'])
    cases = RUN/'source/.deps/RISC-V-CPU-2026/testcases'
    command = [sys.executable, '-u', str(cases.parent/'scripts/testcase.py'), '--kind', 'perf',
               '--testcases', str(cases), '--sim', build['executable'], '--latency', '10']
    print('START six official ER1 performance cases, latency=10', flush=True)
    with (out/'perf.log').open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, cwd=RUN/'source', env=env, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        write(out/'failure.json', dict(phase='PERF', returncode=result.returncode))
        raise SystemExit('Official performance case failed')
    rows = []
    for line in (out/'perf.log').read_text().splitlines():
        match = re.fullmatch(r'(perf_\S+)\s+(\d+)\s+(\d+)\s+([0-9.]+)', line)
        if not match:
            continue
        name, inst, cycles, _ = match.groups()
        case = cases/name
        assert int(inst) == read(case/'metrics.json')['dynamic_instructions'] and int(cycles) > 0
        rows.append(dict(name=name, instructions=int(inst), cycles=int(cycles), ipc=int(inst)/int(cycles),
                         program_sha256=sha(case/'program.data'), metrics_sha256=sha(case/'metrics.json')))
    assert len(rows) == 6 and sorted(r['name'] for r in rows) == proof['perf_cases']
    ipc = dict(status='COMPLETE', latency=10, results=rows,
               geomean_ipc=math.exp(sum(math.log(r['ipc']) for r in rows)/6),
               source_manifest_sha256=sha(RUN/'source_manifest.json'),
               original_er1_manifest_sha256=proof['original_manifest_sha256'],
               compatibility_identity_sha256=sha(RUN/'compatibility_identity.json'),
               build_identity_sha256=sha(RUN/'native_build/build_identity.json'),
               executable_sha256=build['executable_sha256'], official_perf_answers_passed=True,
               official_scripts_unmodified=True, official_sim_cpp_unmodified=True,
               full_correctness_run=False, new_synthesis_run=False)
    check()
    write(out/'ipc.json', ipc)
    print(json.dumps(ipc, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'start', 'observe', 'run'))
    args = parser.parse_args()
    assert os.name == 'nt'
    if args.action == 'prepare':
        assert not RUN.exists()
        failed = read(ORIGINAL/'baseline_program_observation.json')
        assert failed['status'] == 'FAILED' and not live(failed['process_id'])
        errors = (ORIGINAL/'native_build/build.log').read_text(errors='replace')
        assert 'syntax error, unexpected matches' in errors
        manifest = read(ORIGINAL/'source_manifest.json')
        for name, expected in manifest['snapshot_sha256'].items():
            assert sha(ORIGINAL/'source'/name) == expected
            target = RUN/'source'/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ORIGINAL/'source'/name, target)
        name = 'rtl/backend/rv32_lsq.v'
        target = RUN/'source'/name
        original = target.read_bytes()
        assert b'response_query_matches' not in original
        # Exact alpha-renaming: only the four lines containing the declaration
        # and three assignments, five identifier occurrences. Comments unchanged.
        lines = original.splitlines(keepends=True)
        changed_lines = 0
        for i, line in enumerate(lines):
            if line.lstrip().startswith((b'wire ', b'assign ')) and re.search(rb'\bmatches\b', line):
                lines[i] = re.sub(rb'\bmatches\b', b'response_query_matches', line)
                changed_lines += 1
        changed = b''.join(lines)
        assert changed_lines == 4 and changed.count(b'response_query_matches') == 5
        assert changed.replace(b'response_query_matches', b'matches') == original
        target.write_bytes(changed)
        manifest.update(source_root=str(RUN/'source'), status='ER1_IDENTIFIER_COMPATIBLE_FROZEN',
                        original_er1_manifest_sha256=sha(ORIGINAL/'source_manifest.json'))
        manifest['snapshot_sha256'][name] = sha(target)
        write(RUN/'source_manifest.json', manifest)
        config = read(ORIGINAL/'course_windows_config.json')
        config.update(source=str(RUN/'source'), source_manifest=str(RUN/'source_manifest.json'),
                      native_build_path=str(RUN/'native_build'), native_ipc_path=str(RUN/'native_ipc'), out=str(RUN/'result'))
        write(RUN/'course_windows_config.json', config)
        report = ROOT/'reports/ER1_identifier_compat_ipc_pretest_2026-10-05.md'
        assert not report.exists()
        report.write_text('''# ER1 IPC 构建兼容修复与测量前汇报

第一次构建在程序运行前失败：Verilator5.020将 matches 识别为SystemVerilog保留字。
原ER1冻结源、综合结果、失败构建和日志全部保留。独立副本仅对LSQ局部信号做alpha重命名：
matches → response_query_matches，四行、五处标识符；反向字节替换与原文件完全一致，其他156文件逐一SHA256相同。
没有逻辑、参数、寄存器、时钟边界、握手或程序变化。这是兼容修复，不是架构优化。

构建修复后的副本并运行六个官方perf一次，latency10，原metrics指令数/GEOMEAN口径。
不再综合/STA，不运行额外回归。IPC明确记录为ER1标识符兼容副本结果，并引用原ER1综合身份；
不会伪造相同源码hash，也不会把当前EU的频率/面积混入基线。
Windows原生Verilator5.020/课程工具链，禁止WSL。CPU构建与六程序此时尚未启动；汇报后后台执行。
''', encoding='utf-8')
        cases = RUN/'source/.deps/RISC-V-CPU-2026/testcases'
        proof = dict(status='IDENTIFIER_ONLY_REPAIR_PREPARED', renamed_file=name,
                     changed_lines=changed_lines, renamed_occurrences=5, inverse_bytes_identical=True,
                     original_manifest_sha256=sha(ORIGINAL/'source_manifest.json'),
                     compatible_manifest_sha256=sha(RUN/'source_manifest.json'),
                     original_timing_sha256=sha(ORIGINAL/'result/timing_only.json'),
                     config_sha256=sha(RUN/'course_windows_config.json'), manager_sha256=sha(__file__),
                     pretest_report=str(report), pretest_report_sha256=sha(report),
                     perf_cases=sorted(p.name for p in cases.glob('perf_*') if p.is_dir()))
        write(RUN/'compatibility_identity.json', proof)
        print(json.dumps(proof, ensure_ascii=False))
        return
    proof, manifest = check()
    if args.action == 'run':
        run_programs()
        return
    if args.action == 'start':
        assert not (RUN/'dispatch.json').exists() and not (RUN/'result').exists()
        command = [sys.executable, '-u', str(Path(__file__).resolve()), 'run']
        with (RUN/'stdout.log').open('w', encoding='utf-8') as stdout, (RUN/'stderr.log').open('w', encoding='utf-8') as stderr:
            process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                                       creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
        dispatch = dict(process_id=process.pid, command=command, started_at=datetime.now(timezone.utc).isoformat(),
                        proof_sha256=sha(RUN/'compatibility_identity.json'), initial_alive=process.poll() is None)
        write(RUN/'dispatch.json', dispatch)
        print(json.dumps(dispatch))
        return
    dispatch = read(RUN/'dispatch.json')
    assert dispatch['proof_sha256'] == sha(RUN/'compatibility_identity.json')
    ipc = optional(RUN/'result/ipc.json')
    failure = optional(RUN/'result/failure.json')
    if ipc:
        assert ipc['compatibility_identity_sha256'] == sha(RUN/'compatibility_identity.json')
        assert ipc['source_manifest_sha256'] == sha(RUN/'source_manifest.json')
        assert ipc['build_identity_sha256'] == sha(RUN/'native_build/build_identity.json')
        build = read(RUN/'native_build/build_identity.json')
        assert ipc['executable_sha256'] == sha(build['executable'])
        assert len(ipc['results']) == 6 and ipc['official_perf_answers_passed']
        assert math.isclose(ipc['geomean_ipc'], math.exp(sum(math.log(r['instructions']/r['cycles']) for r in ipc['results'])/6), rel_tol=1e-12)
    alive = live(dispatch['process_id'])
    observation = dict(status='IN_PROGRESS' if alive else 'COMPLETE' if ipc else 'FAILED' if failure else 'TERMINAL_INCOMPLETE',
                       observed_at=datetime.now(timezone.utc).isoformat(), process_id=dispatch['process_id'],
                       process_live_now=alive, measured_ipc=ipc['geomean_ipc'] if ipc else None,
                       identifier_only_repair=True, new_synthesis_run=False, failure=failure)
    write(RUN/'observation.json', observation)
    print(json.dumps(observation))


if __name__ == '__main__':
    main()
