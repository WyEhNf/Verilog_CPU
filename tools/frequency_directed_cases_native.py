"""Three finite architecture cases on one pinned frozen native course CPU.

No RTL recompile, parameter sweep, alternate memory timing, or IPC grade.
Preparation assembles the programs; execution reuses the course CPU/oj_io.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

from test_rv32im_native_edges import assemble, BIN

MASK=(1<<32)-1


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def signed(value):
    return value if value<1<<31 else value-(1<<32)


class Program:
    def __init__(self):
        self.lines=[]
        self.checks=[]

    def emit(self,*lines):
        self.lines.extend(lines)

    def check(self,register,expected,reason):
        number=len(self.checks)+1
        self.emit(f'li x30,0x{expected&MASK:08x}',f'bne x{register},x30,fail_{number}')
        self.checks.append(dict(id=number,register=register,expected_u32=expected&MASK,reason=reason))

    def finish(self):
        self.emit('lui x30,0x80000','sw x0,0(x30)','halt: jal x0,halt')
        for check in self.checks:
            self.emit(f'fail_{check["id"]}:',f'li x31,{check["id"]}',
                      'lui x30,0x80000','sw x31,0(x30)','jal x0,halt')
        return self.lines


def arithmetic():
    p=Program()
    pairs=[(0,0xffffffff),(1,0xffffffff),(0xffffffff,0xffffffff),
           (0x80000000,0xffffffff),(0x80000000,0x80000000),
           (0x7fffffff,0xffffffff),(0x80000000,2),
           (0xaaaaaaaa,0x55555555),(0x55555555,0xaaaaaaaa),
           (0x80000001,0xffff0001),(0xffffffff,0x80000001),
           (0x12345678,0xfedcba98)]
    for a,b in pairs:
        p.emit(f'li x1,0x{a:08x}',f'li x2,0x{b:08x}',
               'mul x3,x1,x2','mulh x4,x1,x2','mulhsu x5,x1,x2','mulhu x6,x1,x2')
        products=[a*b,signed(a)*signed(b),signed(a)*b,a*b]
        for register,op,product in zip(range(3,7),('mul','mulh','mulhsu','mulhu'),products):
            expected=product&MASK if op=='mul' else (product>>32)&MASK
            p.check(register,expected,f'{op} A={a:08x} B={b:08x}')
    # Constants specify the ISA rounding, zero-divisor, and overflow edges.
    divisions=[('div',0xfffffff9,3,0xfffffffe),('rem',0xfffffff9,3,0xffffffff),
               ('div',7,0xfffffffd,0xfffffffe),('rem',7,0xfffffffd,1),
               ('divu',0xffffffff,2,0x7fffffff),('remu',0xffffffff,2,1),
               ('div',17,0,0xffffffff),('divu',17,0,0xffffffff),
               ('rem',0x89abcdef,0,0x89abcdef),('remu',0x89abcdef,0,0x89abcdef),
               ('div',0x80000000,0xffffffff,0x80000000),('rem',0x80000000,0xffffffff,0)]
    for op,a,b,answer in divisions:
        p.emit(f'li x1,0x{a:08x}',f'li x2,0x{b:08x}',f'{op} x3,x1,x2')
        p.check(3,answer,f'{op} directed signed/zero/overflow')
    return p


def memory_order():
    p=Program();p.emit('lui x28,0x10')
    for row in range(24):
        offset=row*16
        word=(0x89abcdef+row*0x1020304)&MASK
        byte=(0x80+row)&255
        half=(0x8001+row*131)&65535
        expected=(word&255)|(byte<<8)|(half<<16)
        p.emit(f'li x1,0x{word:08x}',f'li x2,{byte}',f'li x3,{half}',
               f'sw x1,{offset}(x28)',f'sb x2,{offset+1}(x28)',f'sh x3,{offset+2}(x28)',
               f'lw x4,{offset}(x28)',f'lb x5,{offset+1}(x28)',f'lhu x6,{offset+2}(x28)')
        p.check(4,expected,'overlapping word/byte/half stores and load')
        p.check(5,byte-256,'byte signed extension')
        p.check(6,half,'half unsigned extension')
    for row in range(12):
        offset=512+row*16
        value=(0x8badf00d+row*0x1234567)&MASK
        p.emit(f'li x1,{offset*3}','li x2,3','divu x3,x1,x2','add x3,x28,x3',
               f'li x4,0x{value:08x}','sw x4,0(x3)',
               f'lw x5,{offset}(x28)',f'lbu x6,{offset+3}(x28)')
        p.check(5,value,'older store address waits for division')
        p.check(6,value>>24,'load upper byte after unresolved older store')
    return p


def recovery():
    p=Program();p.emit('lui x28,0x10','li x4,0x13579bdf','sw x4,0(x28)')
    for row in range(16):
        a=12345+row*257
        p.emit(f'li x1,{a}','li x2,3','li x10,0x2468ace0','li x11,-1',
               'mulhu x13,x11,x11','divu x9,x1,x2',f'bne x9,x0,survive_{row}',
               'mul x10,x1,x2','divu x11,x1,x2','lw x12,1024(x28)',
               'mulh x14,x1,x2','sw x10,0(x28)','addi x10,x10,71',
               f'survive_{row}:','lw x15,0(x28)')
        p.check(9,a//3,'older division must survive resolving branch')
        p.check(13,0xfffffffe,'older multiplier survives resolving branch')
        p.check(10,0x2468ace0,'wrong-path destination must not replace architectural value')
        p.check(15,0x13579bdf,'wrong-path store must not commit')
        p.emit('mulhsu x16,x11,x2')
        p.check(16,0xffffffff,'new task after recovery must make progress')
    return p


def prepare(out):
    if out.exists():
        raise FileExistsError('Preserve directed cases: '+str(out))
    out.mkdir(parents=True)
    inputs={str(Path(__file__).resolve()):sha(__file__)}
    for tool in ('as','ld','objcopy','objdump'):
        path=BIN/f'riscv-none-elf-{tool}.exe';inputs[str(path)]=sha(path)
    cases=[]
    for name,builder in [('rv32m_edges',arithmetic),('lsq_wrap_forward',memory_order),('recovery_reuse',recovery)]:
        program=builder();case=out/name;case.mkdir()
        code,image=assemble(name,program.finish(),case)
        (case/'program.data').write_bytes(image.read_bytes())
        (case/'expected.txt').write_text('0\n',encoding='utf-8')
        (case/'checks.json').write_text(json.dumps(program.checks,indent=2)+'\n',encoding='utf-8')
        cases.append(dict(name=name,expected_u32=0,checks=len(program.checks),image_bytes=len(code)))
        for path in case.iterdir():
            if path.is_file():inputs[str(path.resolve())]=sha(path)
    manifest=dict(status='PREPARED_NOT_SIMULATED',cases=cases,input_sha256=inputs,
                  max_cycles=100000,latency=10,
                  scope='Three finite architectural cases; timing/backpressure/recovery coverage is stimulus, not internal-state proof; not official IPC')
    (out/'cases.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=manifest['status'],cases=cases)),flush=True)


def run(out,config_path):
    config=json.loads(config_path.read_text(encoding='utf-8'))
    frozen=json.loads(Path(config['source_manifest']).read_text(encoding='utf-8'))
    source=Path(config['source']);build=Path(config['native_build_path'])
    identity_path=build/'build_identity.json';identity=json.loads(identity_path.read_text(encoding='utf-8'))
    assert os.name=='nt' and identity['status']=='COMPLETE'
    assert identity['source_manifest_sha256']==sha(config['source_manifest'])
    assert identity['verilator_sha256']==sha(config['verilator'])
    assert identity['verilator_build_driver_sha256']==sha(config['verilator_build_driver'])
    for name,digest in frozen['snapshot_sha256'].items():assert sha(source/name)==digest,name
    exe=Path(identity['executable']);assert sha(exe)==identity['executable_sha256']
    manifest=json.loads((out/'cases.json').read_text(encoding='utf-8'))
    for name,digest in manifest['input_sha256'].items():assert sha(name)==digest,name
    report_path=out/'results.json'
    if report_path.exists():raise FileExistsError('Preserve directed results')
    io_path=source/'.deps/RISC-V-CPU-2026/scripts/oj_io.py'
    spec=importlib.util.spec_from_file_location('frozen_oj_io',io_path)
    io=importlib.util.module_from_spec(spec);spec.loader.exec_module(io)
    env=dict(os.environ);env['PATH']=config['runtime_bin']+';'+config['build_bin']+';'+env['PATH']
    results=[]
    for case in manifest['cases']:
        case_dir=out/case['name']
        data,answer=io.prepare_case(case_dir,manifest['max_cycles'],manifest['latency'])
        began=__import__('time').monotonic()
        result=subprocess.run([str(exe)],input=data,text=True,capture_output=True,cwd=source,env=env,timeout=300)
        log=case_dir/'simulation.log';log.write_text(result.stdout+result.stderr,encoding='utf-8')
        error=io.compare_output(result.stdout,answer)
        cycles=re.search(r'^CPU2026 cycles=(\d+)$',result.stderr,re.M)
        passed=result.returncode==0 and error is None and cycles is not None
        row=dict(name=case['name'],status='PASS' if passed else 'FAIL',
                 returncode=result.returncode,cycles=int(cycles[1]) if cycles else None,
                 wall_seconds=__import__('time').monotonic()-began,
                 output_error=error,log_sha256=sha(log),checks=case['checks'])
        results.append(row);print(json.dumps(row),flush=True)
    report=dict(status='COMPLETE' if all(r['status']=='PASS' for r in results) else 'COMPLETE_WITH_FAILURES',
                results=results,environment='WINDOWS_NATIVE',latency=manifest['latency'],
                source_manifest_sha256=sha(config['source_manifest']),build_identity_sha256=sha(identity_path),
                executable_sha256=sha(exe),cases_manifest_sha256=sha(out/'cases.json'),oj_io_sha256=sha(io_path),
                official_ipc=False,scope=manifest['scope'])
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if report['status']!='COMPLETE':raise SystemExit('Directed cases failed: '+str(report_path))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--config',type=Path)
    args=parser.parse_args()
    if args.config:run(args.out.resolve(),args.config.resolve())
    else:prepare(args.out.resolve())


if __name__=='__main__':main()
