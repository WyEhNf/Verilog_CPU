"""Prepare two combined DM1 descendants using source edits only; never run EDA."""
import difflib
import hashlib
import json
from pathlib import Path

from prepare_staged_frequency_candidate import ROOT, change, prepare


ADD_SIMM12 = '''

// Addition of an RV32 load/store signed 12-bit displacement. The low twelve
// bits use three carry-select blocks. The upper word changes only by -1, 0,
// or +1; its increment/decrement prefixes are independent of the low carry.
// No state, and all arithmetic wraps modulo 2^32.
(* keep_hierarchy = 1 *)
module rv32_frequency_add_simm12 (
    input wire [31:0] base_i,
    input wire [11:0] immediate_i,
    output wire [31:0] sum_o
);
    wire [2:0] generate_stage [0:2];
    wire [2:0] propagate_stage [0:2];
    wire [3:0] sum_zero [0:2],sum_one [0:2];
    wire [19:0] ones_prefix [0:5],zeros_prefix [0:5];
    wire increment = generate_stage[2][2] && !immediate_i[11];
    wire decrement = !generate_stage[2][2] && immediate_i[11];
    wire [9:0] adjustment_views;
    rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(5)) adjustment_tree (
        .signal_i({decrement,increment}),.views_o(adjustment_views));
    assign ones_prefix[0]=base_i[31:12];
    assign zeros_prefix[0]=~base_i[31:12];
    genvar block_index,prefix_level,upper_bit;
    generate
        for(block_index=0;block_index<3;block_index=block_index+1) begin:g_low_block
            wire [4:0] block_sum={1'b0,base_i[block_index*4 +: 4]}+
                {1'b0,immediate_i[block_index*4 +: 4]};
            assign sum_zero[block_index]=block_sum[3:0];
            assign sum_one[block_index]=block_sum[3:0]+4'd1;
            assign generate_stage[0][block_index]=block_sum[4];
            assign propagate_stage[0][block_index]=
                &(base_i[block_index*4 +: 4] ^ immediate_i[block_index*4 +: 4]);
            if(block_index==0) begin:g_first
                assign sum_o[0 +: 4]=sum_zero[0];
            end else begin:g_select
                assign sum_o[block_index*4 +: 4]=generate_stage[2][block_index-1] ?
                    sum_one[block_index] : sum_zero[block_index];
            end
        end
        for(prefix_level=0;prefix_level<2;prefix_level=prefix_level+1) begin:g_low_prefix
            localparam integer DISTANCE=1<<prefix_level;
            for(block_index=0;block_index<3;block_index=block_index+1) begin:g_block
                if(block_index>=DISTANCE) begin:g_combine
                    assign generate_stage[prefix_level+1][block_index]=generate_stage[prefix_level][block_index] |
                        (propagate_stage[prefix_level][block_index] && generate_stage[prefix_level][block_index-DISTANCE]);
                    assign propagate_stage[prefix_level+1][block_index]=propagate_stage[prefix_level][block_index] &&
                        propagate_stage[prefix_level][block_index-DISTANCE];
                end else begin:g_copy
                    assign generate_stage[prefix_level+1][block_index]=generate_stage[prefix_level][block_index];
                    assign propagate_stage[prefix_level+1][block_index]=propagate_stage[prefix_level][block_index];
                end
            end
        end
        for(prefix_level=0;prefix_level<5;prefix_level=prefix_level+1) begin:g_upper_prefix
            localparam integer DISTANCE=1<<prefix_level;
            for(upper_bit=0;upper_bit<20;upper_bit=upper_bit+1) begin:g_bit
                if(upper_bit>=DISTANCE) begin:g_combine
                    assign ones_prefix[prefix_level+1][upper_bit]=ones_prefix[prefix_level][upper_bit] &&
                        ones_prefix[prefix_level][upper_bit-DISTANCE];
                    assign zeros_prefix[prefix_level+1][upper_bit]=zeros_prefix[prefix_level][upper_bit] &&
                        zeros_prefix[prefix_level][upper_bit-DISTANCE];
                end else begin:g_copy
                    assign ones_prefix[prefix_level+1][upper_bit]=ones_prefix[prefix_level][upper_bit];
                    assign zeros_prefix[prefix_level+1][upper_bit]=zeros_prefix[prefix_level][upper_bit];
                end
            end
        end
        for(upper_bit=0;upper_bit<20;upper_bit=upper_bit+1) begin:g_upper_sum
            localparam integer DOMAIN=upper_bit/4;
            wire increment_bit=adjustment_views[DOMAIN*2];
            wire decrement_bit=adjustment_views[DOMAIN*2+1];
            if(upper_bit==0) begin:g_first
                assign sum_o[12]=base_i[12] ^ (increment_bit || decrement_bit);
            end else begin:g_later
                assign sum_o[12+upper_bit]=base_i[12+upper_bit] ^
                    ((increment_bit && ones_prefix[5][upper_bit-1]) ||
                     (decrement_bit && zeros_prefix[5][upper_bit-1]));
            end
        end
    endgenerate
endmodule
'''


def store_backend(t):
    t=change(t, '        `RV32IM_ROB_GENERATION_WIDTH\n) (', '''        `RV32IM_ROB_GENERATION_WIDTH,
    // Default preserves unrestricted standalone trace immediates. The CPU
    // enables this for its decoder's signed twelve-bit store displacement.
    parameter integer STORE_ALLOC_IMM12 = 0
) (''')
    return change(t, '''            assign lsq_alloc_addr[io_lane*32 +: 32] =
                rs_src1_value[io_lane*32 +: 32] + d_imm[io_lane*32 +: 32];''', '''            if(STORE_ALLOC_IMM12!=0) begin:g_store_alloc_simm12
                // Only stores with alloc_addr_valid observe this payload.
                // Loads leave addr_ready clear until their ordinary AGU update.
                rv32_frequency_add_simm12 address_adder (
                    .base_i(rs_src1_value[io_lane*32 +: 32]),
                    .immediate_i(d_imm[io_lane*32 +: 12]),
                    .sum_o(lsq_alloc_addr[io_lane*32 +: 32]));
            end else begin:g_store_alloc_generic
                assign lsq_alloc_addr[io_lane*32 +: 32] =
                    rs_src1_value[io_lane*32 +: 32] + d_imm[io_lane*32 +: 32];
            end''')


def store_core(t):
    return change(t, '    rv32_backend_joint #(.RS_PHYSICAL_WAKEUP(1),',
                  '    rv32_backend_joint #(.STORE_ALLOC_IMM12(1), .RS_PHYSICAL_WAKEUP(1),')


PRECOMPARE = '''
    // Equality can run alongside full-tag authority and arbitration. Route
    // its single-bit result with the EXACT same one-hot source grant as the
    // physical destination payload, instead of comparing after that payload mux.
    // Query-dependent bits are never retained in a completion/hold packet.
    genvar match_source,match_read,match_lane,match_node;
    generate if(BYPASS==2 && READ_MATCH_PORTS>0) begin:g_direct_read_match
        wire [READ_MATCH_COUNT-1:0] source_match [0:SOURCES-1];
        wire [CDB_WIDTH*SOURCES*READ_MATCH_COUNT-1:0] match_grant;
        for(match_source=0;match_source<SOURCES;match_source=match_source+1) begin:g_source
            for(match_read=0;match_read<READ_MATCH_COUNT;match_read=match_read+1) begin:g_query
                assign source_match[match_source][match_read]=
                    producer_phys_rd_i[match_source*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==
                    read_match_phys_i[match_read*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
            end
            for(match_lane=0;match_lane<CDB_WIDTH;match_lane=match_lane+1) begin:g_grant
                // One bounded grant leaf controls at most sixteen match bits.
                localparam integer WORDS=(READ_MATCH_COUNT+15)/16;
                wire [WORDS-1:0] grant_views;
                genvar match_word;
                rv32_frequency_control_tree #(.LEAVES(WORDS)) grant_tree (
                    .signal_i(selected_mask[match_lane][match_source] && !reset_i && !flush_i),
                    .views_o(grant_views));
                for(match_word=0;match_word<WORDS;match_word=match_word+1) begin:g_word
                    localparam integer LOW=match_word*16;
                    localparam integer BITS=(READ_MATCH_COUNT-LOW>=16)?16:READ_MATCH_COUNT-LOW;
                    assign match_grant[(match_lane*SOURCES+match_source)*READ_MATCH_COUNT+LOW +: BITS]={BITS{grant_views[match_word]}};
                end
            end
        end
        for(match_read=0;match_read<READ_MATCH_COUNT;match_read=match_read+1) begin:g_read
            for(match_lane=0;match_lane<BE_WIDTH;match_lane=match_lane+1) begin:g_lane
                if(match_lane<CDB_WIDTH) begin:g_present
                    wire match_tree [1:2*RANK_LEAVES-1];
                    for(match_source=0;match_source<RANK_LEAVES;match_source=match_source+1) begin:g_leaf
                        if(match_source<SOURCES) begin:g_source
                            assign match_tree[RANK_LEAVES+match_source]=
                                match_grant[(match_lane*SOURCES+match_source)*READ_MATCH_COUNT+match_read] && source_match[match_source][match_read];
                        end else begin:g_padding
                            assign match_tree[RANK_LEAVES+match_source]=1'b0;
                        end
                    end
                    for(match_node=1;match_node<RANK_LEAVES;match_node=match_node+1) begin:g_reduce
                        assign match_tree[match_node]=match_tree[2*match_node] || match_tree[2*match_node+1];
                    end
                    assign prf_read_match_o[match_read*BE_WIDTH+match_lane]=match_tree[1];
                end else begin:g_unused_lane
                    assign prf_read_match_o[match_read*BE_WIDTH+match_lane]=1'b0;
                end
            end
        end
    end else begin:g_no_direct_read_match
        assign prf_read_match_o=0;
    end endgenerate

'''


def completion(t):
    t=change(t, '''    parameter integer COUNT_WIDTH = (FIFO_DEPTH <= 1) ? 1 : $clog2(FIFO_DEPTH + 1)
) (''', '''    parameter integer COUNT_WIDTH = (FIFO_DEPTH <= 1) ? 1 : $clog2(FIFO_DEPTH + 1),
    parameter integer READ_MATCH_PORTS = 0,
    parameter integer READ_MATCH_COUNT = (READ_MATCH_PORTS>0)?READ_MATCH_PORTS:1
) (''')
    t=change(t, '''    output wire [COUNT_WIDTH-1:0]       occupancy_o
);''', '''    output wire [COUNT_WIDTH-1:0]       occupancy_o,
    input wire [READ_MATCH_COUNT*PHYS_ADDR_WIDTH-1:0] read_match_phys_i,
    output wire [READ_MATCH_COUNT*BE_WIDTH-1:0] prf_read_match_o
);''')
    return change(t, '    localparam integer DIRECT_META_WIDTH=TAG_WIDTH+PHYS_ADDR_WIDTH+7;',
                  PRECOMPARE+'    localparam integer DIRECT_META_WIDTH=TAG_WIDTH+PHYS_ADDR_WIDTH+7;')


def prf(t):
    t=change(t, '    parameter integer PHYS_ADDR_WIDTH = (PHYS_REGS <= 1) ? 1 : $clog2(PHYS_REGS)\n) (',
             '''    parameter integer PHYS_ADDR_WIDTH = (PHYS_REGS <= 1) ? 1 : $clog2(PHYS_REGS),
    parameter integer EXTERNAL_BYPASS_MATCH = 0
) (''')
    t=change(t, '    input  wire [BE_WIDTH-1:0]           write_valid_i\n);',
             '''    input  wire [BE_WIDTH-1:0]           write_valid_i,
    // Read-major, then write lane. Used only by the parallel read path.
    input wire [2*BE_WIDTH*BE_WIDTH-1:0] bypass_match_i
);''')
    return change(t, '''                assign bypass_match[wl]=legal && write_valid_i[wl] &&
                    write_phys_i[wl*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==address;''',
             '''                // Actual write-valid, P0/range checks and highest-lane
                // priority remain local even with pre-arbitration equality.
                assign bypass_match[wl]=legal && write_valid_i[wl] &&
                    ((EXTERNAL_BYPASS_MATCH!=0) ? bypass_match_i[rp*BE_WIDTH+wl] :
                     (write_phys_i[wl*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==address));''')


def precompare_backend(t):
    t=change(t, '    parameter integer STORE_ALLOC_IMM12 = 0\n) (', '''    parameter integer STORE_ALLOC_IMM12 = 0,
    parameter integer PRF_BYPASS_PRECOMPARE = 0
) (''')
    t=change(t, '    wire [BE_WIDTH-1:0] completion_prf_write_valid;', '''    wire [BE_WIDTH-1:0] completion_prf_write_valid;
    localparam integer PRF_MATCH_ENABLED=(PRF_BYPASS_PRECOMPARE!=0) &&
        (COMPLETION_BYPASS==2) && (PRF_READ_MUX_IMPL!=0);
    localparam integer PRF_MATCH_PORTS=PRF_MATCH_ENABLED ? 2*BE_WIDTH : 0;
    localparam integer PRF_MATCH_COUNT=PRF_MATCH_ENABLED ? 2*BE_WIDTH : 1;
    wire [PRF_MATCH_COUNT*BE_WIDTH-1:0] completion_prf_read_match;
    wire [2*BE_WIDTH*BE_WIDTH-1:0] prf_bypass_match;
    // A redirecting JAL/JALR overrides the final active PRF write lane.
    // Override its equality as well as its value/address, with the same priority.
    genvar bypass_read,bypass_lane;
    generate if(PRF_MATCH_ENABLED!=0) begin:g_prf_early_match
        for(bypass_read=0;bypass_read<2*BE_WIDTH;bypass_read=bypass_read+1) begin:g_read
            for(bypass_lane=0;bypass_lane<BE_WIDTH;bypass_lane=bypass_lane+1) begin:g_lane
                if(bypass_lane==CDB_WIDTH-1) begin:g_branch_link
                    assign prf_bypass_match[bypass_read*BE_WIDTH+bypass_lane]=
                        (branch_pending && branch_pending_rd_we) ?
                        (branch_pending_phys==prf_read_phys[bypass_read*PAW +: PAW]) :
                        completion_prf_read_match[bypass_read*BE_WIDTH+bypass_lane];
                end else begin:g_completion
                    assign prf_bypass_match[bypass_read*BE_WIDTH+bypass_lane]=
                        completion_prf_read_match[bypass_read*BE_WIDTH+bypass_lane];
                end
            end
        end
    end else begin:g_prf_late_match
        assign prf_bypass_match=0;
    end endgenerate''')
    t=change(t, ' .READ_MUX_IMPL(PRF_READ_MUX_IMPL), .LOCAL_VALUE_ROWS(1)) prf (',
             ' .READ_MUX_IMPL(PRF_READ_MUX_IMPL), .LOCAL_VALUE_ROWS(1), .EXTERNAL_BYPASS_MATCH(PRF_MATCH_ENABLED)) prf (')
    t=change(t, ' .write_valid_i(prf_write_valid)\n    );',
             ' .write_valid_i(prf_write_valid), .bypass_match_i(prf_bypass_match)\n    );')
    t=change(t, ' .PHYS_ADDR_WIDTH(PAW), .BYPASS(COMPLETION_BYPASS)) completion (',
             ' .PHYS_ADDR_WIDTH(PAW), .BYPASS(COMPLETION_BYPASS), .READ_MATCH_PORTS(PRF_MATCH_PORTS)) completion (')
    t=change(t, '    rv32_completion_network #(', '''    wire [PRF_MATCH_COUNT*PAW-1:0] completion_read_match_queries;
    generate if(PRF_MATCH_ENABLED!=0) begin:g_completion_read_match_queries
        assign completion_read_match_queries=prf_read_phys;
    end else begin:g_no_completion_read_match_queries
        assign completion_read_match_queries=0;
    end endgenerate

    rv32_completion_network #(''')
    return change(t, '''        .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .kill_valid_i(recovery_domains[6]),''',
             '''        .read_match_phys_i(completion_read_match_queries), .prf_read_match_o(completion_prf_read_match),
        .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .kill_valid_i(recovery_domains[6]),''')


def precompare_core(t):
    return change(t, '    rv32_backend_joint #(.STORE_ALLOC_IMM12(1),',
                  '    rv32_backend_joint #(.PRF_BYPASS_PRECOMPARE(1), .STORE_ALLOC_IMM12(1),')


def verify_parent(parent):
    manifest=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))
    for relative,expected in manifest['source_sha256'].items():
        actual=hashlib.sha256((parent/relative).read_bytes()).hexdigest()
        if actual!=expected:
            raise ValueError(f'Parent source changed: {parent / relative}')


def record_delta(out,parent,groups):
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    previous=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))
    changed=[n for n,sha in manifest['source_sha256'].items() if sha!=previous['source_sha256'][n]]
    patch=''.join(''.join(difflib.unified_diff((parent/n).read_text(encoding='utf-8').splitlines(keepends=True),
                 (out/n).read_text(encoding='utf-8').splitlines(keepends=True),
                 fromfile=parent.name+'/'+n,tofile=out.name+'/'+n)) for n in changed)
    (out/'changes_vs_parent.patch').write_text(patch,encoding='utf-8')
    manifest.update(changed_files_vs_parent=changed,
                    actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    measured_parent_run='F:/CPU2026CourseRuns/architecture_DM1_20261005',
                    implemented_groups=groups,added_declared_state_bits_vs_DM1=0,
                    behavior='Combinational restructuring; no new pipeline edge or handshake changes',
                    adopted=False,synthesis_started=False,timing_started=False,tests_started=False)
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    dm1=ROOT/'DM1_lsq_report_bound_widths'
    verify_parent(dm1)
    dp=prepare('DP_store_alloc_simm12',dm1,
        {'rtl/backend/rv32_backend_joint.v':store_backend,
         'rtl/cpu_core.v':store_core,
         'rtl/common/rv32_asap7_fanout.v':lambda t:t+ADD_SIMM12},
        'Specialize allocation-only store effective-address arithmetic to the decoder signed-12-bit contract; retain generic standalone default, full tags, ordinary AGU, and original cycles.')
    record_delta(dp,dm1,['allocation_store_signed_12bit_adder'])
    verify_parent(dp)
    dq=prepare('DQ_prf_compare_before_completion',dp,
        {'rtl/backend/rv32_backend_joint.v':precompare_backend,
         'rtl/backend/rv32_completion_network.v':completion,
         'rtl/rv32_physical_register_file.v':prf,
         'rtl/cpu_core.v':precompare_core},
        'Combine DP with pre-arbitration physical destination/read-query equality, selected by unchanged completion grants; preserve full authority, actual write-valid, branch-link override and PRF highest-lane priority. No added state or cycles.')
    record_delta(dq,dp,['allocation_store_signed_12bit_adder','prf_compare_before_completion'])
    print(json.dumps({'combined_candidate':str(dq),
        'manifest_sha256':hashlib.sha256((dq/'candidate.json').read_bytes()).hexdigest(),
        'tests_started':False,'adopted':False},ensure_ascii=False))
