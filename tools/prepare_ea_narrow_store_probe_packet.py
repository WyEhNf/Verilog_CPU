"""Prepare a conditional, isolated EA store-probe register boundary; no EDA."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta
from prepare_store_address_inflight import backend as exclude_inflight


def backend(text):
    text = change(text, '        wire [RS_ENTRIES-1:0] selected_rs;', '''        wire [RS_ENTRIES-1:0] selected_rs;
        wire [TAG_WIDTH-1:0] selected_lsq_tag,probe_rob_tag;
        wire [31:0] probe_base;
        // The CPU decoder contract permits a 12-bit saved store offset.
        // Generic standalone configurations retain all 32 immediate bits.
        localparam integer PROBE_IMM_WIDTH=(STORE_ALLOC_IMM12!=0)?12:32;
        localparam integer PROBE_PACKET_WIDTH=2*TAG_WIDTH+32+PROBE_IMM_WIDTH;
        wire [PROBE_IMM_WIDTH-1:0] probe_imm;
        wire probe_valid;
        wire [ROB_SLOT_WIDTH-1:0] probe_slot=probe_rob_tag[3 +: ROB_SLOT_WIDTH];''')
    text = change(text, '.rows_i(rob_live_rows),.index_i(selected_slot),.value_o(selected_live));',
                  '.rows_i(rob_live_rows),.index_i(probe_slot),.value_o(selected_live));')
    text = change(text, '.lsq_tag_o(shared_store_addr_tag), .rob_tag_o(selected_rob_tag), .base_value_o(selected_base), .base_select_o(selected_rs)',
                  '.lsq_tag_o(selected_lsq_tag), .rob_tag_o(selected_rob_tag), .base_value_o(selected_base), .base_select_o(selected_rs)')
    text = change(text, '''        assign shared_store_addr_valid = selected && !reset_i && !flush_i &&
            !branch_busy_domains[0] && selected_rob_tag[0] && selected_live[ROB_GENERATION_WIDTH] &&
            (selected_rob_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH] ==
             selected_live[0 +: ROB_GENERATION_WIDTH]);''', '''        // Recheck the complete saved ROB identity at publication. An index
        // or an old live predicate alone cannot authorize a saved packet.
        assign shared_store_addr_valid = probe_valid && !reset_i && !flush_i &&
            !branch_busy_domains[0] && probe_rob_tag[0] && selected_live[ROB_GENERATION_WIDTH] &&
            (probe_rob_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH] ==
             selected_live[0 +: ROB_GENERATION_WIDTH]);''')
    text = change(text, '        if(STORE_ALLOC_IMM12!=0) begin:g_decoder_store_offset', '''        wire [PROBE_PACKET_WIDTH-1:0] selected_probe_packet,probe_packet;
        assign selected_probe_packet={selected_rob_tag,selected_lsq_tag,selected_base,
                                      selected_imm[0 +: PROBE_IMM_WIDTH]};
        assign {probe_rob_tag,shared_store_addr_tag,probe_base,probe_imm}=probe_packet;
        if(STORE_RS_LINKS!=0) begin:g_probe_pipeline
            reg saved_valid;
            wire capture=selected && selected_rob_tag[0] && !reset_i &&
                !flush_i && !branch_busy_domains[0];
            // Capture before an ordinary same-cycle issue releases the RS.
            // This read-only probe does not consume issue or completion work.
            rv32_frequency_word_bank #(.WIDTH(PROBE_PACKET_WIDTH)) packet_owner (
                .clk_i(clk_i),.write_i(capture),.data_i(selected_probe_packet),.data_o(probe_packet));
            always @(posedge clk_i) begin
                if(reset_i || flush_i || branch_busy_domains[0]) saved_valid<=1'b0;
                else saved_valid<=selected && selected_rob_tag[0];
            end
            assign probe_valid=saved_valid;
        end else begin:g_legacy_probe
            assign probe_packet=selected_probe_packet;
            assign probe_valid=selected;
        end
        if(STORE_ALLOC_IMM12!=0) begin:g_decoder_store_offset''')
    text = change(text, '.base_i(selected_base),.immediate_i(selected_imm[11:0]),',
                  '.base_i(probe_base),.immediate_i(probe_imm[11:0]),')
    text = change(text, '.lhs_i(selected_base),.rhs_i(selected_imm),.sum_o(shared_store_addr));',
                  '.lhs_i(probe_base),.rhs_i(probe_imm),.sum_o(shared_store_addr));')
    return exclude_inflight(text)


def main():
    parent = ROOT/'EA_combined_control_locality'
    verify_parent(parent)
    out = prepare('EC_ea_narrow_store_probe_packet', parent,
        {'rtl/backend/rv32_backend_joint.v': backend},
        'Conditional alternative to EA: register full selected store identities, base and narrow decoder offset before shared AGU; retain effective same-cycle RS wake/issue. Recheck current full ROB identity, preserve full LSQ publication checks, exclude the publishing owner from next selection. Adds one early-probe cycle and 79 declared bits in current configuration. Source-only, not adopted or measured.')
    groups = json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    record_delta(out, parent, groups+['narrow_tagged_packet_before_shared_store_agu'])
    path = out/'candidate.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    manifest.update(
        actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        declared_additional_state_bits_vs_parent=79, added_declared_state_bits_vs_DM1=79,
        new_declared_sequential_state_bits=79,
        state_formula='STORE_RS_LINKS ? (2*TAG_WIDTH+32+(STORE_ALLOC_IMM12 ? 12 : 32)+1) : 0',
        behavior='One extra cycle for the opportunistic early store-address probe. Ordinary RS wake/issue, ALU addresses, store data, complete tags, request/commit authority are retained. No additional ordinary integer pipeline stage.',
        timing_tradeoff='Separates effective RS operand + selection from address arithmetic and publication; early store address/conflict release may be delayed. No IPC or frequency gain is claimed.',
        measured_parent_run=None, measured_reference_run='F:/CPU2026CourseRuns/architecture_DM1_20261005',
        adoption_condition='Inspect EA mapped critical paths first. Consider if store selection/operand to shared AGU remains material; compare with EB registered-base alternative, then report the chosen scope before measuring.')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         adopted=False,tests_started=False,declared_new_state_bits=79)))


if __name__=='__main__':
    main()
