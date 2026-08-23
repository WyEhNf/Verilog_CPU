`timescale 1ns/1ps

module cpu_core_matrix_tb;
    reg clk;
    reg reset;
    wire [8:0] halted;
    wire [8:0] error;

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    initial begin
        reset = 1'b1;
        #12;
        reset = 1'b0;
        #8;
        if ((|halted) || (|error)) begin
            $display("FAIL: supported parameter matrix did not reset cleanly");
            $finish(1);
        end
        $display("PASS: H-00 FE/BE width matrix");
        $finish(0);
    end

    cpu_core #(.FE_WIDTH(1), .BE_WIDTH(1), .PHYS_REGS(64), .ROB_ENTRIES(32)) c11
        (.clk(clk), .reset(reset), .halted(halted[0]), .error(error[0]), .return_value());
    cpu_core #(.FE_WIDTH(1), .BE_WIDTH(2), .PHYS_REGS(64), .ROB_ENTRIES(32)) c12
        (.clk(clk), .reset(reset), .halted(halted[1]), .error(error[1]), .return_value());
    cpu_core #(.FE_WIDTH(1), .BE_WIDTH(4), .PHYS_REGS(64), .ROB_ENTRIES(32)) c14
        (.clk(clk), .reset(reset), .halted(halted[2]), .error(error[2]), .return_value());
    cpu_core #(.FE_WIDTH(2), .BE_WIDTH(1), .PHYS_REGS(64), .ROB_ENTRIES(32)) c21
        (.clk(clk), .reset(reset), .halted(halted[3]), .error(error[3]), .return_value());
    cpu_core #(.FE_WIDTH(2), .BE_WIDTH(2), .PHYS_REGS(64), .ROB_ENTRIES(32)) c22
        (.clk(clk), .reset(reset), .halted(halted[4]), .error(error[4]), .return_value());
    cpu_core #(.FE_WIDTH(2), .BE_WIDTH(4), .PHYS_REGS(64), .ROB_ENTRIES(32)) c24
        (.clk(clk), .reset(reset), .halted(halted[5]), .error(error[5]), .return_value());
    cpu_core #(.FE_WIDTH(4), .BE_WIDTH(1), .PHYS_REGS(64), .ROB_ENTRIES(32)) c41
        (.clk(clk), .reset(reset), .halted(halted[6]), .error(error[6]), .return_value());
    cpu_core #(.FE_WIDTH(4), .BE_WIDTH(2), .PHYS_REGS(64), .ROB_ENTRIES(32)) c42
        (.clk(clk), .reset(reset), .halted(halted[7]), .error(error[7]), .return_value());
    cpu_core #(.FE_WIDTH(4), .BE_WIDTH(4), .PHYS_REGS(96), .ROB_ENTRIES(64)) c44
        (.clk(clk), .reset(reset), .halted(halted[8]), .error(error[8]), .return_value());

endmodule
