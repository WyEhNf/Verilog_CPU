`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Two request slots decouple front-end ready from tag/MSHR/response logic.
// Epoch-stale requests drain independently of lookup readiness.
module rv32_icache_query_queue #(parameter integer EPOCH_WIDTH=4) (
    input wire clk_i,reset_i,
    input wire [EPOCH_WIDTH-1:0] current_epoch_i,
    input wire valid_i,
    output wire ready_o,
    input wire [31:0] pc_i,
    input wire [EPOCH_WIDTH-1:0] epoch_i,
    output wire valid_o,
    input wire ready_i,
    output wire [31:0] pc_o,
    output wire [EPOCH_WIDTH-1:0] epoch_o
);
    reg [1:0] count;
    reg read_slot,write_slot;
    localparam integer PAYLOAD_WIDTH=32+EPOCH_WIDTH;
    localparam integer PAYLOAD_WORDS=(PAYLOAD_WIDTH+15)/16;
    wire [PAYLOAD_WIDTH-1:0] payload [0:1];
    wire [PAYLOAD_WORDS-1:0] read_views;
    wire [PAYLOAD_WIDTH-1:0] read_payload;
    rv32_frequency_control_tree #(.LEAVES(PAYLOAD_WORDS)) read_tree (
        .signal_i(read_slot),.views_o(read_views));
    assign {pc_o,epoch_o}=read_payload;
    genvar read_word;
    generate for(read_word=0;read_word<PAYLOAD_WORDS;read_word=read_word+1) begin:g_read_word
        localparam integer LOW=read_word*16;
        localparam integer BITS=(PAYLOAD_WIDTH-LOW>=16)?16:PAYLOAD_WIDTH-LOW;
        assign read_payload[LOW +: BITS]=read_views[read_word]?
            payload[1][LOW +: BITS]:payload[0][LOW +: BITS];
    end endgenerate
    wire stale=count!=0 && epoch_o!=current_epoch_i;
    assign ready_o=!reset_i && count<2;
    assign valid_o=!reset_i && count!=0 && !stale;
    wire push=valid_i && ready_o;
    wire pop=!reset_i && (stale || (valid_o && ready_i));
    genvar queue_row;
    generate for(queue_row=0;queue_row<2;queue_row=queue_row+1) begin:g_row
        // Preserve the same two unreset payload slots and write edge.
        // Each write leaf now owns at most sixteen existing hold muxes.
        rv32_frequency_word_bank #(.WIDTH(PAYLOAD_WIDTH)) owner (
            .clk_i(clk_i),.write_i(push && write_slot==queue_row),
            .data_i({pc_i,epoch_i}),.data_o(payload[queue_row]));
    end endgenerate
    always @(posedge clk_i) begin
        if(reset_i)
        begin
            count<=0;
            read_slot<=0;
            write_slot<=0;
        end
        else
        begin
            count<=count+push-pop;
            if(pop)
                read_slot<=!read_slot;
            if(push)
                write_slot<=!write_slot;
        end
    end
endmodule
