`timescale 1ns/1ps

module cpu_core_invalid_tb #(
    parameter integer FE_WIDTH = 1,
    parameter integer BE_WIDTH = 1,
    parameter integer PHYS_REGS = 64,
    parameter integer ROB_ENTRIES = 32
);
    reg clk;
    reg reset;

    initial begin
        clk = 1'b0;
        reset = 1'b0;
        #20;
        $display("FAIL: invalid configuration was not rejected");
        $finish(1);
    end

    always #5 clk = ~clk;

    cpu_core #(
        .FE_WIDTH(FE_WIDTH),
        .BE_WIDTH(BE_WIDTH),
        .PHYS_REGS(PHYS_REGS),
        .ROB_ENTRIES(ROB_ENTRIES)
    ) dut (
        .clk(clk),
        .reset(reset),
        .halted(),
        .error(),
        .return_value()
    );
endmodule
