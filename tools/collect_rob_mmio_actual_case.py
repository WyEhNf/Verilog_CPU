"""Certify one finished actual ROB64 proof while other configurations continue.

Freeze the progress snapshot rather than binding to a report still being
updated. Independently check the exact proof commands, all proof points,
original interface/state aliases and the observational golden annotation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('directory',type=Path)
    ap.add_argument('--bank',type=int,choices=(0,1),required=True)
    ap.add_argument('--outdir',type=Path,required=True)
    a=ap.parse_args()
    root,out=a.directory.resolve(),a.outdir.resolve()
    assert not out.exists()
    progress_bytes=(root/'report.json').read_bytes()
    progress=json.loads(progress_bytes)
    assert progress['status'] in ('RUNNING','COMPLETE') and not progress['small_only']
    assert progress['original_annotation_removal_exact'] and progress['no_input_assumptions']
    params=dict(BE_WIDTH=4,ROB_ENTRIES=64,PHYS_REGS=64,PHYS_ADDR_WIDTH=6,
                GENERATION_WIDTH=8,CHECKPOINT_WIDTH=192,CHECKPOINT_IMPL=1,
                STORE_BUFFERED_RETIRE=1,COMMIT_BANKED_READ=a.bank,ALLOC_BANKED_WRITE=1,
                ROB_CONTROL_REGISTER_BANKS=0,ASAP7_FANOUT_BUFFERS=0)
    result_rows=[r for r in progress['results'] if r['parameters']==params|dict(MMIO_PREDECODE=1)]
    assert len(result_rows)==1 and result_rows[0]['status']=='PROVEN'
    reported=result_rows[0]
    stem=f'be4_rob64_cp1_sb1_bank{a.bank}_gen8_mmio1'
    script,log,prepared=(root/(stem+s) for s in ('.ys','.log','.prepared.json'))
    hashes=dict(progress['input_sha256'])
    for path,key in [(script,'script_sha256'),(log,'log_sha256'),(prepared,'prepared_sha256')]:
        assert sha(path)==reported[key]
        hashes[str(path)]=sha(path)
    for name,want in hashes.items():assert sha(name)==want,name
    original=(root/'source_snapshot/original.v').read_text()
    observed=(root/'source_snapshot/original_observed.v').read_text()
    annotation='''
    (* keep *) wire mmio_word_mem [0:ROB_ENTRIES-1];
    (* keep *) wire [BE_WIDTH-1:0] head_mmio_word;
    genvar proof_row, proof_lane;
    generate
        for (proof_row=0; proof_row<ROB_ENTRIES; proof_row=proof_row+1) begin:g_mmio_predicate_observation
            assign mmio_word_mem[proof_row] =
                (store_addr_mem[proof_row] == 32'h80000000) &&
                (store_mask_mem[proof_row] == 4'hf);
        end
        for (proof_lane=0; proof_lane<BE_WIDTH; proof_lane=proof_lane+1) begin:g_mmio_head_observation
            assign head_mmio_word[proof_lane] =
                (head_store_addr[proof_lane] == 32'h80000000) &&
                (head_store_mask[proof_lane] == 4'hf);
        end
    endgenerate
'''
    assert observed.count(annotation)==1 and observed.replace(annotation,'')==original
    quote=lambda p:'"'+p.as_posix()+'"'
    settings=' '.join(f'-set {k} {v}' for k,v in params.items())
    expected=[]
    for label,file in [('gold','original_observed.v'),('gate','candidate.v')]:
        expected += ['read_verilog -I rtl '+quote(root/'source_snapshot'/file),
                     'chparam '+settings+(' -set MMIO_PREDECODE 1' if label=='gate' else '')+' rv32_rob',
                     'hierarchy -check -top rv32_rob','rename -top '+label,'proc','memory_map',
                     'opt_expr -keepdc','opt_clean','setattr -mod -unset top','design -stash '+label,'design -reset']
    expected += ['design -copy-from gold -as gold gold','design -copy-from gate -as gate gate',
                 'write_json '+quote(prepared),'equiv_make gold gate equiv','hierarchy -check -top equiv',
                 'check -assert','equiv_simple -short -seq 2','equiv_induct -seq 4','equiv_status -assert']
    assert script.read_text().splitlines()==expected
    text=log.read_text()
    matches=re.findall(r'Found (\d+) \$equiv cells in equiv:\s+Of those cells (\d+) are proven and (\d+) are unproven.',text)
    assert len(matches)==1
    total,proven,unproven=map(int,matches[0])
    assert total==proven==reported['equiv_cells'] and unproven==0
    assert 'Equivalence successfully proven!' in text and 'ERROR:' not in text
    models=json.loads(prepared.read_text())['modules']
    gold,gate=models['gold'],models['gate']
    schema=lambda m:{n:(p['direction'],len(p['bits'])) for n,p in m['ports'].items()}
    assert schema(gold)==schema(gate)
    original_arrays=set(re.findall(r'\breg\s+(?:\[[^;]+?\]\s+)?(\w+_mem)\s*\[0:ROB_ENTRIES-1\];',original))
    assert len(original_arrays)>=20 and 'mmio_word_mem' not in original_arrays
    fields=[];aliases=[]
    for name,net in gold['netnames'].items():
        match=re.fullmatch(r'(\w+_mem)\[\d+\]',name)
        if not match:continue
        if match[1]=='mmio_word_mem':aliases.append(name)
        else:
            assert match[1] in original_arrays
            assert name in gate['netnames'] and len(net['bits'])==len(gate['netnames'][name]['bits']),name
            fields.append(name)
    assert len(fields)==reported['preserved_original_state_aliases'] and len(aliases)==64
    assert all(n in gate['netnames'] for n in aliases)
    out.mkdir(parents=True)
    snapshot=out/'progress_snapshot.json';snapshot.write_bytes(progress_bytes)
    hashes[str(snapshot)]=sha(snapshot)
    hashes[str(Path(__file__).resolve())]=sha(__file__)
    for name,want in hashes.items():assert sha(name)==want,name
    result=dict(status='COMPLETE',independent_verification='VERIFIED',parameters=params|dict(MMIO_PREDECODE=1),
                equiv_cells=total,preserved_original_state_aliases=len(fields),observational_golden_aliases=len(aliases),
                input_sha256=hashes,original_annotation_removal_exact=True,all_original_ports_and_active_state_preserved=True,
                no_input_assumptions=True,no_proof_points_suppressed=True,actual64_proof=True,whole_cpu_claim=False,
                baseline_sha256=sha(root/'source_snapshot/original.v'),candidate_sha256=sha(root/'source_snapshot/candidate.v'),
                source_directory=str(root),scope='Only specified actual64 bank mode; other cases may still be running.')
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','independent_verification','equiv_cells','actual64_proof','whole_cpu_claim')}))


if __name__=='__main__':main()
