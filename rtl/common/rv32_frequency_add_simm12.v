`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Addition of an RV32 load/store signed 12-bit displacement. The low twelve
// bits use three carry-select blocks. The upper word changes only by -1, 0,
// or +1; its increment/decrement prefixes are independent of the low carry.
// No state, and all arithmetic wraps modulo 2^32.
(* keep_hierarchy = 1 *)
module rv32_frequency_add_simm12 #(
    parameter CLASS_COMPARE=0
) (
    input wire [31:0] base_i,
    input wire [11:0] immediate_i,
    output wire [31:0] sum_o,
    output wire [2:0] class_flags_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign sum_o = base_i + {{20{immediate_i[11]}},immediate_i};
    assign class_flags_o = (CLASS_COMPARE != 0) ?
        {sum_o[1:0]==2'b00,!sum_o[0],sum_o[31:28]==4'b0} : 3'b0;
`else
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
    // A signed12 displacement changes base[31:12] by only -1,0,+1.
    // Classify each possible high word before the existing low12 carry;
    // do not form four late adjusted sum bits and then reduce them.
    generate if(CLASS_COMPARE!=0) begin:g_class_compare
        wire high_zero=base_i[31:28]==4'h0;
        wire high_ones=base_i[31:28]==4'hf;
        wire high_one=base_i[31:28]==4'h1;
        // These exact lower16 reductions already exist for the full sum.
        wire middle_ones=ones_prefix[5][15];
        wire middle_zero=zeros_prefix[5][15];
        wire ram_increment=middle_ones ? high_ones : high_zero;
        wire ram_decrement=middle_zero ? high_one : high_zero;
        wire ram_carry_zero=immediate_i[11] ? ram_decrement : high_zero;
        wire ram_carry_one=immediate_i[11] ? high_zero : ram_increment;
        wire ram=generate_stage[2][2] ? ram_carry_one : ram_carry_zero;
        assign class_flags_o={sum_o[1:0]==2'b00,!sum_o[0],ram};
    end else begin:g_no_class_compare
        assign class_flags_o=3'b0;
    end endgenerate
`endif
endmodule
