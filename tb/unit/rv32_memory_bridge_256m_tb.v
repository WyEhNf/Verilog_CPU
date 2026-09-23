`timescale 1ns/1ps

module rv32_memory_bridge_256m_tb;
    reg clk = 0;
    reg reset = 1;
    reg [31:0] address = 0;
    wire forwarded;
    wire ready;
    always #5 clk = ~clk;

    rv32_memory_bridge #(.MEMORY_SIZE(268435456)) dut (
        .clk_i(clk), .reset_i(reset),
        .cache_i_req_valid_i(1'b0), .cache_i_req_line_addr_i(32'b0),
        .cache_i_req_id_i(8'b0), .cache_i_resp_ready_i(1'b1),
        .cache_d_req_valid_i(1'b1), .cache_d_req_ready_o(ready),
        .cache_d_req_write_i(1'b0), .cache_d_req_line_addr_i(address),
        .cache_d_req_wdata_i(128'b0), .cache_d_req_wmask_i(16'b0),
        .cache_d_req_id_i(8'b0), .cache_d_resp_ready_i(1'b1),
        .mem_i_req_ready_i(1'b1), .mem_i_resp_valid_i(1'b0),
        .mem_i_resp_line_addr_i(32'b0), .mem_i_resp_data_i(128'b0),
        .mem_i_resp_id_i(8'b0), .mem_i_resp_error_i(1'b0),
        .mem_d_req_ready_i(1'b1), .mem_d_req_valid_o(forwarded),
        .mem_d_resp_valid_i(1'b0), .mem_d_resp_line_addr_i(32'b0),
        .mem_d_resp_data_i(128'b0), .mem_d_resp_id_i(8'b0),
        .mem_d_resp_error_i(1'b0)
    );

    initial begin
        @(posedge clk); #1; reset = 0;
        address = 32'h0ffffff0; #1;
        if (!ready || !forwarded) $fatal(1, "last 16-byte RAM line rejected");
        reset = 1; @(posedge clk); #1; reset = 0;
        address = 32'h10000000; #1;
        if (!ready || forwarded) $fatal(1, "first byte past RAM forwarded");
        $display("PASS: 256 MiB bridge bounds");
        $finish;
    end
endmodule
