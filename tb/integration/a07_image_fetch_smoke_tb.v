`timescale 1ns/1ps
`include "rv32im_defs.vh"

module a07_image_fetch_smoke_tb;
    reg clk, reset, stop;
    wire if_req_valid, if_req_ready;
    wire [31:0] if_req_pc;
    wire [3:0] if_req_epoch;
    wire if_resp_valid, if_resp_ready;
    wire [31:0] if_resp_pc, if_resp_line_addr;
    wire [127:0] if_resp_line_data;
    wire [3:0] if_resp_epoch;
    wire if_resp_error;
    wire fetch_valid;
    wire [`RV32IM_FETCH_PACKET_WIDTH-1:0] fetch_packet;
    wire [3:0] current_epoch;

    wire ic_mem_req_valid, ic_mem_req_ready;
    wire [31:0] ic_mem_req_addr;
    wire [7:0] ic_mem_req_id;
    wire ic_mem_resp_valid, ic_mem_resp_ready;
    wire [31:0] ic_mem_resp_addr;
    wire [127:0] ic_mem_resp_data;
    wire [7:0] ic_mem_resp_id;
    wire ic_mem_resp_error;
    wire i_event_request, i_event_hit, i_event_miss, i_event_refill, i_event_stall;

    wire mem_i_req_valid, mem_i_req_ready;
    wire [31:0] mem_i_req_addr;
    wire [7:0] mem_i_req_id;
    wire mem_i_resp_valid, mem_i_resp_ready, mem_i_resp_error;
    wire [31:0] mem_i_resp_addr;
    wire [127:0] mem_i_resp_data;
    wire [7:0] mem_i_resp_id;
    wire mem_d_req_valid, mem_d_req_ready, mem_d_req_write;
    wire [31:0] mem_d_req_addr;
    wire [127:0] mem_d_req_wdata;
    wire [15:0] mem_d_req_wmask;
    wire [7:0] mem_d_req_id;
    wire mem_d_resp_valid, mem_d_resp_ready, mem_d_resp_error;
    wire [31:0] mem_d_resp_addr;
    wire [127:0] mem_d_resp_data;
    wire [7:0] mem_d_resp_id;
    wire bridge_i_request;
    integer request_count, miss_count, refill_count, memory_request_count;
    reg [31:0] expected_inst;

    rv32_fetch_frontend #(.FE_WIDTH(1), .FQ_DEPTH(4)) frontend (
        .clk_i(clk), .reset_i(reset), .redirect_valid_i(1'b0),
        .redirect_pc_i(32'd0), .redirect_epoch_i(4'd0), .stop_i(stop),
        .error_i(1'b0), .if_req_valid_o(if_req_valid), .if_req_ready_i(if_req_ready),
        .if_req_pc_o(if_req_pc), .if_req_epoch_o(if_req_epoch),
        .if_resp_valid_i(if_resp_valid), .if_resp_ready_o(if_resp_ready),
        .if_resp_pc_i(if_resp_pc), .if_resp_line_addr_i(if_resp_line_addr),
        .if_resp_line_data_i(if_resp_line_data), .if_resp_epoch_i(if_resp_epoch),
        .if_resp_error_i(if_resp_error), .if_resp_pred_taken_i(1'b0),
        .if_resp_pred_target_i(32'd0), .if_resp_pred_kind_i(2'd0),
        .if_resp_pred_btb_hit_i(1'b0), .fetch_valid_o(fetch_valid),
        .fetch_ready_i(1'b0), .fetch_packet_o(fetch_packet),
        .current_epoch_o(current_epoch), .frozen_o(), .event_fetch_o(),
        .event_redirect_o(), .event_stall_o()
    );

    rv32_icache icache (
        .clk_i(clk), .reset_i(reset), .current_epoch_i(current_epoch),
        .if_req_valid_i(if_req_valid), .if_req_ready_o(if_req_ready),
        .if_req_pc_i(if_req_pc), .if_req_epoch_i(if_req_epoch),
        .if_resp_valid_o(if_resp_valid), .if_resp_ready_i(if_resp_ready),
        .if_resp_pc_o(if_resp_pc), .if_resp_line_addr_o(if_resp_line_addr),
        .if_resp_line_data_o(if_resp_line_data), .if_resp_epoch_o(if_resp_epoch),
        .if_resp_error_o(if_resp_error), .mem_req_valid_o(ic_mem_req_valid),
        .mem_req_ready_i(ic_mem_req_ready), .mem_req_line_addr_o(ic_mem_req_addr),
        .mem_req_id_o(ic_mem_req_id), .mem_resp_valid_i(ic_mem_resp_valid),
        .mem_resp_ready_o(ic_mem_resp_ready), .mem_resp_line_addr_i(ic_mem_resp_addr),
        .mem_resp_data_i(ic_mem_resp_data), .mem_resp_id_i(ic_mem_resp_id),
        .mem_resp_error_i(ic_mem_resp_error), .event_request_o(i_event_request),
        .event_hit_o(i_event_hit), .event_miss_o(i_event_miss),
        .event_refill_o(i_event_refill), .event_stall_o(i_event_stall)
    );

    rv32_memory_bridge bridge (
        .clk_i(clk), .reset_i(reset), .cache_i_req_valid_i(ic_mem_req_valid),
        .cache_i_req_ready_o(ic_mem_req_ready), .cache_i_req_line_addr_i(ic_mem_req_addr),
        .cache_i_req_id_i(ic_mem_req_id), .cache_i_resp_valid_o(ic_mem_resp_valid),
        .cache_i_resp_ready_i(ic_mem_resp_ready), .cache_i_resp_line_addr_o(ic_mem_resp_addr),
        .cache_i_resp_data_o(ic_mem_resp_data), .cache_i_resp_id_o(ic_mem_resp_id),
        .cache_i_resp_error_o(ic_mem_resp_error), .cache_d_req_valid_i(1'b0),
        .cache_d_req_ready_o(), .cache_d_req_write_i(1'b0),
        .cache_d_req_line_addr_i(32'd0), .cache_d_req_wdata_i(128'd0),
        .cache_d_req_wmask_i(16'd0), .cache_d_req_id_i(8'd0),
        .cache_d_resp_valid_o(), .cache_d_resp_ready_i(1'b1),
        .cache_d_resp_line_addr_o(), .cache_d_resp_data_o(),
        .cache_d_resp_id_o(), .cache_d_resp_error_o(),
        .mem_i_req_valid_o(mem_i_req_valid), .mem_i_req_ready_i(mem_i_req_ready),
        .mem_i_req_line_addr_o(mem_i_req_addr), .mem_i_req_id_o(mem_i_req_id),
        .mem_i_resp_valid_i(mem_i_resp_valid), .mem_i_resp_ready_o(mem_i_resp_ready),
        .mem_i_resp_line_addr_i(mem_i_resp_addr), .mem_i_resp_data_i(mem_i_resp_data),
        .mem_i_resp_id_i(mem_i_resp_id), .mem_i_resp_error_i(mem_i_resp_error),
        .mem_d_req_valid_o(mem_d_req_valid), .mem_d_req_ready_i(mem_d_req_ready),
        .mem_d_req_write_o(mem_d_req_write), .mem_d_req_line_addr_o(mem_d_req_addr),
        .mem_d_req_wdata_o(mem_d_req_wdata), .mem_d_req_wmask_o(mem_d_req_wmask),
        .mem_d_req_id_o(mem_d_req_id), .mem_d_resp_valid_i(mem_d_resp_valid),
        .mem_d_resp_ready_o(mem_d_resp_ready), .mem_d_resp_line_addr_i(mem_d_resp_addr),
        .mem_d_resp_data_i(mem_d_resp_data), .mem_d_resp_id_i(mem_d_resp_id),
        .mem_d_resp_error_i(mem_d_resp_error), .event_i_mem_request_o(bridge_i_request),
        .event_d_mem_read_o(), .event_d_mem_write_o()
    );

    rv32im_memory_model memory (
        .clk_i(clk), .reset_i(reset), .i_req_valid_i(mem_i_req_valid),
        .i_req_ready_o(mem_i_req_ready), .i_req_line_addr_i(mem_i_req_addr),
        .i_req_id_i(mem_i_req_id), .i_resp_valid_o(mem_i_resp_valid),
        .i_resp_ready_i(mem_i_resp_ready), .i_resp_line_addr_o(mem_i_resp_addr),
        .i_resp_data_o(mem_i_resp_data), .i_resp_id_o(mem_i_resp_id),
        .i_resp_error_o(mem_i_resp_error), .d_req_valid_i(mem_d_req_valid),
        .d_req_ready_o(mem_d_req_ready), .d_req_write_i(mem_d_req_write),
        .d_req_line_addr_i(mem_d_req_addr), .d_req_wdata_i(mem_d_req_wdata),
        .d_req_wmask_i(mem_d_req_wmask), .d_req_id_i(mem_d_req_id),
        .d_resp_valid_o(mem_d_resp_valid), .d_resp_ready_i(mem_d_resp_ready),
        .d_resp_line_addr_o(mem_d_resp_addr), .d_resp_data_o(mem_d_resp_data),
        .d_resp_id_o(mem_d_resp_id), .d_resp_error_o(mem_d_resp_error)
    );

    initial begin clk = 1'b0; forever #5 clk = ~clk; end
    always @(posedge clk) begin
        if (i_event_request) request_count = request_count + 1;
        if (i_event_miss) miss_count = miss_count + 1;
        if (i_event_refill) refill_count = refill_count + 1;
        if (bridge_i_request) memory_request_count = memory_request_count + 1;
    end

    initial begin
        reset = 1'b1; stop = 1'b0; request_count = 0; miss_count = 0;
        refill_count = 0; memory_request_count = 0;
        repeat (3) @(posedge clk);
        @(negedge clk); reset = 1'b0;
        while (!fetch_valid) @(negedge clk);
        stop = 1'b1;
        expected_inst = {memory.memory[3], memory.memory[2],
                         memory.memory[1], memory.memory[0]};
        if ((^fetch_packet) === 1'bx || fetch_packet[31:0] != 32'd0 ||
            fetch_packet[63:32] != expected_inst || fetch_packet[103:100] != 4'd0) begin
            $display("FAIL: A-07 image packet pc=%08x inst=%08x/%08x epoch=%0d",
                     fetch_packet[31:0], fetch_packet[63:32], expected_inst,
                     fetch_packet[103:100]);
            $finish(1);
        end
        repeat (2) @(posedge clk); #1;
        if (request_count != 1 || miss_count != 1 || refill_count != 1 ||
            memory_request_count != 1 || i_event_hit) begin
            $display("FAIL: A-07 image event balance req=%0d miss=%0d refill=%0d mem=%0d",
                     request_count, miss_count, refill_count, memory_request_count);
            $finish(1);
        end
        $display("PASS: A-07 image fetch smoke inst=%08x", expected_inst);
        $finish(0);
    end

    initial begin
        #5000;
        $display("FAIL: A-07 image fetch timeout");
        $finish(1);
    end
endmodule
