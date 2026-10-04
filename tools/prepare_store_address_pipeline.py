"""Prepare an unmeasured store-probe pipeline alternative without adopting it."""
import difflib
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare


def backend(text):
    text=change(text,'        wire [RS_ENTRIES-1:0] selected_rs;',
        '''        wire [RS_ENTRIES-1:0] selected_rs;
        wire [TAG_WIDTH-1:0] selected_lsq_tag;
        wire [TAG_WIDTH-1:0] probe_rob_tag;
        wire [31:0] probe_base,probe_imm;
        wire probe_valid;
        wire [ROB_SLOT_WIDTH-1:0] probe_slot=probe_rob_tag[3 +: ROB_SLOT_WIDTH];''')
    text=change(text,'.rows_i(rob_live_rows),.index_i(selected_slot),.value_o(selected_live));',
        '.rows_i(rob_live_rows),.index_i(probe_slot),.value_o(selected_live));')
    text=change(text,'.lsq_tag_o(shared_store_addr_tag), .rob_tag_o(selected_rob_tag), .base_value_o(selected_base), .base_select_o(selected_rs)',
        '.lsq_tag_o(selected_lsq_tag), .rob_tag_o(selected_rob_tag), .base_value_o(selected_base), .base_select_o(selected_rs)')
    text=change(text,
        '''        assign shared_store_addr_valid = selected && !reset_i && !flush_i &&
            !branch_busy_domains[0] && selected_rob_tag[0] && selected_live[ROB_GENERATION_WIDTH] &&
            (selected_rob_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH] ==
             selected_live[0 +: ROB_GENERATION_WIDTH]);''',
        '''        // Qualification uses the saved complete ROB identity at publication,
        // after the register boundary. Recovery suppresses the probe before
        // a killed ROB owner can be reclaimed or its index reused.
        assign shared_store_addr_valid = probe_valid && !reset_i && !flush_i &&
            !branch_busy_domains[0] && probe_rob_tag[0] && selected_live[ROB_GENERATION_WIDTH] &&
            (probe_rob_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH] ==
             selected_live[0 +: ROB_GENERATION_WIDTH]);''')
    return change(text,
        '''        rv32_frequency_add32_select address_adder (
            .lhs_i(selected_base),.rhs_i(selected_imm),.sum_o(shared_store_addr));''',
        '''        localparam integer PROBE_PACKET_WIDTH=2*TAG_WIDTH+64;
        wire [PROBE_PACKET_WIDTH-1:0] selected_probe_packet,probe_packet;
        assign selected_probe_packet={selected_rob_tag,selected_lsq_tag,selected_base,selected_imm};
        assign {probe_rob_tag,shared_store_addr_tag,probe_base,probe_imm}=probe_packet;
        if(STORE_RS_LINKS!=0) begin:g_probe_pipeline
            reg saved_valid;
            wire capture=selected && selected_rob_tag[0] && !reset_i &&
                !flush_i && !branch_busy_domains[0];
            // No replay/issue owner is consumed by this opportunistic probe.
            // Each captured packet is consumed the next cycle. The original
            // ALU address/data update remains available for every store.
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
        rv32_frequency_add32_select address_adder (
            .lhs_i(probe_base),.rhs_i(probe_imm),.sum_o(shared_store_addr));''')


if __name__=='__main__':
    parent=ROOT/'DM1_lsq_report_bound_widths'
    original=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))
    for name,expected in original['source_sha256'].items():
        assert hashlib.sha256((parent/name).read_bytes()).hexdigest()==expected,name
    name='rtl/backend/rv32_backend_joint.v'
    out=prepare('DO_store_address_pipeline',parent,{name:backend},
        'DM1 alternative: one tagged packet register between linked store selection and shared AGU. '
        'Same-cycle ordinary RS wake/issue retained; full ROB authority at publication and original ALU updates retained. '
        'Source-only, untested, not adopted.')
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        changed_files_vs_parent=[name],declared_additional_state_bits_vs_parent=99,
        timing_tradeoff='One extra store-probe cycle; captures owner before RS release, keeps ordinary issue unchanged.')
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    patch=''.join(difflib.unified_diff(
        (parent/name).read_text(encoding='utf-8').splitlines(keepends=True),
        (out/name).read_text(encoding='utf-8').splitlines(keepends=True),
        fromfile=parent.name+'/'+name,tofile=out.name+'/'+name))
    (out/'changes_vs_DM1.patch').write_text(patch,encoding='utf-8')
