`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32_fetch_frontend_tb #(
    parameter integer FE_WIDTH = 1
);
    localparam integer PW = `RV32IM_FETCH_PACKET_WIDTH;
    reg clk, reset;
    reg redirect_valid;
    reg [31:0] redirect_pc;
    reg [3:0] redirect_epoch;
    reg stop_i, error_i;
    wire if_req_valid, if_req_ready;
    wire [31:0] if_req_pc;
    wire [3:0] if_req_epoch;
    reg if_resp_valid;
    wire if_resp_ready;
    reg [31:0] if_resp_pc, if_resp_line_addr;
    reg [127:0] if_resp_line_data;
    reg [3:0] if_resp_epoch;
    reg if_resp_error;
    reg [FE_WIDTH-1:0] if_resp_pred_taken;
    reg [FE_WIDTH*32-1:0] if_resp_pred_target;
    reg [FE_WIDTH*2-1:0] if_resp_pred_kind;
    reg [FE_WIDTH-1:0] if_resp_pred_btb_hit;
    wire [FE_WIDTH-1:0] fetch_valid;
    reg [FE_WIDTH-1:0] fetch_ready;
    wire [FE_WIDTH*PW-1:0] fetch_packet;
    wire [3:0] current_epoch;
    wire frozen;
    wire event_fetch, event_redirect, event_stall;
    integer cycle;
    integer i;
    reg [FE_WIDTH*PW-1:0] held_packet;

    rv32_fetch_frontend #(.FE_WIDTH(FE_WIDTH), .FQ_DEPTH(8)) dut (
        .clk_i(clk), .reset_i(reset), .redirect_valid_i(redirect_valid),
        .redirect_pc_i(redirect_pc), .redirect_epoch_i(redirect_epoch),
        .stop_i(stop_i), .error_i(error_i), .if_req_valid_o(if_req_valid),
        .if_req_ready_i(if_req_ready), .if_req_pc_o(if_req_pc),
        .if_req_epoch_o(if_req_epoch), .if_resp_valid_i(if_resp_valid),
        .if_resp_ready_o(if_resp_ready), .if_resp_pc_i(if_resp_pc),
        .if_resp_line_addr_i(if_resp_line_addr), .if_resp_line_data_i(if_resp_line_data),
        .if_resp_epoch_i(if_resp_epoch), .if_resp_error_i(if_resp_error),
        .if_resp_pred_taken_i(if_resp_pred_taken),
        .if_resp_pred_target_i(if_resp_pred_target),
        .if_resp_pred_kind_i(if_resp_pred_kind),
        .if_resp_pred_btb_hit_i(if_resp_pred_btb_hit),
        .fetch_valid_o(fetch_valid), .fetch_ready_i(fetch_ready),
        .fetch_packet_o(fetch_packet), .current_epoch_o(current_epoch),
        .frozen_o(frozen), .event_fetch_o(event_fetch),
        .event_redirect_o(event_redirect), .event_stall_o(event_stall)
    );

    assign if_req_ready = 1'b1;
    initial begin clk = 1'b0; forever #5 clk = ~clk; end
    always @(posedge clk) cycle = cycle + 1;

    task clear_response;
        begin
            if_resp_valid = 1'b0;
            if_resp_pc = 32'd0;
            if_resp_line_addr = 32'd0;
            if_resp_line_data = 128'd0;
            if_resp_epoch = 4'd0;
            if_resp_error = 1'b0;
            if_resp_pred_taken = {FE_WIDTH{1'b0}};
            if_resp_pred_target = {FE_WIDTH*32{1'b0}};
            if_resp_pred_kind = {FE_WIDTH*2{1'b0}};
            if_resp_pred_btb_hit = {FE_WIDTH{1'b0}};
        end
    endtask

    task send_response;
        input [31:0] pc;
        input [31:0] line_addr;
        input [127:0] line_data;
        input [3:0] epoch;
        input error;
        begin
            @(negedge clk);
            if_resp_valid = 1'b1;
            if_resp_pc = pc;
            if_resp_line_addr = line_addr;
            if_resp_line_data = line_data;
            if_resp_epoch = epoch;
            if_resp_error = error;
            while (!if_resp_ready) @(negedge clk);
            @(posedge clk);
            @(negedge clk);
            clear_response();
        end
    endtask

    function [31:0] packet_pc;
        input integer lane;
        packet_pc = fetch_packet[lane*PW +: 32];
    endfunction

    initial begin
        cycle = 0;
        reset = 1'b1;
        redirect_valid = 1'b0;
        redirect_pc = 32'd0;
        redirect_epoch = 4'd0;
        stop_i = 1'b0;
        error_i = 1'b0;
        fetch_ready = {FE_WIDTH{1'b0}};
        clear_response();
        repeat (2) @(posedge clk);
        if (if_req_valid !== 1'b0 || fetch_valid !== {FE_WIDTH{1'b0}} ||
            current_epoch !== 4'd0 || frozen !== 1'b0) begin
            $display("FAIL: A-04 reset determinism"); $finish(1);
        end
        @(negedge clk); reset = 1'b0; #1;
        if (!if_req_valid || if_req_pc != 0 || if_req_epoch != 0) begin
            $display("FAIL: A-04 initial PC request valid=%b pc=%08x epoch=%0d reset=%b frozen=%b stop=%b error=%b pending=%b", if_req_valid, if_req_pc, if_req_epoch, reset, frozen, stop_i, error_i, dut.req_pending_reg); $finish(1);
        end
        @(posedge clk); @(negedge clk);

        // Predicted taken truncates the bundle at the first predicted control flow.
        if (FE_WIDTH == 1) begin
            if_resp_pred_taken[0] = 1'b1;
            if_resp_pred_target[31:0] = 32'h00000100;
            if_resp_pred_kind[1:0] = `RV32IM_PRED_BRANCH;
        end else begin
            if_resp_pred_taken[1] = 1'b1;
            if_resp_pred_target[63:32] = 32'h00000100;
            if_resp_pred_kind[3:2] = `RV32IM_PRED_BRANCH;
        end
        send_response(32'h00000000, 32'h00000000,
                      128'h00000013000000130000001300000013, 4'd0, 1'b0);
        held_packet = fetch_packet;
        for (i = 0; i < FE_WIDTH; i = i + 1) begin
            if (i < ((FE_WIDTH == 1) ? 1 : 2)) begin
                if (!fetch_valid[i] || packet_pc(i) != (i*4)) begin
                    $display("FAIL: A-04 bundle lane %0d", i); $finish(1);
                end
            end else if (fetch_valid[i]) begin
                $display("FAIL: A-04 bundle not truncated at lane %0d", i); $finish(1);
            end
        end
        repeat (3) begin
            @(negedge clk);
            if (fetch_packet !== held_packet || fetch_valid !== ((FE_WIDTH == 1) ? 1'b1 : 2'b11)) begin
                $display("FAIL: A-04 payload changed under backpressure"); $finish(1);
            end
        end
        fetch_ready = {FE_WIDTH{1'b1}};
        @(posedge clk); @(negedge clk);
        if (if_req_pc != 32'h00000100 || current_epoch != 4'd0) begin
            $display("FAIL: A-04 predicted next PC"); $finish(1);
        end

        // A response beginning at the final word of a line produces one entry only.
        send_response(32'h0000000c, 32'h00000000,
                      128'h00000013000000130000001300000013, 4'd0, 1'b0);
        if (!fetch_valid[0] || packet_pc(0) != 32'h0000000c) begin
            $display("FAIL: A-04 line-tail packet"); $finish(1);
        end
        for (i = 1; i < FE_WIDTH; i = i + 1)
            if (fetch_valid[i]) begin $display("FAIL: A-04 line-tail extra lane"); $finish(1); end
        fetch_ready = {FE_WIDTH{1'b1}};
        @(posedge clk); @(negedge clk);

        // Redirect flushes queued old-epoch entries and restarts request generation.
        fetch_ready = {FE_WIDTH{1'b0}};
        send_response(32'h00000020, 32'h00000020,
                      128'h00000013000000130000001300000013, 4'd0, 1'b0);
        redirect_pc = 32'h00000200;
        redirect_epoch = 4'd1;
        redirect_valid = 1'b1;
        @(posedge clk); @(negedge clk);
        redirect_valid = 1'b0;
        if (fetch_valid !== {FE_WIDTH{1'b0}} || current_epoch != 4'd1 ||
            if_req_pc != 32'h00000200 || !event_redirect) begin
            $display("FAIL: A-04 redirect flush/epoch"); $finish(1);
        end

        // Old responses are not accepted after redirect.
        if_resp_valid = 1'b1;
        if_resp_pc = 32'h00000020;
        if_resp_line_addr = 32'h00000020;
        if_resp_line_data = 128'h00000013000000130000001300000013;
        if_resp_epoch = 4'd0;
        @(negedge clk);
        if (if_resp_ready) begin $display("FAIL: A-04 accepted stale response"); $finish(1); end
        clear_response();

        // Error response freezes generation and does not enqueue an invalid packet.
        send_response(32'h00000200, 32'h00000200, 128'd0, 4'd1, 1'b1);
        if (!frozen || fetch_valid !== {FE_WIDTH{1'b0}} || if_req_valid) begin
            $display("FAIL: A-04 error freeze"); $finish(1);
        end
        $display("PASS: A-04 frontend FE_WIDTH=%0d queue, truncation, redirect, and freeze", FE_WIDTH);
        $finish(0);
    end

    initial begin
        #20000;
        $display("FAIL: A-04 timeout cycle=%0d", cycle);
        $finish(1);
    end
endmodule
