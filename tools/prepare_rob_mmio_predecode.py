"""Stage exact MMIO-word classification at ROB completion, before retirement.

Preserve every original payload and output. The CPU's unused store-address
observation path can then be pruned by the unchanged synthesis flow; the ROB's
retirement rules consume one stored predicate instead of a late 32-bit compare.
No architectural store, MMIO handshake, or pipeline latency is changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def once(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    assert not out.exists()
    source = Path('F:/CPU2026Candidates/legal_addi_fix_20261003')
    name = 'rtl/backend/rv32_rob.v'
    profile = json.loads((ROOT/'build/cpu2026/verified_legal_addi_profile_20261003.json').read_text())
    assert sha(source/name) == profile['source_sha256'][name]
    old = (source/name).read_text()
    code = once(old, '    parameter integer CHECKPOINT_IMPL = 0,',
                '    parameter integer MMIO_PREDECODE = 0,\n    parameter integer CHECKPOINT_IMPL = 0,')
    code = once(code, '    reg [31:0] store_addr_mem [0:ROB_ENTRIES-1];',
                '''    reg [31:0] store_addr_mem [0:ROB_ENTRIES-1];
    // Updated with exactly the same completion enable/priority as address and
    // mask. Payload remains observable; only retirement classification moves.
    reg mmio_word_mem [0:ROB_ENTRIES-1];''')
    mmio_read = '''    wire [BE_WIDTH-1:0] head_mmio_word;
    genvar mmio_lane;
    generate for (mmio_lane=0; mmio_lane<BE_WIDTH; mmio_lane=mmio_lane+1) begin:g_mmio_read
        wire [31:0] raw_slot = head_commit_index + mmio_lane;
        wire [31:0] selected_slot = (raw_slot >= ROB_ENTRIES) ? raw_slot - ROB_ENTRIES : raw_slot;
        assign head_mmio_word[mmio_lane] = (MMIO_PREDECODE != 0) ?
            mmio_word_mem[selected_slot] :
            ((head_store_addr[mmio_lane] == 32'h80000000) &&
             (head_store_mask[mmio_lane] == 4'hf));
    end endgenerate\n'''
    # Icarus requires declarations before references inside generate scopes.
    anchor = '    wire [PHYS_ADDR_WIDTH-1:0] head_new_phys [0:BE_WIDTH-1];'
    code = once(code, anchor, anchor + '\n' + mmio_read)
    assignment = '                            store_addr_mem[slot_index] <= completion_store_addr_i[(complete_lane*32) +: 32];'
    assert code.count(assignment) == 2
    code = code.replace(assignment, assignment + '''
                            if (MMIO_PREDECODE != 0)
                                mmio_word_mem[slot_index] <=
                                    (completion_store_addr_i[(complete_lane*32) +: 32] == 32'h80000000) &&
                                    (completion_store_mask_i[(complete_lane*4) +: 4] == 4'hf);''')
    # These are the three architectural retirement uses. Observation outputs
    # still read the complete original address/mask/data arrays.
    expression = r"\(head_store_addr\[(commit_lane|update_commit_lane)\] == 32'h80000000\) &&\s*\(head_store_mask\[\1\] == 4'hf\)"
    code, count = re.subn(expression, lambda m:'head_mmio_word['+m[1]+']', code)
    assert count == 3
    assert len(re.findall(r'\bmmio_word_mem\[slot_index\]\s*<=',code)) == 2
    tb = (ROOT/'tb/unit/rv32_rob_tb.v').read_text()
    tb = once(tb, '.ALLOC_BANKED_WRITE(ALLOC_BANKED_WRITE)',
              '.ALLOC_BANKED_WRITE(ALLOC_BANKED_WRITE), .MMIO_PREDECODE(1)')
    protocol_origin = ROOT/'tools/test_rob_banked_allocation_clean.py'
    protocol = protocol_origin.read_text()
    protocol = protocol.replace('ROOT = Path(__file__).resolve().parents[1]', "ROOT = Path('E:/Verilog_cpu')")
    protocol = protocol.replace('test_rob_banked_allocation_clean.py', 'test_rob_mmio_protocol.py')
    diff_origin = ROOT/'tools/test_rob_parallel_completion_differential.py'
    diff = diff_origin.read_text().replace('ROOT = Path(__file__).resolve().parents[1]', "ROOT = Path('E:/Verilog_cpu')")
    diff = diff.replace('COMPLETION_PARALLEL_WRITE', 'MMIO_PREDECODE')
    needle = '                rng=next_random(rng);completion_store_mask_i[lane*4 +: 4]=rng[3:0];'
    diff = once(diff, needle, needle + '''
                // Alternate true word exits, partial writes, adjacent-address
                // stores, and ordinary stores, including duplicate-tag lanes.
                case ((cycle+lane)%6)
                    0: begin completion_store_addr_i[lane*32 +: 32]=32'h80000000;
                             completion_store_mask_i[lane*4 +: 4]=4'hf; end
                    1: begin completion_store_addr_i[lane*32 +: 32]=32'h80000000;
                             completion_store_mask_i[lane*4 +: 4]=4'h3; end
                    2: begin completion_store_addr_i[lane*32 +: 32]=32'h80000004;
                             completion_store_mask_i[lane*4 +: 4]=4'hf; end
                    3: begin completion_store_addr_i[lane*32 +: 32]=32'h00000000;
                             completion_store_mask_i[lane*4 +: 4]=4'hf; end
                endcase''')
    files = {name:code, 'tb/unit/rv32_rob_tb.v':tb,
             'tools/test_rob_mmio_protocol.py':protocol,
             'tools/test_rob_mmio_differential.py':diff}
    for name, text in files.items():
        path = out/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    baseline = out/'baseline/rv32_rob.v';baseline.parent.mkdir(parents=True)
    baseline.write_bytes((source/'rtl/backend/rv32_rob.v').read_bytes())
    report = dict(status='STAGED', default_mmio_predecode=0, cpu_integrated=False,
                  baseline_sha256=sha(baseline), candidate_sha256=sha(out/'rtl/backend/rv32_rob.v'),
                  files_sha256={n:sha(out/n) for n in files},
                  preparer_inputs_sha256={str(p):sha(p) for p in [Path(__file__).resolve(),protocol_origin,diff_origin,ROOT/'tb/unit/rv32_rob_tb.v']},
                  original_payloads_and_ports_preserved=True,
                  scope='New optional per-row exit-word classification with exact original completion priority; full-module validation and original-flow CPU PPA pending.')
    (out/'candidate_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__': main()
