`timescale 1ns/1ps

// Transaction bridge between the caches and the independent line ports.  The
// instruction side is deliberately transparent so a non-blocking I-cache can
// keep several tagged reads in flight.  The data side retains its one-entry
// ordered transaction buffer until the D-cache grows multiple MSHRs.
module rv32_memory_bridge #(
    parameter integer MEMORY_SIZE = 1048576
) (
    input  wire         clk_i,
    input  wire         reset_i,

    input  wire         cache_i_req_valid_i,
    output wire         cache_i_req_ready_o,
    input  wire [31:0]  cache_i_req_line_addr_i,
    input  wire [7:0]   cache_i_req_id_i,
    output wire         cache_i_resp_valid_o,
    input  wire         cache_i_resp_ready_i,
    output wire [31:0]  cache_i_resp_line_addr_o,
    output wire [127:0] cache_i_resp_data_o,
    output wire [7:0]   cache_i_resp_id_o,
    output wire         cache_i_resp_error_o,

    input  wire         cache_d_req_valid_i,
    output wire         cache_d_req_ready_o,
    input  wire         cache_d_req_write_i,
    input  wire [31:0]  cache_d_req_line_addr_i,
    input  wire [127:0] cache_d_req_wdata_i,
    input  wire [15:0]  cache_d_req_wmask_i,
    input  wire [7:0]   cache_d_req_id_i,
    output wire         cache_d_resp_valid_o,
    input  wire         cache_d_resp_ready_i,
    output wire [31:0]  cache_d_resp_line_addr_o,
    output wire [127:0] cache_d_resp_data_o,
    output wire [7:0]   cache_d_resp_id_o,
    output wire         cache_d_resp_error_o,

    output wire         mem_i_req_valid_o,
    input  wire         mem_i_req_ready_i,
    output wire [31:0]  mem_i_req_line_addr_o,
    output wire [7:0]   mem_i_req_id_o,
    input  wire         mem_i_resp_valid_i,
    output wire         mem_i_resp_ready_o,
    input  wire [31:0]  mem_i_resp_line_addr_i,
    input  wire [127:0] mem_i_resp_data_i,
    input  wire [7:0]   mem_i_resp_id_i,
    input  wire         mem_i_resp_error_i,

    output wire         mem_d_req_valid_o,
    input  wire         mem_d_req_ready_i,
    output wire         mem_d_req_write_o,
    output wire [31:0]  mem_d_req_line_addr_o,
    output wire [127:0] mem_d_req_wdata_o,
    output wire [15:0]  mem_d_req_wmask_o,
    output wire [7:0]   mem_d_req_id_o,
    input  wire         mem_d_resp_valid_i,
    output wire         mem_d_resp_ready_o,
    input  wire [31:0]  mem_d_resp_line_addr_i,
    input  wire [127:0] mem_d_resp_data_i,
    input  wire [7:0]   mem_d_resp_id_i,
    input  wire         mem_d_resp_error_i,

    output wire         event_i_mem_request_o,
    output wire         event_d_mem_read_o,
    output wire         event_d_mem_write_o
);
    localparam [31:0] MEMORY_SIZE_U = MEMORY_SIZE;

    reg i_local_error;
    reg [31:0] i_line_addr;
    reg [7:0] i_id;

    reg d_active;
    reg d_request_sent;
    reg d_local_error;
    reg d_write;
    reg [31:0] d_line_addr;
    reg [127:0] d_wdata;
    reg [15:0] d_wmask;
    reg [7:0] d_id;

    wire i_line_valid = line_address_valid(cache_i_req_line_addr_i);
    wire i_cache_req_fire = cache_i_req_valid_i && cache_i_req_ready_o;
    wire d_cache_req_fire = cache_d_req_valid_i && cache_d_req_ready_o;
    wire i_mem_req_fire = mem_i_req_valid_o && mem_i_req_ready_i;
    wire d_mem_req_fire = mem_d_req_valid_o && mem_d_req_ready_i;
    wire d_response_match = (mem_d_resp_line_addr_i == d_line_addr) &&
                            (mem_d_resp_id_i == d_id);
    wire d_mem_resp_fire = mem_d_resp_valid_i && mem_d_resp_ready_o;
    wire i_local_resp_fire = i_local_error && cache_i_resp_ready_i;
    wire d_local_resp_fire = d_local_error && cache_d_resp_ready_i;

    function line_address_valid;
        input [31:0] address;
        begin
            line_address_valid = (address[3:0] == 4'd0) && (address < MEMORY_SIZE_U);
        end
    endfunction

    assign cache_i_req_ready_o = !reset_i && !i_local_error &&
                                 (i_line_valid ? mem_i_req_ready_i : 1'b1);
    assign cache_d_req_ready_o = !reset_i && !d_active && !d_local_error;

    assign mem_i_req_valid_o = !reset_i && !i_local_error &&
                               cache_i_req_valid_i && i_line_valid;
    assign mem_i_req_line_addr_o = cache_i_req_line_addr_i;
    assign mem_i_req_id_o = cache_i_req_id_i;
    assign mem_d_req_valid_o = d_active && !d_request_sent;
    assign mem_d_req_write_o = d_write;
    assign mem_d_req_line_addr_o = d_line_addr;
    assign mem_d_req_wdata_o = d_wdata;
    assign mem_d_req_wmask_o = d_wmask;
    assign mem_d_req_id_o = d_id;

    assign cache_i_resp_valid_o = i_local_error || mem_i_resp_valid_i;
    assign cache_i_resp_line_addr_o = i_local_error ? i_line_addr : mem_i_resp_line_addr_i;
    assign cache_i_resp_data_o = i_local_error ? 128'd0 : mem_i_resp_data_i;
    assign cache_i_resp_id_o = i_local_error ? i_id : mem_i_resp_id_i;
    assign cache_i_resp_error_o = i_local_error || mem_i_resp_error_i;
    assign mem_i_resp_ready_o = !i_local_error && cache_i_resp_ready_i;

    assign cache_d_resp_valid_o = d_local_error ||
                                  (d_active && d_request_sent && mem_d_resp_valid_i);
    assign cache_d_resp_line_addr_o = (d_local_error || d_active) ? d_line_addr : 32'd0;
    assign cache_d_resp_data_o = d_local_error ? 128'd0 :
                                 ((d_active && d_request_sent && d_response_match) ? mem_d_resp_data_i : 128'd0);
    assign cache_d_resp_id_o = (d_local_error || d_active) ? d_id : 8'd0;
    assign cache_d_resp_error_o = d_local_error ||
                                  (d_active && d_request_sent && mem_d_resp_valid_i &&
                                   (mem_d_resp_error_i || !d_response_match));
    assign mem_d_resp_ready_o = d_active && d_request_sent && cache_d_resp_ready_i;

    assign event_i_mem_request_o = i_mem_req_fire;
    assign event_d_mem_read_o = d_mem_req_fire && !d_write;
    assign event_d_mem_write_o = d_mem_req_fire && d_write;

    always @(posedge clk_i) begin
        if (reset_i) begin
            i_local_error <= 1'b0;
            i_line_addr <= 32'd0;
            i_id <= 8'd0;
            d_active <= 1'b0;
            d_request_sent <= 1'b0;
            d_local_error <= 1'b0;
            d_write <= 1'b0;
            d_line_addr <= 32'd0;
            d_wdata <= 128'd0;
            d_wmask <= 16'd0;
            d_id <= 8'd0;
        end else begin
            if (i_cache_req_fire) begin
                i_line_addr <= cache_i_req_line_addr_i;
                i_id <= cache_i_req_id_i;
                if (!i_line_valid)
                    i_local_error <= 1'b1;
            end
            if (d_cache_req_fire) begin
                d_write <= cache_d_req_write_i;
                d_line_addr <= cache_d_req_line_addr_i;
                d_wdata <= cache_d_req_wdata_i;
                d_wmask <= cache_d_req_wmask_i;
                d_id <= cache_d_req_id_i;
                if (line_address_valid(cache_d_req_line_addr_i)) begin
                    d_active <= 1'b1;
                    d_request_sent <= 1'b0;
                end else begin
                    d_local_error <= 1'b1;
                end
            end
            if (d_mem_req_fire)
                d_request_sent <= 1'b1;
            if (d_mem_resp_fire) begin
                d_active <= 1'b0;
                d_request_sent <= 1'b0;
            end
            if (i_local_resp_fire)
                i_local_error <= 1'b0;
            if (d_local_resp_fire)
                d_local_error <= 1'b0;
        end
    end

    initial begin
        if (MEMORY_SIZE < 16 || (MEMORY_SIZE % 16) != 0) begin
            $display("ERROR: memory bridge MEMORY_SIZE must be a positive multiple of 16 (got %0d)", MEMORY_SIZE);
            $finish;
        end
    end
endmodule
