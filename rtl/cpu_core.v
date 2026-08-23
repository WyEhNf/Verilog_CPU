`timescale 1ns/1ps
`include "rv32im_defs.vh"

// H-00 top-level stub. Functional pipeline state is added by later plan steps.
module cpu_core #(
    parameter integer FE_WIDTH = `RV32IM_FE_WIDTH_DEFAULT,
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer PHYS_REGS = `RV32IM_PHYS_REGS_DEFAULT,
    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT
) (
    input  wire       clk,
    input  wire       reset,
    output reg        halted,
    output reg        error,
    output reg [7:0]  return_value
);

    initial begin
        if ((FE_WIDTH != 1) && (FE_WIDTH != 2) && (FE_WIDTH != 4)) begin
            $display("ERROR: invalid FE_WIDTH=%0d; expected 1, 2, or 4", FE_WIDTH);
            $finish;
        end
        if ((BE_WIDTH != 1) && (BE_WIDTH != 2) && (BE_WIDTH != 4)) begin
            $display("ERROR: invalid BE_WIDTH=%0d; expected 1, 2, or 4", BE_WIDTH);
            $finish;
        end
        if (PHYS_REGS < 33) begin
            $display("ERROR: invalid PHYS_REGS=%0d; expected at least 33", PHYS_REGS);
            $finish;
        end
        if ((ROB_ENTRIES < 2) || ((ROB_ENTRIES & (ROB_ENTRIES - 1)) != 0)) begin
            $display("ERROR: invalid ROB_ENTRIES=%0d; expected a power of two", ROB_ENTRIES);
            $finish;
        end
    end

    always @(posedge clk) begin
        if (reset) begin
            halted       <= 1'b0;
            error        <= 1'b0;
            return_value <= 8'd0;
        end
    end

endmodule
