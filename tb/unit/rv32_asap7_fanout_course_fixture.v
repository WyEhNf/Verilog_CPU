`timescale 1ns/1ps
// A non-CPU integration fixture that must pass the unmodified course SRAM
// validation/lowering before any Liberty modules are imported.
module student_top #(
    parameter integer ENABLED = 0,
    parameter integer REGISTERED = 0
) (
    input wire clock,
    input wire reset,
    input wire control_i,
    input wire [1023:0] data_i,
    output wire [1023:0] data_o,
    input wire ram_en,
    input wire ram_we,
    input wire [3:0] ram_wmask,
    input wire [3:0] ram_addr,
    input wire [31:0] ram_wdata,
    output wire [31:0] ram_rdata
);
    generate
        if (REGISTERED != 0) begin : g_registered
            rv32_registered_fanout_fixture #(.ENABLED(ENABLED)) control_fixture(
                .clock(clock), .reset(reset), .control_i(control_i),
                .data_i(data_i), .data_o(data_o));
        end else begin : g_physical
            rv32_asap7_fanout_fixture #(.ENABLED(ENABLED)) control_fixture(
                .clock(clock), .reset(reset), .control_i(control_i),
                .data_i(data_i), .data_o(data_o));
        end
    endgenerate
    sram_fakeram #(.DEPTH(16), .WIDTH(32), .WRITE_GRANULARITY(8)) real_ram(
        .clk(clock), .en(ram_en), .we(ram_we), .wmask(ram_wmask),
        .addr(ram_addr), .wdata(ram_wdata), .rdata(ram_rdata));
endmodule
