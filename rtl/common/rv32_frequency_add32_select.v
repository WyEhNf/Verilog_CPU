`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Eight independent four-bit adders produce block G/P and both sum choices.
// Three prefix levels resolve carries. Each late carry selects four bits.
// Exact modulo-2^32 addition with no registers or additional clock edge.
(* keep_hierarchy = 1 *)
module rv32_frequency_add32_select (
    input wire [31:0] lhs_i,rhs_i,
    output wire [31:0] sum_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign sum_o = lhs_i + rhs_i;
`else
    wire [7:0] generate_stage [0:3];
    wire [7:0] propagate_stage [0:3];
    wire [3:0] sum_zero [0:7],sum_one [0:7];
    genvar block_index,prefix_level;
    generate
        for(block_index=0;block_index<8;block_index=block_index+1) begin:g_block
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
                assign sum_o[block_index*4 +: 4]=generate_stage[3][block_index-1] ?
                    sum_one[block_index] : sum_zero[block_index];
            end
        end
        for(prefix_level=0;prefix_level<3;prefix_level=prefix_level+1) begin:g_prefix
            localparam integer DISTANCE=1<<prefix_level;
            for(block_index=0;block_index<8;block_index=block_index+1) begin:g_block
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
`endif
endmodule
