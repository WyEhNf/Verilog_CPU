"""Fuse completion/PRF bypass data routing; source edits only, never run EDA."""
import hashlib
import json
from pathlib import Path

from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


DIRECT_VALUE = '''
        // Select the last matching ACTUAL PRF write lane, then route its
        // original producer value directly. This factors two serial payload
        // muxes into one, while preserving PRF write-valid and lane priority.
        if(READ_DIRECT_VALUE!=0) begin:g_direct_values
            genvar value_read,value_lane,value_source,value_node;
            for(value_read=0;value_read<READ_MATCH_COUNT;value_read=value_read+1) begin:g_read
                wire [BE_WIDTH-1:0] lane_hit,lane_grant;
                wire [SOURCES-1:0] source_grant;
                wire [31:0] value_tree [1:2*RANK_LEAVES-1];
                for(value_lane=0;value_lane<BE_WIDTH;value_lane=value_lane+1) begin:g_lane
                    if(value_lane<CDB_WIDTH) begin:g_present
                        // Branch-link publication overrides the last active
                        // lane; even a nonmatching link must hide its normal
                        // completion's physical destination and value.
                        assign lane_hit[value_lane]=prf_read_match_o[value_read*BE_WIDTH+value_lane] &&
                            bypass_write_valid_i[value_lane] &&
                            ((value_lane==CDB_WIDTH-1) ? !bypass_last_override_i : 1'b1);
                    end else begin:g_unused
                        assign lane_hit[value_lane]=1'b0;
                    end
                    if(value_lane==BE_WIDTH-1) begin:g_last
                        assign lane_grant[value_lane]=lane_hit[value_lane];
                    end else begin:g_priority
                        assign lane_grant[value_lane]=lane_hit[value_lane] && !(|lane_hit[BE_WIDTH-1:value_lane+1]);
                    end
                end
                assign direct_read_valid_o[value_read]=|lane_hit;
                for(value_source=0;value_source<RANK_LEAVES;value_source=value_source+1) begin:g_source
                    if(value_source<SOURCES) begin:g_present
                        wire [CDB_WIDTH-1:0] chosen_lanes;
                        wire [1:0] data_views;
                        for(value_lane=0;value_lane<CDB_WIDTH;value_lane=value_lane+1) begin:g_owner
                            assign chosen_lanes[value_lane]=lane_grant[value_lane] && selected_mask[value_lane][value_source];
                        end
                        assign source_grant[value_source]=|chosen_lanes;
                        rv32_frequency_control_tree #(.LEAVES(2)) data_tree (
                            .signal_i(source_grant[value_source]),.views_o(data_views));
                        assign value_tree[RANK_LEAVES+value_source]={
                            {16{data_views[1]}} & producer_value_i[value_source*32+16 +: 16],
                            {16{data_views[0]}} & producer_value_i[value_source*32 +: 16]};
                    end else begin:g_padding
                        assign value_tree[RANK_LEAVES+value_source]=0;
                    end
                end
                for(value_node=1;value_node<RANK_LEAVES;value_node=value_node+1) begin:g_reduce
                    assign value_tree[value_node]=value_tree[2*value_node] | value_tree[2*value_node+1];
                end
                assign direct_read_value_o[value_read*32 +: 32]=value_tree[1];
            end
        end else begin:g_no_direct_values
            assign direct_read_valid_o=0;
            assign direct_read_value_o=0;
        end
'''


def completion(t):
    t=change(t, '    parameter integer LATE_ELIGIBILITY_SOURCE = -1\n) (', '''    parameter integer LATE_ELIGIBILITY_SOURCE = -1,
    parameter integer READ_DIRECT_VALUE = 0
) (''')
    t=change(t, '    output wire [READ_MATCH_COUNT*BE_WIDTH-1:0] prf_read_match_o\n);', '''    output wire [READ_MATCH_COUNT*BE_WIDTH-1:0] prf_read_match_o,
    input wire [BE_WIDTH-1:0] bypass_write_valid_i,
    input wire bypass_last_override_i,
    output wire [READ_MATCH_COUNT-1:0] direct_read_valid_o,
    output wire [READ_MATCH_COUNT*32-1:0] direct_read_value_o
);''')
    return change(t, '''    end else begin:g_no_direct_read_match
        assign prf_read_match_o=0;
    end endgenerate''', DIRECT_VALUE+'''    end else begin:g_no_direct_read_match
        assign prf_read_match_o=0;
        assign direct_read_valid_o=0;
        assign direct_read_value_o=0;
    end endgenerate''')


def prf(t):
    t=change(t, '    parameter integer EXTERNAL_BYPASS_MATCH = 0\n) (', '''    parameter integer EXTERNAL_BYPASS_MATCH = 0,
    parameter integer EXTERNAL_BYPASS_VALUE = 0
) (''')
    t=change(t, '    input wire [2*BE_WIDTH*BE_WIDTH-1:0] bypass_match_i\n);', '''    input wire [2*BE_WIDTH*BE_WIDTH-1:0] bypass_match_i,
    input wire [2*BE_WIDTH-1:0] bypass_valid_i,
    input wire [2*BE_WIDTH*32-1:0] bypass_value_i
);''')
    start=t.index('            for(wl=0;wl<BE_WIDTH;wl=wl+1) begin:g_bypass')
    end=t.index('            rv32_frequency_control_tree #(.LEAVES(2)) bypass_choice_tree',start)
    original=t[start:end]
    return t[:start]+'''            if(EXTERNAL_BYPASS_VALUE!=0) begin:g_fused_bypass
                // The external router still gates every lane with the actual
                // write_valid, full-qualified completion grant and original
                // highest-lane/branch override priority. P0/range stay local.
                assign bypass_write=legal && bypass_valid_i[rp];
                assign bypass_value=bypass_value_i[rp*32 +: 32];
            end else begin:g_local_bypass
'''+original+'''            end
'''+t[end:]


def backend(t):
    t=change(t, '    parameter integer COMPLETION_LATE_LOAD_SELECT = 0\n) (', '''    parameter integer COMPLETION_LATE_LOAD_SELECT = 0,
    parameter integer PRF_DIRECT_OPERAND_BYPASS = 0
) (''')
    t=change(t, '    localparam integer PRF_MATCH_PORTS=PRF_MATCH_ENABLED ? 2*BE_WIDTH : 0;', '''    localparam integer PRF_VALUE_BYPASS_ENABLED=PRF_MATCH_ENABLED && (PRF_DIRECT_OPERAND_BYPASS!=0);
    localparam integer PRF_MATCH_PORTS=PRF_MATCH_ENABLED ? 2*BE_WIDTH : 0;''')
    t=change(t, '    wire [2*BE_WIDTH*BE_WIDTH-1:0] prf_bypass_match;', '''    wire [2*BE_WIDTH*BE_WIDTH-1:0] prf_bypass_match;
    wire [PRF_MATCH_COUNT-1:0] completion_direct_read_valid;
    wire [PRF_MATCH_COUNT*32-1:0] completion_direct_read_value;
    wire [2*BE_WIDTH-1:0] prf_direct_read_valid;
    wire [2*BE_WIDTH*32-1:0] prf_direct_read_value;
    genvar direct_read_port,direct_read_word;
    generate if(PRF_VALUE_BYPASS_ENABLED!=0) begin:g_prf_fused_value
        for(direct_read_port=0;direct_read_port<2*BE_WIDTH;direct_read_port=direct_read_port+1) begin:g_read
            wire link_match=(branch_pending && branch_pending_rd_we) &&
                branch_pending_phys==prf_read_phys[direct_read_port*PAW +: PAW];
            wire [1:0] link_value_views;
            rv32_frequency_control_tree #(.LEAVES(2)) link_tree (
                .signal_i(link_match),.views_o(link_value_views));
            assign prf_direct_read_valid[direct_read_port]=link_match || completion_direct_read_valid[direct_read_port];
            for(direct_read_word=0;direct_read_word<2;direct_read_word=direct_read_word+1) begin:g_word
                assign prf_direct_read_value[direct_read_port*32+direct_read_word*16 +: 16]=link_value_views[direct_read_word] ?
                    branch_pending_value[direct_read_word*16 +: 16] :
                    completion_direct_read_value[direct_read_port*32+direct_read_word*16 +: 16];
            end
        end
    end else begin:g_prf_local_value
        assign prf_direct_read_valid=0;
        assign prf_direct_read_value=0;
    end endgenerate''')
    t=change(t, ' .EXTERNAL_BYPASS_MATCH(PRF_MATCH_ENABLED)) prf (',
             ' .EXTERNAL_BYPASS_MATCH(PRF_MATCH_ENABLED), .EXTERNAL_BYPASS_VALUE(PRF_VALUE_BYPASS_ENABLED)) prf (')
    t=change(t, ' .bypass_match_i(prf_bypass_match)\n    );',
             ' .bypass_match_i(prf_bypass_match), .bypass_valid_i(prf_direct_read_valid), .bypass_value_i(prf_direct_read_value)\n    );')
    t=change(t, ' .LATE_ELIGIBILITY_SOURCE(COMPLETION_LATE_LOAD_SELECT ? LSQ_SOURCE : -1)) completion (',
             ' .LATE_ELIGIBILITY_SOURCE(COMPLETION_LATE_LOAD_SELECT ? LSQ_SOURCE : -1), .READ_DIRECT_VALUE(PRF_VALUE_BYPASS_ENABLED)) completion (')
    return change(t, '''        .read_match_phys_i(completion_read_match_queries), .prf_read_match_o(completion_prf_read_match),''', '''        .read_match_phys_i(completion_read_match_queries), .prf_read_match_o(completion_prf_read_match),
        .bypass_write_valid_i(prf_write_valid), .bypass_last_override_i(branch_pending && branch_pending_rd_we),
        .direct_read_valid_o(completion_direct_read_valid), .direct_read_value_o(completion_direct_read_value),''')


def core(t):
    return change(t, '    rv32_backend_joint #(.COMPLETION_LATE_LOAD_SELECT(1),',
                  '    rv32_backend_joint #(.PRF_DIRECT_OPERAND_BYPASS(1), .COMPLETION_LATE_LOAD_SELECT(1),')


if __name__=='__main__':
    parent=ROOT/'DR_late_lsq_completion_grants'
    verify_parent(parent)
    out=prepare('DS_direct_prf_operand_bypass',parent,
        {'rtl/backend/rv32_completion_network.v':completion,
         'rtl/backend/rv32_backend_joint.v':backend,
         'rtl/rv32_physical_register_file.v':prf,
         'rtl/cpu_core.v':core},
        'Combine DP/DQ/DR with a fused direct producer-to-read operand bypass. Qualify each completion lane with actual PRF write_valid, suppress the branch-link-overridden lane, preserve highest matching-lane priority, then route original producer data once. Keep normal PRF state writes and no new clock edge.')
    record_delta(out,parent,['allocation_store_signed_12bit_adder','prf_compare_before_completion',
                            'late_lsq_completion_grants','fused_producer_to_prf_operand_bypass'])
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    manifest['actual_preparation_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest['source_review']='Manual source and priority/ownership algebra only; no HDL compiler, lint, simulation, synthesis, STA or formal run.'
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'candidate':str(out),
        'manifest_sha256':hashlib.sha256((out/'candidate.json').read_bytes()).hexdigest(),
        'tests_started':False,'adopted':False},ensure_ascii=False))
