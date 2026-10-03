"""Finish and independently check preserved ROB MMIO proof artifacts.

The first runner incorrectly classified a new observational golden alias as
original state in the parameter-zero case. Preserve its incomplete report and
all solver evidence; verify all seven proofs and original state separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    root = args.directory.resolve()
    output = root/'verified_completion.json'
    assert not output.exists()
    progress_path = root/'report.json'
    progress = json.loads(progress_path.read_text())
    assert progress['small_only'] and len(progress['results']) == 6
    hashes = dict(progress['input_sha256'])
    hashes[str(progress_path)] = sha(progress_path)
    hashes[str(Path(__file__).resolve())] = sha(Path(__file__))
    for name, expected in hashes.items(): assert sha(name) == expected, name
    original = (root/'source_snapshot/original.v').read_text()
    observed = (root/'source_snapshot/original_observed.v').read_text()
    # Strictly check every added statement is an observational comparator.
    annotation = '''
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
    assert observed.count(annotation) == 1 and observed.replace(annotation, '') == original
    original_arrays = set(re.findall(r'\breg\s+(?:\[[^;]+?\]\s+)?(\w+_mem)\s*\[0:ROB_ENTRIES-1\];', original))
    assert len(original_arrays) >= 20 and 'mmio_word_mem' not in original_arrays
    cases = [(1,4,1,1,1,2,1),(2,8,1,1,1,2,1),(4,8,1,1,1,2,1),
             (4,8,0,0,0,2,1),(4,8,1,0,1,2,1),(2,8,0,1,1,2,1),
             (4,8,1,1,1,2,0)]
    rows = []
    for width, depth, checkpoint, buffered, bank, gen, mode in cases:
        stem = f'be{width}_rob{depth}_cp{checkpoint}_sb{buffered}_bank{bank}_gen{gen}_mmio{mode}'
        script, log, prepared = (root/(stem+suffix) for suffix in ('.ys','.log','.prepared.json'))
        commands = script.read_text().splitlines()
        params = dict(BE_WIDTH=width, ROB_ENTRIES=depth, PHYS_REGS=64, PHYS_ADDR_WIDTH=6,
                      GENERATION_WIDTH=gen, CHECKPOINT_WIDTH=256, CHECKPOINT_IMPL=checkpoint,
                      STORE_BUFFERED_RETIRE=buffered, COMMIT_BANKED_READ=bank, ALLOC_BANKED_WRITE=1,
                      ROB_CONTROL_REGISTER_BANKS=0, ASAP7_FANOUT_BUFFERS=0)
        settings = ' '.join(f'-set {k} {v}' for k,v in params.items())
        quote = lambda path: '"'+path.as_posix()+'"'
        expected = []
        for label, filename in [('gold','original_observed.v'),('gate','candidate.v')]:
            expected += ['read_verilog -I rtl '+quote(root/'source_snapshot'/filename),
                         'chparam '+settings+(f' -set MMIO_PREDECODE {mode}' if label=='gate' else '')+' rv32_rob',
                         'hierarchy -check -top rv32_rob','rename -top '+label,
                         'proc','memory_map','opt_expr -keepdc','opt_clean',
                         'setattr -mod -unset top','design -stash '+label,'design -reset']
        expected += ['design -copy-from gold -as gold gold','design -copy-from gate -as gate gate',
                     'write_json '+quote(prepared),'equiv_make gold gate equiv','hierarchy -check -top equiv',
                     'check -assert','equiv_simple -short -seq 2','equiv_induct -seq 4','equiv_status -assert']
        assert commands == expected, stem
        text = log.read_text()
        counts = re.findall(r'Found (\d+) \$equiv cells in equiv:\s+Of those cells (\d+) are proven and (\d+) are unproven.', text)
        assert len(counts) == 1
        total, proven, unproven = map(int, counts[0])
        assert total == proven and unproven == 0 and 'Equivalence successfully proven!' in text and 'ERROR:' not in text
        modules = json.loads(prepared.read_text())['modules']
        gold, gate = modules['gold'], modules['gate']
        schema = lambda m: {n:(p['direction'],len(p['bits'])) for n,p in m['ports'].items()}
        assert schema(gold) == schema(gate)
        fields = []
        annotation_aliases = []
        for name, net in gold['netnames'].items():
            match = re.fullmatch(r'(\w+_mem)\[\d+\]',name)
            if not match: continue
            if match[1] == 'mmio_word_mem':
                annotation_aliases.append(name)
            else:
                assert match[1] in original_arrays, name
                assert name in gate['netnames'] and len(net['bits']) == len(gate['netnames'][name]['bits']), name
                fields.append(name)
        assert fields and len(annotation_aliases) == depth
        if mode:
            assert all(n in gate['netnames'] for n in annotation_aliases)
        for path in (script,log,prepared): hashes[str(path)] = sha(path)
        rows.append(dict(status='PROVEN', parameters=params | dict(MMIO_PREDECODE=mode),
                         equiv_cells=total, preserved_original_state_aliases=len(fields),
                         observational_golden_aliases=len(annotation_aliases),
                         script_sha256=sha(script), log_sha256=sha(log), prepared_sha256=sha(prepared)))
    for name, expected in hashes.items(): assert sha(name) == expected, name
    result = dict(status='COMPLETE', independent_verification='VERIFIED', results=rows,
                  equiv_cells=sum(r['equiv_cells'] for r in rows), input_sha256=hashes,
                  original_annotation_removal_exact=True, all_original_ports_and_active_state_preserved=True,
                  no_input_assumptions=True, no_proof_points_suppressed=True,
                  original_incomplete_report_preserved=True, actual64_proof=False, whole_cpu_claim=False,
                  correction='Exclude added golden observational mmio_word_mem aliases only from original-state inventory; all original fields and all solver equivalence points are verified.')
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','independent_verification','equiv_cells','actual64_proof','whole_cpu_claim')}))


if __name__ == '__main__':
    main()
