`timescale 1ns/1ps

module rv32im_memory_image_tb;
    reg clk, reset, req_valid, resp_ready;
    reg [31:0] req_addr;
    reg [7:0] req_id;
    wire req_ready, resp_valid, resp_error;
    wire [31:0] resp_addr;
    wire [127:0] resp_data;
    wire [7:0] resp_id;

    rv32im_memory_model mem (
        .clk_i(clk), .reset_i(reset),
        .i_req_valid_i(req_valid), .i_req_ready_o(req_ready), .i_req_line_addr_i(req_addr), .i_req_id_i(req_id),
        .i_resp_valid_o(resp_valid), .i_resp_ready_i(resp_ready), .i_resp_line_addr_o(resp_addr), .i_resp_data_o(resp_data), .i_resp_id_o(resp_id), .i_resp_error_o(resp_error),
        .d_req_valid_i(1'b0), .d_req_ready_o(), .d_req_write_i(1'b0), .d_req_line_addr_i(32'd0), .d_req_wdata_i(128'd0), .d_req_wmask_i(16'd0), .d_req_id_i(8'd0),
        .d_resp_valid_o(), .d_resp_ready_i(1'b1), .d_resp_line_addr_o(), .d_resp_data_o(), .d_resp_id_o(), .d_resp_error_o()
    );
    initial begin clk = 1'b0; forever #5 clk = ~clk; end
    initial begin
        reset = 1'b1; req_valid = 1'b0; resp_ready = 1'b1; req_addr = 32'h1000; req_id = 8'h66;
        #12; reset = 1'b0;
        @(negedge clk); req_valid = 1'b1;
        while (!req_ready) @(negedge clk);
        @(negedge clk); req_valid = 1'b0;
        wait(resp_valid);
        if (resp_error || resp_id != 8'h66 || resp_data[31:0] !== 32'h00001737) begin
            $display("FAIL: sparse @address image was not loaded");
            $finish(1);
        end
        $display("PASS: H-03 external sparse image loader");
        $finish(0);
    end
endmodule
