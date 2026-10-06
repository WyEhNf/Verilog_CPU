"""Prove the same frozen whole RS16 after constant-folding mapped memory reads.

The original prepared gold/gate designs are unchanged. Standard opt_expr
-keepdc only folds constants in a fresh proof copy. Preserve all port and
architectural state names/widths, impose no input assumptions, and assert all
equivalence points at the end. Never change the measured RTL or netlist.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
STATE = re.compile(r'^(?:valid_mem|target_live_mem|op_mem|pc_mem|rob_tag_mem|phys_rd_mem|'
                   r'src[12]_(?:value|tag|ready)_mem|store_data_mem|metadata_mem|age_mem)\[\d+\]$'
                   r'|^(?:age_counter|occupancy_o)$')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def schemas(path):
    modules = json.loads(path.read_text())['modules']
    assert set(modules) == {'gold', 'gate'}
    result = {}
    for name, module in modules.items():
        assert not any(c['type'] in ('$assume', '$anyconst', '$anyseq') for c in module['cells'].values())
        ports = {n: (p['direction'], len(p['bits'])) for n,p in module['ports'].items()}
        states = {n: len(w['bits']) for n,w in module['netnames'].items() if STATE.fullmatch(n)}
        assert len(states) == 16*15 + 2, 'Missing complete RS16 state schema'
        result[name] = dict(ports=ports, state=states, cell_count=len(module['cells']),
                            direct_outputs_are_state_aliases={
                                port: module['ports'][port]['bits'] == [bit for row in range(16)
                                    for bit in module['netnames'][state+'['+str(row)+']']['bits']]
                                for port,state in [('entry_metadata_o','metadata_mem'),
                                                   ('entry_rob_tag_o','rob_tag_mem')]})
    assert result['gold']['ports'] == result['gate']['ports']
    assert result['gold']['state'] == result['gate']['state']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof-dir', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    source,out = args.proof_dir.resolve(),args.outdir.resolve()
    if out.exists():
        raise SystemExit('Choose a fresh normalized proof directory')
    prepared = source/'be4_entries16_wake10_metadata70.prepared.json'
    inputs = [prepared, source/'be4_entries16_wake10_metadata70.ys', Path(__file__),
              source/'source_snapshot/original.v', source/'source_snapshot/candidate.v',
              source/'source_snapshot/rtl/rv32im_defs.vh']
    hashes = {str(p):sha(p) for p in inputs}
    before = schemas(prepared)
    out.mkdir(parents=True)
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite/'bin/yosys.exe'
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    report = dict(status='PREPARING', no_input_assumptions=True, proves_whole_cpu=False,
                  input_sha256=hashes, before=before, measured_sources_changed=False,
                  parameters=dict(BE_WIDTH=4,ENTRIES=16,WAKE_WIDTH=10,METADATA_WIDTH=70,
                                  TAG_WIDTH=17,PHYS_ADDR_WIDTH=6,AGE_WIDTH=32,WAKE_MUX_IMPL=1),
                  parameter_change={'ALLOC_STATIC_WRITE':[0,1]})
    def save():
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def run(name, commands):
        script,log = out/(name+'.ys'),out/(name+'.log')
        script.write_text('\n'.join(commands)+'\n')
        with log.open('w') as stream:
            result = subprocess.run([str(yosys),'-T','-s',str(script)],env=env,
                                    stdout=stream,stderr=subprocess.STDOUT)
        report[name+'_script_sha256'] = sha(script)
        report[name+'_log_sha256'] = sha(log)
        if result.returncode:
            report.update(status='FAILED',failure_log=str(log));save()
            raise SystemExit('Normalized RS16 proof failed: '+str(log))
        return log.read_text()
    save()
    print('START constant-folding same full prepared RS16; retain all ports/state',flush=True)
    normalized = out/'normalized.json'
    run('normalize', ['read_json "'+prepared.as_posix()+'"', 'opt_expr -keepdc', 'opt_clean',
                      'write_json "'+normalized.as_posix()+'"'])
    after = schemas(normalized)
    for name in before:
        assert before[name]['ports'] == after[name]['ports']
        assert before[name]['state'] == after[name]['state']
    report.update(status='RUNNING',after=after,normalized_sha256=sha(normalized))
    save()
    print('Normalized gold/gate cell counts: '+str({n:(before[n]['cell_count'],after[n]['cell_count']) for n in before}),flush=True)
    text = run('proof', ['read_json "'+normalized.as_posix()+'"',
                         'equiv_make gold gate equiv','hierarchy -check -top equiv',
                         'equiv_simple -short -seq 2','equiv_simple -short -seq 2',
                         'write_json "'+(out/'after_simple.json').as_posix()+'"',
                         'equiv_induct -seq 4','equiv_status -assert'])
    assert 'Equivalence successfully proven!' in text
    count = re.search(r'Found (\d+) \$equiv cells in equiv:',text)
    assert count
    for name,expected in hashes.items():
        assert sha(Path(name)) == expected,'Original proof input changed: '+name
    assert sha(normalized) == report['normalized_sha256']
    report.update(status='PROVEN',equiv_cells=int(count[1]),unproven_cells=0,
                  yosys_sha256=sha(yosys),method='opt_expr -keepdc; opt_clean; equiv_make; two equiv_simple -short -seq2; equiv_induct -seq4; equiv_status -assert')
    save()
    print('PROVEN same complete RS16 with constant reads folded: '+str(count[1])+' points',flush=True)


if __name__ == '__main__':
    main()
