"""Prove a standalone RAT candidate against the literal frozen backend block.

The reference block is extracted unchanged, not replaced with an assumed model.
Both the loop and parallel candidates must match all 32 architectural mappings
for arbitrary input bits. This does not connect the candidate to the CPU or
prove a whole-core performance/area result.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def quote(path):
    return '"' + path.resolve().as_posix() + '"'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    snapshot = out / 'source_snapshot'
    hashes = {}
    sources = [ROOT / 'rtl/backend/rv32_backend_joint.v', ROOT / 'rtl/backend/rv32_rat_recovery.v', Path(__file__)]
    for source in sources:
        target = snapshot / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and sha(target) != sha(source):
            raise SystemExit('Existing source snapshot differs')
        shutil.copyfile(source, target)
        hashes[str(target)] = sha(target)
    backend = (snapshot / 'rtl/backend/rv32_backend_joint.v').read_text()
    match = re.search(r'    always @\* begin\n        recovery_rat_state =.*?^    end$', backend, re.S | re.M)
    if not match or 'for (recovery_rat_age = ROB_ENTRIES - 1;' not in match[0]:
        raise SystemExit('Could not locate the real backend recovery block')
    reference = out / 'literal_backend_reference.v'
    reference.write_text('''module literal_backend_reference #(
    parameter integer ROB_ENTRIES=32, PAW=6,
    parameter integer SLOT_WIDTH=$clog2(ROB_ENTRIES), COUNT_WIDTH=$clog2(ROB_ENTRIES+1)
) (
    input wire [32*PAW-1:0] rat_i,
    input wire [SLOT_WIDTH-1:0] head_i, branch_slot_i,
    input wire [COUNT_WIDTH-1:0] occupancy_i,
    input wire [ROB_ENTRIES-1:0] valid_i, rd_we_i,
    input wire [ROB_ENTRIES*5-1:0] rd_i,
    input wire [ROB_ENTRIES*PAW-1:0] old_phys_i,
    input wire branch_rd_we_i,
    input wire [4:0] branch_rd_i,
    input wire [PAW-1:0] branch_new_phys_i,
    output wire [32*PAW-1:0] restore_o
);
    localparam integer CHECKPOINT_IMPL=1, CHECK_RAT_WIDTH=32*PAW;
    localparam integer ROB_SLOT_WIDTH=SLOT_WIDTH;
    wire [CHECK_RAT_WIDTH-1:0] rat_state=rat_i, rob_checkpoint_restore=0;
    wire [SLOT_WIDTH+2:0] branch_pending_tag={branch_slot_i,3'b000};
    wire [SLOT_WIDTH-1:0] rob_head_views=head_i;
    wire [COUNT_WIDTH-1:0] rob_occupancy=occupancy_i;
    wire [ROB_ENTRIES-1:0] rob_entry_valid=valid_i, rob_entry_rd_we=rd_we_i;
    wire [ROB_ENTRIES*5-1:0] rob_entry_rd=rd_i;
    wire [ROB_ENTRIES*PAW-1:0] rob_entry_old_phys=old_phys_i;
    wire rob_recovery_rd_we=branch_rd_we_i;
    wire [4:0] rob_recovery_rd=branch_rd_i;
    wire [PAW-1:0] rob_recovery_new_phys=branch_new_phys_i;
    reg [CHECK_RAT_WIDTH-1:0] recovery_rat_state;
    integer recovery_rat_age, recovery_rat_branch_age, recovery_rat_slot;
    wire [0:0] free_bitmap_state=0, rob_recovery_reclaim_bitmap=0;
    reg [0:0] recovery_free_bitmap;
    wire [COUNT_WIDTH-1:0] free_count=0, rob_recovery_reclaim_count=0;
    reg [COUNT_WIDTH-1:0] recovery_free_count;
    assign restore_o=recovery_rat_state;
''' + match[0] + '\nendmodule\n')
    suite = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite'
    yosys = suite / 'bin/yosys.exe'
    hashes[str(yosys)] = sha(yosys)
    env = dict(os.environ)
    env['PATH'] = str(suite / 'bin') + os.pathsep + str(suite / 'lib') + os.pathsep + env['PATH']
    results = []
    for depth, width in ((8,6), (16,6), (32,6), (32,7)):
        for implementation in (0,1):
            name = f'rob{depth}_paw{width}_impl{implementation}'
            script, log = out / (name + '.ys'), out / (name + '.log')
            script.write_text('\n'.join([
                'read_verilog ' + quote(reference),
                f'chparam -set ROB_ENTRIES {depth} -set PAW {width} literal_backend_reference',
                'rename literal_backend_reference gold',
                'read_verilog ' + quote(snapshot / 'rtl/backend/rv32_rat_recovery.v'),
                f'chparam -set ROB_ENTRIES {depth} -set PAW {width} -set IMPL {implementation} rv32_rat_recovery',
                'rename rv32_rat_recovery gate', 'hierarchy -check', 'proc', 'flatten gold gate',
                'opt_expr gold gate', 'opt_clean gold gate',
                'equiv_make gold gate equiv', 'hierarchy -check -top equiv',
                'check -assert', 'equiv_simple', 'equiv_status -assert',
            ]) + '\n')
            print('START ' + name, flush=True)
            with log.open('w') as stream:
                run = subprocess.run([str(yosys), '-T', '-s', str(script)], env=env,
                                     stdout=stream, stderr=subprocess.STDOUT)
            text = log.read_text()
            counts = re.findall(r'Of those cells (\d+) are proven and (\d+) are unproven', text)
            if run.returncode or not counts or int(counts[-1][1]) or 'Equivalence successfully proven!' not in text:
                raise SystemExit('Literal backend identity NOT proven: ' + str(log))
            results.append(dict(name=name, status='PROVEN', proven_cells=int(counts[-1][0]),
                                unproven_cells=0, log_sha256=sha(log)))
            print('PROVEN ' + name, flush=True)
    for path, expected in hashes.items():
        if sha(Path(path)) != expected:
            raise SystemExit('Frozen proof source changed')
    (out / 'report.json').write_text(json.dumps(dict(
        status='COMPLETE', results=results, source_sha256=hashes,
        literal_reference_sha256=sha(reference), integrated_into_cpu=False,
        proves_whole_cpu=False, claims_cpu_ppa=False), indent=2) + '\n')
    print('COMPLETE: eight literal-backend combinational recovery proofs')


if __name__ == '__main__':
    main()
