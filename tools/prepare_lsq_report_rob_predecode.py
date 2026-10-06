"""Prepare a post-DT, unmeasured bank-mask query alternative. Source only."""
import hashlib
import json
from pathlib import Path

from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


BANK_READ='''

// Read a packed row array using two already-decoded index banks. A selected
// input bit drives bounded row groups; no encoded-index decode follows the
// late report selection. The caller retains the full normal generation check.
(* keep_hierarchy = 1 *)
module rv32_frequency_array_read_bank_masks #(
    parameter integer WIDTH=9,ENTRIES=64,
    parameter integer INDEX_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES),
    parameter integer LOW_BITS=(INDEX_WIDTH+1)/2,
    parameter integer HIGH_BITS=INDEX_WIDTH-LOW_BITS,
    parameter integer LOW_ROWS=1<<LOW_BITS,HIGH_ROWS=1<<HIGH_BITS,
    parameter integer WORDS=(WIDTH+15)/16,
    parameter integer LEAVES=1<<$clog2(ENTRIES)
) (
    input wire [ENTRIES*WIDTH-1:0] rows_i,
    input wire [LOW_ROWS+HIGH_ROWS-1:0] query_i,
    output wire [WIDTH-1:0] value_o
);
    wire [2*(LOW_ROWS+HIGH_ROWS)-1:0] query_views;
    wire [WIDTH-1:0] reads [1:2*LEAVES-1];
    rv32_frequency_control_tree #(.WIDTH(LOW_ROWS+HIGH_ROWS),.LEAVES(2)) query_tree (
        .signal_i(query_i),.views_o(query_views));
    assign value_o=reads[1];
    genvar row,word,node;
    generate
        for(row=0;row<LEAVES;row=row+1) begin:g_row
            if(row<ENTRIES && row<(1<<INDEX_WIDTH)) begin:g_present
                localparam integer DOMAIN=(row*2)/ENTRIES;
                wire [WORDS-1:0] selects;
                wire hit=query_views[DOMAIN*(LOW_ROWS+HIGH_ROWS)+(row%LOW_ROWS)] &&
                    query_views[DOMAIN*(LOW_ROWS+HIGH_ROWS)+LOW_ROWS+(row/LOW_ROWS)];
                rv32_frequency_control_tree #(.LEAVES(WORDS)) select_tree (
                    .signal_i(hit),.views_o(selects));
                for(word=0;word<WORDS;word=word+1) begin:g_word
                    localparam integer LOW=word*16;
                    localparam integer BITS=(WIDTH-LOW>=16)?16:WIDTH-LOW;
                    assign reads[LEAVES+row][LOW +: BITS]=
                        {BITS{selects[word]}} & rows_i[row*WIDTH+LOW +: BITS];
                end
            end else begin:g_padding
                assign reads[LEAVES+row]=0;
            end
        end
        for(node=1;node<LEAVES;node=node+1) begin:g_reduce
            assign reads[node]=reads[2*node] | reads[2*node+1];
        end
    endgenerate
endmodule
'''


def lsq(t):
    t=change(t, '''        2*((ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES)) + $clog2(ROB_ENTRIES+1)
) (''', '''        2*((ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES)) + $clog2(ROB_ENTRIES+1),
    parameter integer REPORT_ROB_PREDECODE = 0,
    parameter integer REPORT_ROB_LOW_BITS=(((ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES))+1)/2,
    parameter integer REPORT_ROB_HIGH_BITS=((ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES))-REPORT_ROB_LOW_BITS
) (''')
    t=change(t, '    output reg                          load_complete_cancel_o\n);', '''    output reg                          load_complete_cancel_o,
    // {high-index bank one-hot,low-index bank one-hot}; default disabled.
    output wire [(1<<REPORT_ROB_LOW_BITS)+(1<<REPORT_ROB_HIGH_BITS)-1:0] load_complete_rob_query_o
);''')
    t=change(t, '    localparam integer REPORT_WIDTH=PHYS_ADDR_WIDTH+ROB_TAG_WIDTH+TAG_WIDTH+35;', '''    localparam integer REPORT_BASE_WIDTH=PHYS_ADDR_WIDTH+ROB_TAG_WIDTH+TAG_WIDTH+35;
    localparam integer REPORT_ROB_LOW_ROWS=1<<REPORT_ROB_LOW_BITS;
    localparam integer REPORT_ROB_HIGH_ROWS=1<<REPORT_ROB_HIGH_BITS;
    localparam integer REPORT_ROB_QUERY_WIDTH=REPORT_ROB_LOW_ROWS+REPORT_ROB_HIGH_ROWS;
    localparam integer REPORT_WIDTH=REPORT_BASE_WIDTH+
        ((REPORT_ROB_PREDECODE!=0)?REPORT_ROB_QUERY_WIDTH:0);''')
    t=change(t, '    genvar report_row,report_word,report_node;', '    genvar report_row,report_word,report_node,report_decode;')
    t=change(t, '''                wire [REPORT_WIDTH-1:0] report_payload={
                    row_cancel,!retired_mem[report_row],physical_destinations[report_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                    complete_error_mem[report_row],complete_value_mem[report_row],
                    make_lsq_tag(report_row,generation_mem[report_row]),rob_tag_mem[report_row]};''', '''                wire [REPORT_BASE_WIDTH-1:0] base_report_payload={
                    row_cancel,!retired_mem[report_row],physical_destinations[report_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                    complete_error_mem[report_row],complete_value_mem[report_row],
                    make_lsq_tag(report_row,generation_mem[report_row]),rob_tag_mem[report_row]};
                wire [REPORT_WIDTH-1:0] report_payload;
                if(REPORT_ROB_PREDECODE!=0) begin:g_predecoded_query
                    wire [REPORT_ROB_QUERY_WIDTH-1:0] query;
                    // Decode stored row tags before late head/report selection.
                    // No new FF, and the original full tag is still reported.
                    for(report_decode=0;report_decode<REPORT_ROB_LOW_ROWS;report_decode=report_decode+1) begin:g_low
                        assign query[report_decode]=rob_tag_mem[report_row][3 +: REPORT_ROB_LOW_BITS]==report_decode;
                    end
                    for(report_decode=0;report_decode<REPORT_ROB_HIGH_ROWS;report_decode=report_decode+1) begin:g_high
                        if(REPORT_ROB_HIGH_BITS>0) begin:g_bits
                            assign query[REPORT_ROB_LOW_ROWS+report_decode]=
                                rob_tag_mem[report_row][3+REPORT_ROB_LOW_BITS +: REPORT_ROB_HIGH_BITS]==report_decode;
                        end else begin:g_single_bank
                            assign query[REPORT_ROB_LOW_ROWS+report_decode]=1'b1;
                        end
                    end
                    assign report_payload={query,base_report_payload};
                end else begin:g_original_query
                    assign report_payload=base_report_payload;
                end''')
    t=change(t, '''        {load_complete_cancel_o,load_complete_unretired_o,load_complete_phys_rd_o,load_complete_error_o,load_complete_value_o,load_complete_lsq_tag_o,load_complete_rob_tag_o}=report_payload_tree[1];''', '''        {load_complete_cancel_o,load_complete_unretired_o,load_complete_phys_rd_o,load_complete_error_o,load_complete_value_o,load_complete_lsq_tag_o,load_complete_rob_tag_o}=report_payload_tree[1][0 +: REPORT_BASE_WIDTH];''')
    return change(t, '''    always @* begin
        complete_slot_found=report_valid_tree[1];''', '''    generate if(REPORT_ROB_PREDECODE!=0) begin:g_report_rob_query
        assign load_complete_rob_query_o=report_payload_tree[1][REPORT_BASE_WIDTH +: REPORT_ROB_QUERY_WIDTH];
    end else begin:g_no_report_rob_query
        assign load_complete_rob_query_o=0;
    end endgenerate

    always @* begin
        complete_slot_found=report_valid_tree[1];''')


def backend(t):
    t=change(t, '    parameter integer PRF_DIRECT_OPERAND_BYPASS = 0\n) (', '''    parameter integer PRF_DIRECT_OPERAND_BYPASS = 0,
    parameter integer LSQ_ROB_QUERY_PREDECODE = 0
) (''')
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


def core(t):
    return change(t, '    rv32_backend_joint #(.PRF_DIRECT_OPERAND_BYPASS(1),',
                  '    rv32_backend_joint #(.LSQ_ROB_QUERY_PREDECODE(1), .PRF_DIRECT_OPERAND_BYPASS(1),')


if __name__=='__main__':
    parent=ROOT/'DT_completion_local_prf_enable'
    verify_parent(parent)
    out=prepare('DU_lsq_report_rob_predecode',parent,
        {'rtl/backend/rv32_lsq.v':lsq,'rtl/backend/rv32_backend_joint.v':backend,
         'rtl/cpu_core.v':core,'rtl/common/rv32_asap7_fanout.v':lambda t:t+BANK_READ},
        'Conditional post-DT alternative: decode each stored LSQ ROB slot into two bank masks before completion-row arbitration, carry the masks with the exact selected full-tag report, then query the unchanged normal ROB valid/generation rows. No authority removal, clock edge or new declared state; wider completion packet. Unadopted and unmeasured.')
    record_delta(out,parent,['allocation_store_signed_12bit_adder','prf_compare_before_completion',
        'late_lsq_completion_grants','fused_producer_to_prf_operand_bypass','completion_local_prf_write_enable',
        'lsq_report_rob_slot_predecode'])
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    manifest['actual_preparation_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest['adoption_condition']='Review DT timing first; consider only if selected LSQ tag -> normal ROB lookup remains a material limiting cone.'
    manifest['report_payload_width_current_configuration']=91
    manifest['report_extra_payload_bits_current_configuration']=16
    manifest['new_declared_sequential_state_bits']=0
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'candidate':str(out),'manifest_sha256':hashlib.sha256((out/'candidate.json').read_bytes()).hexdigest(),
                      'tests_started':False,'adopted':False},ensure_ascii=False))
