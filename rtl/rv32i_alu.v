`timescale 1ns/1ps
`include "rv32im_defs.vh"

// One-cycle registered integer execution, branch, and address-generation unit.
// The immediate input is already sign-extended by decode.  Memory operations
// produce an address and store payload only; the LSQ/cache owns the access.
module rv32i_alu #(
    parameter integer OP_WIDTH = `RV32IM_OP_WIDTH,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT,
    parameter integer EPOCH_WIDTH = `RV32IM_EPOCH_WIDTH
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         flush_i,

    input  wire                         issue_valid_i,
    output wire                         issue_ready_o,
    input  wire [OP_WIDTH-1:0]          issue_op_i,
    input  wire [31:0]                  issue_pc_i,
    input  wire [31:0]                  issue_imm_i,
    input  wire [31:0]                  issue_src1_value_i,
    input  wire [31:0]                  issue_src2_value_i,
    input  wire [31:0]                  issue_store_data_i,
    input  wire [PHYS_ADDR_WIDTH-1:0]   issue_phys_rd_i,
    input  wire [TAG_WIDTH-1:0]         issue_rob_tag_i,
    input  wire [EPOCH_WIDTH-1:0]       issue_epoch_i,
    input  wire                         issue_target_live_i,
    input  wire                         issue_pred_taken_i,
    input  wire [31:0]                  issue_pred_target_i,
    input  wire [1:0]                   issue_pred_kind_i,
    input  wire [1:0]                   issue_mem_size_i,
    input  wire                         issue_mem_unsigned_i,

    output wire                         exec_valid_o,
    input  wire                         exec_ready_i,
    output wire [31:0]                  exec_value_o,
    output wire [PHYS_ADDR_WIDTH-1:0]   exec_phys_rd_o,
    output wire [TAG_WIDTH-1:0]         exec_rob_tag_o,
    output wire [EPOCH_WIDTH-1:0]       exec_epoch_o,
    output wire                         exec_rd_we_o,
    output wire                         exec_is_branch_o,
    output wire                         exec_branch_taken_o,
    output wire [31:0]                  exec_branch_target_o,
    output wire                         exec_redirect_valid_o,
    output wire [31:0]                  exec_redirect_pc_o,
    output wire                         exec_is_memory_o,
    output wire                         exec_is_load_o,
    output wire                         exec_is_store_o,
    output wire [31:0]                  exec_mem_addr_o,
    output wire [1:0]                   exec_mem_size_o,
    output wire                         exec_mem_unsigned_o,
    output wire [31:0]                  exec_store_data_o,

    input  wire                         live_tag_valid_i,
    input  wire [TAG_WIDTH-1:0]         live_tag_i
);
    reg result_valid_reg;
    reg [31:0] result_value_reg;
    reg [PHYS_ADDR_WIDTH-1:0] result_phys_rd_reg;
    reg [TAG_WIDTH-1:0] result_rob_tag_reg;
    reg [EPOCH_WIDTH-1:0] result_epoch_reg;
    reg result_rd_we_reg;
    reg result_is_branch_reg;
    reg result_branch_taken_reg;
    reg [31:0] result_branch_target_reg;
    reg result_redirect_valid_reg;
    reg [31:0] result_redirect_pc_reg;
    reg result_is_memory_reg;
    reg result_is_load_reg;
    reg result_is_store_reg;
    reg [31:0] result_mem_addr_reg;
    reg [1:0] result_mem_size_reg;
    reg result_mem_unsigned_reg;
    reg [31:0] result_store_data_reg;

    reg [31:0] calc_value;
    reg calc_rd_we;
    reg calc_is_branch;
    reg calc_branch_taken;
    reg [31:0] calc_branch_target;
    reg calc_redirect_valid;
    reg [31:0] calc_redirect_pc;
    reg calc_is_memory;
    reg calc_is_load;
    reg calc_is_store;
    reg [31:0] calc_mem_addr;
    reg [1:0] calc_mem_size;
    reg calc_mem_unsigned;
    reg [31:0] calc_store_data;
    reg actual_control;
    reg [31:0] actual_next_pc;
    reg live_match;
    reg [31:0] adder_lhs;
    reg [31:0] adder_rhs;
    reg adder_subtract;
    reg [31:0] shared_sum;
    reg [31:0] pc_plus_four;

    wire result_visible = result_valid_reg &&
        (!live_tag_valid_i || (result_rob_tag_reg == live_tag_i));
    assign exec_valid_o = result_visible;
    assign issue_ready_o = !flush_i &&
        (!result_valid_reg || exec_ready_i ||
         (live_tag_valid_i && (result_rob_tag_reg != live_tag_i)));

    assign exec_value_o = result_value_reg;
    assign exec_phys_rd_o = result_phys_rd_reg;
    assign exec_rob_tag_o = result_rob_tag_reg;
    assign exec_epoch_o = result_epoch_reg;
    assign exec_rd_we_o = result_rd_we_reg;
    assign exec_is_branch_o = result_is_branch_reg;
    assign exec_branch_taken_o = result_branch_taken_reg;
    assign exec_branch_target_o = result_branch_target_reg;
    assign exec_redirect_valid_o = result_redirect_valid_reg;
    assign exec_redirect_pc_o = result_redirect_pc_reg;
    assign exec_is_memory_o = result_is_memory_reg;
    assign exec_is_load_o = result_is_load_reg;
    assign exec_is_store_o = result_is_store_reg;
    assign exec_mem_addr_o = result_mem_addr_reg;
    assign exec_mem_size_o = result_mem_size_reg;
    assign exec_mem_unsigned_o = result_mem_unsigned_reg;
    assign exec_store_data_o = result_store_data_reg;

    // All operation semantics are combinational from the accepted IssuePacket.
    // The resulting fields are latched below, making completion visible one
    // cycle after issue and stable while the consumer applies backpressure.
    always @* begin
        // Only one operation is accepted per cycle.  Select the operands up
        // front so address generation, branch targets and integer add/sub all
        // share one 32-bit adder instead of inferring parallel adders.
        adder_lhs = issue_src1_value_i;
        adder_rhs = issue_src2_value_i;
        adder_subtract = (issue_op_i == `RV32IM_OP_SUB);
        case (issue_op_i)
            `RV32IM_OP_AUIPC,
            `RV32IM_OP_JAL,
            `RV32IM_OP_BEQ,
            `RV32IM_OP_BNE,
            `RV32IM_OP_BLT,
            `RV32IM_OP_BGE,
            `RV32IM_OP_BLTU,
            `RV32IM_OP_BGEU: begin
                adder_lhs = issue_pc_i;
                adder_rhs = issue_imm_i;
            end
            `RV32IM_OP_JALR,
            `RV32IM_OP_LB,
            `RV32IM_OP_LH,
            `RV32IM_OP_LW,
            `RV32IM_OP_LBU,
            `RV32IM_OP_LHU,
            `RV32IM_OP_SB,
            `RV32IM_OP_SH,
            `RV32IM_OP_SW,
            `RV32IM_OP_ADDI: begin
                adder_lhs = issue_src1_value_i;
                adder_rhs = issue_imm_i;
            end
            default: begin end
        endcase
        shared_sum = adder_lhs + (adder_subtract ? ~adder_rhs : adder_rhs) +
            {{31{1'b0}}, adder_subtract};
        pc_plus_four = issue_pc_i + 32'd4;

        calc_value = 32'b0;
        calc_rd_we = 1'b0;
        calc_is_branch = 1'b0;
        calc_branch_taken = 1'b0;
        calc_branch_target = 32'b0;
        calc_redirect_valid = 1'b0;
        calc_redirect_pc = 32'b0;
        calc_is_memory = 1'b0;
        calc_is_load = 1'b0;
        calc_is_store = 1'b0;
        calc_mem_addr = 32'b0;
        calc_mem_size = issue_mem_size_i;
        calc_mem_unsigned = issue_mem_unsigned_i;
        calc_store_data = issue_store_data_i;
        actual_control = 1'b0;
        actual_next_pc = 32'b0;

        case (issue_op_i)
            `RV32IM_OP_LUI: begin
                calc_value = issue_imm_i;
                calc_rd_we = 1'b1;
            end
            `RV32IM_OP_AUIPC: begin
                calc_value = shared_sum;
                calc_rd_we = 1'b1;
            end
            `RV32IM_OP_JAL: begin
                calc_value = pc_plus_four;
                calc_rd_we = 1'b1;
                calc_is_branch = 1'b1;
                calc_branch_taken = 1'b1;
                actual_control = 1'b1;
                actual_next_pc = shared_sum;
                calc_branch_target = actual_next_pc;
            end
            `RV32IM_OP_JALR: begin
                calc_value = pc_plus_four;
                calc_rd_we = 1'b1;
                calc_is_branch = 1'b1;
                calc_branch_taken = 1'b1;
                actual_control = 1'b1;
                actual_next_pc = shared_sum & 32'hfffffffe;
                calc_branch_target = actual_next_pc;
            end
            `RV32IM_OP_BEQ: begin calc_is_branch = 1'b1; calc_branch_taken = (issue_src1_value_i == issue_src2_value_i); end
            `RV32IM_OP_BNE: begin calc_is_branch = 1'b1; calc_branch_taken = (issue_src1_value_i != issue_src2_value_i); end
            `RV32IM_OP_BLT: begin calc_is_branch = 1'b1; calc_branch_taken = ($signed(issue_src1_value_i) < $signed(issue_src2_value_i)); end
            `RV32IM_OP_BGE: begin calc_is_branch = 1'b1; calc_branch_taken = ($signed(issue_src1_value_i) >= $signed(issue_src2_value_i)); end
            `RV32IM_OP_BLTU: begin calc_is_branch = 1'b1; calc_branch_taken = (issue_src1_value_i < issue_src2_value_i); end
            `RV32IM_OP_BGEU: begin calc_is_branch = 1'b1; calc_branch_taken = (issue_src1_value_i >= issue_src2_value_i); end
            `RV32IM_OP_LB,
            `RV32IM_OP_LH,
            `RV32IM_OP_LW,
            `RV32IM_OP_LBU,
            `RV32IM_OP_LHU: begin
                calc_is_memory = 1'b1;
                calc_is_load = 1'b1;
                calc_rd_we = 1'b1;
                calc_mem_addr = shared_sum;
            end
            `RV32IM_OP_SB,
            `RV32IM_OP_SH,
            `RV32IM_OP_SW: begin
                calc_is_memory = 1'b1;
                calc_is_store = 1'b1;
                calc_mem_addr = shared_sum;
                // Store data remains access-relative inside the backend.
                // A zero predecoded payload selects the live rs2 value; the
                // LSQ expands it to cache-line coordinates at its boundary.
                if (issue_store_data_i == 32'b0)
                    calc_store_data = issue_src2_value_i;
            end
            `RV32IM_OP_ADDI,
            `RV32IM_OP_ADD: begin calc_value = shared_sum; calc_rd_we = 1'b1; end
            `RV32IM_OP_SLTI: begin calc_value = ($signed(issue_src1_value_i) < $signed(issue_imm_i)) ? 32'd1 : 32'd0; calc_rd_we = 1'b1; end
            `RV32IM_OP_SLTIU: begin calc_value = (issue_src1_value_i < issue_imm_i) ? 32'd1 : 32'd0; calc_rd_we = 1'b1; end
            `RV32IM_OP_XORI: begin calc_value = issue_src1_value_i ^ issue_imm_i; calc_rd_we = 1'b1; end
            `RV32IM_OP_ORI: begin calc_value = issue_src1_value_i | issue_imm_i; calc_rd_we = 1'b1; end
            `RV32IM_OP_ANDI: begin calc_value = issue_src1_value_i & issue_imm_i; calc_rd_we = 1'b1; end
            `RV32IM_OP_SLLI: begin calc_value = issue_src1_value_i << issue_imm_i[4:0]; calc_rd_we = 1'b1; end
            `RV32IM_OP_SRLI: begin calc_value = issue_src1_value_i >> issue_imm_i[4:0]; calc_rd_we = 1'b1; end
            `RV32IM_OP_SRAI: begin calc_value = $signed(issue_src1_value_i) >>> issue_imm_i[4:0]; calc_rd_we = 1'b1; end
            `RV32IM_OP_SUB: begin calc_value = shared_sum; calc_rd_we = 1'b1; end
            `RV32IM_OP_SLL: begin calc_value = issue_src1_value_i << issue_src2_value_i[4:0]; calc_rd_we = 1'b1; end
            `RV32IM_OP_SLT: begin calc_value = ($signed(issue_src1_value_i) < $signed(issue_src2_value_i)) ? 32'd1 : 32'd0; calc_rd_we = 1'b1; end
            `RV32IM_OP_SLTU: begin calc_value = (issue_src1_value_i < issue_src2_value_i) ? 32'd1 : 32'd0; calc_rd_we = 1'b1; end
            `RV32IM_OP_XOR: begin calc_value = issue_src1_value_i ^ issue_src2_value_i; calc_rd_we = 1'b1; end
            `RV32IM_OP_SRL: begin calc_value = issue_src1_value_i >> issue_src2_value_i[4:0]; calc_rd_we = 1'b1; end
            `RV32IM_OP_SRA: begin calc_value = $signed(issue_src1_value_i) >>> issue_src2_value_i[4:0]; calc_rd_we = 1'b1; end
            `RV32IM_OP_OR: begin calc_value = issue_src1_value_i | issue_src2_value_i; calc_rd_we = 1'b1; end
            `RV32IM_OP_AND: begin calc_value = issue_src1_value_i & issue_src2_value_i; calc_rd_we = 1'b1; end
            default: begin end
        endcase

        if ((issue_op_i == `RV32IM_OP_BEQ) || (issue_op_i == `RV32IM_OP_BNE) ||
            (issue_op_i == `RV32IM_OP_BLT) || (issue_op_i == `RV32IM_OP_BGE) ||
            (issue_op_i == `RV32IM_OP_BLTU) || (issue_op_i == `RV32IM_OP_BGEU)) begin
            actual_control = 1'b1;
            calc_branch_target = shared_sum;
            actual_next_pc = calc_branch_taken ? shared_sum : pc_plus_four;
        end
        if (actual_control) begin
            calc_redirect_pc = actual_next_pc;
            calc_redirect_valid = (issue_pred_taken_i != calc_branch_taken) ||
                (calc_branch_taken && (issue_pred_target_i != calc_branch_target));
        end
    end

    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            result_valid_reg <= 1'b0;
            result_value_reg <= 32'b0;
            result_phys_rd_reg <= {PHYS_ADDR_WIDTH{1'b0}};
            result_rob_tag_reg <= {TAG_WIDTH{1'b0}};
            result_epoch_reg <= {EPOCH_WIDTH{1'b0}};
            result_rd_we_reg <= 1'b0;
            result_is_branch_reg <= 1'b0;
            result_branch_taken_reg <= 1'b0;
            result_branch_target_reg <= 32'b0;
            result_redirect_valid_reg <= 1'b0;
            result_redirect_pc_reg <= 32'b0;
            result_is_memory_reg <= 1'b0;
            result_is_load_reg <= 1'b0;
            result_is_store_reg <= 1'b0;
            result_mem_addr_reg <= 32'b0;
            result_mem_size_reg <= `RV32IM_MEM_NONE;
            result_mem_unsigned_reg <= 1'b0;
            result_store_data_reg <= 32'b0;
        end else if (result_valid_reg && live_tag_valid_i && (result_rob_tag_reg != live_tag_i) && !exec_ready_i) begin
            // A stale completion cannot remain buffered when the live-tag
            // authority has already moved on, even under output backpressure.
            result_valid_reg <= 1'b0;
        end else if (issue_ready_o) begin
            if (issue_valid_i) begin
                result_valid_reg <= issue_target_live_i && issue_rob_tag_i[0];
                result_value_reg <= calc_value;
                result_phys_rd_reg <= issue_phys_rd_i;
                result_rob_tag_reg <= issue_rob_tag_i;
                result_epoch_reg <= issue_epoch_i;
                result_rd_we_reg <= calc_rd_we;
                result_is_branch_reg <= calc_is_branch;
                result_branch_taken_reg <= calc_branch_taken;
                result_branch_target_reg <= calc_branch_target;
                result_redirect_valid_reg <= calc_redirect_valid;
                result_redirect_pc_reg <= calc_redirect_pc;
                result_is_memory_reg <= calc_is_memory;
                result_is_load_reg <= calc_is_load;
                result_is_store_reg <= calc_is_store;
                result_mem_addr_reg <= calc_mem_addr;
                result_mem_size_reg <= calc_mem_size;
                result_mem_unsigned_reg <= calc_mem_unsigned;
                result_store_data_reg <= calc_store_data;
            end else if (exec_ready_i) begin
                result_valid_reg <= 1'b0;
            end
        end
    end
endmodule
