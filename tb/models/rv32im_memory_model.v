`timescale 1ns/1ps

module rv32im_memory_model #(
    parameter integer MEMORY_SIZE = 1048576,
    parameter integer LATENCY = 50,
    parameter integer I_OUTSTANDING = 4,
    parameter integer D_OUTSTANDING = 4
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
    reg d_slot_valid [0:D_OUTSTANDING-1];
    reg d_slot_ready [0:D_OUTSTANDING-1];
    integer d_slot_count [0:D_OUTSTANDING-1];
    reg [31:0] d_slot_addr [0:D_OUTSTANDING-1];
    reg [7:0] d_slot_id [0:D_OUTSTANDING-1];
    reg [127:0] d_slot_snapshot [0:D_OUTSTANDING-1];
    reg d_slot_error [0:D_OUTSTANDING-1];
    integer d_head;
    integer d_tail;
    integer d_occupancy;

    reg i_slot_valid [0:I_OUTSTANDING-1];
    reg i_slot_ready [0:I_OUTSTANDING-1];
    integer i_slot_count [0:I_OUTSTANDING-1];
    reg [31:0] i_slot_addr [0:I_OUTSTANDING-1];
    reg [7:0] i_slot_id [0:I_OUTSTANDING-1];
    reg [127:0] i_slot_snapshot [0:I_OUTSTANDING-1];
    reg i_slot_error [0:I_OUTSTANDING-1];
    integer i_head;
    integer i_tail;
    integer i_occupancy;
    integer k;
    reg [1023:0] image_path;

    initial begin
        for (k = 0; k < MEMORY_SIZE; k = k + 1) memory[k] = 8'h00;
        if ($value$plusargs("IMAGE=%s", image_path)) begin
            $display("INFO: loading image %0s", image_path);
            $readmemh(image_path, memory);
        end
    end

    assign i_req_ready_o = (i_occupancy < I_OUTSTANDING);
    assign d_req_ready_o = (d_occupancy < D_OUTSTANDING);
    assign i_resp_valid_o = (i_occupancy > 0) && i_slot_ready[i_head];
    assign i_resp_line_addr_o = (i_occupancy > 0) ? i_slot_addr[i_head] : 32'd0;
    assign i_resp_data_o = (i_occupancy > 0) ? i_slot_snapshot[i_head] : 128'd0;
    assign i_resp_id_o = (i_occupancy > 0) ? i_slot_id[i_head] : 8'd0;
    assign i_resp_error_o = (i_occupancy > 0) ? i_slot_error[i_head] : 1'b0;
    assign d_resp_valid_o = (d_occupancy > 0) && d_slot_ready[d_head];
    assign d_resp_line_addr_o = (d_occupancy > 0) ? d_slot_addr[d_head] : 32'd0;
    assign d_resp_data_o = (d_occupancy > 0) ? d_slot_snapshot[d_head] : 128'd0;
    assign d_resp_id_o = (d_occupancy > 0) ? d_slot_id[d_head] : 8'd0;
    assign d_resp_error_o = (d_occupancy > 0) ? d_slot_error[d_head] : 1'b0;

    always @(posedge clk_i) begin
        if (reset_i) begin
            i_head <= 0;
            i_tail <= 0;
            i_occupancy <= 0;
            for (k = 0; k < I_OUTSTANDING; k = k + 1) begin
                i_slot_valid[k] <= 1'b0;
                i_slot_ready[k] <= 1'b0;
                i_slot_count[k] <= 0;
                i_slot_addr[k] <= 32'd0;
                i_slot_id[k] <= 8'd0;
                i_slot_snapshot[k] <= 128'd0;
                i_slot_error[k] <= 1'b0;
            end
            d_head <= 0;
            d_tail <= 0;
            d_occupancy <= 0;
            for (k = 0; k < D_OUTSTANDING; k = k + 1) begin
                d_slot_valid[k] <= 1'b0;
                d_slot_ready[k] <= 1'b0;
                d_slot_count[k] <= 0;
                d_slot_addr[k] <= 32'd0;
                d_slot_id[k] <= 8'd0;
                d_slot_snapshot[k] <= 128'd0;
                d_slot_error[k] <= 1'b0;
            end
        end else begin
            if (i_req_valid_i && i_req_ready_o) begin
                i_slot_valid[i_tail] <= 1'b1;
                i_slot_ready[i_tail] <= 1'b0;
                // The acceptance edge is cycle one of the externally visible
                // latency, matching the original single-entry model.
                i_slot_count[i_tail] <= (LATENCY > 1) ? (LATENCY-1) : 1;
                i_slot_addr[i_tail] <= i_req_line_addr_i;
                i_slot_id[i_tail] <= i_req_id_i;
                i_slot_error[i_tail] <= (i_req_line_addr_i[3:0] != 0) ||
                                        (i_req_line_addr_i >= MEMORY_SIZE - 15);
                for (k = 0; k < 16; k = k + 1)
                    if (i_req_line_addr_i + k < MEMORY_SIZE)
                        i_slot_snapshot[i_tail][(k*8) +: 8] <= memory[i_req_line_addr_i + k];
                    else
                        i_slot_snapshot[i_tail][(k*8) +: 8] <= 8'h00;
                if (i_tail == I_OUTSTANDING-1)
                    i_tail <= 0;
                else
                    i_tail <= i_tail + 1;
            end
            if (d_req_valid_i && d_req_ready_o) begin
                d_slot_valid[d_tail] <= 1'b1;
                d_slot_ready[d_tail] <= 1'b0;
                d_slot_count[d_tail] <= (LATENCY > 1) ? (LATENCY-1) : 1;
                d_slot_addr[d_tail] <= d_req_line_addr_i;
                d_slot_id[d_tail] <= d_req_id_i;
                d_slot_error[d_tail] <= (d_req_line_addr_i[3:0] != 0) ||
                                        (d_req_line_addr_i >= MEMORY_SIZE - 15);
                for (k = 0; k < 16; k = k + 1)
                    if (d_req_line_addr_i + k < MEMORY_SIZE)
                        d_slot_snapshot[d_tail][(k*8) +: 8] <= memory[d_req_line_addr_i + k];
                    else
                        d_slot_snapshot[d_tail][(k*8) +: 8] <= 8'h00;
                // Apply accepted writes in request order.  This makes a later
                // queued read observe every older write while the completion
                // response still retains the configured fixed latency.
                if (d_req_write_i &&
                    (d_req_line_addr_i[3:0] == 0) &&
                    (d_req_line_addr_i < MEMORY_SIZE - 15)) begin
                    for (k = 0; k < 16; k = k + 1)
                        if (d_req_wmask_i[k])
                            memory[d_req_line_addr_i + k] <= d_req_wdata_i[(k*8) +: 8];
                end
                if (d_tail == D_OUTSTANDING-1)
                    d_tail <= 0;
                else
                    d_tail <= d_tail + 1;
            end
            for (k = 0; k < I_OUTSTANDING; k = k + 1) begin
                if (i_slot_valid[k] && !i_slot_ready[k]) begin
                    if (i_slot_count[k] == 1)
                        i_slot_ready[k] <= 1'b1;
                    else
                        i_slot_count[k] <= i_slot_count[k] - 1;
                end
            end
            if (i_resp_valid_o && i_resp_ready_i) begin
                i_slot_valid[i_head] <= 1'b0;
                i_slot_ready[i_head] <= 1'b0;
                if (i_head == I_OUTSTANDING-1)
                    i_head <= 0;
                else
                    i_head <= i_head + 1;
            end
            case ({(i_req_valid_i && i_req_ready_o),
                   (i_resp_valid_o && i_resp_ready_i)})
                2'b10: i_occupancy <= i_occupancy + 1;
                2'b01: i_occupancy <= i_occupancy - 1;
                default: i_occupancy <= i_occupancy;
            endcase
            for (k = 0; k < D_OUTSTANDING; k = k + 1) begin
                if (d_slot_valid[k] && !d_slot_ready[k]) begin
                    if (d_slot_count[k] == 1)
                        d_slot_ready[k] <= 1'b1;
                    else
                        d_slot_count[k] <= d_slot_count[k] - 1;
                end
            end
            if (d_resp_valid_o && d_resp_ready_i) begin
                d_slot_valid[d_head] <= 1'b0;
                d_slot_ready[d_head] <= 1'b0;
                if (d_head == D_OUTSTANDING-1)
                    d_head <= 0;
                else
                    d_head <= d_head + 1;
            end
            case ({(d_req_valid_i && d_req_ready_o),
                   (d_resp_valid_o && d_resp_ready_i)})
                2'b10: d_occupancy <= d_occupancy + 1;
                2'b01: d_occupancy <= d_occupancy - 1;
                default: d_occupancy <= d_occupancy;
            endcase
        end
    end

    initial begin
        if (I_OUTSTANDING < 1) begin
            $display("ERROR: memory model I_OUTSTANDING must be positive");
            $finish;
        end
        if (D_OUTSTANDING < 1) begin
            $display("ERROR: memory model D_OUTSTANDING must be positive");
            $finish;
        end
    end
endmodule
