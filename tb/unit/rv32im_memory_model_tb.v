`timescale 1ns/1ps

module rv32im_memory_model_tb;
    reg clk, reset;
    reg i_valid, i_ready, d_valid, d_ready;
    reg [31:0] i_addr, d_addr;
    reg [7:0] i_id, d_id;
    reg d_write;
    reg [127:0] d_wdata;
    reg [15:0] d_wmask;
    wire i_req_ready, d_req_ready, i_resp_valid, d_resp_valid;
    wire [31:0] i_resp_addr, d_resp_addr;
    wire [127:0] i_resp_data, d_resp_data;
    wire [7:0] i_resp_id, d_resp_id;
    wire i_resp_error, d_resp_error;
    integer cycle;
    integer i_accept_cycle;
    integer d_accept_cycle;
    integer i_response_cycle;
    integer d_response_cycle;
    reg i_response_seen;
    reg d_response_seen;

    rv32im_memory_model mem (
        .clk_i(clk), .reset_i(reset),
        .i_req_valid_i(i_valid), .i_req_ready_o(i_req_ready), .i_req_line_addr_i(i_addr), .i_req_id_i(i_id),
        .i_resp_valid_o(i_resp_valid), .i_resp_ready_i(i_ready), .i_resp_line_addr_o(i_resp_addr), .i_resp_data_o(i_resp_data), .i_resp_id_o(i_resp_id), .i_resp_error_o(i_resp_error),
        .d_req_valid_i(d_valid), .d_req_ready_o(d_req_ready), .d_req_write_i(d_write), .d_req_line_addr_i(d_addr), .d_req_wdata_i(d_wdata), .d_req_wmask_i(d_wmask), .d_req_id_i(d_id),
        .d_resp_valid_o(d_resp_valid), .d_resp_ready_i(d_ready), .d_resp_line_addr_o(d_resp_addr), .d_resp_data_o(d_resp_data), .d_resp_id_o(d_resp_id), .d_resp_error_o(d_resp_error)
    );
    initial begin clk=0; forever #5 clk=~clk; end
    always @(posedge clk) begin
        cycle <= cycle + 1;
        if (!reset && i_resp_valid && !i_response_seen) begin
            i_response_seen <= 1'b1;
            i_response_cycle <= cycle + 1;
        end
        if (!reset && d_resp_valid && !d_response_seen) begin
            d_response_seen <= 1'b1;
            d_response_cycle <= cycle + 1;
        end
    end
    initial begin
        reset=1; i_valid=0; i_ready=1; d_valid=0; d_ready=1; i_addr=0; d_addr=0; i_id=8'h11; d_id=8'h22;
        d_write=0; d_wdata=0; d_wmask=0; cycle=0; i_accept_cycle=-1; d_accept_cycle=-1;
        i_response_cycle=-1; d_response_cycle=-1;
        i_response_seen=0; d_response_seen=0;
        #12; reset=0;
        @(negedge clk); i_valid=1; i_addr=32'h00000000; i_id=8'h11;
        d_valid=1; d_addr=32'h00000100; d_id=8'h22;
        while (!i_req_ready || !d_req_ready) @(negedge clk);
        @(posedge clk); i_accept_cycle = cycle + 1; d_accept_cycle = cycle + 1;
        @(negedge clk); i_valid=0; d_valid=0;
        wait(i_response_seen && d_response_seen);
        if ((i_response_cycle - i_accept_cycle) != 50 ||
            (d_response_cycle - d_accept_cycle) != 50) begin
            $display("FAIL: response latency was not exactly 50 cycles (i=%0d d=%0d)",
                     i_response_cycle - i_accept_cycle,
                     d_response_cycle - d_accept_cycle);
            $finish(1);
        end
        if (i_resp_id != 8'h11 || d_resp_id != 8'h22 || i_resp_error || d_resp_error) begin $display("FAIL: parallel response identity/error"); $finish(1); end
        if (i_resp_data[31:0] !== 32'h00000000) begin $display("FAIL: initial image data"); $finish(1); end
        @(negedge clk); d_valid=1; d_write=1; d_addr=32'h00000020; d_id=8'h33; d_wdata=128'h000000000000000000000000AABBCCDD; d_wmask=16'h0001;
        while (!d_req_ready) @(negedge clk);
        @(negedge clk); d_valid=0;
        wait(d_resp_valid); @(negedge clk); d_valid=1; d_write=0; d_addr=32'h00000020; d_id=8'h34;
        while (!d_req_ready) @(negedge clk);
        @(negedge clk); d_valid=0; wait(d_resp_valid);
        if (d_resp_data[31:0] !== 32'h000000DD) begin $display("FAIL: byte mask/endianness"); $finish(1); end
        @(negedge clk); i_valid=1; i_addr=32'h00000003; i_id=8'h55;
        while (!i_req_ready) @(negedge clk);
        @(negedge clk); i_valid=0; wait(i_resp_valid);
        if (!i_resp_error) begin $display("FAIL: unaligned address error"); $finish(1); end
        $display("PASS: H-03/S-02 dual-port memory, 50-cycle latency, snapshot, mask, and error");
        $finish(0);
    end

    initial begin
        #20000;
        $display("FAIL: H-03 memory model timeout cycle=%0d i_seen=%b d_seen=%b", cycle,
                 i_response_seen, d_response_seen);
        $finish(1);
    end
endmodule
