`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32i_alu_tb;
    localparam integer TAGW = `RV32IM_ROB_TAG_WIDTH_DEFAULT;
    localparam integer PAW = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT;
    localparam integer EW = `RV32IM_EPOCH_WIDTH;
    reg clk, reset, flush;
    reg issue_valid, exec_ready;
    reg [`RV32IM_OP_WIDTH-1:0] issue_op;
    reg [31:0] issue_pc, issue_imm, issue_src1, issue_src2;
    reg [127:0] issue_store_data;
    reg [PAW-1:0] issue_phys_rd;
    reg [TAGW-1:0] issue_tag;
    reg [EW-1:0] issue_epoch;
    reg issue_target_live, issue_pred_taken, issue_mem_unsigned;
    reg [31:0] issue_pred_target;
    reg [1:0] issue_pred_kind, issue_mem_size;
    wire issue_ready, exec_valid, exec_rd_we, exec_is_branch, exec_branch_taken;
    wire exec_redirect_valid, exec_is_memory, exec_is_load, exec_is_store, exec_mem_unsigned;
    wire [31:0] exec_value, exec_branch_target, exec_redirect_pc, exec_mem_addr;
    wire [PAW-1:0] exec_phys_rd;
    wire [TAGW-1:0] exec_tag;
    wire [EW-1:0] exec_epoch;
    wire [1:0] exec_mem_size;
    wire [127:0] exec_store_data;
    reg live_tag_valid;
    reg [TAGW-1:0] live_tag;
    integer bad;

    rv32i_alu dut (
        .clk_i(clk), .reset_i(reset), .flush_i(flush), .issue_valid_i(issue_valid), .issue_ready_o(issue_ready),
        .issue_op_i(issue_op), .issue_pc_i(issue_pc), .issue_imm_i(issue_imm), .issue_src1_value_i(issue_src1),
        .issue_src2_value_i(issue_src2), .issue_store_data_i(issue_store_data), .issue_phys_rd_i(issue_phys_rd),
        .issue_rob_tag_i(issue_tag), .issue_epoch_i(issue_epoch), .issue_target_live_i(issue_target_live),
        .issue_pred_taken_i(issue_pred_taken), .issue_pred_target_i(issue_pred_target), .issue_pred_kind_i(issue_pred_kind),
        .issue_mem_size_i(issue_mem_size), .issue_mem_unsigned_i(issue_mem_unsigned), .exec_valid_o(exec_valid),
        .exec_ready_i(exec_ready), .exec_value_o(exec_value), .exec_phys_rd_o(exec_phys_rd), .exec_rob_tag_o(exec_tag),
        .exec_epoch_o(exec_epoch), .exec_rd_we_o(exec_rd_we), .exec_is_branch_o(exec_is_branch),
        .exec_branch_taken_o(exec_branch_taken), .exec_branch_target_o(exec_branch_target),
        .exec_redirect_valid_o(exec_redirect_valid), .exec_redirect_pc_o(exec_redirect_pc),
        .exec_is_memory_o(exec_is_memory), .exec_is_load_o(exec_is_load), .exec_is_store_o(exec_is_store),
        .exec_mem_addr_o(exec_mem_addr), .exec_mem_size_o(exec_mem_size), .exec_mem_unsigned_o(exec_mem_unsigned),
        .exec_store_data_o(exec_store_data), .live_tag_valid_i(live_tag_valid), .live_tag_i(live_tag)
    );
    initial begin clk = 0; forever #5 clk = ~clk; end

    task clear_issue;
        begin issue_valid = 0; issue_op = 0; issue_pc = 0; issue_imm = 0; issue_src1 = 0; issue_src2 = 0; issue_store_data = 0; issue_phys_rd = 0; issue_tag = 16'h0101; issue_epoch = 0; issue_target_live = 1; issue_pred_taken = 0; issue_pred_target = 0; issue_pred_kind = 0; issue_mem_size = `RV32IM_MEM_WORD; issue_mem_unsigned = 0; end
    endtask
    task issue_and_check;
        input [5:0] op; input [31:0] pc; input [31:0] imm; input [31:0] s1; input [31:0] s2; input [31:0] expected; input integer rdwe;
        begin
            while (!issue_ready) @(posedge clk);
            issue_op = op; issue_pc = pc; issue_imm = imm; issue_src1 = s1; issue_src2 = s2; issue_valid = 1; @(posedge clk); #1; issue_valid = 0; #1;
            if (!exec_valid || exec_value !== expected || exec_rd_we !== rdwe) bad = bad + 1;
            @(posedge clk); #1;
        end
    endtask
    initial begin
        bad = 0; reset = 1; flush = 0; exec_ready = 1; live_tag_valid = 0; live_tag = 0; clear_issue(); #12; reset = 0; #1;
        issue_and_check(`RV32IM_OP_ADD, 0, 0, 32'd7, 32'd9, 32'd16, 1);
        issue_and_check(`RV32IM_OP_SUB, 0, 0, 32'd7, 32'd9, 32'hfffffffe, 1);
        issue_and_check(`RV32IM_OP_ADDI, 0, -32'sd3, 32'd7, 0, 32'd4, 1);
        issue_and_check(`RV32IM_OP_XOR, 0, 0, 32'h55aa, 32'h0f0f, 32'h5aa5, 1);
        issue_and_check(`RV32IM_OP_OR, 0, 0, 32'h5500, 32'h00aa, 32'h55aa, 1);
        issue_and_check(`RV32IM_OP_AND, 0, 0, 32'h55aa, 32'h0f0f, 32'h050a, 1);
        issue_and_check(`RV32IM_OP_XORI, 0, 32'h0f0f, 32'h5500, 0, 32'h5a0f, 1);
        issue_and_check(`RV32IM_OP_ORI, 0, 32'h00aa, 32'h5500, 0, 32'h55aa, 1);
        issue_and_check(`RV32IM_OP_ANDI, 0, 32'h0f0f, 32'h55aa, 0, 32'h050a, 1);
        issue_and_check(`RV32IM_OP_LUI, 0, 32'h12345000, 0, 0, 32'h12345000, 1);
        issue_and_check(`RV32IM_OP_AUIPC, 32'h1000, 32'h00012000, 0, 0, 32'h00013000, 1);
        issue_and_check(`RV32IM_OP_SLLI, 0, 32, 32'h1, 32'h0, 32'h1, 1);
        issue_and_check(`RV32IM_OP_SLL, 0, 0, 32'h1, 32'h20, 32'h1, 1);
        issue_and_check(`RV32IM_OP_SRLI, 0, 31, 32'h80000000, 0, 1, 1);
        issue_and_check(`RV32IM_OP_SRAI, 0, 1, 32'h80000000, 0, 32'hc0000000, 1);
        issue_and_check(`RV32IM_OP_SRL, 0, 0, 32'h80000000, 32'h20, 32'h80000000, 1);
        issue_and_check(`RV32IM_OP_SRA, 0, 0, 32'h80000000, 32'h20, 32'h80000000, 1);
        issue_and_check(`RV32IM_OP_SLT, 0, 0, 32'hffffffff, 1, 1, 1);
        issue_and_check(`RV32IM_OP_SLTU, 0, 0, 32'hffffffff, 1, 0, 1);
        issue_and_check(`RV32IM_OP_SLTI, 0, -32'sd1, 32'hffffffff, 0, 0, 1);
        issue_and_check(`RV32IM_OP_SLTIU, 0, 1, 32'h0, 0, 1, 1);

        clear_issue(); issue_op = `RV32IM_OP_BEQ; issue_pc = 32'h100; issue_imm = 32'h20; issue_src1 = 4; issue_src2 = 4; issue_pred_taken = 1; issue_pred_target = 32'h120; issue_valid = 1; @(posedge clk); #1; issue_valid = 0;
        if (!exec_valid || !exec_is_branch || !exec_branch_taken || exec_branch_target != 32'h120 || exec_redirect_valid) bad = bad + 1; @(posedge clk); #1;
        clear_issue(); issue_op = `RV32IM_OP_BNE; issue_pc = 32'h100; issue_imm = 32'h20; issue_src1 = 4; issue_src2 = 4; issue_valid = 1; @(posedge clk); #1; issue_valid = 0;
        if (!exec_valid || exec_branch_taken || exec_redirect_valid) bad = bad + 1; @(posedge clk); #1;
        clear_issue(); issue_op = `RV32IM_OP_BLT; issue_pc = 32'h100; issue_imm = 32'h20; issue_src1 = 32'hffffffff; issue_src2 = 1; issue_valid = 1; @(posedge clk); #1; issue_valid = 0;
        if (!exec_valid || !exec_branch_taken || exec_redirect_pc != 32'h120 || !exec_redirect_valid) bad = bad + 1; @(posedge clk); #1;
        clear_issue(); issue_op = `RV32IM_OP_BGE; issue_pc = 32'h100; issue_imm = 32'h20; issue_src1 = 32'hffffffff; issue_src2 = 1; issue_pred_taken = 1; issue_pred_target = 32'h120; issue_valid = 1; @(posedge clk); #1; issue_valid = 0;
        if (!exec_valid || exec_branch_taken || !exec_redirect_valid || exec_redirect_pc != 32'h104) bad = bad + 1; @(posedge clk); #1;
        clear_issue(); issue_op = `RV32IM_OP_BLTU; issue_pc = 32'hfffffffc; issue_imm = 32'h10; issue_src1 = 32'hffffffff; issue_src2 = 1; issue_valid = 1; @(posedge clk); #1; issue_valid = 0;
        if (!exec_valid || exec_branch_taken || exec_redirect_valid || exec_redirect_pc != 32'h0) bad = bad + 1; @(posedge clk); #1;
        clear_issue(); issue_op = `RV32IM_OP_BGEU; issue_pc = 32'hfffffffc; issue_imm = 32'h10; issue_src1 = 32'hffffffff; issue_src2 = 1; issue_pred_taken = 1; issue_pred_target = 32'h0000000c; issue_valid = 1; @(posedge clk); #1; issue_valid = 0;
        if (!exec_valid || !exec_branch_taken || exec_branch_target != 32'h0000000c || exec_redirect_valid) bad = bad + 1; @(posedge clk); #1;
        clear_issue(); issue_op = `RV32IM_OP_JALR; issue_pc = 32'h200; issue_imm = 3; issue_src1 = 32'h100; issue_pred_taken = 0; issue_valid = 1; @(posedge clk); #1; issue_valid = 0;
        if (!exec_valid || exec_value != 32'h204 || exec_branch_target != 32'h102 || !exec_redirect_valid) bad = bad + 1; @(posedge clk); #1;

        clear_issue(); issue_op = `RV32IM_OP_LW; issue_src1 = 32'hfffffffc; issue_imm = 8; issue_mem_size = `RV32IM_MEM_WORD; issue_valid = 1; @(posedge clk); #1; issue_valid = 0;
        if (!exec_valid || !exec_is_memory || !exec_is_load || exec_mem_addr != 32'h4) bad = bad + 1; @(posedge clk); #1;
        clear_issue(); issue_op = `RV32IM_OP_SB; issue_src1 = 32'hffffffff; issue_imm = 1; issue_store_data = 128'hdeadbeef; issue_mem_size = `RV32IM_MEM_BYTE; issue_valid = 1; @(posedge clk); #1; issue_valid = 0;
        if (!exec_valid || !exec_is_store || exec_mem_addr != 32'h0 || exec_store_data[31:0] != 32'hdeadbeef) bad = bad + 1; @(posedge clk); #1;

        // Registered output and backpressure stability.
        clear_issue(); exec_ready = 0; issue_op = `RV32IM_OP_XOR; issue_src1 = 32'h55aa; issue_src2 = 32'h0f0f; issue_valid = 1; @(posedge clk); #1; issue_valid = 0;
        if (!exec_valid || exec_value != 32'h5aa5) bad = bad + 1; @(posedge clk); #1; if (!exec_valid || exec_value != 32'h5aa5) bad = bad + 1; exec_ready = 1; @(posedge clk); #1;
        // Flush removes a pending result before it can be consumed.
        clear_issue(); exec_ready = 0; issue_op = `RV32IM_OP_OR; issue_src1 = 1; issue_src2 = 2; issue_valid = 1; @(posedge clk); #1; issue_valid = 0; flush = 1; @(posedge clk); #1; flush = 0; exec_ready = 1; if (exec_valid) bad = bad + 1; @(posedge clk); #1;
        // A live-tag mismatch suppresses and drains a stale candidate.
        clear_issue(); issue_op = `RV32IM_OP_AND; issue_src1 = 7; issue_src2 = 3; issue_tag = 16'h0201; issue_valid = 1; @(posedge clk); #1; issue_valid = 0; live_tag_valid = 1; live_tag = 16'h0301; #1; if (exec_valid) bad = bad + 1; @(posedge clk); #1; live_tag_valid = 0; if (exec_valid) bad = bad + 1;
        if (bad != 0) begin $display("FAIL: B-05 ALU checks=%0d", bad); $finish(1); end
        $display("PASS: B-05 ALU/branch/AGU"); $finish(0);
    end
endmodule
