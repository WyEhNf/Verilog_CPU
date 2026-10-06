"""Move carry-dependent arithmetic before the final selector; no HDL/EDA."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def alu(source):
    source=change(source,'        reg [4:0] chunk_sum;',
        '''        reg [4:0] chunk_sum;
        reg [31:0] sum_zero,sum_one;''')
    source=change(source,'                g0[chunk] = chunk_sum[4];',
        '''                // Both nibble results precede the group carry tree.
                // A late carry selects four bits; it does not start an adder.
                sum_zero[chunk*4 +: 4] = chunk_sum[3:0];
                sum_one[chunk*4 +: 4] = chunk_sum[3:0] + 4'd1;
                g0[chunk] = chunk_sum[4];''')
    source=change(source,'''                fast_add_carry[chunk*4 +: 4] = lhs[chunk*4 +: 4] +
                    adjusted_rhs[chunk*4 +: 4] + carry[chunk];''',
        '''                fast_add_carry[chunk*4 +: 4] = carry[chunk] ?
                    sum_one[chunk*4 +: 4] : sum_zero[chunk*4 +: 4];''')
    return source


def common(source):
    if 'module rv32_frequency_add64_select' in source:
        raise ValueError('Preserve existing add64 module')
    return source+'''

// Sixteen parallel four-bit adders generate block G/P and both sum choices.
// A four-level prefix tree resolves block carries; each late carry controls
// only four sum bits. Exact modulo-2^64 addition, with no state or new edge.
module rv32_frequency_add64_select (
    input wire [63:0] lhs_i,rhs_i,
    output wire [63:0] sum_o
);
    wire [15:0] generate_stage [0:4];
    wire [15:0] propagate_stage [0:4];
    wire [3:0] sum_zero [0:15],sum_one [0:15];
    genvar block_index,prefix_level;
    generate
        for(block_index=0;block_index<16;block_index=block_index+1) begin:g_block
            wire [4:0] block_sum={1'b0,lhs_i[block_index*4 +: 4]}+
                {1'b0,rhs_i[block_index*4 +: 4]};
            assign sum_zero[block_index]=block_sum[3:0];
            assign sum_one[block_index]=block_sum[3:0]+4'd1;
            assign generate_stage[0][block_index]=block_sum[4];
            assign propagate_stage[0][block_index]=
                &(lhs_i[block_index*4 +: 4] ^ rhs_i[block_index*4 +: 4]);
            if(block_index==0) begin:g_first
                assign sum_o[0 +: 4]=sum_zero[0];
            end else begin:g_selected
                assign sum_o[block_index*4 +: 4]=generate_stage[4][block_index-1] ?
                    sum_one[block_index] : sum_zero[block_index];
            end
        end
        for(prefix_level=0;prefix_level<4;prefix_level=prefix_level+1) begin:g_prefix
            localparam integer DISTANCE=1<<prefix_level;
            for(block_index=0;block_index<16;block_index=block_index+1) begin:g_block
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
    endgenerate
endmodule
'''


def multiplier(source):
    return change(source,'    wire [63:0] product=s2_rows[0]+s2_rows[1];',
        '''    wire [63:0] product;
    rv32_frequency_add64_select final_add (
        .lhs_i(s2_rows[0]),.rhs_i(s2_rows[1]),.sum_o(product));''')


def rs_comment(source):
    return change(source,'''    // Rank/ready remain unchanged. A selection never drives an entire packet;
    // it is distributed into <=32-bit words before balanced payload reduction.''',
        '''    // Rank policy and ready remain unchanged. Each selection controls
    // <=16-bit words before balanced payload reduction.''')


if __name__=='__main__':
    prepare('CZ_carry_select_tails',ROOT/'CY_local_execution_wake',{
        'rtl/rv32i_alu.v':alu,
        'rtl/rv32m_multiplier.v':multiplier,
        'rtl/common/rv32_asap7_fanout.v':common,
        'rtl/backend/rv32_reservation_station.v':rs_comment,
    },'Precompute carry0/carry1 nibble sums before late group carries for ALU and MUL final64 CPA; modulo arithmetic, pipeline/metadata/FF unchanged; RS comment repair; no HDL/EDA tests')
