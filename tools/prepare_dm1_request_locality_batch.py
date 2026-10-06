"""Prepare a combined DM1 descendant using source edits only; no HDL run."""
import hashlib
import json
from pathlib import Path

from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta
from prepare_negative_polarity_distribution import distribution
from prepare_lsq_report_rob_predecode import lsq as report_lsq, BANK_READ


REQUEST_OWNER = '''

// Construct one LSQ request with local control loads. Admission and partial
// forwarding predicates never directly qualify a wide packet or barrel shift.
// Each externally visible payload still equals zero when no request is sent.
// Forwarding temporaries also retain their original admission/load gating.
(* keep_hierarchy = 1 *)
module rv32_lsq_request_owner #(
    parameter integer TAG_WIDTH=17,ROB_TAG_WIDTH=17
) (
    input wire flush_i,recovery_i,found_i,wait_i,load_i,ready_i,
    input wire [1:0] size_i,
    input wire unsigned_i,
    input wire [31:0] address_i,store_data_i,forward_data_i,
    input wire [3:0] store_mask_i,forward_mask_i,
    input wire [ROB_TAG_WIDTH-1:0] rob_tag_i,
    input wire [TAG_WIDTH-1:0] lsq_tag_i,
    output wire valid_o,load_o,store_o,unsigned_o,fire_o,
    output wire [1:0] size_o,
    output wire [15:0] mask_o,
    output wire [127:0] data_o,
    output wire [ROB_TAG_WIDTH-1:0] rob_tag_o,
    output wire [TAG_WIDTH-1:0] lsq_tag_o,
    output wire [3:0] target_mask_o,forward_mask_o,
    output wire [31:0] forward_data_o
);
    localparam integer ROB_WORDS=(ROB_TAG_WIDTH+15)/16;
    localparam integer LSQ_WORDS=(TAG_WIDTH+15)/16;
    localparam integer ROB_START=3,LSQ_START=ROB_START+ROB_WORDS;
    localparam integer DATA_START=LSQ_START+LSQ_WORDS;
    localparam integer VALID_LEAVES=DATA_START+8;
    wire admitted=!flush_i && !recovery_i && found_i && !wait_i;
    wire admitted_load=admitted && load_i;
    function [3:0] decode_access_mask;
        input [1:0] size;
        begin
            case(size)
                2'd0: decode_access_mask=4'b0001;
                2'd1: decode_access_mask=4'b0011;
                default: decode_access_mask=4'b1111;
            endcase
        end
    endfunction
    wire [3:0] access_mask=decode_access_mask(size_i);
    wire incomplete_forward=(forward_mask_i & access_mask)!=access_mask;
    wire request_valid=admitted && (!load_i || incomplete_forward);
    wire [2:0] forward_enable;
    wire [VALID_LEAVES-1:0] valid_views;
    wire [3:0] load_views;
    wire [31:0] relative_data;
    wire [127:0] inserted_data;
    wire [3:0] relative_mask=load_views[0]?
        (access_mask & ~forward_mask_i):store_mask_i;
    wire [15:0] inserted_mask={12'b0,relative_mask} << address_i[3:0];
    rv32_frequency_control_tree #(.LEAVES(3)) forward_tree (
        .signal_i(admitted_load),.views_o(forward_enable));
    rv32_frequency_control_tree #(.LEAVES(VALID_LEAVES)) valid_tree (
        .signal_i(request_valid),.views_o(valid_views));
    rv32_frequency_control_tree #(.LEAVES(4)) source_tree (
        .signal_i(load_i),.views_o(load_views));
    // A leaf owns eight mask bits, sixteen data bits, or at most five flags.
    assign target_mask_o={4{forward_enable[0]}} & access_mask;
    assign forward_mask_o={4{forward_enable[0]}} & forward_mask_i;
    assign valid_o=request_valid;
    assign fire_o=valid_views[0] && ready_i;
    assign load_o=valid_views[1] && load_views[3];
    assign store_o=valid_views[1] && !load_views[3];
    assign size_o={2{valid_views[1]}} & size_i;
    assign unsigned_o=valid_views[1] && load_views[3] && unsigned_i;
    assign mask_o={16{valid_views[2]}} & inserted_mask;
    genvar word;
    generate
        for(word=0;word<2;word=word+1) begin:g_relative
            assign forward_data_o[word*16 +: 16]=
                {16{forward_enable[word+1]}} & forward_data_i[word*16 +: 16];
            assign relative_data[word*16 +: 16]=load_views[word+1]?
                forward_data_i[word*16 +: 16]:store_data_i[word*16 +: 16];
        end
        for(word=0;word<ROB_WORDS;word=word+1) begin:g_rob_tag
            localparam integer LOW=word*16;
            localparam integer BITS=(ROB_TAG_WIDTH-LOW>=16)?16:ROB_TAG_WIDTH-LOW;
            assign rob_tag_o[LOW +: BITS]={BITS{valid_views[ROB_START+word]}} & rob_tag_i[LOW +: BITS];
        end
        for(word=0;word<LSQ_WORDS;word=word+1) begin:g_lsq_tag
            localparam integer LOW=word*16;
            localparam integer BITS=(TAG_WIDTH-LOW>=16)?16:TAG_WIDTH-LOW;
            assign lsq_tag_o[LOW +: BITS]={BITS{valid_views[LSQ_START+word]}} & lsq_tag_i[LOW +: BITS];
        end
        for(word=0;word<8;word=word+1) begin:g_line
            assign data_o[word*16 +: 16]=
                {16{valid_views[DATA_START+word]}} & inserted_data[word*16 +: 16];
        end
    endgenerate
    rv32_frequency_line_insert32 insertion (
        .value_i(relative_data),.offset_i(address_i[3:0]),.line_o(inserted_data));
endmodule
'''


def request_lsq(t):
    fields=('dcache_req_valid_o','dcache_req_is_load_o','dcache_req_is_store_o',
            'dcache_req_addr_o','dcache_req_size_o','dcache_req_unsigned_o',
            'dcache_req_mask_o','dcache_req_rob_tag_o','dcache_req_lsq_tag_o')
    lines=t.splitlines(keepends=True)
    for i,line in enumerate(lines):
        if 'output reg ' in line and any(n+',' in line for n in fields):
            lines[i]=line.replace('output reg ', 'output wire', 1)
    t=''.join(lines)
    for old,new in [('    reg [3:0] target_mask;', '    wire [3:0] target_mask;'),
                    ('    reg [3:0] fwd_mask;', '    wire [3:0] fwd_mask;'),
                    ('    reg [31:0] fwd_data;', '    wire [31:0] fwd_data;'),
                    ('    reg request_fire;', '    wire request_fire;')]:
        t=change(t,old,new)
    t=change(t, "        target_mask = 4'b0;\n        fwd_mask = 4'b0;\n        fwd_data = 32'b0;\n", '')
    t=change(t, '''        // Unconditional defaults: these temporaries are written only inside
        // nested conditions below, and a conditional-only write would infer
        // latches (thousands of proc_dlatch candidates in synthesis).''',
        '        // Allocation/response temporaries retain unconditional defaults.')
    start=t.index("        dcache_req_valid_o = 1'b0;")
    end=t.index('        // A fully covered load never touches the cache.',start)
    t=t[:start]+t[end:]
    start=t.index('    // The old request-admission gate fed ~151 mapped pins')
    end=t.index('    // Move the existing backend LSQ_ENTRIES x PHYS_ADDR_WIDTH map',start)
    t=t[:start]+'''    // Admission is resolved beside bounded output groups. No new state.
    wire [3:0] raw_forward_mask=(REQUEST_PIPELINE!=0 && forwarding_hold_valid)?
        forwarding_hold_mask:tree_forward_mask;
    wire [31:0] raw_forward_data=(REQUEST_PIPELINE!=0 && forwarding_hold_valid)?
        forwarding_hold_data:tree_forward_data;
    assign dcache_req_addr_o=selected_addr;
    (* keep_hierarchy = 1 *)
    rv32_lsq_request_owner #(.TAG_WIDTH(TAG_WIDTH),.ROB_TAG_WIDTH(ROB_TAG_WIDTH)) request_owner (
        .flush_i(flush_i),.recovery_i(recovery_valid_i),.found_i(candidate_found),
        .wait_i(candidate_wait),.load_i(selected_load),.ready_i(dcache_req_ready_i),
        .size_i(selected_size),.unsigned_i(selected_unsigned),.address_i(selected_addr),
        .store_data_i(selected_store_data),.store_mask_i(selected_store_mask),
        .forward_data_i(raw_forward_data),.forward_mask_i(raw_forward_mask),
        .rob_tag_i(selected_rob_tag),.lsq_tag_i(selected_lsq_tag),
        .valid_o(dcache_req_valid_o),.load_o(dcache_req_is_load_o),.store_o(dcache_req_is_store_o),
        .unsigned_o(dcache_req_unsigned_o),.fire_o(request_fire),.size_o(dcache_req_size_o),
        .mask_o(dcache_req_mask_o),.data_o(dcache_req_wdata_o),
        .rob_tag_o(dcache_req_rob_tag_o),.lsq_tag_o(dcache_req_lsq_tag_o),
        .target_mask_o(target_mask),.forward_mask_o(fwd_mask),.forward_data_o(fwd_data));

'''+t[end:]
    return t+REQUEST_OWNER


def predecode_backend(t):
    t=change(t, '    parameter integer STORE_ALLOC_IMM12 = 0\n) (',
             '    parameter integer STORE_ALLOC_IMM12 = 0,\n    parameter integer LSQ_ROB_QUERY_PREDECODE = 0\n) (')
    t=change(t, '    wire [TAG_WIDTH-1:0] lsq_load_complete_tag;', '''    wire [TAG_WIDTH-1:0] lsq_load_complete_tag;
    localparam integer LSQ_ROB_LOW_BITS=(ROB_SLOT_WIDTH+1)/2;
    localparam integer LSQ_ROB_HIGH_BITS=ROB_SLOT_WIDTH-LSQ_ROB_LOW_BITS;
    localparam integer LSQ_ROB_QUERY_WIDTH=(1<<LSQ_ROB_LOW_BITS)+(1<<LSQ_ROB_HIGH_BITS);
    wire [LSQ_ROB_QUERY_WIDTH-1:0] lsq_load_complete_rob_query;''')
    t=change(t, '''            rv32_frequency_array_read #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                .rows_i(rob_live_rows),
                .index_i(producer_query_tags[status_source*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]),
                .value_o(producer_live_reads[status_source*ROB_LIVE_WIDTH +: ROB_LIVE_WIDTH]));''', '''            if(LSQ_ROB_QUERY_PREDECODE!=0 && status_source==LSQ_SOURCE) begin:g_predecoded_load
                rv32_frequency_array_read_bank_masks #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                    .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                    .rows_i(rob_live_rows),.query_i(lsq_load_complete_rob_query),
                    .value_o(producer_live_reads[status_source*ROB_LIVE_WIDTH +: ROB_LIVE_WIDTH]));
            end else begin:g_original_status_query
                rv32_frequency_array_read #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                    .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                    .rows_i(rob_live_rows),
                    .index_i(producer_query_tags[status_source*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]),
                    .value_o(producer_live_reads[status_source*ROB_LIVE_WIDTH +: ROB_LIVE_WIDTH]));
            end''')
    t=change(t, ' .LOCAL_REPORT_CANCEL(LOCAL_EXEC_RECOVERY), .TAG_WIDTH(TAG_WIDTH),',
             ' .LOCAL_REPORT_CANCEL(LOCAL_EXEC_RECOVERY), .REPORT_ROB_PREDECODE(LSQ_ROB_QUERY_PREDECODE), .TAG_WIDTH(TAG_WIDTH),')
    return change(t, ' .load_complete_rob_tag_o(lsq_load_complete_tag),',
                  ' .load_complete_rob_tag_o(lsq_load_complete_tag), .load_complete_rob_query_o(lsq_load_complete_rob_query),')


def main():
    parent=ROOT/'DP_store_alloc_simm12'
    verify_parent(parent)
    out=prepare('DX_dm1_request_locality_and_predecode',parent,
        {'rtl/backend/rv32_lsq.v':lambda t:report_lsq(request_lsq(t)),
         'rtl/backend/rv32_backend_joint.v':predecode_backend,
         'rtl/common/rv32_asap7_fanout.v':lambda t:distribution(t)+BANK_READ,
         'rtl/cpu_core.v':lambda t:change(t,'    rv32_backend_joint #(.STORE_ALLOC_IMM12(1),',
               '    rv32_backend_joint #(.LSQ_ROB_QUERY_PREDECODE(1), .STORE_ALLOC_IMM12(1),')},
        'Combined measured-DM1 descendant: DP signed-12-bit store addition; global negative-polarity bounded distribution; local LSQ request/forwarding output owner; predecode LSQ report ROB query before report selection. Preserve full authority, original cycles and output-zero gating. No test or EDA execution.')
    record_delta(out,parent,['allocation_store_signed_12bit_adder',
        'negative_polarity_distribution','local_lsq_request_and_forwarding_owner',
        'lsq_report_rob_slot_predecode'])
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        measured_parent_run='F:/CPU2026CourseRuns/architecture_DM1_20261005',
        excluded_DT_groups=['precompare_after_arbitration_grants','dual_lsq_grant_assumptions',
                            'fused_producer_to_prf_operand_bypass','local_completion_prf_write_enable'],
        report_extra_combinational_payload_bits=16,report_payload_width=91,
        source_path_distribution_inverter_depth_reduction=2,
        request_payload_leaf_max_gate_bits=16,
        new_declared_sequential_state_bits=0,mapped_gain_proven=False,
        adoption_condition='Finish source review and deliver new pretest report. No measurement until current feasible non-cycle candidates have been considered together. Never reuse DM1/DT measured metrics for DX.')
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'candidate':str(out),'manifest_sha256':hashlib.sha256((out/'candidate.json').read_bytes()).hexdigest(),
                      'adopted':False,'tests_started':False},ensure_ascii=False))


if __name__=='__main__':
    main()
