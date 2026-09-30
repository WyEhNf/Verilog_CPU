"""Measure the frozen AXI CPU using the course's original external RAM driver.

Images/answers come from the already-built project suites; retirement counts
are measured on the RTL, not borrowed from the earlier line-memory simulator.
The official C++ driver differs by one read-only counter print, verified here.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, default=ROOT / 'build/vlt/course_axi_p4_r32p64_ctx')
    parser.add_argument('--suite', choices=('benchmark', 'basic', 'simulator', 'boundary'), default='benchmark')
    parser.add_argument('--latency', type=int, default=20)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--source-snapshot', type=Path,
                        help='Verify a frozen build against its immutable area source snapshot instead of the working tree')
    args = parser.parse_args()
    if args.latency != 20:
        parser.error('This performance/correctness audit requires latency20')
    manifest_path = args.build / 'build_manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    source_root = args.source_snapshot.resolve() if args.source_snapshot else ROOT
    inputs = {source_root / name: expected.lower() for name, expected in manifest['source_sha256'].items()}
    inputs[Path(manifest['executable'])] = manifest['executable_sha256'].lower()
    observed_driver = Path(manifest['generated_driver'])
    inputs[observed_driver] = manifest['generated_driver_sha256'].lower()
    inputs[Path(__file__)] = sha(Path(__file__))
    for path, expected in inputs.items():
        if sha(path) != expected:
            raise SystemExit('Frozen course input changed: ' + str(path))
    original = (source_root / '.deps/RISC-V-CPU-2026/scripts/sim.cpp').read_text()
    observed = observed_driver.read_text()
    observation = '        std::cerr << "CPU2026 instret=" << top.debug_instret << std::endl;\n'
    if observed.count(observation) != 1 or observed.replace(observation, '') != original:
        raise SystemExit('Driver differs by more than one nonintrusive retirement print')
    if args.suite == 'benchmark':
        local_path = ROOT / 'build/cpu2026/dcache_sram_ram256m_report.json'
        inputs[local_path] = sha(local_path)
        local = json.loads(local_path.read_text(encoding='utf-8-sig'))
        cases = [(item['name'], ROOT / item['image'], 0, 20_000_000) for item in local['results']]
        if len(cases) != 6 or {name for name, *_ in cases} != {'median', 'multiply', 'qsort', 'rsort', 'towers', 'vvadd'}:
            raise SystemExit('All six authorized benchmarks required')
    elif args.suite == 'basic':
        cases = [(name, ROOT / f'build/cpu2026/final_basic/{name}/{name}.image', result, 1_000_000)
                 for name, result in (('vmul', 8), ('vvadd', 72), ('accumulate', 5050),
                                      ('halfword_smoke', 0), ('m_isa_smoke', 90))]
    elif args.suite == 'boundary':
        cases = [('ram-256m-last-word', ROOT / 'build/images/ram_256m_last_word/ram_256m_last_word.image', 598, 100_000)]
    else:
        local_path = ROOT / 'build/cpu2026/simulator_mmio_dcache_sram_ram256m_report.json'
        inputs[local_path] = sha(local_path)
        local = json.loads(local_path.read_text(encoding='utf-8-sig'))
        cases = [(item['name'], ROOT / f"build/cpu2026/simulator_mmio/{item['name']}/{item['name']}.image",
                  item['expected_signed'], 20_000_000) for item in local['results']]
        if len(cases) != 17 or len({name for name, *_ in cases}) != 17 or any(name == 'pi' for name, *_ in cases):
            raise SystemExit('Exactly 17 simulator cases excluding frozen pi required')
    for _, image, _, _ in cases:
        inputs[image] = sha(image)
    results = []
    for name, image, expected, limit in cases:
        command = [manifest['executable'], str(image), str(expected & 0xffffffff), str(limit), '20']
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        pass_line = re.search(r'^PASS cycles=(\d+) result=(\d+) expected=(\d+)$', completed.stdout, re.MULTILINE)
        retired = re.search(r'^CPU2026 instret=(\d+)$', completed.stderr, re.MULTILINE)
        if (completed.returncode or not pass_line or not retired or
                int(pass_line[2]) != (expected & 0xffffffff) or
                int(pass_line[3]) != (expected & 0xffffffff)):
            raise SystemExit(name + ' failed:\n' + completed.stdout + completed.stderr)
        cycles, instret = int(pass_line[1]), int(retired[1])
        if not cycles or not instret:
            raise SystemExit('Invalid cycle/retirement count')
        result = dict(name=name, status='passed', image=str(image), expected_u32=expected & 0xffffffff,
                      return_u32=int(pass_line[2]), cycles=cycles, instret=instret, ipc=instret/cycles)
        results.append(result)
        print(f'PASS: AXI {name} cycles={cycles} instret={instret} IPC={instret/cycles:.6f}', flush=True)
    for path, expected in inputs.items():
        if sha(path) != expected:
            raise SystemExit('Input changed during course evaluation: ' + str(path))
    total_cycles = sum(item['cycles'] for item in results)
    total_instret = sum(item['instret'] for item in results)
    current_differences = [name for name, expected in manifest['source_sha256'].items()
                           if not (ROOT / name).is_file() or sha(ROOT / name) != expected.lower()]
    report = dict(format='cpu2026-course-axi-v1', suite=args.suite, status='COMPLETE', results=results,
                  external_memory=dict(driver='official sim.cpp plus one counter observation',
                                       word_bytes=4, shared_ar_r=True, independent_aw_w_b=True,
                                       fifo_depth=16, latency_cycles=20, exit_at_b_handshake=True,
                                       external_ram_bytes=268435456),
                  build_manifest=str(manifest_path), evaluated_source_root=str(source_root),
                  evaluates_current_worktree=not current_differences,
                  current_source_differences=current_differences,
                  total_cycles=total_cycles, total_instret=total_instret,
                  aggregate_ipc=total_instret/total_cycles,
                  geomean_ipc=math.exp(sum(math.log(item['ipc']) for item in results)/len(results)),
                  source_sha256={str(path): expected for path, expected in inputs.items()}, pi_excluded=True)
    destination = args.report or ROOT / f'build/cpu2026/course_axi_{args.suite}_report.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n')
    print(f"COMPLETE: {args.suite} {len(results)} cases GEO_IPC={report['geomean_ipc']:.9f}")


if __name__ == '__main__':
    main()
