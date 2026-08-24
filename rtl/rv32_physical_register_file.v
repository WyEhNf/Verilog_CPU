`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Physical register file for the rename/issue boundary.
//
// Ports are flattened in lane order: lane n occupies the slice beginning at
// n*width.  A write in the highest numbered lane wins when multiple valid
// writes target the same physical register in one cycle.
module rv32_physical_register_file #(
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer PHYS_REGS = `RV32IM_PHYS_REGS_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = (PHYS_REGS <= 1) ? 1 : $clog2(PHYS_REGS)
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire [(2*BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] read_phys_i,
    output reg  [(2*BE_WIDTH*32)-1:0]   read_data_o,
    output reg  [(2*BE_WIDTH)-1:0]      read_ready_o,
    input  wire [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] write_phys_i,
    input  wire [(BE_WIDTH*32)-1:0]      write_data_i,
    input  wire [BE_WIDTH-1:0]           write_valid_i
);
    reg [(PHYS_REGS*32)-1:0] value;
    reg [PHYS_REGS-1:0] ready;
    integer reset_index;
    integer write_lane;

    initial begin
        if ((BE_WIDTH != 1) && (BE_WIDTH != 2) && (BE_WIDTH != 4)) begin
            $display("ERROR: invalid PRF BE_WIDTH=%0d; expected 1, 2, or 4", BE_WIDTH);
            $finish;
        end
        if (PHYS_REGS < 33) begin
            $display("ERROR: invalid PRF PHYS_REGS=%0d; expected at least 33", PHYS_REGS);
            $finish;
        end
        if (PHYS_ADDR_WIDTH < $clog2(PHYS_REGS)) begin
            $display("ERROR: invalid PRF PHYS_ADDR_WIDTH=%0d for PHYS_REGS=%0d", PHYS_ADDR_WIDTH, PHYS_REGS);
            $finish;
        end
    end

    // Reads are combinational.  Each generated process has constant part
    // selects, avoiding simulator ambiguity around variable slice sensitivity.
    genvar read_port;
    generate
        for (read_port = 0; read_port < (2*BE_WIDTH); read_port = read_port + 1) begin : g_read_port
            integer bypass_lane;
            always @(read_phys_i or write_phys_i or write_data_i or write_valid_i or value or ready) begin
                read_data_o[(read_port*32) +: 32] = 32'b0;
                read_ready_o[read_port] = 1'b0;
                if (read_phys_i[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] == 0) begin
                    read_ready_o[read_port] = 1'b1;
                end else if (read_phys_i[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] < PHYS_REGS) begin
                    read_data_o[(read_port*32) +: 32] = value[(read_phys_i[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]*32) +: 32];
                    read_ready_o[read_port] = ready[read_phys_i[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]];
                    for (bypass_lane = 0; bypass_lane < BE_WIDTH; bypass_lane = bypass_lane + 1) begin
                        if (write_valid_i[bypass_lane] &&
                            (write_phys_i[(bypass_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] ==
                             read_phys_i[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH])) begin
                            read_data_o[(read_port*32) +: 32] = write_data_i[(bypass_lane*32) +: 32];
                            read_ready_o[read_port] = 1'b1;
                        end
                    end
                end
            end
        end
    endgenerate

    always @(posedge clk_i) begin
        if (reset_i) begin
            for (reset_index = 0; reset_index < PHYS_REGS; reset_index = reset_index + 1) begin
                value[(reset_index*32) +: 32] <= 32'b0;
                ready[reset_index] <= (reset_index == 0);
            end
        end else begin
            // Iterating low-to-high makes the highest lane deterministic.
            // P0 is hardwired and out-of-range encoded addresses are ignored.
            for (write_lane = 0; write_lane < BE_WIDTH; write_lane = write_lane + 1) begin
                if (write_valid_i[write_lane] &&
                    (write_phys_i[(write_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] != 0) &&
                    (write_phys_i[(write_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] < PHYS_REGS)) begin
                    value[(write_phys_i[(write_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]*32) +: 32] <= write_data_i[(write_lane*32) +: 32];
                    ready[write_phys_i[(write_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]] <= 1'b1;
                end
            end
            value[31:0] <= 32'b0;
            ready[0] <= 1'b1;
        end
    end
endmodule
