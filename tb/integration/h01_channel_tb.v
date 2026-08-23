`timescale 1ns/1ps
`include "rv32im_defs.vh"

module h01_channel_tb;
    reg clk;
    reg reset;
    reg producer_valid;
    reg consumer_ready;
    reg flush_valid;
    reg [3:0] producer_epoch;
    reg [`RV32IM_FETCH_PACKET_WIDTH-1:0] producer_payload;
    reg [`RV32IM_FETCH_PACKET_WIDTH-1:0] held_payload;
    reg held_valid;
    integer fire_count;

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    always @(posedge clk) begin
        if (reset) begin
            producer_valid <= 1'b0;
            held_valid <= 1'b0;
            fire_count <= 0;
        end else if (flush_valid) begin
            producer_valid <= 1'b0;
            held_valid <= 1'b0;
        end else begin
            if (producer_valid && !consumer_ready) begin
                if (held_valid && (held_payload !== producer_payload)) begin
                    $display("FAIL: payload changed while valid without ready");
                    $finish(1);
                end
                held_payload <= producer_payload;
                held_valid <= 1'b1;
            end else if (producer_valid && consumer_ready) begin
                fire_count <= fire_count + 1;
                held_valid <= 1'b0;
            end
        end
    end

    initial begin
        reset = 1'b1;
        producer_valid = 1'b0;
        consumer_ready = 1'b0;
        flush_valid = 1'b0;
        producer_epoch = 4'h1;
        producer_payload = `RV32IM_FETCH_PACKET_PACK(32'h0, 32'h00000013, 1'b0, 32'h4, `RV32IM_PRED_NONE, 1'b0, producer_epoch);
        held_payload = {`RV32IM_FETCH_PACKET_WIDTH{1'b0}};
        held_valid = 1'b0;
        fire_count = 0;
        #12;
        reset = 1'b0;
        producer_valid = 1'b1;
        #20;
        consumer_ready = 1'b1;
        #12;
        producer_payload = `RV32IM_FETCH_PACKET_PACK(32'h4, 32'h00100093, 1'b0, 32'h8, `RV32IM_PRED_NONE, 1'b0, producer_epoch);
        #8;
        flush_valid = 1'b1;
        #10;
        flush_valid = 1'b0;
        producer_epoch = 4'h2;
        producer_payload = `RV32IM_FETCH_PACKET_PACK(32'h100, 32'h00000013, 1'b0, 32'h104, `RV32IM_PRED_NONE, 1'b0, producer_epoch);
        producer_valid = 1'b1;
        #10;
        if (fire_count != 3) begin
            $display("FAIL: expected two pre-flush and one post-flush handshake, got %0d", fire_count);
            $finish(1);
        end
        $display("PASS: H-01/S-01 valid-ready stability, flush, and epoch transfer");
        $finish(0);
    end
endmodule
