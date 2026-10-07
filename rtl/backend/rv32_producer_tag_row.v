`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32_producer_tag_row #(parameter integer LANES=4,TAG_WIDTH=17) (
    input wire clk_i,reset_i,
    input wire [LANES-1:0] match_i,
    input wire [LANES*TAG_WIDTH-1:0] tag_i,
    output wire [TAG_WIDTH-1:0] tag_o
);
    reg stored_valid;
    reg [TAG_WIDTH-1:0] stored_tag;
    wire [LANES-1:0] grants,local_grants;
    wire write_local;
    genvar lane;
    generate for(lane=0;lane<LANES;lane=lane+1) begin:g_grant
        if(lane==LANES-1) begin : g_named_17_26
assign grants[lane]=match_i[lane];
end
        else begin : g_named_18_13
assign grants[lane]=match_i[lane] && !(|match_i[LANES-1:lane+1]);
end
    end endgenerate
    rv32_frequency_control_tree #(.WIDTH(LANES),.LEAVES(1)) grant_tree (
        .signal_i(grants),.views_o(local_grants));
    rv32_frequency_control_tree #(.LEAVES(1)) write_tree (
        .signal_i(!reset_i && (|match_i)),.views_o(write_local));
    reg [TAG_WIDTH-1:0] next_tag;
    integer writer;
    always @* begin
        next_tag=0;
        for(writer=0;writer<LANES;writer=writer+1)
            next_tag=next_tag | ({TAG_WIDTH{local_grants[writer]}} &
                               tag_i[writer*TAG_WIDTH +: TAG_WIDTH]);
    end
    always @(posedge clk_i) if(write_local)
        stored_tag<=next_tag;
    always @(posedge clk_i) begin
        if(reset_i)
            stored_valid<=0;
        else
            if(|match_i)
                stored_valid<=1;
    end
    // Before the first write after reset, the visible tag is exactly zero,
    // matching the former full-word reset. A write replaces all tag bits.
    assign tag_o={TAG_WIDTH{stored_valid}} & stored_tag;
endmodule
