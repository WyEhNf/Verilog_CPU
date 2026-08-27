`timescale 1ns/1ps

module cpu_core_join01_tb;
    reg clk;
    reg reset;
    wire halted;
    wire error;
    wire [7:0] return_value;
    wire [31:0] cycles;
    wire [31:0] instret;

    wire mem_i_req_valid;
    wire mem_i_req_ready;
    wire [31:0] mem_i_req_line_addr;
    wire [7:0] mem_i_req_id;
    wire mem_i_resp_valid;
    wire mem_i_resp_ready;
    wire [31:0] mem_i_resp_line_addr;
    wire [127:0] mem_i_resp_data;
    wire [7:0] mem_i_resp_id;
    wire mem_i_resp_error;
    wire mem_d_req_valid;
    wire mem_d_req_ready;
    wire mem_d_req_write;
    wire [31:0] mem_d_req_line_addr;
    wire [127:0] mem_d_req_wdata;
    wire [15:0] mem_d_req_wmask;
    wire [7:0] mem_d_req_id;
    wire mem_d_resp_valid;
    wire mem_d_resp_ready;
    wire [31:0] mem_d_resp_line_addr;
    wire [127:0] mem_d_resp_data;
    wire [7:0] mem_d_resp_id;
    wire mem_d_resp_error;

    cpu_core dut (
        .clk(clk), .reset(reset), .halted(halted), .error(error),
        .return_value(return_value), .cycles(cycles), .instret(instret),
        .mem_i_req_valid(mem_i_req_valid), .mem_i_req_ready(mem_i_req_ready),
        .mem_i_req_line_addr(mem_i_req_line_addr), .mem_i_req_id(mem_i_req_id),
        .mem_i_resp_valid(mem_i_resp_valid), .mem_i_resp_ready(mem_i_resp_ready),
        .mem_i_resp_line_addr(mem_i_resp_line_addr), .mem_i_resp_data(mem_i_resp_data),
        .mem_i_resp_id(mem_i_resp_id), .mem_i_resp_error(mem_i_resp_error),
        .mem_d_req_valid(mem_d_req_valid), .mem_d_req_ready(mem_d_req_ready),
        .mem_d_req_write(mem_d_req_write), .mem_d_req_line_addr(mem_d_req_line_addr),
        .mem_d_req_wdata(mem_d_req_wdata), .mem_d_req_wmask(mem_d_req_wmask),
        .mem_d_req_id(mem_d_req_id), .mem_d_resp_valid(mem_d_resp_valid),
        .mem_d_resp_ready(mem_d_resp_ready), .mem_d_resp_line_addr(mem_d_resp_line_addr),
        .mem_d_resp_data(mem_d_resp_data), .mem_d_resp_id(mem_d_resp_id),
        .mem_d_resp_error(mem_d_resp_error)
    );

    rv32im_memory_model memory (
        .clk_i(clk), .reset_i(reset),
        .i_req_valid_i(mem_i_req_valid), .i_req_ready_o(mem_i_req_ready),
        .i_req_line_addr_i(mem_i_req_line_addr), .i_req_id_i(mem_i_req_id),
        .i_resp_valid_o(mem_i_resp_valid), .i_resp_ready_i(mem_i_resp_ready),
        .i_resp_line_addr_o(mem_i_resp_line_addr), .i_resp_data_o(mem_i_resp_data),
        .i_resp_id_o(mem_i_resp_id), .i_resp_error_o(mem_i_resp_error),
        .d_req_valid_i(mem_d_req_valid), .d_req_ready_o(mem_d_req_ready),
        .d_req_write_i(mem_d_req_write), .d_req_line_addr_i(mem_d_req_line_addr),
        .d_req_wdata_i(mem_d_req_wdata), .d_req_wmask_i(mem_d_req_wmask),
        .d_req_id_i(mem_d_req_id), .d_resp_valid_o(mem_d_resp_valid),
        .d_resp_ready_i(mem_d_resp_ready), .d_resp_line_addr_o(mem_d_resp_line_addr),
        .d_resp_data_o(mem_d_resp_data), .d_resp_id_o(mem_d_resp_id),
        .d_resp_error_o(mem_d_resp_error)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    initial begin
        reset = 1'b1;
        memory.memory[0] = 8'h13;
        memory.memory[1] = 8'h05;
        memory.memory[2] = 8'h70;
        memory.memory[3] = 8'h00;
        memory.memory[4] = 8'h13;
        memory.memory[5] = 8'h05;
        memory.memory[6] = 8'hf0;
        memory.memory[7] = 8'h0f;
        #12;
        reset = 1'b0;
        wait (halted || error);
        if (error || !halted || return_value !== 8'd7 || instret < 2) begin
            $display("FAIL: JOIN-01 ADDI/HALT halted=%b error=%b return=%0d instret=%0d cycles=%0d", halted, error, return_value, instret, cycles);
            $finish(1);
        end
        $display("PASS: JOIN-01 ADDI/HALT end-to-end return=%0d instret=%0d cycles=%0d", return_value, instret, cycles);
        $finish(0);
    end

    initial begin
        #100000;
        $display("FAIL: JOIN-01 ADDI/HALT timeout");
        $finish(1);
    end
endmodule
