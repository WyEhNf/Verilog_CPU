`timescale 1ns/1ps

module rv32im_memory_model #(
    parameter integer MEMORY_SIZE = 1048576,
    parameter integer LATENCY = 50
) (
    input  wire         clk_i,
    input  wire         reset_i,
    input  wire         i_req_valid_i,
    output wire         i_req_ready_o,
    input  wire [31:0]  i_req_line_addr_i,
    input  wire [7:0]   i_req_id_i,
    output wire         i_resp_valid_o,
    input  wire         i_resp_ready_i,
    output wire [31:0]  i_resp_line_addr_o,
    output wire [127:0] i_resp_data_o,
    output wire [7:0]   i_resp_id_o,
    output wire         i_resp_error_o,
    input  wire         d_req_valid_i,
    output wire         d_req_ready_o,
    input  wire         d_req_write_i,
    input  wire [31:0]  d_req_line_addr_i,
    input  wire [127:0] d_req_wdata_i,
    input  wire [15:0]  d_req_wmask_i,
    input  wire [7:0]   d_req_id_i,
    output wire         d_resp_valid_o,
    input  wire         d_resp_ready_i,
    output wire [31:0]  d_resp_line_addr_o,
    output wire [127:0] d_resp_data_o,
    output wire [7:0]   d_resp_id_o,
    output wire         d_resp_error_o
);
    reg [7:0] memory [0:MEMORY_SIZE-1];
    reg i_busy, d_busy, i_resp_valid, d_resp_valid;
    reg [7:0] i_count, d_count;
    reg [31:0] i_addr, d_addr;
    reg [7:0] i_id, d_id;
    reg d_write;
    reg [127:0] i_snapshot, d_snapshot, d_wdata;
    reg [15:0] d_wmask;
    reg i_error, d_error;
    integer k;
    reg [1023:0] image_path;

    initial begin
        for (k = 0; k < MEMORY_SIZE; k = k + 1) memory[k] = 8'h00;
        if ($value$plusargs("IMAGE=%s", image_path)) begin
            $display("INFO: loading image %0s", image_path);
            $readmemh(image_path, memory);
        end
    end

    assign i_req_ready_o = !i_busy && !i_resp_valid;
    assign d_req_ready_o = !d_busy && !d_resp_valid;
    assign i_resp_valid_o = i_resp_valid;
    assign i_resp_line_addr_o = i_addr;
    assign i_resp_data_o = i_snapshot;
    assign i_resp_id_o = i_id;
    assign i_resp_error_o = i_error;
    assign d_resp_valid_o = d_resp_valid;
    assign d_resp_line_addr_o = d_addr;
    assign d_resp_data_o = d_snapshot;
    assign d_resp_id_o = d_id;
    assign d_resp_error_o = d_error;

    always @(posedge clk_i) begin
        if (reset_i) begin
            i_busy <= 1'b0; d_busy <= 1'b0;
            i_resp_valid <= 1'b0; d_resp_valid <= 1'b0;
            i_count <= 0; d_count <= 0;
        end else begin
            if (i_resp_valid && i_resp_ready_i) i_resp_valid <= 1'b0;
            if (d_resp_valid && d_resp_ready_i) begin
                d_resp_valid <= 1'b0;
                if (d_write && !d_error)
                    for (k = 0; k < 16; k = k + 1)
                        if (d_wmask[k]) memory[d_addr + k] <= d_wdata[(k*8) +: 8];
            end
            if (i_req_valid_i && i_req_ready_o) begin
                i_busy <= 1'b1; i_count <= LATENCY; i_addr <= i_req_line_addr_i; i_id <= i_req_id_i;
                i_error <= (i_req_line_addr_i[3:0] != 0) || (i_req_line_addr_i >= MEMORY_SIZE - 15);
                for (k = 0; k < 16; k = k + 1)
                    if (i_req_line_addr_i + k < MEMORY_SIZE) i_snapshot[(k*8) +: 8] <= memory[i_req_line_addr_i + k];
                    else i_snapshot[(k*8) +: 8] <= 8'h00;
            end
            if (d_req_valid_i && d_req_ready_o) begin
                d_busy <= 1'b1; d_count <= LATENCY; d_addr <= d_req_line_addr_i; d_id <= d_req_id_i;
                d_write <= d_req_write_i; d_wdata <= d_req_wdata_i; d_wmask <= d_req_wmask_i;
                d_error <= (d_req_line_addr_i[3:0] != 0) || (d_req_line_addr_i >= MEMORY_SIZE - 15);
                for (k = 0; k < 16; k = k + 1)
                    if (d_req_line_addr_i + k < MEMORY_SIZE) d_snapshot[(k*8) +: 8] <= memory[d_req_line_addr_i + k];
                    else d_snapshot[(k*8) +: 8] <= 8'h00;
            end
            if (i_busy && !i_resp_valid) begin
                if (i_count == 1) begin i_busy <= 1'b0; i_resp_valid <= 1'b1; end
                else i_count <= i_count - 1'b1;
            end
            if (d_busy && !d_resp_valid) begin
                if (d_count == 1) begin d_busy <= 1'b0; d_resp_valid <= 1'b1; end
                else d_count <= d_count - 1'b1;
            end
        end
    end
endmodule
