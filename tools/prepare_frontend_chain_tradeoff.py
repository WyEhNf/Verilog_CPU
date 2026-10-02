"""Stage one frontend response/request chaining switch in an isolated CPU.

Default 1 preserves the baseline; 0 waits for the registered next PC before
launching another request. It changes cycle behavior and needs full native
regression/IPC measurement, not an equivalence claim for mode 0.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def replace(text, old, new):
    assert text.count(old)==1, 'Ambiguous anchor: '+old
    return text.replace(old,new)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--baseline-build',type=Path,required=True)
    parser.add_argument('--outdir',type=Path,required=True)
    args=parser.parse_args()
    source,out=args.source_root.resolve(),args.outdir.resolve()
    assert not out.exists()
    build=read(args.baseline_build)
    compiled={name:h.lower() for name,h in build['source_sha256'].items()}
    dependencies=read(source/'measurement_dependencies.json')['input_sha256']
    files=dependencies|compiled
    for name,expected in files.items():
        assert sha(source/name)==expected.lower(), 'Baseline changed: '+name
        target=out/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/name,target)
    changed=['rtl/frontend/rv32_fetch_frontend.v','rtl/cpu_core.v','rtl/course/student_top.v']
    for name in changed:
        backup=out/'baseline'/name
        backup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/name,backup)
        code=(out/name).read_text(encoding='utf-8')
        if name.endswith('rv32_fetch_frontend.v'):
            code=replace(code,'    parameter integer PREDICTOR_META = 0',
                '    parameter integer RESPONSE_CHAINING = 1,\n    parameter integer PREDICTOR_META = 0')
            code=replace(code,'    wire response_can_chain = if_resp_valid_i && if_resp_ready_o &&',
                '    wire response_can_chain = (RESPONSE_CHAINING != 0) &&\n'
                '                              if_resp_valid_i && if_resp_ready_o &&')
            code=replace(code,'    initial begin\n',
                '    initial begin\n        if (RESPONSE_CHAINING != 0 && RESPONSE_CHAINING != 1)\n'
                '            $fatal(1, "Invalid frontend response chaining configuration");\n')
        else:
            code=replace(code,'    parameter integer RAT_READ_BYPASS = 0,',
                '    parameter integer RAT_READ_BYPASS = 0,\n'
                '    parameter integer FRONTEND_RESPONSE_CHAINING = 1,')
            if name.endswith('cpu_core.v'):
                code=replace(code,'.PREDICTOR_META(PREDICTOR_DIRECT_BRANCH_TARGET == 2)) frontend (',
                    '.PREDICTOR_META(PREDICTOR_DIRECT_BRANCH_TARGET == 2),\n'
                    '        .RESPONSE_CHAINING(FRONTEND_RESPONSE_CHAINING)) frontend (')
            else:
                code=replace(code,'.RAT_READ_BYPASS(RAT_READ_BYPASS),',
                    '.RAT_READ_BYPASS(RAT_READ_BYPASS), .FRONTEND_RESPONSE_CHAINING(FRONTEND_RESPONSE_CHAINING),')
        (out/name).write_text(code,encoding='utf-8')
    actual=[name for name,h in compiled.items() if sha(out/name)!=h]
    assert set(actual)==set(changed)
    assert all(sha(source/name)==h.lower() for name,h in files.items())
    report=dict(status='STAGED',purpose=__doc__,source_root=str(source),source_mutated=False,
                baseline_build=str(args.baseline_build.resolve()),baseline_build_sha256=sha(args.baseline_build),
                baseline_sha256=compiled,staged_sha256={n:sha(out/n) for n in compiled},
                changed_files=changed,parameter_default=1,experiment_parameter=0,
                measurement_dependencies_sha256={n:sha(out/n) for n in dependencies},
                not_yet_cpu_result=True,preparer_sha256=sha(__file__))
    (out/'staging_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status='STAGED',root=str(out),changed_files=changed,compiled_inputs=len(compiled))))


if __name__=='__main__':
    main()
