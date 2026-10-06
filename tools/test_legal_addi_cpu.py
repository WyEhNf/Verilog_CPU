"""Exercise legal ADDI255 at eight instruction offsets on the frozen real CPU.

Use the unmodified course memory/AXI/MMIO driver with its read-only instret
print. These additional correctness cases are not benchmark IPC measurements.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--outdir',type=Path,required=True)
    args=parser.parse_args()
    source,out=args.source_root.resolve(),args.outdir.resolve()
    assert not out.exists();out.mkdir(parents=True)
    manifest_path=args.build.resolve()/'build_manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    hashes={str(manifest_path):sha(manifest_path),str(Path(__file__)):sha(__file__)}
    for name,value in manifest['source_sha256'].items():
        assert sha(source/name)==value.lower();hashes[str(source/name)]=value.lower()
    exe,driver=Path(manifest['executable']),Path(manifest['generated_driver'])
    assert sha(exe)==manifest['executable_sha256'].lower()
    assert sha(driver)==manifest['generated_driver_sha256'].lower()
    original=source/'.deps/RISC-V-CPU-2026/scripts/sim.cpp'
    observation='        std::cerr << "CPU2026 instret=" << top.debug_instret << std::endl;\n'
    observed=driver.read_text()
    assert observed.count(observation)==1 and observed.replace(observation,'')==original.read_text()
    for path in (exe,driver,original):hashes[str(path)]=sha(path)
    report=dict(status='RUNNING',additional_correctness_only=True,results=[],input_sha256=hashes,
                memory_latency=20,exit='MMIO0x80000000 wordWSTRBf Bhandshake')
    for offset in range(8):
        name=f'addi255_pc{offset*4:02x}'
        words=[0x00000013]*offset+[0x0ff00513,0x00150513,0x800002b7,0x00a2a023,0x0000006f]
        code=out/(name+'.S')
        code.write_text('.section .text\n.globl _start\n_start:\n'+'    addi x0,x0,0\n'*offset+
                        '    addi a0,x0,255\n    addi a0,a0,1\n    lui t0,0x80000\n    sw a0,0(t0)\n1:  jal x0,1b\n')
        data=b''.join(w.to_bytes(4,'little') for w in words)
        image=out/(name+'.image')
        image.write_text('@00000000\n'+'\n'.join(' '.join(f'{b:02X}' for b in data[i:i+16]) for i in range(0,len(data),16))+'\n')
        run=subprocess.run([str(exe),str(image),'256','2000','20'],cwd=source,text=True,capture_output=True)
        log=out/(name+'.log');log.write_text(run.stdout+run.stderr)
        match=re.search(r'^PASS cycles=(\d+) result=256 expected=256$',run.stdout,re.M)
        retired=re.search(r'^CPU2026 instret=(\d+)$',run.stderr,re.M)
        for path in (code,image,log):hashes[str(path)]=sha(path)
        if run.returncode or not match or not retired:
            report.update(status='FAILED',failure_log=str(log))
            (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(str(log))
        report['results'].append(dict(name=name,status='PASS',cycles=int(match[1]),instret=int(retired[1]),result=256))
        print('PASS '+name+' cycles='+match[1],flush=True)
    for path,value in hashes.items():assert sha(path)==value
    report['status']='COMPLETE';(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('COMPLETE8 native RV32I ADDI255 alignments with real MMIO exit',flush=True)


if __name__=='__main__':main()
