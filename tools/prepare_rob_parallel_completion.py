"""Prepare an isolated whole-ROB parallel completion-write experiment.

Preserve every architectural state, port, cycle and write priority. All
matching lanes contribute sticky errors; the last lane supplies payload.
No CPU source or previous evidence is edited by this preparer.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(text, old, new):
    assert text.count(old) == 1, 'Ambiguous anchor: ' + old[:90]
    return text.replace(old, new)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


DECODE = '''
    // Decode each live generation once, then select the final matching lane
    // in parallel. Error is sticky from every match, including losing lanes.
    wire [ROB_ENTRIES-1:0] parallel_completion_fire;
    wire [ROB_ENTRIES-1:0] parallel_completion_error;
    wire [99:0] parallel_completion_packet [0:ROB_ENTRIES-1];
    genvar completion_row, completion_source;
    generate
        for (completion_row = 0; completion_row < ROB_ENTRIES;
             completion_row = completion_row + 1) begin: g_parallel_completion
            if (COMPLETION_PARALLEL_WRITE != 0) begin: g_enabled
                wire [BE_WIDTH-1:0] completion_match_bits, grants;
                for (completion_source = 0; completion_source < BE_WIDTH;
                     completion_source = completion_source + 1) begin: g_lane
                    assign completion_match_bits[completion_source] =
                        completion_valid_i[completion_source] &&
                        completion_done_i[completion_source] &&
                        completion_tag_i[completion_source*TAG_WIDTH + VALID_LSB] &&
                        valid_mem[completion_row] &&
                        (completion_tag_i[completion_source*TAG_WIDTH + SLOT_LSB +: SLOT_WIDTH] == completion_row) &&
                        (completion_tag_i[completion_source*TAG_WIDTH + GEN_LSB +: GENERATION_WIDTH] ==
                         generation_mem[completion_row]);
                    if (completion_source == BE_WIDTH-1)
                        assign grants[completion_source] = completion_match_bits[completion_source];
                    else
                        assign grants[completion_source] = completion_match_bits[completion_source] &&
                            !(|completion_match_bits[BE_WIDTH-1:completion_source+1]);
                end
                reg [99:0] packet;
                integer packet_lane;
                always @* begin
                    packet = 100'b0;
                    for (packet_lane = 0; packet_lane < BE_WIDTH; packet_lane = packet_lane + 1)
                        packet = packet | ({100{grants[packet_lane]}} &
                            {completion_value_i[packet_lane*32 +: 32],
                             completion_store_addr_i[packet_lane*32 +: 32],
                             completion_store_mask_i[packet_lane*4 +: 4],
                             completion_store_data_i[packet_lane*32 +: 32]});
                end
                assign parallel_completion_fire[completion_row] = |completion_match_bits;
                assign parallel_completion_error[completion_row] = |(completion_match_bits & completion_error_i);
                assign parallel_completion_packet[completion_row] = packet;
            end else begin: g_disabled
                assign parallel_completion_fire[completion_row] = 1'b0;
                assign parallel_completion_error[completion_row] = 1'b0;
                assign parallel_completion_packet[completion_row] = 100'b0;
            end
        end
    endgenerate
    integer parallel_completion_row;
    integer parallel_completion_age;

'''


def writes(recovery):
    condition = 'parallel_completion_fire[parallel_completion_row]'
    age = ''
    if recovery:
        condition += ' && (parallel_completion_age <= branch_age)'
        age = '''                    parallel_completion_age = parallel_completion_row - head_update_index;
                    if (parallel_completion_age < 0)
                        parallel_completion_age = parallel_completion_age + ROB_ENTRIES;
'''
    return '''            if (COMPLETION_PARALLEL_WRITE != 0) begin
                for (parallel_completion_row = 0; parallel_completion_row < ROB_ENTRIES;
                     parallel_completion_row = parallel_completion_row + 1) begin
''' + age + '''                    if (''' + condition + ''') begin
                        ready_mem[parallel_completion_row] <= 1'b1;
                        {value_mem[parallel_completion_row], store_addr_mem[parallel_completion_row],
                         store_mask_mem[parallel_completion_row], store_data_mem[parallel_completion_row]} <=
                            parallel_completion_packet[parallel_completion_row];
                        if (parallel_completion_error[parallel_completion_row])
                            error_mem[parallel_completion_row] <= 1'b1;
                    end
                end
            end else begin
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    assert not out.exists(), 'Choose a new candidate directory'
    name = 'rtl/backend/rv32_rob.v'
    source = ROOT / name
    original = source.read_text(encoding='utf-8')
    text = replace(original, '    parameter integer ALLOC_BANKED_WRITE = 0,',
                   '    parameter integer ALLOC_BANKED_WRITE = 0,\n'
                   '    parameter integer COMPLETION_PARALLEL_WRITE = 0,')
    text = replace(text, '            (ALLOC_BANKED_WRITE != 0 && ALLOC_BANKED_WRITE != 1) ||',
                   '            (ALLOC_BANKED_WRITE != 0 && ALLOC_BANKED_WRITE != 1) ||\n'
                   '            (COMPLETION_PARALLEL_WRITE != 0 && COMPLETION_PARALLEL_WRITE != 1) ||')
    text = replace(text, '    assign head_o = head_views[4*SLOT_WIDTH +: SLOT_WIDTH];',
                   DECODE + '    assign head_o = head_views[4*SLOT_WIDTH +: SLOT_WIDTH];')
    start = '            for (complete_lane = 0; complete_lane < BE_WIDTH; complete_lane = complete_lane + 1) begin'
    assert text.count(start) == 2
    for recovery, end in ((True, '            tail_reg <= advance_slot(chosen_slot'),
                          (False, '            for (slot_index = 0; slot_index < ROB_ENTRIES; slot_index = slot_index + 1) begin\n                if (store_ack_valid_i')):
        end_pos = text.index(end)
        start_pos = text.rindex(start, 0, end_pos)
        legacy = text[start_pos:end_pos]
        text = text[:start_pos] + writes(recovery) + legacy + '            end\n' + text[end_pos:]
    files = {name: text}
    tb = (ROOT/'tb/unit/rv32_rob_tb.v').read_text(encoding='utf-8')
    tb = replace(tb, '    parameter integer ALLOC_BANKED_WRITE = 1',
                 '    parameter integer COMPLETION_PARALLEL_WRITE = 1,\n    parameter integer ALLOC_BANKED_WRITE = 1')
    tb = replace(tb, '.ALLOC_BANKED_WRITE(ALLOC_BANKED_WRITE)) dut (',
                 '.ALLOC_BANKED_WRITE(ALLOC_BANKED_WRITE), .COMPLETION_PARALLEL_WRITE(COMPLETION_PARALLEL_WRITE)) dut (')
    tb = replace(tb, '    integer bad;', '    initial begin\n'
                 '        if (dut.COMPLETION_PARALLEL_WRITE != 1) $fatal(1, "parallel completion path not enabled");\n'
                 '    end\n    integer bad;')
    files['tb/unit/rv32_rob_tb.v'] = tb
    helper = (ROOT/'tools/test_rob_banked_allocation_clean.py').read_text(encoding='utf-8')
    helper = replace(helper, 'ROOT = Path(__file__).resolve().parents[1]', "ROOT = Path('E:/Verilog_cpu')")
    helper = helper.replace('tools/test_rob_banked_allocation_clean.py', 'tools/test_rob_parallel_completion.py')
    helper = replace(helper, 'STORE_BUFFERED_RETIRE=buffered)',
                     'STORE_BUFFERED_RETIRE=buffered, COMMIT_BANKED_READ=mode,\n'
                     '                            ALLOC_BANKED_WRITE=args.alloc_mode)')
    helper = replace(helper, "f' -set COMMIT_BANKED_READ {mode} -set ALLOC_BANKED_WRITE {args.alloc_mode} rv32_rob'",
                     "' -set COMPLETION_PARALLEL_WRITE 1 rv32_rob'")
    helper = replace(helper, "'rename rv32_rob gate', 'proc', 'memory_map', 'opt_clean',",
                     "'rename rv32_rob gate', 'proc', 'memory_map', 'opt_expr -keepdc', 'opt_clean',")
    helper = helper.replace('ROB bank-read', 'ROB parallel-completion')
    files['tools/test_rob_parallel_completion.py'] = helper
    probe = (ROOT/'tools/probe_localized_component.py').read_text(encoding='utf-8')
    probe = replace(probe, "else f'commit1_allocate{variant}')", "else f'commit1_allocate1_completion{variant}')")
    probe = replace(probe, 'ALLOC_BANKED_WRITE=variant)', 'ALLOC_BANKED_WRITE=1, COMPLETION_PARALLEL_WRITE=variant)')
    files['tools/probe_localized_component.py'] = probe
    files['baseline/rv32_rob.v'] = original
    for filename, contents in files.items():
        target = out/filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding='utf-8')
    (out/'baseline/rv32_rob.v').write_bytes(source.read_bytes())
    assert sha(source) == sha(out/'baseline/rv32_rob.v')
    report = dict(status='PREPARED', source=str(source), original_sha256=sha(source),
                  files_sha256={name:sha(out/name) for name in files},
                  only_new_parameter='COMPLETION_PARALLEL_WRITE', default_value=0,
                  all_error_lanes_preserved=True, last_matching_lane_payload=True,
                  extra_execution_cycles=0, not_a_cpu_result=True, integrated_into_cpu=False)
    (out/'candidate_manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
