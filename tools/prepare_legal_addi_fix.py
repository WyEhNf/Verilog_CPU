"""Propagate the existing legacy-halt mode into fetch and predictor prefixing.

Course/default mode must execute ADDI a0,zero,255 as ordinary RV32I, including
at cache-line ends. Preserve the explicit legacy mode for older testbenches.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from prepare_functional_hierarchy import sha, read


def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--baseline-result', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.source_root.resolve(), args.outdir.resolve()
    assert not out.exists()
    verified = read(args.baseline_result)
    assert verified['status'] == 'VERIFIED' and verified['all_correctness_cases'] == 29
    assert Path(verified['evaluated_source_root']).resolve() == source
    for name, value in verified['input_sha256'].items():
        assert sha(name) == value, name
    manifest_path = Path(verified['directory'])/'build/build_manifest.json'
    manifest = read(manifest_path)
    originals = {n:h.lower() for n,h in manifest['source_sha256'].items()}
    dependencies = read(source/'measurement_dependencies.json')['input_sha256']
    files = dependencies | originals
    for name, value in files.items():
        assert sha(source/name) == value.lower(), name
    framework = out/'.deps/RISC-V-CPU-2026'
    framework.parent.mkdir(parents=True)
    revision = '54fc150ffc290f52aa024209ffb9a29d43856f6d'
    subprocess.run(['git','clone','--no-hardlinks','--no-checkout',str(source/'.deps/RISC-V-CPU-2026'),str(framework)], check=True)
    subprocess.run(['git','-C',str(framework),'checkout','--detach',revision], check=True)
    for name in files:
        target = out/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name, target)
    dependency_manifest = dict(status='COMPLETE', source_root=str(source), stage_root=str(out),
                               purpose='Byte-identical inherited measurement dependencies',
                               input_sha256={n:sha(out/n) for n in dependencies})
    (out/'measurement_dependencies.json').write_text(json.dumps(dependency_manifest,indent=2)+'\n')
    changed = {'rtl/frontend/rv32_fetch_frontend.v', 'rtl/predictor/rv32_banked_predictor.v', 'rtl/cpu_core.v'}
    for name in changed:
        backup = out/'baseline'/name
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source/name, backup)
    path = out/'rtl/frontend/rv32_fetch_frontend.v'
    code = path.read_text()
    code = replace(code, '    parameter integer PREDICTOR_META = 0',
                   '    parameter integer LEGACY_SENTINEL_HALT = 0,\n    parameter integer PREDICTOR_META = 0')
    code = replace(code, "                if ((if_resp_line_data_i >> ((word_index+b)*32)) == 32'h0ff00513) begin",
                   "                if ((LEGACY_SENTINEL_HALT != 0) &&\n                    ((if_resp_line_data_i >> ((word_index+b)*32)) == 32'h0ff00513)) begin")
    path.write_text(code)
    path = out/'rtl/predictor/rv32_banked_predictor.v'
    code = path.read_text()
    code = replace(code, '    parameter integer DIRECT_BRANCH_TARGET = 0,',
                   '    parameter integer LEGACY_SENTINEL_HALT = 0,\n    parameter integer DIRECT_BRANCH_TARGET = 0,')
    code = replace(code, "                    ((query_line_i >> (history_word*32)) == 32'h0ff00513))",
                   "                    ((LEGACY_SENTINEL_HALT != 0) &&\n                     ((query_line_i >> (history_word*32)) == 32'h0ff00513)))")
    path.write_text(code)
    path = out/'rtl/cpu_core.v'
    code = path.read_text()
    code = replace(code, '.HISTORY_BITS(PREDICTOR_HISTORY_BITS)) predictor (',
                   '.HISTORY_BITS(PREDICTOR_HISTORY_BITS), .LEGACY_SENTINEL_HALT(LEGACY_SENTINEL_HALT)) predictor (')
    code = replace(code, '.PREDICTOR_META(PREDICTOR_DIRECT_BRANCH_TARGET == 2)) frontend (',
                   '.PREDICTOR_META(PREDICTOR_DIRECT_BRANCH_TARGET == 2), .LEGACY_SENTINEL_HALT(LEGACY_SENTINEL_HALT)) frontend (')
    path.write_text(code)
    assert {n for n,h in originals.items() if sha(out/n) != h} == changed
    assert not subprocess.check_output(['git','-C',str(framework),'status','--porcelain'],text=True).strip()
    sta = out/'.deps/OpenSTA/build/sta'
    sta.parent.mkdir(parents=True)
    shutil.copyfile(source/'.deps/OpenSTA/build/sta',sta)
    root = Path(__file__).resolve().parents[1]
    for name in ['tb/unit/rv32_fetch_frontend_tb.v', 'tb/unit/rv32_banked_predictor_tb.v',
                 'tb/unit/rv32_frontend_legal_addi_tb.v',
                 'tb/unit/rv32_indexed_history_predictor_tb.v',
                 'tb/unit/rv32_predictor_legal_addi_tb.v']:
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,target)
    reproduction = Path('F:/CPU2026Proofs/legal_addi255_reproduction_20261003/reproduction.json')
    assert read(reproduction)['status'] == 'REPRODUCED_TIMEOUT'
    result = dict(status='STAGED', source_root=str(source), baseline_result=str(args.baseline_result.resolve()),
                  baseline_manifest=str(manifest_path), baseline_sha256=originals,
                  staged_sha256={n:sha(out/n) for n in originals}, changed_files=sorted(changed),
                  parameters=manifest['parameter_overrides'],
                  measurement_dependencies_sha256={n:sha(out/n) for n in dependencies},
                  original_framework_revision=revision, opensta_sha256=sha(sta),
                  baseline_has_confirmed_isa_defect=True, reproduction=str(reproduction),
                  reproduction_sha256=sha(reproduction), legacy_mode_preserved=True,
                  no_cpu_ppa_claim=True, preparer_sha256=sha(__file__))
    (out/'staging_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='STAGED',changed_files=sorted(changed),compiled_inputs=len(originals)),indent=2))


if __name__ == '__main__':
    main()
