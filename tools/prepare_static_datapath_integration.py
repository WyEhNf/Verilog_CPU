"""Stage RS static allocation and PRF parallel reads without changing live inputs.

The source tree used by a running CPU PPA and queued tradeoff remains frozen.
This prepares the five-file integration for review and elaborates all actual
CPU sources at the same parameters. It is not simulation or a CPU PPA result.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def replace_once(text, before, after):
    assert text.count(before) == 1, 'Expected one integration anchor: ' + before
    return text.replace(before, after, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-manifest', type=Path, required=True)
    parser.add_argument('--rs-candidate', type=Path, required=True)
    parser.add_argument('--prf-candidate', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh staging directory')
    baseline = json.loads(args.build_manifest.read_text(encoding='utf-8-sig'))
    originals = baseline['source_sha256']
    for name, expected in originals.items():
        assert digest(ROOT/name).lower() == expected.lower(), 'Live input changed: ' + name
    replacements = {
        'rtl/backend/rv32_reservation_station.v': args.rs_candidate.resolve()/'rtl/backend/rv32_reservation_station.v',
        'rtl/rv32_physical_register_file.v': args.prf_candidate.resolve()/'rtl/rv32_physical_register_file.v',
    }
    expected_candidates = {
        'rtl/backend/rv32_reservation_station.v': '9dbf90f1121ac3f0495b4910a3c42502d167db036c50fec49cdd3307a507365f',
        'rtl/rv32_physical_register_file.v': '2e38185e5dfac4ffe479134505c04aae13f598518685363c32d9d02e39b5a86b',
    }
    for name, path in replacements.items():
        assert digest(path) == expected_candidates[name], 'Candidate changed: ' + name
    out.mkdir(parents=True)
    for name in originals:
        target = out/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    modified = dict(replacements)
    for name in ['rtl/course/student_top.v', 'rtl/cpu_core.v', 'rtl/backend/rv32_backend_joint.v']:
        modified[name] = None
    for name in modified:
        backup = out/'baseline'/name
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, backup)
    for name, path in replacements.items():
        shutil.copyfile(path, out/name)
    for name in ['rtl/course/student_top.v', 'rtl/cpu_core.v', 'rtl/backend/rv32_backend_joint.v']:
        path = out/name
        code = path.read_text()
        code = replace_once(code, '    parameter integer RS_WAKE_MUX_IMPL = 0,',
                            '    parameter integer RS_WAKE_MUX_IMPL = 0,\n'
                            '    parameter integer RS_ALLOC_STATIC_WRITE = 0,\n'
                            '    parameter integer PRF_READ_MUX_IMPL = 0,')
        if name.endswith('rv32_backend_joint.v'):
            code = replace_once(code, '.WAKE_MUX_IMPL(RS_WAKE_MUX_IMPL)) rs (',
                                '.WAKE_MUX_IMPL(RS_WAKE_MUX_IMPL), .ALLOC_STATIC_WRITE(RS_ALLOC_STATIC_WRITE)) rs (')
            code = replace_once(code, 'rv32_physical_register_file #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS)) prf (',
                                'rv32_physical_register_file #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS), .READ_MUX_IMPL(PRF_READ_MUX_IMPL)) prf (')
        else:
            code = replace_once(code, '.RS_WAKE_MUX_IMPL(RS_WAKE_MUX_IMPL),',
                                '.RS_WAKE_MUX_IMPL(RS_WAKE_MUX_IMPL), .RS_ALLOC_STATIC_WRITE(RS_ALLOC_STATIC_WRITE), .PRF_READ_MUX_IMPL(PRF_READ_MUX_IMPL),')
        path.write_text(code)
    changed = [name for name in originals if digest(out/name).lower() != originals[name].lower()]
    assert set(changed) == set(modified)
    for name in replacements:
        assert digest(out/name) == expected_candidates[name]
    params = baseline['parameter_overrides'] | dict(RS_ALLOC_STATIC_WRITE=1, PRF_READ_MUX_IMPL=1)
    files = []
    for line in (out/'verilog/filelist.f').read_text().splitlines():
        name = line.split('#',1)[0].strip()
        if name:
            files.append((out/'verilog'/name).resolve())
    files.append(out/'.deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv')
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    compiler = suite/'bin/iverilog.exe'
    command = [str(compiler), '-g2012', '-I', str(out/'rtl'), '-s', 'student_top',
               '-o', str(out/'student_top.vvp')]
    command += [f'-Pstudent_top.{name}={value}' for name,value in sorted(params.items())]
    command += [str(path) for path in files]
    report = dict(status='STAGED', main_tree_modified=False, is_cpu_simulation=False,
                  is_cpu_ppa=False, candidate_only=True,
                  baseline_manifest=str(args.build_manifest.resolve()),
                  baseline_manifest_sha256=digest(args.build_manifest),
                  baseline_sha256=originals, staged_sha256={n:digest(out/n) for n in originals},
                  changed_files=changed, parameters=params, compile_command=command,
                  compiler_sha256=digest(compiler), preparer_sha256=digest(Path(__file__)))
    def save():
        (out/'staging_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    print('START complete CPU elaboration of staged five-file integration',flush=True)
    log = out/'elaborate.log'
    with log.open('w') as stream:
        result = subprocess.run(command,cwd=out,env=env,stdout=stream,stderr=subprocess.STDOUT)
    assert all(digest(ROOT/n).lower() == h.lower() for n,h in originals.items()), 'Live inputs changed while staging'
    assert all(digest(out/n) == h for n,h in report['staged_sha256'].items()), 'Staged input changed'
    report.update(status='ELABORATED' if result.returncode == 0 else 'ELABORATION_FAILED',
                  elaborate_log_sha256=digest(log), elaborate_returncode=result.returncode)
    if result.returncode == 0:
        report['elaborated_model_sha256'] = digest(out/'student_top.vvp')
    save()
    if result.returncode:
        raise SystemExit('Staged CPU elaboration failed; see ' + str(log))
    print('COMPLETE staged CPU elaboration; main inputs unchanged; no CPU score',flush=True)


if __name__ == '__main__':
    main()
