"""Combine confirmed allocation-path cut with LSQ direct grants/local hold."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def lsq(text):
    text=change(text,'    reg [3:0] forwarding_hold_mask;', '    wire [3:0] forwarding_hold_mask;')
    text=change(text,'    reg [31:0] forwarding_hold_data;', '    wire [31:0] forwarding_hold_data;')
    text=change(text,'''    wire forwarding_payload_write;
    rv32_frequency_control_tree #(.LEAVES(1)) forwarding_hold_tree (
        .signal_i(forwarding_hold_write),.views_o(forwarding_payload_write));''', '''    // Same 36 unreset payload bits and write edge, with existing word owners.
    // A final enable drives <=16 hold muxes instead of all 36 (72 pins).
    rv32_frequency_word_bank #(.WIDTH(36)) forwarding_hold_owner (
        .clk_i(clk_i),.write_i(forwarding_hold_write),
        .data_i({fwd_mask,fwd_data}),.data_o({forwarding_hold_mask,forwarding_hold_data}));''')
    text=change(text, '        if(forwarding_payload_write) begin forwarding_hold_mask<=fwd_mask;forwarding_hold_data<=fwd_data;end\n', '')
    text=change(text,'''    wire [3:0] raw_forward_mask=(REQUEST_PIPELINE!=0 && forwarding_hold_valid)?
        forwarding_hold_mask:tree_forward_mask;
    wire [31:0] raw_forward_data=(REQUEST_PIPELINE!=0 && forwarding_hold_valid)?
        forwarding_hold_data:tree_forward_data;''', '''    wire [2:0] saved_forward_views;
    rv32_frequency_control_tree #(.LEAVES(3)) saved_forward_tree (
        .signal_i(REQUEST_PIPELINE!=0 && forwarding_hold_valid),.views_o(saved_forward_views));
    wire [3:0] raw_forward_mask=saved_forward_views[2]?
        forwarding_hold_mask:tree_forward_mask;
    wire [31:0] raw_forward_data;
    assign raw_forward_data[0 +: 16]=saved_forward_views[0]?
        forwarding_hold_data[0 +: 16]:tree_forward_data[0 +: 16];
    assign raw_forward_data[16 +: 16]=saved_forward_views[1]?
        forwarding_hold_data[16 +: 16]:tree_forward_data[16 +: 16];''')
    text=change(text, '    genvar report_row,report_word,report_node,report_decode;', '''    // The original tournament orders candidates by (wrap, physical row).
    // Choose the first eligible non-wrapped row, otherwise the first eligible
    // row, directly as one-hot. Keep the original binary slot for metadata;
    // wide report routing no longer waits for its encode/decode chain.
    localparam integer REPORT_GRANT_DOMAINS=(LSQ_ENTRIES+3)/4;
    wire [LSQ_ENTRIES-1:0] report_eligible,report_upper,report_first;
    wire [REPORT_GRANT_DOMAINS-1:0] report_wrap_enable_views;
    rv32_frequency_control_tree #(.LEAVES(REPORT_GRANT_DOMAINS)) report_wrap_enable_tree (
        .signal_i(!(|report_upper)),.views_o(report_wrap_enable_views));
    genvar report_row,report_word,report_node,report_decode;''')
    text=change(text, '''                assign report_wrap_tree[REPORT_ROWS+report_row]=circular_wrap_views[report_row*8+5];''', '''                assign report_wrap_tree[REPORT_ROWS+report_row]=circular_wrap_views[report_row*8+5];
                assign report_eligible[report_row]=report_valid_tree[REPORT_ROWS+report_row];
                assign report_upper[report_row]=report_eligible[report_row] &&
                    !report_wrap_tree[REPORT_ROWS+report_row];
                if(report_row==0) begin:g_first_direct_report
                    assign report_first[report_row]=report_upper[report_row] ||
                        (report_wrap_enable_views[report_row/4] && report_eligible[report_row]);
                end else begin:g_later_direct_report
                    assign report_first[report_row]=
                        (report_upper[report_row] && !(|report_upper[report_row-1:0])) ||
                        (report_wrap_enable_views[report_row/4] && report_eligible[report_row] &&
                         !(|report_eligible[report_row-1:0]));
                end''')
    return change(text, '.signal_i(report_valid_tree[1] && report_slot_tree[1]==report_row),.views_o(report_select));',
                  '.signal_i(report_first[report_row]),.views_o(report_select));')


def main():
    parent=ROOT/'ED_ea_shared_only_store_address'
    verify_parent(parent)
    out=prepare('EE_lsq_direct_report_and_forward_hold',parent,
        {'rtl/backend/rv32_lsq.v':lsq},
        'ED plus direct circular one-hot report payload grants, preserving original binary metadata winner and full tags. Group the same 36 forwarding hold FF payload writes and saved/live reads using existing control trees/word bank. No added state/cycle beyond ED allocation-address availability tradeoff. Source-only, unmeasured.')
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    record_delta(out,parent,groups+['direct_circular_onehot_lsq_report_payload',
        'lsq_forwarding_hold_word_owners','lsq_saved_forwarding_read_domains'])
    path=out/'candidate.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        declared_additional_state_bits_vs_parent=0,new_declared_sequential_state_bits=0,
        existing_clocked_payload_refactor='Forwarding hold 36 bits moved from the original conditional clock block to existing word-bank owner, same data/write/edge, unreset.',
        behavior='Inherits ED loss of allocation-edge early store address. LSQ report payload winner, binary metadata slot, full tags, handshake and forwarding hold cycles are retained; ordinary integer pipeline stays 10 stages.',
        measured_parent_run=None,measured_reference_run='F:/CPU2026CourseRuns/architecture_EA_20261005',
        source_algebra='Old report tournament returns minimum (wrap,row) among eligible leaves. Direct grant returns first unwrapped eligible if any, else first eligible; same winner independent of head/occupancy invariants.',
        adoption_condition='Finish source review and report the full EA-to-EE combination before one timing-only measurement. No intermediate ED/EE or program tests.')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         adopted=False,tests_started=False,new_declared_state_bits=0)))


if __name__=='__main__':
    main()
