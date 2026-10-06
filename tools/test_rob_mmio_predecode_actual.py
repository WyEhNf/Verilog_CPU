"""Prove actual ROB64 MMIO predecode with observational predicate aliases.

Keep all original ports, payloads and named state; use no input assumptions.
This is component equivalence, not whole-CPU correctness or a PPA result.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def quote(path):
    return '"'+Path(path).resolve().as_posix()+'"'


def available_memory():
    class Memory(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)]+[
            (name, ctypes.c_ulonglong) for name in
            ('total_phys', 'avail_phys', 'total_page', 'avail_page', 'total_virtual', 'avail_virtual', 'avail_extended')]
    memory = Memory()
    memory.length = ctypes.sizeof(memory)
    assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory))
    return memory.avail_phys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--small-only', action='store_true')
    args = parser.parse_args()
    candidate, out = args.candidate_root.resolve(), args.outdir.resolve()
    assert not out.exists(), 'Preserve previous proof evidence'
    cm_path = candidate/'candidate_manifest.json'
    cm = json.loads(cm_path.read_text())
    assert cm['default_mmio_predecode'] == 0 and cm['original_payloads_and_ports_preserved']
    assert sha(candidate/'baseline/rv32_rob.v') == cm['baseline_sha256']
    assert sha(candidate/'rtl/backend/rv32_rob.v') == cm['candidate_sha256']
    snapshot = out/'source_snapshot'
    origins = {snapshot/'original.v': candidate/'baseline/rv32_rob.v',
               snapshot/'candidate.v': candidate/'rtl/backend/rv32_rob.v',
               snapshot/'rtl/rv32im_defs.vh': ROOT/'rtl/rv32im_defs.vh',
               snapshot/Path(__file__).name: Path(__file__).resolve()}
    hashes = {str(cm_path): sha(cm_path)}
    for target, source in origins.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[str(source)] = sha(source)
        hashes[str(target)] = sha(target)
    # The original comparator values are exposed under names of new candidate
    # predicates. These are observational wires, never assumptions or state
    # changes. Proving their equivalence establishes the required state relation.
    original = (snapshot/'original.v').read_text()
    marker = '    wire [PHYS_ADDR_WIDTH-1:0] head_new_phys [0:BE_WIDTH-1];'
    assert original.count(marker) == 1
    aliases = """
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
"""
    annotated = original.replace(marker, marker+aliases)
    assert annotated.replace(aliases, '') == original
    annotated_path = snapshot/'original_observed.v'
    annotated_path.write_text(annotated)
    hashes[str(annotated_path)] = sha(annotated_path)
    suite = ROOT/'.deps/oss-cad-suite-install/oss-cad-suite'
    binary = suite/'bin/yosys.exe'
    hashes[str(binary)] = sha(binary)
    env = dict(os.environ)
    env['PATH'] = str(suite/'bin')+os.pathsep+str(suite/'lib')+os.pathsep+env['PATH']
    report = dict(status='RUNNING', input_sha256=hashes, results=[],
                  no_input_assumptions=True, no_original_ports_or_state_fields_omitted=True,
                  new_state_is_mmio_word_predicate=True, proves_whole_cpu=False,
                  small_only=args.small_only, original_annotation_is_observational_only=True,
                  original_annotation_removal_exact=True, added_aliases=['mmio_word_mem', 'head_mmio_word'])

    def save():
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')

    def verify():
        for name, expected in hashes.items():
            assert sha(name) == expected, name

    assert not args.small_only, 'This helper only proves the actual ROB64 configurations'
    cases = [(4,64,1,1,1,8,1),(4,64,1,1,0,8,1)]
    for width, depth, checkpoint, buffered, banked, generation, mmio in cases:
        params = dict(BE_WIDTH=width, ROB_ENTRIES=depth, PHYS_REGS=64, PHYS_ADDR_WIDTH=6,
                      GENERATION_WIDTH=generation, CHECKPOINT_WIDTH=192, CHECKPOINT_IMPL=checkpoint,
                      STORE_BUFFERED_RETIRE=buffered, COMMIT_BANKED_READ=banked, ALLOC_BANKED_WRITE=1,
                      ROB_CONTROL_REGISTER_BANKS=0, ASAP7_FANOUT_BUFFERS=0)
        stem = f'be{width}_rob{depth}_cp{checkpoint}_sb{buffered}_bank{banked}_gen{generation}_mmio{mmio}'
        report.update(active_case=stem, phase='wait_memory'); save()
        # Small proofs use less than a full CPU synthesis. Actual64 waits for
        # the same conservative 8 GB threshold as other full ROB experiments.
        threshold = 8_192_000_000 if depth >= 64 else 2_048_000_000
        while available_memory() < threshold:
            time.sleep(30)
        settings = ' '.join(f'-set {k} {v}' for k,v in params.items())
        commands = []
        for label, filename in [('gold','original_observed.v'),('gate','candidate.v')]:
            commands += ['read_verilog -I rtl '+quote(snapshot/filename),
                         'chparam '+settings+(f' -set MMIO_PREDECODE {mmio}' if label == 'gate' else '')+' rv32_rob',
                         'hierarchy -check -top rv32_rob','rename -top '+label,
                         'proc','memory_map','opt_expr -keepdc','opt_clean',
                         'setattr -mod -unset top','design -stash '+label,'design -reset']
        prepared = out/(stem+'.prepared.json')
        commands += ['design -copy-from gold -as gold gold','design -copy-from gate -as gate gate',
                     'write_json '+quote(prepared),'equiv_make gold gate equiv','hierarchy -check -top equiv',
                     'check -assert','equiv_simple -short -seq 2','equiv_induct -seq 4','equiv_status -assert']
        script, log = out/(stem+'.ys'), out/(stem+'.log')
        script.write_text('\n'.join(commands)+'\n')
        report.update(phase='formal'); save(); verify()
        print('START '+stem, flush=True)
        with log.open('w') as stream:
            process = subprocess.run([str(binary),'-T','-s',str(script)], cwd=snapshot, env=env,
                                     stdout=stream, stderr=subprocess.STDOUT)
        verify()
        text = log.read_text()
        if process.returncode or 'Equivalence successfully proven!' not in text or 'ERROR:' in text:
            report.update(status='FAILED', failure_log=str(log)); save()
            raise SystemExit('Complete ROB proof not established: '+str(log))
        modules = json.loads(prepared.read_text())['modules']
        schema = lambda m: {n:(v['direction'],len(v['bits'])) for n,v in m['ports'].items()}
        assert schema(modules['gold']) == schema(modules['gate'])
        fields = [n for n in modules['gold']['netnames'] if re.fullmatch(r'\w+_mem\[\d+\]', n)]
        assert fields
        for name in fields:
            assert name in modules['gate']['netnames']
            assert len(modules['gold']['netnames'][name]['bits']) == len(modules['gate']['netnames'][name]['bits'])
        report['results'].append(dict(status='PROVEN', parameters=params | dict(MMIO_PREDECODE=mmio),
            equiv_cells=int(re.search(r'Found (\d+) \$equiv cells in equiv:',text)[1]),
            preserved_original_state_aliases=len(fields), prepared_sha256=sha(prepared),
            script_sha256=sha(script), log_sha256=sha(log)))
        save(); print('PROVEN '+stem, flush=True)
    verify(); report.update(status='COMPLETE', active_case=None, phase='complete'); save()
    print(f'COMPLETE {len(cases)} complete-ROB equivalence cases', flush=True)


if __name__ == '__main__':
    main()
