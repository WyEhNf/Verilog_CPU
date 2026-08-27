`timescale 1ns/1ps
`include "rv32im_defs.vh"

module a07_frontend_cache_tb;
    reg clk, reset;
    reg redirect_valid, stop, frontend_error;
    reg [31:0] redirect_pc;
    reg [3:0] redirect_epoch;
    wire if_req_valid, if_req_ready;
    wire [31:0] if_req_pc;
    wire [3:0] if_req_epoch;
    wire if_resp_valid, if_resp_ready;
    wire [31:0] if_resp_pc, if_resp_line_addr;
    wire [127:0] if_resp_line_data;
    wire [3:0] if_resp_epoch;
    wire if_resp_error;
    reg fetch_ready;
    wire fetch_valid;
    wire [`RV32IM_FETCH_PACKET_WIDTH-1:0] fetch_packet;
    wire [3:0] current_epoch;
    wire frontend_frozen;
    wire frontend_event_fetch, frontend_event_redirect, frontend_event_stall;

    wire predictor_taken, predictor_btb_hit;
    wire [31:0] predictor_target;
    wire [1:0] predictor_kind;
    wire [31:0] predictor_inst;
    wire [5:0] unused_bht_index;
    wire [3:0] unused_btb_index;
    wire [1:0] unused_pred_counter;
    wire [31:0] unused_prediction_count, unused_correct_count;

    wire ic_mem_req_valid, ic_mem_req_ready;
    wire [31:0] ic_mem_req_addr;
    wire [7:0] ic_mem_req_id;
    wire ic_mem_resp_valid, ic_mem_resp_ready;
    wire [31:0] ic_mem_resp_addr;
    wire [127:0] ic_mem_resp_data;
    wire [7:0] ic_mem_resp_id;
    wire ic_mem_resp_error;
    wire i_event_request, i_event_hit, i_event_miss, i_event_refill, i_event_stall;

    reg d_req_valid, d_req_load, d_req_store, d_req_unsigned;
    wire d_req_ready;
    reg [31:0] d_req_addr;
    reg [1:0] d_req_size;
    reg [15:0] d_req_mask, d_req_rob, d_req_lsq;
    reg [127:0] d_req_wdata;
    wire d_resp_valid, d_resp_line_valid, d_resp_error;
    reg d_resp_ready;
    wire [15:0] d_resp_lsq;
    wire [31:0] d_resp_addr, d_resp_word;
    wire [127:0] d_resp_line;
    wire d_ack_valid, d_ack_error;
    wire [15:0] d_ack_lsq;
    wire dc_mem_req_valid, dc_mem_req_ready, dc_mem_req_write;
    wire [31:0] dc_mem_req_addr;
    wire [127:0] dc_mem_req_wdata;
    wire [15:0] dc_mem_req_wmask;
    wire [7:0] dc_mem_req_id;
    wire dc_mem_resp_valid, dc_mem_resp_ready, dc_mem_resp_error;
    wire [31:0] dc_mem_resp_addr;
    wire [127:0] dc_mem_resp_data;
    wire [7:0] dc_mem_resp_id;
    wire d_event_request, d_event_hit, d_event_miss, d_event_refill;
    wire d_event_writeback, d_event_stall;

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
    wire bridge_i_request, bridge_d_read, bridge_d_write;

    wire [63:0] i_request_count, i_hit_count, i_miss_count, i_refill_count, i_stall_count;
    wire [63:0] d_request_count, d_hit_count, d_miss_count, d_refill_count;
    wire [63:0] d_writeback_count, d_stall_count;
    wire [63:0] i_mem_request_count, d_mem_read_count, d_mem_write_count;

    integer cycle, bad;
    integer fetch_count, d_response_count;
    integer first_i_mem_cycle, first_d_mem_cycle;
    integer pc4_accept_cycle, pc4_response_cycle;
    integer pc24_accept_cycle, pc24_response_cycle;
    integer observed_concurrent_memory;
    integer n;
    reg [31:0] fetched_pc [0:7];
    reg [31:0] fetched_inst [0:7];
    reg fetched_taken [0:7];
    reg [31:0] fetched_target [0:7];
    reg [1:0] fetched_kind [0:7];
    reg [3:0] fetched_epoch [0:7];
    reg [`RV32IM_FETCH_PACKET_WIDTH-1:0] held_fetch_packet;
    reg [15:0] held_d_lsq;
    reg [31:0] held_d_addr, held_d_word;
    reg [127:0] held_d_line;
    reg held_d_error;

    assign predictor_inst = if_resp_line_data >> (if_resp_pc[3:2] * 32);

    rv32_fetch_frontend #(.FE_WIDTH(1), .FQ_DEPTH(8)) frontend (
        .clk_i(clk), .reset_i(reset), .redirect_valid_i(redirect_valid),
        .redirect_pc_i(redirect_pc), .redirect_epoch_i(redirect_epoch),
        .stop_i(stop), .error_i(frontend_error), .if_req_valid_o(if_req_valid),
        .if_req_ready_i(if_req_ready), .if_req_pc_o(if_req_pc),
        .if_req_epoch_o(if_req_epoch), .if_resp_valid_i(if_resp_valid),
        .if_resp_ready_o(if_resp_ready), .if_resp_pc_i(if_resp_pc),
        .if_resp_line_addr_i(if_resp_line_addr), .if_resp_line_data_i(if_resp_line_data),
        .if_resp_epoch_i(if_resp_epoch), .if_resp_error_i(if_resp_error),
        .if_resp_pred_taken_i(predictor_taken), .if_resp_pred_target_i(predictor_target),
        .if_resp_pred_kind_i(predictor_kind), .if_resp_pred_btb_hit_i(predictor_btb_hit),
        .fetch_valid_o(fetch_valid), .fetch_ready_i(fetch_ready),
        .fetch_packet_o(fetch_packet), .current_epoch_o(current_epoch),
        .frozen_o(frontend_frozen), .event_fetch_o(frontend_event_fetch),
        .event_redirect_o(frontend_event_redirect), .event_stall_o(frontend_event_stall)
    );

    rv32_branch_predictor predictor (
        .clk_i(clk), .reset_i(reset), .query_valid_i(if_resp_valid),
        .query_pc_i(if_resp_pc), .query_inst_i(predictor_inst),
        .pred_taken_o(predictor_taken), .pred_target_o(predictor_target),
        .pred_kind_o(predictor_kind), .pred_btb_hit_o(predictor_btb_hit),
        .pred_bht_index_o(unused_bht_index), .pred_btb_index_o(unused_btb_index),
        .pred_counter_o(unused_pred_counter), .feedback_valid_i(1'b0),
        .feedback_pc_i(32'd0), .feedback_kind_i(2'd0), .feedback_taken_i(1'b0),
        .feedback_target_i(32'd0), .feedback_pred_taken_i(1'b0),
        .feedback_pred_target_i(32'd0), .prediction_count_o(unused_prediction_count),
        .correct_count_o(unused_correct_count)
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

    rv32_dcache dcache (
        .clk_i(clk), .reset_i(reset), .flush_i(redirect_valid),
        .dcache_req_valid_i(d_req_valid), .dcache_req_ready_o(d_req_ready),
        .dcache_req_is_load_i(d_req_load), .dcache_req_is_store_i(d_req_store),
        .dcache_req_addr_i(d_req_addr), .dcache_req_size_i(d_req_size),
        .dcache_req_unsigned_i(d_req_unsigned), .dcache_req_mask_i(d_req_mask),
        .dcache_req_wdata_i(d_req_wdata), .dcache_req_rob_tag_i(d_req_rob),
        .dcache_req_lsq_tag_i(d_req_lsq), .dcache_resp_valid_o(d_resp_valid),
        .dcache_resp_ready_i(d_resp_ready), .dcache_resp_lsq_tag_o(d_resp_lsq),
        .dcache_resp_addr_o(d_resp_addr), .dcache_resp_line_data_o(d_resp_line),
        .dcache_resp_word_data_o(d_resp_word), .dcache_resp_line_valid_o(d_resp_line_valid),
        .dcache_resp_error_o(d_resp_error), .dcache_store_ack_valid_o(d_ack_valid),
        .dcache_store_ack_ready_i(1'b1), .dcache_store_ack_lsq_tag_o(d_ack_lsq),
        .dcache_store_ack_error_o(d_ack_error), .mem_req_valid_o(dc_mem_req_valid),
        .mem_req_ready_i(dc_mem_req_ready), .mem_req_write_o(dc_mem_req_write),
        .mem_req_line_addr_o(dc_mem_req_addr), .mem_req_wdata_o(dc_mem_req_wdata),
        .mem_req_wmask_o(dc_mem_req_wmask), .mem_req_id_o(dc_mem_req_id),
        .mem_resp_valid_i(dc_mem_resp_valid), .mem_resp_ready_o(dc_mem_resp_ready),
        .mem_resp_line_addr_i(dc_mem_resp_addr), .mem_resp_data_i(dc_mem_resp_data),
        .mem_resp_id_i(dc_mem_resp_id), .mem_resp_error_i(dc_mem_resp_error),
        .event_request_o(d_event_request), .event_hit_o(d_event_hit),
        .event_miss_o(d_event_miss), .event_refill_o(d_event_refill),
        .event_writeback_o(d_event_writeback), .event_stall_o(d_event_stall)
    );

    rv32_memory_bridge bridge (
        .clk_i(clk), .reset_i(reset), .cache_i_req_valid_i(ic_mem_req_valid),
        .cache_i_req_ready_o(ic_mem_req_ready), .cache_i_req_line_addr_i(ic_mem_req_addr),
        .cache_i_req_id_i(ic_mem_req_id), .cache_i_resp_valid_o(ic_mem_resp_valid),
        .cache_i_resp_ready_i(ic_mem_resp_ready), .cache_i_resp_line_addr_o(ic_mem_resp_addr),
        .cache_i_resp_data_o(ic_mem_resp_data), .cache_i_resp_id_o(ic_mem_resp_id),
        .cache_i_resp_error_o(ic_mem_resp_error), .cache_d_req_valid_i(dc_mem_req_valid),
        .cache_d_req_ready_o(dc_mem_req_ready), .cache_d_req_write_i(dc_mem_req_write),
        .cache_d_req_line_addr_i(dc_mem_req_addr), .cache_d_req_wdata_i(dc_mem_req_wdata),
        .cache_d_req_wmask_i(dc_mem_req_wmask), .cache_d_req_id_i(dc_mem_req_id),
        .cache_d_resp_valid_o(dc_mem_resp_valid), .cache_d_resp_ready_i(dc_mem_resp_ready),
        .cache_d_resp_line_addr_o(dc_mem_resp_addr), .cache_d_resp_data_o(dc_mem_resp_data),
        .cache_d_resp_id_o(dc_mem_resp_id), .cache_d_resp_error_o(dc_mem_resp_error),
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
        .event_d_mem_read_o(bridge_d_read), .event_d_mem_write_o(bridge_d_write)
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

    rv32_cache_stats stats (
        .clk_i(clk), .reset_i(reset), .i_event_request_i(i_event_request),
        .i_event_hit_i(i_event_hit), .i_event_miss_i(i_event_miss),
        .i_event_refill_i(i_event_refill), .i_event_stall_i(i_event_stall),
        .d_event_request_i(d_event_request), .d_event_hit_i(d_event_hit),
        .d_event_miss_i(d_event_miss), .d_event_refill_i(d_event_refill),
        .d_event_writeback_i(d_event_writeback), .d_event_stall_i(d_event_stall),
        .i_mem_request_fire_i(bridge_i_request), .d_mem_read_fire_i(bridge_d_read),
        .d_mem_write_fire_i(bridge_d_write), .i_request_count_o(i_request_count),
        .i_hit_count_o(i_hit_count), .i_miss_count_o(i_miss_count),
        .i_refill_count_o(i_refill_count), .i_stall_count_o(i_stall_count),
        .d_request_count_o(d_request_count), .d_hit_count_o(d_hit_count),
        .d_miss_count_o(d_miss_count), .d_refill_count_o(d_refill_count),
        .d_writeback_count_o(d_writeback_count), .d_stall_count_o(d_stall_count),
        .i_mem_request_count_o(i_mem_request_count), .d_mem_read_count_o(d_mem_read_count),
        .d_mem_write_count_o(d_mem_write_count)
    );

    initial begin clk = 1'b0; forever #5 clk = ~clk; end

    always @(posedge clk) begin
        cycle = cycle + 1;
        if (bridge_i_request && first_i_mem_cycle < 0) first_i_mem_cycle = cycle;
        if (bridge_d_read && first_d_mem_cycle < 0) first_d_mem_cycle = cycle;
        if (memory.i_busy && memory.d_busy) observed_concurrent_memory = 1;
        if (if_req_valid && if_req_ready && if_req_pc == 32'h00000004) pc4_accept_cycle = cycle;
        if (if_req_valid && if_req_ready && if_req_pc == 32'h00000024) pc24_accept_cycle = cycle;
        if (fetch_valid && fetch_ready) begin
            fetched_pc[fetch_count] = fetch_packet[31:0];
            fetched_inst[fetch_count] = fetch_packet[63:32];
            fetched_taken[fetch_count] = fetch_packet[64];
            fetched_target[fetch_count] = fetch_packet[96:65];
            fetched_kind[fetch_count] = fetch_packet[98:97];
            fetched_epoch[fetch_count] = fetch_packet[103:100];
            fetch_count = fetch_count + 1;
        end
        if (d_resp_valid && d_resp_ready)
            d_response_count = d_response_count + 1;
    end

    always @(negedge clk) begin
        if (if_resp_valid && if_resp_ready && if_resp_pc == 32'h00000004)
            pc4_response_cycle = cycle;
        if (if_resp_valid && if_resp_ready && if_resp_pc == 32'h00000024)
            pc24_response_cycle = cycle;
    end

    task clear_d_request;
        begin
            d_req_valid = 1'b0; d_req_load = 1'b0; d_req_store = 1'b0;
            d_req_unsigned = 1'b0; d_req_addr = 32'd0; d_req_size = `RV32IM_MEM_NONE;
            d_req_mask = 16'd0; d_req_wdata = 128'd0; d_req_rob = 16'd0; d_req_lsq = 16'd0;
        end
    endtask

    task issue_d_load;
        input [31:0] address;
        input [15:0] tag;
        begin
            @(negedge clk);
            d_req_valid = 1'b1; d_req_load = 1'b1; d_req_addr = address;
            d_req_size = `RV32IM_MEM_WORD; d_req_unsigned = 1'b1;
            d_req_rob = tag; d_req_lsq = tag;
            while (!d_req_ready) @(negedge clk);
            @(posedge clk); @(negedge clk); clear_d_request();
        end
    endtask

    task pulse_redirect;
        input [31:0] address;
        input [3:0] epoch;
        begin
            @(negedge clk);
            redirect_valid = 1'b1; redirect_pc = address; redirect_epoch = epoch;
            @(posedge clk); @(negedge clk); redirect_valid = 1'b0;
        end
    endtask

    initial begin
        cycle = 0; bad = 0; fetch_count = 0; d_response_count = 0;
        first_i_mem_cycle = -1; first_d_mem_cycle = -1;
        pc4_accept_cycle = -1; pc4_response_cycle = -1;
        pc24_accept_cycle = -1; pc24_response_cycle = -1;
        observed_concurrent_memory = 0;
        reset = 1'b1; redirect_valid = 1'b0; redirect_pc = 0; redirect_epoch = 0;
        stop = 1'b0; frontend_error = 1'b0; fetch_ready = 1'b0; d_resp_ready = 1'b0;
        clear_d_request();
        for (n = 0; n < 8; n = n + 1) begin
            fetched_pc[n] = 0; fetched_inst[n] = 0; fetched_taken[n] = 0;
            fetched_target[n] = 0; fetched_kind[n] = 0; fetched_epoch[n] = 0;
        end
        #1;
        memory.memory[16'h0000] = 8'h93; memory.memory[16'h0001] = 8'h00;
        memory.memory[16'h0002] = 8'h10; memory.memory[16'h0003] = 8'h00;
        memory.memory[16'h0004] = 8'h6f; memory.memory[16'h0005] = 8'h00;
        memory.memory[16'h0006] = 8'hc0; memory.memory[16'h0007] = 8'h01;
        memory.memory[16'h0020] = 8'h13; memory.memory[16'h0021] = 8'h01;
        memory.memory[16'h0022] = 8'h20; memory.memory[16'h0023] = 8'h00;
        memory.memory[16'h0024] = 8'h13; memory.memory[16'h0025] = 8'h05;
        memory.memory[16'h0026] = 8'hf0; memory.memory[16'h0027] = 8'h0f;
        memory.memory[16'h0200] = 8'h12; memory.memory[16'h0201] = 8'h34;
        memory.memory[16'h0202] = 8'h56; memory.memory[16'h0203] = 8'h78;
        memory.memory[16'h0400] = 8'h93; memory.memory[16'h0401] = 8'h01;
        memory.memory[16'h0402] = 8'h30; memory.memory[16'h0403] = 8'h00;
        memory.memory[16'h0500] = 8'h13; memory.memory[16'h0501] = 8'h05;
        memory.memory[16'h0502] = 8'hf0; memory.memory[16'h0503] = 8'h0f;

        repeat (3) @(posedge clk); #1;
        if (if_req_valid !== 1'b0 || if_resp_valid !== 1'b0 || d_req_ready !== 1'b0 ||
            fetch_valid !== 1'b0 || i_request_count !== 0 || d_request_count !== 0 ||
            i_mem_request_count !== 0 || d_mem_read_count !== 0) begin
            $display("FAIL: A-07 reset state is not deterministic"); $finish(1);
        end
        @(negedge clk); reset = 1'b0;

        // The LSQ stub starts a D miss beside the frontend's initial I miss.
        issue_d_load(32'h00000200, 16'h00d1);

        // Hold both CPU consumers and verify complete response payload stability.
        while (!fetch_valid) @(negedge clk);
        held_fetch_packet = fetch_packet;
        repeat (3) begin
            @(negedge clk);
            if (!fetch_valid || fetch_packet != held_fetch_packet) begin
                $display("FAIL: A-07 FetchPacket changed under backpressure"); bad = bad + 1;
            end
        end
        while (!d_resp_valid) @(negedge clk);
        held_d_lsq = d_resp_lsq; held_d_addr = d_resp_addr; held_d_word = d_resp_word;
        held_d_line = d_resp_line; held_d_error = d_resp_error;
        repeat (3) begin
            @(negedge clk);
            if (!d_resp_valid || d_resp_lsq != held_d_lsq || d_resp_addr != held_d_addr ||
                d_resp_word != held_d_word || d_resp_line != held_d_line ||
                d_resp_error != held_d_error) begin
                $display("FAIL: A-07 D response changed under backpressure"); bad = bad + 1;
            end
        end
        if (held_d_lsq != 16'h00d1 || held_d_addr != 32'h200 ||
            held_d_word != 32'h78563412 || held_d_error || !d_resp_line_valid) begin
            $display("FAIL: A-07 LSQ response tag/data lsq=%04x addr=%08x data=%08x error=%b",
                     held_d_lsq, held_d_addr, held_d_word, held_d_error); bad = bad + 1;
        end
        if (first_i_mem_cycle < 0 || first_d_mem_cycle < 0 || !observed_concurrent_memory) begin
            $display("FAIL: A-07 I/D memory transactions did not overlap I=%0d D=%0d overlap=%0d",
                     first_i_mem_cycle, first_d_mem_cycle, observed_concurrent_memory); bad = bad + 1;
        end
        @(negedge clk); fetch_ready = 1'b1; d_resp_ready = 1'b1;

        while (fetch_count < 4) @(negedge clk);
        repeat (3) @(negedge clk);
        if (!frontend_frozen) begin $display("FAIL: A-07 HALT did not freeze frontend"); bad = bad + 1; end
        if (fetched_pc[0] != 32'h0 || fetched_inst[0] != 32'h00100093 ||
            fetched_pc[1] != 32'h4 || fetched_inst[1] != 32'h01c0006f ||
            fetched_pc[2] != 32'h20 || fetched_inst[2] != 32'h00200113 ||
            fetched_pc[3] != 32'h24 || fetched_inst[3] != 32'h0ff00513) begin
            $display("FAIL: A-07 fetch order %08x %08x %08x %08x",
                     fetched_pc[0], fetched_pc[1], fetched_pc[2], fetched_pc[3]); bad = bad + 1;
        end
        if (!fetched_taken[1] || fetched_target[1] != 32'h20 ||
            fetched_kind[1] != `RV32IM_PRED_JAL) begin
            $display("FAIL: A-07 JAL prediction metadata taken=%b target=%08x kind=%0d",
                     fetched_taken[1], fetched_target[1], fetched_kind[1]); bad = bad + 1;
        end
        if ((pc4_response_cycle - pc4_accept_cycle) != 3 ||
            (pc24_response_cycle - pc24_accept_cycle) != 3) begin
            $display("FAIL: A-07 warm-hit latency pc4=%0d pc24=%0d",
                     pc4_response_cycle-pc4_accept_cycle,
                     pc24_response_cycle-pc24_accept_cycle); bad = bad + 1;
        end

        // Redirect after an old miss reaches memory; only the new epoch may enter the queue.
        pulse_redirect(32'h00000400, 4'd1);
        while (i_mem_request_count < 3) @(negedge clk);
        pulse_redirect(32'h00000500, 4'd2);
        while (fetch_count < 5) @(negedge clk);
        repeat (5) @(negedge clk);
        if (fetched_pc[4] != 32'h00000500 || fetched_inst[4] != 32'h0ff00513 ||
            fetched_epoch[4] != 4'd2) begin
            $display("FAIL: A-07 redirect delivery pc=%08x inst=%08x epoch=%0d",
                     fetched_pc[4], fetched_inst[4], fetched_epoch[4]); bad = bad + 1;
        end
        for (n = 0; n < fetch_count; n = n + 1)
            if (fetched_pc[n] == 32'h00000400) begin
                $display("FAIL: A-07 stale epoch packet escaped"); bad = bad + 1;
            end
        if (fetch_count != 5 || d_response_count != 1) begin
            $display("FAIL: A-07 duplicate response balance fetch=%0d D=%0d",
                     fetch_count, d_response_count); bad = bad + 1;
        end

        repeat (3) @(posedge clk); #1;
        if (i_request_count != 6 || i_hit_count != 2 || i_miss_count != 4 ||
            i_refill_count != 4 || i_mem_request_count != 4 || i_stall_count == 0) begin
            $display("FAIL: A-07 I counters req=%0d hit=%0d miss=%0d refill=%0d mem=%0d stall=%0d",
                     i_request_count, i_hit_count, i_miss_count, i_refill_count,
                     i_mem_request_count, i_stall_count); bad = bad + 1;
        end
        if (d_request_count != 1 || d_hit_count != 0 || d_miss_count != 1 ||
            d_refill_count != 1 || d_writeback_count != 0 || d_mem_read_count != 1 ||
            d_mem_write_count != 0) begin
            $display("FAIL: A-07 D counters req=%0d hit=%0d miss=%0d refill=%0d wb=%0d read=%0d write=%0d",
                     d_request_count, d_hit_count, d_miss_count, d_refill_count,
                     d_writeback_count, d_mem_read_count, d_mem_write_count); bad = bad + 1;
        end

        if (bad != 0) begin $display("FAIL: A-07 frontend/cache checks=%0d", bad); $finish(1); end
        $display("PASS: A-07 frontend/cache joint gate prediction, concurrency, redirect, tags, and counters");
        $finish(0);
    end

    initial begin
        #30000;
        $display("FAIL: A-07 frontend/cache timeout cycle=%0d fetch=%0d", cycle, fetch_count);
        $finish(1);
    end
endmodule
