`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Five binary shift stages. Each amount-bit leaf selects <=16 mux bits;
// right-shift logical/arithmetic behavior differs only in the fill bit.
// Immediate and register amounts keep separate networks, so this change
// does not add an opcode-selected amount mux ahead of the barrel stages.
module rv32_frequency_barrel32 (
    input wire [31:0] value_i,
    input wire [4:0] amount_i,
    input wire fill_i,
    output wire [31:0] left_o,
    output wire [31:0] right_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign left_o = value_i << amount_i;
    // The fill is independent of value_i[31], including for logical shifts.
    assign right_o = (value_i >> amount_i) |
        (fill_i ? ~(32'hffffffff >> amount_i) : 32'b0);
`else
    wire [19:0] amount_views;
    wire [4:0] fill_views;
    wire [31:0] left_stage [0:5];
    wire [31:0] right_stage [0:5];
    rv32_frequency_control_tree #(.WIDTH(5),.LEAVES(4)) amount_tree (
        .signal_i(amount_i),.views_o(amount_views));
    rv32_frequency_control_tree #(.LEAVES(5)) fill_tree (
        .signal_i(fill_i),.views_o(fill_views));
    assign left_stage[0]=value_i;
    assign right_stage[0]=value_i;
    assign left_o=left_stage[5];
    assign right_o=right_stage[5];
    genvar stage,bit_id;
    generate for(stage=0;stage<5;stage=stage+1) begin:g_stage
        localparam integer DISTANCE=1<<stage;
        for(bit_id=0;bit_id<32;bit_id=bit_id+1) begin:g_bit
            if(bit_id>=DISTANCE) begin:g_left_data
                assign left_stage[stage+1][bit_id]=amount_views[(bit_id/16)*5+stage]?
                    left_stage[stage][bit_id-DISTANCE]:left_stage[stage][bit_id];
            end else begin:g_left_zero
                assign left_stage[stage+1][bit_id]=!amount_views[(bit_id/16)*5+stage] && left_stage[stage][bit_id];
            end
            if(bit_id+DISTANCE<32) begin:g_right_data
                assign right_stage[stage+1][bit_id]=amount_views[(2+bit_id/16)*5+stage]?
                    right_stage[stage][bit_id+DISTANCE]:right_stage[stage][bit_id];
            end else begin:g_right_fill
                assign right_stage[stage+1][bit_id]=amount_views[(2+bit_id/16)*5+stage]?
                    fill_views[stage]:right_stage[stage][bit_id];
            end
        end
    end endgenerate
`endif
endmodule
