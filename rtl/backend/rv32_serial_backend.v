`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Area-oriented, one-instruction-at-a-time backend.  This is an optional
// implementation for the single-issue profile; the default out-of-order
// backend remains available unchanged.  A single read port visits rs1 and
// rs2 on consecutive cycles, avoiding the rename map, free list, ROB, issue
// queues, LSQ and dual-read physical register file.
module rv32_serial_backend #(
    parameter integer BE_WIDTH = 1,
    parameter integer SHIFT_IMPL = 1,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         flush_i,
    input  wire [BE_WIDTH-1:0]          trace_valid_i,
    output wire [BE_WIDTH-1:0]          trace_ready_o,
    input  wire [BE_WIDTH*32-1:0]       trace_pc_i,
    input  wire [BE_WIDTH*32-1:0]       trace_inst_i,
    input  wire [BE_WIDTH*`RV32IM_OP_WIDTH-1:0] trace_op_i,
    input  wire [BE_WIDTH*32-1:0]       trace_imm_i,
    input  wire [BE_WIDTH*5-1:0]        trace_rd_i,
    input  wire [BE_WIDTH*5-1:0]        trace_rs1_i,
    input  wire [BE_WIDTH*5-1:0]        trace_rs2_i,
    input  wire [BE_WIDTH-1:0]          trace_rd_we_i,
    input  wire [BE_WIDTH-1:0]          trace_rs1_used_i,
    input  wire [BE_WIDTH-1:0]          trace_rs2_used_i,
    input  wire [BE_WIDTH-1:0]          trace_is_load_i,
    input  wire [BE_WIDTH-1:0]          trace_is_store_i,
    input  wire [BE_WIDTH-1:0]          trace_is_branch_i,
    input  wire [BE_WIDTH-1:0]          trace_is_halt_i,
    input  wire [BE_WIDTH-1:0]          trace_is_error_i,
    input  wire [BE_WIDTH*2-1:0]        trace_mem_size_i,
    input  wire [BE_WIDTH-1:0]          trace_mem_unsigned_i,
    input  wire [BE_WIDTH*128-1:0]      trace_store_data_i,
    input  wire [BE_WIDTH-1:0]          trace_pred_taken_i,
    input  wire [BE_WIDTH*32-1:0]       trace_pred_target_i,
    input  wire [BE_WIDTH*2-1:0]        trace_pred_kind_i,

    output wire                         dcache_req_valid_o,
    input  wire                         dcache_req_ready_i,
    output wire                         dcache_req_is_load_o,
    output wire                         dcache_req_is_store_o,
    output wire [31:0]                  dcache_req_addr_o,
    output wire [1:0]                   dcache_req_size_o,
    output wire                         dcache_req_unsigned_o,
    output wire [15:0]                  dcache_req_mask_o,
    output wire [127:0]                 dcache_req_wdata_o,
    output wire [TAG_WIDTH-1:0]         dcache_req_rob_tag_o,
    output wire [TAG_WIDTH-1:0]         dcache_req_lsq_tag_o,
    input  wire                         dcache_resp_valid_i,
    output wire                         dcache_resp_ready_o,
    input  wire [TAG_WIDTH-1:0]         dcache_resp_lsq_tag_i,
    input  wire [31:0]                  dcache_resp_addr_i,
    input  wire [127:0]                 dcache_resp_line_data_i,
    input  wire [31:0]                  dcache_resp_word_data_i,
    input  wire                         dcache_resp_line_valid_i,
    input  wire                         dcache_resp_error_i,
    input  wire                         dcache_store_ack_valid_i,
    input  wire [TAG_WIDTH-1:0]         dcache_store_ack_lsq_tag_i,
    input  wire                         dcache_store_ack_error_i,

    input  wire                         commit_ready_i,
    output wire [BE_WIDTH-1:0]          commit_valid_o,
    output wire [BE_WIDTH*32-1:0]       commit_pc_o,
    output wire [BE_WIDTH*32-1:0]       commit_inst_o,
    output wire [BE_WIDTH*5-1:0]        commit_rd_o,
    output wire [BE_WIDTH-1:0]          commit_rd_we_o,
    output wire [BE_WIDTH*32-1:0]       commit_value_o,
    output wire [BE_WIDTH-1:0]          commit_is_store_o,
    output wire [BE_WIDTH*32-1:0]       commit_store_addr_o,
    output wire [BE_WIDTH*16-1:0]       commit_store_mask_o,
    output wire [BE_WIDTH*128-1:0]      commit_store_data_o,
    output wire [BE_WIDTH*TAG_WIDTH-1:0] commit_tag_o,
    output wire                         redirect_valid_o,
    output wire [31:0]                  redirect_pc_o,
    output wire [3:0]                   redirect_epoch_o,
    output reg                          halted_o,
    output reg                          error_o,
    output reg  [7:0]                   return_value_o,
    output wire                         branch_feedback_valid_o,
    output wire [31:0]                  branch_feedback_pc_o,
    output wire [1:0]                   branch_feedback_kind_o,
    output wire                         branch_feedback_taken_o,
    output wire [31:0]                  branch_feedback_target_o,
    output wire                         branch_feedback_pred_taken_o,
    output wire [31:0]                  branch_feedback_pred_target_o
);
    localparam [2:0] S_IDLE       = 3'd0;
    localparam [2:0] S_READ_RS1   = 3'd1;
    localparam [2:0] S_READ_RS2   = 3'd2;
    localparam [2:0] S_ISSUE      = 3'd3;
    localparam [2:0] S_WAIT_EXEC  = 3'd4;
    localparam [2:0] S_WAIT_MEM   = 3'd5;
    localparam [2:0] S_WAIT_STORE = 3'd6;
    localparam [2:0] S_COMMIT     = 3'd7;

    reg [2:0] state;
    reg [31:0] registers [1:31];
    reg [4:0] rs1_reg, rs2_reg, rd_reg;
    reg [31:0] src1_reg, src2_reg;
    reg [31:0] pc_reg, inst_reg, imm_reg;
    reg [`RV32IM_OP_WIDTH-1:0] op_reg;
    reg rd_we_reg, halt_reg, decode_error_reg;
    reg [1:0] mem_size_reg;
    reg mem_unsigned_reg;
    reg pred_taken_reg;
    reg [31:0] pred_target_reg;
    reg [1:0] pred_kind_reg;
    reg [3:0] epoch_reg;

    reg [31:0] result_reg;
    reg result_error_reg;
    reg result_is_store_reg;
    reg [31:0] result_store_addr_reg;
    reg [15:0] result_store_mask_reg;
    reg [127:0] result_store_data_reg;

    wire [4:0] read_index = (state == S_READ_RS1) ? rs1_reg : rs2_reg;
    wire [31:0] read_value = (read_index == 0) ? 32'b0 : registers[read_index];
    wire input_fire = trace_valid_i[0] && trace_ready_o[0];
    wire op_is_mdu = (op_reg >= `RV32IM_OP_MUL) && (op_reg <= `RV32IM_OP_REMU);
    wire [TAG_WIDTH-1:0] serial_tag = {{(TAG_WIDTH-1){1'b0}}, 1'b1};

    assign trace_ready_o = {{(BE_WIDTH-1){1'b0}},
        (state == S_IDLE) && !halted_o && !error_o};

    wire alu_issue_ready;
    wire alu_exec_valid;
    wire [31:0] alu_exec_value;
    wire alu_exec_rd_we, alu_exec_is_branch, alu_exec_branch_taken;
    wire [31:0] alu_exec_branch_target;
    wire alu_exec_redirect_valid;
    wire [31:0] alu_exec_redirect_pc;
    wire alu_exec_is_memory, alu_exec_is_load, alu_exec_is_store;
    wire [31:0] alu_exec_mem_addr;
    wire [1:0] alu_exec_mem_size;
    wire alu_exec_mem_unsigned;
    wire [31:0] alu_exec_store_data;
    wire alu_exec_ready = (state == S_WAIT_EXEC) && alu_exec_valid &&
        (!alu_exec_is_memory || dcache_req_ready_i);

    rv32i_alu #(.TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(5),
                .SHIFT_IMPL(SHIFT_IMPL)) alu (
        .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i),
        .issue_valid_i((state == S_ISSUE) && !op_is_mdu),
        .issue_ready_o(alu_issue_ready), .issue_op_i(op_reg),
        .issue_pc_i(pc_reg), .issue_imm_i(imm_reg),
        .issue_src1_value_i(src1_reg), .issue_src2_value_i(src2_reg),
        .issue_store_data_i(src2_reg), .issue_phys_rd_i(rd_reg),
        .issue_rob_tag_i(serial_tag), .issue_epoch_i(epoch_reg),
        .issue_target_live_i(1'b1), .issue_pred_taken_i(pred_taken_reg),
        .issue_pred_target_i(pred_target_reg), .issue_pred_kind_i(pred_kind_reg),
        .issue_mem_size_i(mem_size_reg), .issue_mem_unsigned_i(mem_unsigned_reg),
        .exec_valid_o(alu_exec_valid), .exec_ready_i(alu_exec_ready),
        .exec_value_o(alu_exec_value), .exec_phys_rd_o(), .exec_rob_tag_o(),
        .exec_epoch_o(), .exec_rd_we_o(alu_exec_rd_we),
        .exec_is_branch_o(alu_exec_is_branch),
        .exec_branch_taken_o(alu_exec_branch_taken),
        .exec_branch_target_o(alu_exec_branch_target),
        .exec_redirect_valid_o(alu_exec_redirect_valid),
        .exec_redirect_pc_o(alu_exec_redirect_pc),
        .exec_is_memory_o(alu_exec_is_memory), .exec_is_load_o(alu_exec_is_load),
        .exec_is_store_o(alu_exec_is_store), .exec_mem_addr_o(alu_exec_mem_addr),
        .exec_mem_size_o(alu_exec_mem_size),
        .exec_mem_unsigned_o(alu_exec_mem_unsigned),
        .exec_store_data_o(alu_exec_store_data),
        .live_tag_valid_i(1'b0), .live_tag_i({TAG_WIDTH{1'b0}})
    );

    wire mdu_req_ready, mdu_resp_valid;
    wire [31:0] mdu_resp_value;
    rv32m_mdu_iterative #(.TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(5)) mdu (
        .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i),
        .req_valid_i((state == S_ISSUE) && op_is_mdu),
        .req_ready_o(mdu_req_ready), .req_op_i(op_reg),
        .req_src1_i(src1_reg), .req_src2_i(src2_reg),
        .req_rob_tag_i(serial_tag), .req_phys_rd_i(rd_reg),
        .req_target_live_i(1'b1), .resp_valid_o(mdu_resp_valid),
        .resp_ready_i(state == S_WAIT_EXEC), .resp_value_o(mdu_resp_value),
        .resp_rob_tag_o(), .resp_phys_rd_o(), .resp_rd_we_o(),
        .live_tag_valid_i(1'b0), .live_tag_i({TAG_WIDTH{1'b0}})
    );

    wire [15:0] store_base_mask =
        (alu_exec_mem_size == `RV32IM_MEM_BYTE) ? 16'h0001 :
        (alu_exec_mem_size == `RV32IM_MEM_HALF) ? 16'h0003 : 16'h000f;
    wire [15:0] store_mask = store_base_mask << alu_exec_mem_addr[3:0];
    wire [127:0] store_data =
        {{96{1'b0}}, alu_exec_store_data} << (alu_exec_mem_addr[3:0] * 8);

    assign dcache_req_valid_o = (state == S_WAIT_EXEC) && alu_exec_valid &&
        alu_exec_is_memory;
    assign dcache_req_is_load_o = alu_exec_is_load;
    assign dcache_req_is_store_o = alu_exec_is_store;
    assign dcache_req_addr_o = alu_exec_mem_addr;
    assign dcache_req_size_o = alu_exec_mem_size;
    assign dcache_req_unsigned_o = alu_exec_mem_unsigned;
    assign dcache_req_mask_o = store_mask;
    assign dcache_req_wdata_o = store_data;
    assign dcache_req_rob_tag_o = serial_tag;
    assign dcache_req_lsq_tag_o = serial_tag;
    assign dcache_resp_ready_o = (state == S_WAIT_MEM);

    assign commit_valid_o = {{(BE_WIDTH-1){1'b0}}, state == S_COMMIT};
    assign commit_pc_o = {{(BE_WIDTH-1)*32{1'b0}}, pc_reg};
    assign commit_inst_o = {{(BE_WIDTH-1)*32{1'b0}}, inst_reg};
    assign commit_rd_o = {{(BE_WIDTH-1)*5{1'b0}}, rd_reg};
    assign commit_rd_we_o = {{(BE_WIDTH-1){1'b0}},
        rd_we_reg && (rd_reg != 0) && !result_is_store_reg};
    assign commit_value_o = {{(BE_WIDTH-1)*32{1'b0}}, result_reg};
    assign commit_is_store_o = {{(BE_WIDTH-1){1'b0}}, result_is_store_reg};
    assign commit_store_addr_o = {{(BE_WIDTH-1)*32{1'b0}}, result_store_addr_reg};
    assign commit_store_mask_o = {{(BE_WIDTH-1)*16{1'b0}}, result_store_mask_reg};
    assign commit_store_data_o = {{(BE_WIDTH-1)*128{1'b0}}, result_store_data_reg};
    assign commit_tag_o = {{(BE_WIDTH-1)*TAG_WIDTH{1'b0}}, serial_tag};

    assign redirect_valid_o = (state == S_WAIT_EXEC) && alu_exec_valid &&
        alu_exec_redirect_valid;
    assign redirect_pc_o = alu_exec_redirect_pc;
    assign redirect_epoch_o = epoch_reg + 1'b1;
    assign branch_feedback_valid_o = (state == S_WAIT_EXEC) &&
        alu_exec_valid && alu_exec_is_branch;
    assign branch_feedback_pc_o = pc_reg;
    assign branch_feedback_kind_o = pred_kind_reg;
    assign branch_feedback_taken_o = alu_exec_branch_taken;
    assign branch_feedback_target_o = alu_exec_branch_target;
    assign branch_feedback_pred_taken_o = pred_taken_reg;
    assign branch_feedback_pred_target_o = pred_target_reg;

    integer reset_index;
    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            state <= S_IDLE;
            halted_o <= 1'b0;
            error_o <= 1'b0;
            return_value_o <= 8'b0;
            epoch_reg <= 4'b0;
        end else begin
            case (state)
                S_IDLE: if (input_fire) begin
                    pc_reg <= trace_pc_i[0 +: 32];
                    inst_reg <= trace_inst_i[0 +: 32];
                    op_reg <= trace_op_i[0 +: `RV32IM_OP_WIDTH];
                    imm_reg <= trace_imm_i[0 +: 32];
                    rd_reg <= trace_rd_i[0 +: 5];
                    rs1_reg <= trace_rs1_i[0 +: 5];
                    rs2_reg <= trace_rs2_i[0 +: 5];
                    rd_we_reg <= trace_rd_we_i[0];
                    halt_reg <= trace_is_halt_i[0];
                    decode_error_reg <= trace_is_error_i[0];
                    mem_size_reg <= trace_mem_size_i[0 +: 2];
                    mem_unsigned_reg <= trace_mem_unsigned_i[0];
                    pred_taken_reg <= trace_pred_taken_i[0];
                    pred_target_reg <= trace_pred_target_i[0 +: 32];
                    pred_kind_reg <= trace_pred_kind_i[0 +: 2];
                    state <= S_READ_RS1;
                end
                S_READ_RS1: begin
                    src1_reg <= read_value;
                    state <= S_READ_RS2;
                end
                S_READ_RS2: begin
                    src2_reg <= read_value;
                    state <= S_ISSUE;
                end
                S_ISSUE: begin
                    if ((!op_is_mdu && alu_issue_ready) ||
                        (op_is_mdu && mdu_req_ready))
                        state <= S_WAIT_EXEC;
                end
                S_WAIT_EXEC: begin
                    if (mdu_resp_valid) begin
                        result_reg <= mdu_resp_value;
                        result_error_reg <= decode_error_reg;
                        result_is_store_reg <= 1'b0;
                        state <= S_COMMIT;
                    end else if (alu_exec_valid && !alu_exec_is_memory) begin
                        result_reg <= alu_exec_value;
                        result_error_reg <= decode_error_reg;
                        result_is_store_reg <= 1'b0;
                        if (alu_exec_redirect_valid)
                            epoch_reg <= epoch_reg + 1'b1;
                        state <= S_COMMIT;
                    end else if (alu_exec_valid && alu_exec_is_memory &&
                                 dcache_req_ready_i) begin
                        result_store_addr_reg <= alu_exec_mem_addr;
                        result_store_mask_reg <= store_mask;
                        result_store_data_reg <= store_data;
                        result_is_store_reg <= alu_exec_is_store;
                        state <= alu_exec_is_store ? S_WAIT_STORE : S_WAIT_MEM;
                    end
                end
                S_WAIT_MEM: if (dcache_resp_valid_i) begin
                    result_reg <= dcache_resp_word_data_i;
                    result_error_reg <= decode_error_reg || dcache_resp_error_i;
                    result_is_store_reg <= 1'b0;
                    state <= S_COMMIT;
                end
                S_WAIT_STORE: if (dcache_store_ack_valid_i) begin
                    result_reg <= 32'b0;
                    result_error_reg <= decode_error_reg || dcache_store_ack_error_i;
                    state <= S_COMMIT;
                end
                S_COMMIT: if (commit_ready_i) begin
                    if (rd_we_reg && (rd_reg != 0) && !result_is_store_reg &&
                        !result_error_reg)
                        registers[rd_reg] <= result_reg;
                    if (halt_reg) begin
                        halted_o <= 1'b1;
                        return_value_o <= result_reg[7:0];
                    end
                    if (result_error_reg)
                        error_o <= 1'b1;
                    state <= S_IDLE;
                end
                default: state <= S_IDLE;
            endcase
        end
    end

    // Reserved compatibility inputs are intentionally absent from the
    // serialized datapath; reductions keep lint tools from treating them as
    // accidental omissions.
    wire unused_inputs = ^{trace_rs1_used_i, trace_rs2_used_i,
        trace_is_load_i, trace_is_store_i, trace_is_branch_i,
        trace_store_data_i, dcache_resp_lsq_tag_i, dcache_resp_addr_i,
        dcache_resp_line_data_i, dcache_resp_line_valid_i,
        dcache_store_ack_lsq_tag_i};
endmodule
