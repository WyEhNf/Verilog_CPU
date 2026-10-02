"""Prove the whole frozen age-matrix RS with explicit exact relation aliases.

Add only public names for existing gold comparison signals, matching gate's
cached relation state. No cell, connection, port, input assumption or state is
changed. All original comparison points remain and final equiv_status is global.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof-dir', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.proof_dir.resolve(), args.outdir.resolve()
    assert not out.exists(), 'Preserve existing proofs'
    prepared = source/'be4_entries16_wake10_metadata70_age32.prepared.json'
    input_paths = [prepared, Path(__file__), source/'source_snapshot/original.v',
                   source/'source_snapshot/candidate.v', source/'source_snapshot/rtl/rv32im_defs.vh']
    hashes = {str(p):sha(p) for p in input_paths}
    original = json.loads(prepared.read_text())
    model = copy.deepcopy(original)
    assert set(model['modules']) == {'gold', 'gate'}
    gold, gate = [model['modules'][n] for n in ('gold','gate')]
    schema = lambda m: {n:(v['direction'],len(v['bits'])) for n,v in m['ports'].items()}
    assert schema(gold) == schema(gate)
    assert not any(c['type'] in ('$assume','$anyconst','$anyseq')
                   for m in model['modules'].values() for c in m['cells'].values())
    aliases = []
    for low in range(16):
        for high in range(low+1,16):
            relation = f'g_age_order_matrix.g_low[{low}].g_high[{high}].low_precedes_high'
            comparison = f'g_rank[{high}].g_leaf[{low}].g_compare.older'
            assert relation not in gold['netnames'] and relation in gate['netnames']
            assert comparison in gold['netnames']
            bits = gold['netnames'][comparison]['bits']
            assert len(bits) == 1 and isinstance(bits[0],int)
            gold['netnames'][relation] = dict(hide_name=0,bits=bits[:],attributes={})
            aliases.append(dict(alias=relation,existing_wire=comparison,bits=bits[:]))
    # Removing exactly the added aliases must reproduce the original full model.
    restored = copy.deepcopy(model)
    for row in aliases:
        del restored['modules']['gold']['netnames'][row['alias']]
    assert restored == original
    out.mkdir(parents=True)
    named = out/'named_prepared.json'
    named.write_text(json.dumps(model,separators=(',',':'))+'\n')
    report = dict(status='RUNNING', full_module=True, proves_whole_cpu=False,
                  no_input_assumptions=True, hardware_graph_unchanged=True,
                  all_existing_ports_states_and_names_preserved=True,
                  input_sha256=hashes, named_prepared_sha256=sha(named),
                  aliases=aliases, parameters=dict(BE_WIDTH=4,ENTRIES=16,WAKE_WIDTH=10,
                    METADATA_WIDTH=70,AGE_WIDTH=32,WAKE_MUX_IMPL=1,ALLOC_STATIC_WRITE=1))
    def save():
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    del model,original,restored,gold,gate
    suite=ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    env=dict(os.environ)
    env['PATH']=str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    commands = ['read_json "'+named.as_posix()+'"',
                'equiv_make gold gate equiv','hierarchy -check -top equiv',
                'write_json "'+(out/'before_simple.json').as_posix()+'"',
                'equiv_simple -short -seq 2','equiv_simple -short -seq 2',
                'write_json "'+(out/'after_simple.json').as_posix()+'"',
                'equiv_induct -seq 4','equiv_status -assert']
    script,log = out/'proof.ys',out/'proof.log'
    script.write_text('\n'.join(commands)+'\n')
    print('START exact120relation aliases; entire actualRS16, unchanged physical graph',flush=True)
    with log.open('w') as stream:
        run=subprocess.run([str(suite/'bin/yosys.exe'),'-T','-s',str(script)],env=env,
                           stdout=stream,stderr=subprocess.STDOUT)
    text=log.read_text()
    report.update(log_sha256=sha(log),script_sha256=sha(script),yosys_sha256=sha(suite/'bin/yosys.exe'))
    if run.returncode or 'Equivalence successfully proven!' not in text:
        report.update(status='FAILED',failure_log=str(log));save()
        raise SystemExit('Whole RS age proof failed: '+str(log))
    points=re.search(r'Found (\d+) \$equiv cells in equiv:',text)
    assert points
    for path,expected in hashes.items():
        assert sha(Path(path))==expected,'Frozen source changed: '+path
    assert sha(named)==report['named_prepared_sha256']
    report.update(status='PROVEN',equiv_cells=int(points[1]),unproven_cells=0)
    save()
    print('PROVEN complete age-matrixRS16: '+points[1]+' points',flush=True)


if __name__ == '__main__':
    main()
