"""Shannon-decompose the DM1 late load eligibility; source preparation only."""
import hashlib
import json
from pathlib import Path

from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


NETWORK = '''    localparam integer RANK_WIDTH=(SOURCES<=1)?1:$clog2(SOURCES+1);
    localparam integer RANK_LEAVES=1<<$clog2(SOURCES);
    wire [SOURCES-1:0] selected_mask [0:CDB_WIDTH-1];
    wire [CDB_WIDTH*SOURCES-1:0] selected_flat;
    wire [CDB_WIDTH*SOURCE_WIDTH-1:0] held_sources_flat;
    wire [CDB_WIDTH*TAG_WIDTH-1:0] held_tags_flat;
    genvar rank_source,rank_lane,late_word;
    generate
        for(rank_source=0;rank_source<SOURCES;rank_source=rank_source+1) begin:g_direct_eligibility
            // Full normal ROB authority remains on this FINAL decision.
            assign direct_eligible[rank_source]=producer_valid_i[rank_source] &&
                producer_target_live_i[rank_source] && producer_tag_i[rank_source*TAG_WIDTH] &&
                (!live_tag_valid_i || producer_tag_i[rank_source*TAG_WIDTH +: TAG_WIDTH]==live_tag_i);
        end
        for(rank_lane=0;rank_lane<CDB_WIDTH;rank_lane=rank_lane+1) begin:g_rank_ports
            assign held_sources_flat[rank_lane*SOURCE_WIDTH +: SOURCE_WIDTH]=direct_hold_source[rank_lane];
            assign held_tags_flat[rank_lane*TAG_WIDTH +: TAG_WIDTH]=direct_hold_tag[rank_lane];
            assign selected_mask[rank_lane]=selected_flat[rank_lane*SOURCES +: SOURCES];
        end
        if(BYPASS==2 && LATE_ELIGIBILITY_SOURCE>=0 && LATE_ELIGIBILITY_SOURCE<SOURCES) begin:g_late_eligibility
            wire [SOURCES-1:0] eligible_without,eligible_with;
            wire [CDB_WIDTH*SOURCES-1:0] selected_without,selected_with;
            localparam integer SELECT_WORDS=(CDB_WIDTH*SOURCES+15)/16;
            wire [SELECT_WORDS-1:0] late_views;
            for(rank_source=0;rank_source<SOURCES;rank_source=rank_source+1) begin:g_hypothesis
                if(rank_source==LATE_ELIGIBILITY_SOURCE) begin:g_late
                    assign eligible_without[rank_source]=1'b0;
                    assign eligible_with[rank_source]=1'b1;
                end else begin:g_other
                    assign eligible_without[rank_source]=direct_eligible[rank_source];
                    assign eligible_with[rank_source]=direct_eligible[rank_source];
                end
            end
            // Both hypotheses apply the original round-robin, held full-tag
            // match, rank and free-lane rules. No source can publish until the
            // original late eligibility chooses its matching hypothesis.
            rv32_frequency_completion_grants #(.SOURCES(SOURCES),.CDB_WIDTH(CDB_WIDTH),.TAG_WIDTH(TAG_WIDTH)) absent (
                .cursor_i(direct_rr_reg),.eligible_i(eligible_without),
                .held_valid_i(direct_hold_valid),.held_sources_i(held_sources_flat),
                .held_tags_i(held_tags_flat),.producer_tag_i(producer_tag_i),.selected_o(selected_without));
            rv32_frequency_completion_grants #(.SOURCES(SOURCES),.CDB_WIDTH(CDB_WIDTH),.TAG_WIDTH(TAG_WIDTH)) present (
                .cursor_i(direct_rr_reg),.eligible_i(eligible_with),
                .held_valid_i(direct_hold_valid),.held_sources_i(held_sources_flat),
                .held_tags_i(held_tags_flat),.producer_tag_i(producer_tag_i),.selected_o(selected_with));
            rv32_frequency_control_tree #(.LEAVES(SELECT_WORDS)) late_tree (
                .signal_i(direct_eligible[LATE_ELIGIBILITY_SOURCE]),.views_o(late_views));
            for(late_word=0;late_word<SELECT_WORDS;late_word=late_word+1) begin:g_word
                localparam integer LOW=late_word*16;
                localparam integer BITS=(CDB_WIDTH*SOURCES-LOW>=16)?16:CDB_WIDTH*SOURCES-LOW;
                assign selected_flat[LOW +: BITS]=late_views[late_word] ?
                    selected_with[LOW +: BITS] : selected_without[LOW +: BITS];
            end
        end else begin:g_original_eligibility
            rv32_frequency_completion_grants #(.SOURCES(SOURCES),.CDB_WIDTH(CDB_WIDTH),.TAG_WIDTH(TAG_WIDTH)) original (
                .cursor_i(direct_rr_reg),.eligible_i(direct_eligible),
                .held_valid_i(direct_hold_valid),.held_sources_i(held_sources_flat),
                .held_tags_i(held_tags_flat),.producer_tag_i(producer_tag_i),.selected_o(selected_flat));
        end
    endgenerate
'''


def original_grant_module(t):
    """Extract the original equations without changing its ranking predicates."""
    start=t.index('    wire [SOURCES-1:0] held_source_mask [0:CDB_WIDTH-1];')
    end=t.index('    always @* begin\n        direct_selected_valid=0;',start)
    body=t[start:end]
    body=change(body, '''            assign direct_eligible[rank_source]=producer_valid_i[rank_source] &&
                producer_target_live_i[rank_source] && producer_tag_i[rank_source*TAG_WIDTH] &&
                (!live_tag_valid_i || producer_tag_i[rank_source*TAG_WIDTH +: TAG_WIDTH]==live_tag_i);
''', '')
    return '''

// Original completion ranking as a combinational function of eligibility,
// cursor and held source/full-tag state. Used by both late-load hypotheses.
(* keep_hierarchy = 1 *)
module rv32_frequency_completion_grants #(
    parameter integer SOURCES=6,CDB_WIDTH=3,TAG_WIDTH=17,
    parameter integer SOURCE_WIDTH=(SOURCES<=1)?1:$clog2(SOURCES),
    parameter integer RANK_WIDTH=(SOURCES<=1)?1:$clog2(SOURCES+1),
    parameter integer RANK_LEAVES=1<<$clog2(SOURCES)
) (
    input wire [SOURCE_WIDTH-1:0] cursor_i,
    input wire [SOURCES-1:0] eligible_i,
    input wire [CDB_WIDTH-1:0] held_valid_i,
    input wire [CDB_WIDTH*SOURCE_WIDTH-1:0] held_sources_i,
    input wire [CDB_WIDTH*TAG_WIDTH-1:0] held_tags_i,
    input wire [SOURCES*TAG_WIDTH-1:0] producer_tag_i,
    output wire [CDB_WIDTH*SOURCES-1:0] selected_o
);
    wire [SOURCE_WIDTH-1:0] direct_rr_reg=cursor_i;
    wire [SOURCES-1:0] direct_eligible=eligible_i;
    wire [CDB_WIDTH-1:0] direct_hold_valid=held_valid_i;
    wire [SOURCE_WIDTH-1:0] direct_hold_source [0:CDB_WIDTH-1];
    wire [TAG_WIDTH-1:0] direct_hold_tag [0:CDB_WIDTH-1];
    wire [SOURCES-1:0] direct_used;
    genvar held_lane;
    generate for(held_lane=0;held_lane<CDB_WIDTH;held_lane=held_lane+1) begin:g_ports
        assign direct_hold_source[held_lane]=held_sources_i[held_lane*SOURCE_WIDTH +: SOURCE_WIDTH];
        assign direct_hold_tag[held_lane]=held_tags_i[held_lane*TAG_WIDTH +: TAG_WIDTH];
        assign selected_o[held_lane*SOURCES +: SOURCES]=selected_mask[held_lane];
    end endgenerate
'''+body+'endmodule\n'


def completion(t):
    t=change(t, '    parameter integer READ_MATCH_COUNT = (READ_MATCH_PORTS>0)?READ_MATCH_PORTS:1\n) (', '''    parameter integer READ_MATCH_COUNT = (READ_MATCH_PORTS>0)?READ_MATCH_PORTS:1,
    parameter integer LATE_ELIGIBILITY_SOURCE = -1
) (''')
    start=t.index('    localparam integer RANK_WIDTH=(SOURCES<=1)?1:$clog2(SOURCES+1);')
    end=t.index('    always @* begin\n        direct_selected_valid=0;',start)
    return t[:start]+NETWORK+t[end:]


def backend(t):
    t=change(t, '    parameter integer PRF_BYPASS_PRECOMPARE = 0\n) (', '''    parameter integer PRF_BYPASS_PRECOMPARE = 0,
    parameter integer COMPLETION_LATE_LOAD_SELECT = 0
) (''')
    return change(t, ' .READ_MATCH_PORTS(PRF_MATCH_PORTS)) completion (',
                 ' .READ_MATCH_PORTS(PRF_MATCH_PORTS), .LATE_ELIGIBILITY_SOURCE(COMPLETION_LATE_LOAD_SELECT ? LSQ_SOURCE : -1)) completion (')


def core(t):
    return change(t, '    rv32_backend_joint #(.PRF_BYPASS_PRECOMPARE(1),',
                  '    rv32_backend_joint #(.COMPLETION_LATE_LOAD_SELECT(1), .PRF_BYPASS_PRECOMPARE(1),')


if __name__=='__main__':
    parent=ROOT/'DQ_prf_compare_before_completion'
    verify_parent(parent)
    original=(parent/'rtl/backend/rv32_completion_network.v').read_text(encoding='utf-8')
    grant_module=original_grant_module(original)
    out=prepare('DR_late_lsq_completion_grants',parent,
        {'rtl/backend/rv32_completion_network.v':completion,
         'rtl/backend/rv32_backend_joint.v':backend,
         'rtl/cpu_core.v':core,
         'rtl/common/rv32_asap7_fanout.v':lambda t:t+grant_module},
        'Combine DP/DQ with exact absent/present LSQ-eligibility arbitration hypotheses. Late full-ROB-qualified eligibility selects the original grants via one mux, retaining round-robin/held-tag state, output payloads, backpressure and original clock edges.')
    record_delta(out,parent,['allocation_store_signed_12bit_adder','prf_compare_before_completion','late_lsq_completion_grants'])
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    # record_delta belongs to the other helper; retain both actual caller IDs.
    manifest['actual_preparation_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest['grant_function_origin_sha256']=hashlib.sha256((parent/'rtl/backend/rv32_completion_network.v').read_bytes()).hexdigest()
    manifest['source_review']='Manual algebra and source equations only; no HDL compiler, lint, simulation, synthesis, STA or formal run.'
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'candidate':str(out),
        'manifest_sha256':hashlib.sha256((out/'candidate.json').read_bytes()).hexdigest(),
        'tests_started':False,'adopted':False},ensure_ascii=False))
