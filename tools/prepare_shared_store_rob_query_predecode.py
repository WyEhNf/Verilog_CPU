"""Conditional EL1 child: predecode saved store ROB row before probe selection."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def selector(text):
    text=change(text,'    parameter integer ROB_TAG_WIDTH = TAG_WIDTH,',
        '''    parameter integer ROB_TAG_WIDTH = TAG_WIDTH,
    parameter integer ROB_ENTRIES = 64,
    parameter integer ROB_QUERY_PREDECODE = 0,
    parameter integer ROB_SW = (ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES),
    parameter integer ROB_LOW_BITS = (ROB_SW+1)/2,
    parameter integer ROB_HIGH_BITS = ROB_SW-ROB_LOW_BITS,''')
    text=change(text,'    output wire [RS_ENTRIES-1:0] base_select_o,',
        '''    output wire [RS_ENTRIES-1:0] base_select_o,
    output wire [(1<<ROB_LOW_BITS)+(1<<ROB_HIGH_BITS)-1:0] rob_query_o,''')
    text=change(text,'    localparam integer STORE_PACKET_WIDTH=TAG_WIDTH+ROB_TAG_WIDTH+RS_ENTRIES;',
        '''    localparam integer STORE_BASE_WIDTH=TAG_WIDTH+ROB_TAG_WIDTH+RS_ENTRIES;
    localparam integer ROB_LOW_ROWS=1<<ROB_LOW_BITS,ROB_HIGH_ROWS=1<<ROB_HIGH_BITS;
    localparam integer ROB_QUERY_WIDTH=ROB_LOW_ROWS+ROB_HIGH_ROWS;
    localparam integer STORE_PACKET_WIDTH=STORE_BASE_WIDTH+
        ((ROB_QUERY_PREDECODE!=0)?ROB_QUERY_WIDTH:0);''')
    text=change(text,'    assign lsq_tag_o=chosen_packet[RS_ENTRIES+ROB_TAG_WIDTH +: TAG_WIDTH];',
        '''    assign lsq_tag_o=chosen_packet[RS_ENTRIES+ROB_TAG_WIDTH +: TAG_WIDTH];
    generate if(ROB_QUERY_PREDECODE!=0) begin:g_selected_rob_query
        assign rob_query_o=chosen_packet[STORE_BASE_WIDTH +: ROB_QUERY_WIDTH];
    end else begin:g_unused_rob_query
        assign rob_query_o=0;
    end endgenerate''')
    text=change(text,'''            assign row_packets[row*STORE_PACKET_WIDTH +: STORE_PACKET_WIDTH]={
                lsq_tag_i[row*TAG_WIDTH +: TAG_WIDTH],store_rob_tag_i[row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH],match_grants};''',
        '''            wire [STORE_BASE_WIDTH-1:0] base_packet={
                lsq_tag_i[row*TAG_WIDTH +: TAG_WIDTH],store_rob_tag_i[row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH],match_grants};
            if(ROB_QUERY_PREDECODE!=0) begin:g_saved_rob_decode
                // These fields come from saved LSQ tags, before late ready/
                // circular-priority selection. The complete tag is preserved.
                wire [ROB_QUERY_WIDTH-1:0] query;
                for(genvar query_bit=0;query_bit<ROB_LOW_ROWS;query_bit=query_bit+1) begin:g_low
                    assign query[query_bit]=
                        store_rob_tag_i[row*ROB_TAG_WIDTH+3 +: ROB_LOW_BITS]==query_bit;
                end
                for(genvar query_bit=0;query_bit<ROB_HIGH_ROWS;query_bit=query_bit+1) begin:g_high
                    if(ROB_HIGH_BITS>0) begin:g_bits
                        assign query[ROB_LOW_ROWS+query_bit]=
                            store_rob_tag_i[row*ROB_TAG_WIDTH+3+ROB_LOW_BITS +: ROB_HIGH_BITS]==query_bit;
                    end else begin:g_single_bank
                        assign query[ROB_LOW_ROWS+query_bit]=1'b1;
                    end
                end
                assign row_packets[row*STORE_PACKET_WIDTH +: STORE_PACKET_WIDTH]={query,base_packet};
            end else begin:g_original_packet
                assign row_packets[row*STORE_PACKET_WIDTH +: STORE_PACKET_WIDTH]=base_packet;
            end''')
    return text


def backend(text):
    text=change(text,'    parameter integer LSQ_RESPONSE_QUERY_PREDECODE = 0',
        '''    parameter integer LSQ_RESPONSE_QUERY_PREDECODE = 0,
    parameter integer STORE_PROBE_ROB_PREDECODE = 0''')
    text=change(text,'''        rv32_frequency_array_read #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
            .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
            .rows_i(rob_live_rows),.index_i(selected_slot),.value_o(selected_live));''',
        '''        localparam integer QUERY_LOW_BITS=(ROB_SLOT_WIDTH+1)/2;
        localparam integer QUERY_HIGH_BITS=ROB_SLOT_WIDTH-QUERY_LOW_BITS;
        wire [(1<<QUERY_LOW_BITS)+(1<<QUERY_HIGH_BITS)-1:0] selected_rob_query;
        if(STORE_PROBE_ROB_PREDECODE!=0) begin:g_direct_live_query
            rv32_frequency_array_read_bank_masks #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                .rows_i(rob_live_rows),.query_i(selected_rob_query),.value_o(selected_live));
        end else begin:g_original_live_query
            rv32_frequency_array_read #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                .rows_i(rob_live_rows),.index_i(selected_slot),.value_o(selected_live));
        end''')
    text=change(text,'.TAG_WIDTH(TAG_WIDTH), .ROB_TAG_WIDTH(TAG_WIDTH),.LINKED_RS(STORE_RS_LINKS)) selector (',
        '''.TAG_WIDTH(TAG_WIDTH), .ROB_TAG_WIDTH(TAG_WIDTH),.LINKED_RS(STORE_RS_LINKS),
            .ROB_ENTRIES(ROB_ENTRIES),.ROB_QUERY_PREDECODE(STORE_PROBE_ROB_PREDECODE)) selector (''')
    text=change(text,'.lsq_tag_o(shared_store_addr_tag), .rob_tag_o(selected_rob_tag), .base_value_o(selected_base), .base_select_o(selected_rs)',
        '''.lsq_tag_o(shared_store_addr_tag), .rob_tag_o(selected_rob_tag), .base_value_o(selected_base), .base_select_o(selected_rs),
            .rob_query_o(selected_rob_query)''')
    return text


def core(text):
    return change(text,'.STORE_ALLOC_EARLY_ADDRESS(2),',
        '.STORE_PROBE_ROB_PREDECODE(1), .STORE_ALLOC_EARLY_ADDRESS(2),')


def main():
    parent=ROOT/'EL1_cache_response_match_before_select'
    verify_parent(parent)
    transforms={'rtl/backend/rv32_backend_joint.v':backend,
                'rtl/backend/rv32_store_address_select.v':selector,'rtl/cpu_core.v':core}
    # Check all source anchors before creating a new candidate directory.
    for name,transform in transforms.items():
        transform((parent/name).read_text(encoding='utf-8'))
    out=prepare('EM_shared_store_rob_query_predecode',parent,transforms,
        'Conditional EL1 child: saved store ROB slot predecode before original circular/RS probe choice; select full tag and bank masks, then retain normal ROB valid/full generation query. Existing row authority and ordinary issue unchanged. Source-only; do not include in running EL1.')
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    record_delta(out,parent,groups+['shared_store_saved_rob_query_predecode'])
    path=out/'candidate.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        new_declared_sequential_state_bits=0,declared_additional_state_bits_vs_parent=0,
        measured_parent_run=None,measured_reference_run='F:/CPU2026CourseRuns/architecture_EF_20261005',
        running_unmeasured_parent_run='F:/CPU2026CourseRuns/architecture_EL1_20261005',
        current_rob_query_width=16,current_store_packet_width_before=46,current_store_packet_width_after=62,
        original_scalar_priority_and_full_tag_preserved=True,
        inactive_query_scope='With no selected row, query masks are zero instead of decoding default slot0; selected_live changes only inside a shared-valid expression already qualified by selected=0. No external valid/data protocol changes.',
        timing_tradeoff='Move slot decode before late store selection. Wider selected packet and additional static tag loads can offset the removed late decode. New timing and area unknown.',
        adoption_condition='Only if completed EL1 measured paths still justify this suffix, finish combined source review and report before measurement. No individual test; never mutate the running frozen EL1.')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        adopted=False,tests_started=False,new_declared_state_bits=0)))


if __name__=='__main__':
    main()
