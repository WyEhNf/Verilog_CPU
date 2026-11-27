`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Functional state owner, not a buffer-only hierarchy boundary.
// State logic may flatten and prune unused bits. Kept inversion
// modules inside the write trees retain the electrical domains.
module rv32_decode_field_bank #(
    parameter integer LANES=4,WIDTH=32,ROW=0,CAPACITY=LANES,PW=(CAPACITY<2)?1:$clog2(CAPACITY)
) (
    input wire clk_i,reset_i,flush_i,
    input wire [PW-1:0] tail_i,
    input wire [LANES-1:0] push_i,
    input wire [LANES*WIDTH-1:0] data_i,
    output reg [WIDTH-1:0] data_o
);
    wire unused_reset_i_bits = &{1'b0, reset_i};

    wire unused_flush_i_bits = &{1'b0, flush_i};

    wire [LANES-1:0] selected;
    wire [LANES-1:0] selected_local;
    rv32_frequency_control_tree #(.WIDTH(LANES),.LEAVES(1)) select_tree (
        .signal_i(selected),.views_o(selected_local));
    genvar writer;
    generate for(writer=0;writer<LANES;writer=writer+1) begin:g_select
        assign selected[writer]=push_i[writer] && (((32'(tail_i)+writer)%CAPACITY)==ROW);
    end endgenerate
    wire write_local;
    rv32_frequency_control_tree #(.LEAVES(1)) write_enable_tree (
        .signal_i(|selected_local),.views_o(write_local));
    reg [WIDTH-1:0] next_data;
    integer lane;
    always @* begin
        next_data=0;
        for(lane=0;lane<LANES;lane=lane+1)
            next_data=next_data | ({WIDTH{selected_local[lane]}} & data_i[lane*WIDTH +: WIDTH]);
    end
    always @(posedge clk_i) begin
        if(write_local)
            data_o<=next_data;
    end
endmodule
