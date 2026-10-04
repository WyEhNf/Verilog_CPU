"""Prepare only the two memory/recovery cases, or run the frozen CPU once."""
import argparse
import json
from pathlib import Path
import frequency_directed_cases_native as base
import test_rv32im_native_edges as assembler


def prepare(out):
    if out.exists():
        raise FileExistsError('Preserve prepared cases: '+str(out))
    out.mkdir(parents=True)
    inputs={str(Path(path).resolve()):base.sha(path) for path in
            (__file__,base.__file__,assembler.__file__)}
    for tool in ('as','ld','objcopy','objdump'):
        path=base.BIN/f'riscv-none-elf-{tool}.exe'
        inputs[str(path)]=base.sha(path)
    cases=[]
    for name,builder in [('lsq_wrap_forward',base.memory_order),('recovery_reuse',base.recovery)]:
        program=builder()
        case=out/name
        case.mkdir()
        code,image=base.assemble(name,program.finish(),case)
        (case/'program.data').write_bytes(image.read_bytes())
        (case/'expected.txt').write_text('0\n',encoding='utf-8')
        (case/'checks.json').write_text(json.dumps(program.checks,indent=2)+'\n',encoding='utf-8')
        cases.append(dict(name=name,expected_u32=0,checks=len(program.checks),image_bytes=len(code)))
        for path in case.iterdir():
            if path.is_file():
                inputs[str(path.resolve())]=base.sha(path)
    manifest=dict(status='PREPARED_NOT_SIMULATED',cases=cases,input_sha256=inputs,
                  max_cycles=100000,latency=10,
                  scope='Two finite memory/recovery architectural cases; not internal-state proof or official IPC')
    (out/'cases.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=manifest['status'],cases=cases)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--config',type=Path)
    args=parser.parse_args()
    if args.config:
        base.run(args.out.resolve(),args.config.resolve())
    else:
        prepare(args.out.resolve())
