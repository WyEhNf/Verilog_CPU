`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Two retained entries break the functional-unit ready -> RS ready path.
// Unstalled first-result latency is still one registered selection stage.
module rv32_issue_pipeline_slot #(
    parameter integer PAYLOAD_WIDTH=192, TAG_WIDTH=17, ROB_ENTRIES=64,
    parameter integer SW=(ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES)
) (
    input wire clk_i, reset_i, flush_i, recovery_i,
    input wire [SW-1:0] head_i,
    input wire [TAG_WIDTH-1:0] recovery_tag_i,
    input wire valid_i, eligible_i,
    output wire ready_o,
    input wire [PAYLOAD_WIDTH-1:0] data_i,
    input wire [TAG_WIDTH-1:0] tag_i,
    output wire valid_o,
    input wire ready_i,
    output wire [PAYLOAD_WIDTH-1:0] data_o
);
    localparam integer CHUNKS=(PAYLOAD_WIDTH+15)/16;
    reg [1:0] count,entry_valid;
    reg read_slot,write_slot;
    reg [PAYLOAD_WIDTH-1:0] payload [0:1];
    reg [TAG_WIDTH-1:0] saved_tag [0:1];
    wire [1:0] recovery_keep;
    wire [SW-1:0] branch_age=recovery_tag_i[3 +: SW]-head_i;
    wire push=valid_i && ready_o;
    wire pop=valid_o && ready_i;
    wire [CHUNKS-1:0] read_views;
    rv32_frequency_control_tree #(.LEAVES(CHUNKS)) read_tree (
        .signal_i(read_slot),.views_o(read_views));
    // Ready depends only on registered occupancy, with one spare entry to
    // absorb backpressure. A full queue advertises space after its pop edge.
    assign ready_o=(count<2) && eligible_i && !reset_i && !flush_i && !recovery_i;
    assign valid_o=(count!=0) && !reset_i && !flush_i && !recovery_i;
    genvar queue_row,chunk;
    generate for(queue_row=0;queue_row<2;queue_row=queue_row+1) begin:g_row
        wire [SW-1:0] age=saved_tag[queue_row][3 +: SW]-head_i;
        assign recovery_keep[queue_row]=entry_valid[queue_row] &&
            saved_tag[queue_row][0] && age<branch_age;
        wire [CHUNKS:0] write_views;
        rv32_frequency_control_tree #(.LEAVES(CHUNKS+1)) write_tree (
            .signal_i(push && write_slot==queue_row),.views_o(write_views));
        always @(posedge clk_i) if(write_views[CHUNKS])
            saved_tag[queue_row]<=tag_i;
        for(chunk=0;chunk<CHUNKS;chunk=chunk+1) begin:g_chunk
            localparam integer LOW=chunk*16;
            localparam integer BITS=(PAYLOAD_WIDTH-LOW>=16)?16:PAYLOAD_WIDTH-LOW;
            always @(posedge clk_i) if(write_views[chunk])
                payload[queue_row][LOW +: BITS]<=data_i[LOW +: BITS];
        end
    end
    for(chunk=0;chunk<CHUNKS;chunk=chunk+1) begin:g_read
        localparam integer LOW=chunk*16;
        localparam integer BITS=(PAYLOAD_WIDTH-LOW>=16)?16:PAYLOAD_WIDTH-LOW;
        assign data_o[LOW +: BITS]=read_views[chunk]?
            payload[1][LOW +: BITS]:payload[0][LOW +: BITS];
    end endgenerate
    always @(posedge clk_i) begin
        if(reset_i || flush_i)
        begin
            count<=0;
            entry_valid<=0;
            read_slot<=0;
            write_slot<=0;
        end
        else
            if(recovery_i)
            begin
                entry_valid<=recovery_keep;
                case(recovery_keep)
                2'b11: count<=2;
                2'b01: begin count<=1;read_slot<=0;write_slot<=1;end
                2'b10: begin count<=1;read_slot<=1;write_slot<=0;end
                default: begin count<=0;read_slot<=0;write_slot<=0;end
                endcase
            end
            else
            begin
                count<=count+push-pop;
                if(pop)
                begin
                    entry_valid[read_slot]<=1'b0;
                    read_slot<=!read_slot;
                end
                if(push)
                begin
                    entry_valid[write_slot]<=1'b1;
                    write_slot<=!write_slot;
                end
            end
    end
endmodule
