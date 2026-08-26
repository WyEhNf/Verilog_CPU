`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32im_decoder_tb;
    reg [31:0] inst;
    wire legal, rd_we, rs1_used, rs2_used;
    wire is_load, is_store, is_branch, is_jump, is_serialize;
    wire mem_unsigned, jalr_clear_lsb;
    wire [`RV32IM_OP_WIDTH-1:0] op;
    wire [`RV32IM_CLASS_WIDTH-1:0] class_id;
    wire [4:0] rd, rs1, rs2;
    wire [31:0] imm;
    wire [1:0] mem_size;
    wire [3:0] mem_base_mask;
    integer tests;

    rv32im_decoder dut (
        .inst_i(inst), .legal_o(legal), .op_o(op), .class_o(class_id),
        .rd_o(rd), .rs1_o(rs1), .rs2_o(rs2), .rd_we_o(rd_we),
        .rs1_used_o(rs1_used), .rs2_used_o(rs2_used), .imm_o(imm),
        .is_load_o(is_load), .is_store_o(is_store), .is_branch_o(is_branch),
        .is_jump_o(is_jump), .is_serialize_o(is_serialize),
        .mem_size_o(mem_size), .mem_unsigned_o(mem_unsigned),
        .mem_base_mask_o(mem_base_mask), .jalr_clear_lsb_o(jalr_clear_lsb)
    );

    task check_op;
        input [31:0] raw;
        input [`RV32IM_OP_WIDTH-1:0] expected_op;
        input [31:0] expected_imm;
        begin
            inst = raw; #1; tests = tests + 1;
            if (!legal || op !== expected_op || imm !== expected_imm) begin
                $display("FAIL: decoder raw=%08x legal=%b op=%0d/%0d imm=%08x/%08x",
                         raw, legal, op, expected_op, imm, expected_imm);
                $finish(1);
            end
        end
    endtask

    task check_illegal;
        input [31:0] raw;
        begin
            inst = raw; #1; tests = tests + 1;
            if (legal || op != `RV32IM_OP_INVALID || class_id != `RV32IM_CLASS_INVALID ||
                rd_we || rs1_used || rs2_used || is_load || is_store || is_branch || is_jump) begin
                $display("FAIL: illegal encoding leaked controls raw=%08x", raw);
                $finish(1);
            end
        end
    endtask

    initial begin
        tests = 0;
        check_op(32'h123452b7, `RV32IM_OP_LUI, 32'h12345000);
        check_op(32'hfffff297, `RV32IM_OP_AUIPC, 32'hfffff000);
        check_op(32'h008000ef, `RV32IM_OP_JAL, 32'h00000008);
        check_op(32'hffd100e7, `RV32IM_OP_JALR, 32'hfffffffd);
        if (!jalr_clear_lsb || !is_jump || !rs1_used || !rd_we) begin $display("FAIL: JALR controls"); $finish(1); end

        check_op(32'hfe208ee3, `RV32IM_OP_BEQ, 32'hfffffffc);
        if (!is_branch || !rs1_used || !rs2_used) begin $display("FAIL: branch controls"); $finish(1); end
        check_op(32'h00209463, `RV32IM_OP_BNE, 32'h00000008);
        check_op(32'h0020c463, `RV32IM_OP_BLT, 32'h00000008);
        check_op(32'h0020d463, `RV32IM_OP_BGE, 32'h00000008);
        check_op(32'h0020e463, `RV32IM_OP_BLTU, 32'h00000008);
        check_op(32'h0020f463, `RV32IM_OP_BGEU, 32'h00000008);

        check_op(32'hfff08183, `RV32IM_OP_LB, 32'hffffffff);
        if (!is_load || mem_size != `RV32IM_MEM_BYTE || mem_unsigned || mem_base_mask != 4'b0001) begin $display("FAIL: LB controls"); $finish(1); end
        check_op(32'h0030c183, `RV32IM_OP_LBU, 32'h00000003);
        if (!mem_unsigned || mem_size != `RV32IM_MEM_BYTE) begin $display("FAIL: LBU controls"); $finish(1); end
        check_op(32'h0040a183, `RV32IM_OP_LW, 32'h00000004);
        if (mem_size != `RV32IM_MEM_WORD || mem_base_mask != 4'b1111) begin $display("FAIL: LW controls"); $finish(1); end
        check_op(32'hfe308fa3, `RV32IM_OP_SB, 32'hffffffff);
        if (!is_store || mem_base_mask != 4'b0001) begin $display("FAIL: SB controls"); $finish(1); end
        check_op(32'h0030a423, `RV32IM_OP_SW, 32'h00000008);
        if (mem_base_mask != 4'b1111) begin $display("FAIL: SW controls"); $finish(1); end

        check_op(32'hfff08193, `RV32IM_OP_ADDI, 32'hffffffff);
        check_op(32'h0030a193, `RV32IM_OP_SLTI, 32'h00000003);
        check_op(32'h0030b193, `RV32IM_OP_SLTIU, 32'h00000003);
        check_op(32'h0030c193, `RV32IM_OP_XORI, 32'h00000003);
        check_op(32'h0030e193, `RV32IM_OP_ORI, 32'h00000003);
        check_op(32'h0030f193, `RV32IM_OP_ANDI, 32'h00000003);
        check_op(32'h00309193, `RV32IM_OP_SLLI, 32'h00000003);
        check_op(32'h0030d193, `RV32IM_OP_SRLI, 32'h00000003);
        check_op(32'h4030d193, `RV32IM_OP_SRAI, 32'h00000003);

        check_op(32'h002081b3, `RV32IM_OP_ADD, 32'd0);
        check_op(32'h402081b3, `RV32IM_OP_SUB, 32'd0);
        check_op(32'h002091b3, `RV32IM_OP_SLL, 32'd0);
        check_op(32'h0020a1b3, `RV32IM_OP_SLT, 32'd0);
        check_op(32'h0020b1b3, `RV32IM_OP_SLTU, 32'd0);
        check_op(32'h0020c1b3, `RV32IM_OP_XOR, 32'd0);
        check_op(32'h0020d1b3, `RV32IM_OP_SRL, 32'd0);
        check_op(32'h4020d1b3, `RV32IM_OP_SRA, 32'd0);
        check_op(32'h0020e1b3, `RV32IM_OP_OR, 32'd0);
        check_op(32'h0020f1b3, `RV32IM_OP_AND, 32'd0);

        check_op(32'h022081b3, `RV32IM_OP_MUL, 32'd0);
        check_op(32'h022091b3, `RV32IM_OP_MULH, 32'd0);
        check_op(32'h0220a1b3, `RV32IM_OP_MULHSU, 32'd0);
        check_op(32'h0220b1b3, `RV32IM_OP_MULHU, 32'd0);
        check_op(32'h0220c1b3, `RV32IM_OP_DIV, 32'd0);
        check_op(32'h0220d1b3, `RV32IM_OP_DIVU, 32'd0);
        check_op(32'h0220e1b3, `RV32IM_OP_REM, 32'd0);
        check_op(32'h0220f1b3, `RV32IM_OP_REMU, 32'd0);

        check_op(32'h0ff00513, `RV32IM_OP_HALT, 32'd0);
        if (!is_serialize || class_id != `RV32IM_CLASS_HALT) begin $display("FAIL: HALT controls"); $finish(1); end

        check_illegal(32'h0000100f); // FENCE.I
        check_illegal(32'h00000073); // ECALL
        check_illegal(32'h02109093); // invalid SLLI funct7
        check_illegal(32'h2010d193); // invalid right shift funct7
        check_illegal(32'h0020a063); // reserved branch funct3
        check_illegal(32'h00009183); // LH unsupported
        check_illegal(32'h0000d183); // LHU unsupported
        check_illegal(32'h00309123); // SH unsupported
        check_illegal(32'hffffffff);

        $display("PASS: A-01 decoder %0d directed vectors", tests);
        $finish(0);
    end

    initial begin
        #1000;
        $display("FAIL: A-01 decoder timeout");
        $finish(1);
    end
endmodule
