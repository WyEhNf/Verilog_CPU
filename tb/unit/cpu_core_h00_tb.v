`timescale 1ns/1ps

module cpu_core_h00_tb #(
    parameter integer FE_WIDTH = 1,
    parameter integer BE_WIDTH = 1,
    parameter integer PHYS_REGS = 64,
    parameter integer ROB_ENTRIES = 32
);

    reg clk;
    reg reset;
    wire halted;
    wire error;
    wire [7:0] return_value;

    cpu_core #(
        .FE_WIDTH(FE_WIDTH),
        .BE_WIDTH(BE_WIDTH),
        .PHYS_REGS(PHYS_REGS),
        .ROB_ENTRIES(ROB_ENTRIES)
    ) dut (
        .clk(clk),
        .reset(reset),
        .halted(halted),
        .error(error),
        .return_value(return_value)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    initial begin
        reset = 1'b1;
        #12;
        if ((halted !== 1'b0) || (error !== 1'b0) || (return_value !== 8'd0)) begin
            $display("FAIL: reset outputs are not deterministic");
            $finish(1);
        end
        reset = 1'b0;
        #8;
        $display("PASS: H-00 default elaboration and reset");
        $finish(0);
    end

endmodule
