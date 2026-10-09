`timescale 1ns/1ps
`include "rv32im_defs.vh"

// One-cycle registered integer execution, branch, and address-generation unit.
// The immediate input is already sign-extended by decode.  Memory operations
// produce an address and store payload only; the LSQ/cache owns the access.
module rv32i_alu #(
    parameter integer OP_WIDTH = `RV32IM_OP_WIDTH,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT,
    parameter integer EPOCH_WIDTH = `RV32IM_EPOCH_WIDTH,
    parameter integer SHIFT_IMPL = 0,
    parameter integer SHIFT_SHARED_BARREL = 0,
    parameter integer FORWARD_METADATA = 0,
    parameter integer PRECOMPUTED_ARITHMETIC = 0,
    parameter COMPACT_PRED_TARGET = 0,
    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT,
    parameter integer SELECTIVE_RECOVERY = 0,
    parameter RECOVERY_OLDER_ISSUE = 0,
    parameter ISSUE_RECOVERY_PREDECODE = 0,
    parameter integer RECOVERY_WIDTH = 1+2*((ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES))+$clog2(ROB_ENTRIES+1)
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         flush_i,
    input  wire [RECOVERY_WIDTH-1:0]    recovery_packet_i,

    input  wire                         issue_valid_i,
    input  wire                         issue_cancel_i,
    output wire                         issue_ready_o,
    input  wire [OP_WIDTH-1:0]          issue_op_i,
    input  wire [31:0]                  issue_pc_i,
    input  wire [31:0]                  issue_imm_i,
    input  wire [31:0]                  issue_arithmetic_i,
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
    // Private capture query: saved result validity before selective recovery.
    // It is not an execution/completion handshake or cancellation bypass.
    output wire                         exec_saved_valid_o,
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
    output wire [31:0]                  exec_source_pc_o,
    output wire                         exec_pred_taken_o,
    output wire [31:0]                  exec_pred_target_o,
    output wire [1:0]                   exec_pred_kind_o,

    input  wire                         live_tag_valid_i,
    input  wire [TAG_WIDTH-1:0]         live_tag_i
);
    reg result_valid_reg;
    wire [31:0] result_value_reg;
    wire [PHYS_ADDR_WIDTH-1:0] result_phys_rd_reg;
    wire [TAG_WIDTH-1:0] result_rob_tag_reg;
    wire [EPOCH_WIDTH-1:0] result_epoch_reg;
    wire result_rd_we_reg;
    wire result_is_branch_reg;
    wire result_branch_taken_reg;
    wire [31:0] result_branch_target_reg;
    wire result_redirect_valid_reg;
    wire [31:0] result_redirect_pc_reg;
    wire result_is_memory_reg;
    wire result_is_load_reg;
    wire result_is_store_reg;
    wire [31:0] result_mem_addr_reg;
    wire [1:0] result_mem_size_reg;
    wire result_mem_unsigned_reg;
    wire [31:0] result_store_data_reg;

    wire [31:0] calc_value;
    wire calc_rd_we;
    wire calc_is_branch;
    wire calc_branch_taken;
    wire [31:0] calc_branch_target;
    wire calc_redirect_valid;
    wire [31:0] calc_redirect_pc;
    wire calc_is_memory;
    wire calc_is_load;
    wire calc_is_store;
    wire [31:0] calc_mem_addr;
    wire [1:0] calc_mem_size;
    wire calc_mem_unsigned;
    wire [31:0] calc_store_data;

    // Target and AGU adders have fixed operands, so opcode selection is
    // after arithmetic instead of being in front of all thirty-two bits.
    // They trade combinational area for a shorter operation-to-result path.
    wire [31:0] integer_sum,address_sum;
    initial if(PRECOMPUTED_ARITHMETIC!=0 && PRECOMPUTED_ARITHMETIC!=1)
        $fatal(1,"ALU precomputed arithmetic must be 0 or 1");
    generate if(PRECOMPUTED_ARITHMETIC!=0) begin:g_precomputed_arithmetic
        // Each instruction consumes either register arithmetic or its immediate
        // address sum. The selected word accompanies that exact RS packet.
        assign integer_sum=issue_arithmetic_i;
        assign address_sum=issue_arithmetic_i;
`ifdef VERILATOR
        wire register_rhs=issue_op_i==`RV32IM_OP_ADD || issue_op_i==`RV32IM_OP_SUB;
        wire [31:0] original_rhs=register_rhs ? issue_src2_value_i : issue_imm_i;
        wire [31:0] original_sum=(issue_op_i==`RV32IM_OP_SUB) ?
            issue_src1_value_i-original_rhs : issue_src1_value_i+original_rhs;
        always @(posedge clk_i) if(!reset_i && issue_valid_i)
            assert(issue_arithmetic_i==original_sum)
                else $fatal(1,"ALU precomputed word differs from its complete issue packet");
`endif
    end else begin:g_original_arithmetic
        wire [2:0] integer_subtract_views;
        wire [31:0] integer_adjusted_rhs;
        rv32_frequency_control_tree #(.LEAVES(3)) integer_subtract_tree (
            .signal_i(issue_op_i==`RV32IM_OP_SUB),.views_o(integer_subtract_views));
        assign integer_adjusted_rhs[15:0]=issue_src2_value_i[15:0] ^ {16{integer_subtract_views[0]}};
        assign integer_adjusted_rhs[31:16]=issue_src2_value_i[31:16] ^ {16{integer_subtract_views[1]}};
        assign integer_sum=fast_add_carry(issue_src1_value_i,integer_adjusted_rhs,integer_subtract_views[2]);
        assign address_sum=fast_add_carry(issue_src1_value_i,issue_imm_i,1'b0);
    end endgenerate
    wire [31:0] pc_relative_sum=fast_add_carry(issue_pc_i,issue_imm_i,1'b0);
    reg shift_busy;
    reg [4:0] shift_remaining;
    reg shift_right;
    reg shift_arithmetic;

    function automatic [31:0] fast_add_carry;
        input [31:0] lhs;
        input [31:0] adjusted_rhs;
        input carry_in;
`ifdef CPU2026_WORD_SIM
        begin
            fast_add_carry = lhs + adjusted_rhs + {31'b0, carry_in};
        end
`else
        reg [7:0] g0, p0, g1, p1, g2, p2, g3, p3;
        reg [8:0] carry;
        reg [4:0] chunk_sum;
        reg [31:0] sum_zero,sum_one;
        integer chunk;
        begin
            for (chunk = 0; chunk < 8; chunk = chunk + 1) begin
                chunk_sum = {1'b0, lhs[chunk*4 +: 4]} +
                            {1'b0, adjusted_rhs[chunk*4 +: 4]};
                // Both nibble results precede the group carry tree.
                // A late carry selects four bits; it does not start an adder.
                sum_zero[chunk*4 +: 4] = chunk_sum[3:0];
                sum_one[chunk*4 +: 4] = chunk_sum[3:0] + 4'd1;
                g0[chunk] = chunk_sum[4];
                p0[chunk] = &(lhs[chunk*4 +: 4] ^ adjusted_rhs[chunk*4 +: 4]);
            end
            for (chunk = 0; chunk < 8; chunk = chunk + 1) begin
                g1[chunk] = g0[chunk]; p1[chunk] = p0[chunk];
                if (chunk >= 1) begin
                    g1[chunk] = g0[chunk] | (p0[chunk] & g0[chunk-1]);
                    p1[chunk] = p0[chunk] & p0[chunk-1];
                end
            end
            for (chunk = 0; chunk < 8; chunk = chunk + 1) begin
                g2[chunk] = g1[chunk]; p2[chunk] = p1[chunk];
                if (chunk >= 2) begin
                    g2[chunk] = g1[chunk] | (p1[chunk] & g1[chunk-2]);
                    p2[chunk] = p1[chunk] & p1[chunk-2];
                end
            end
            for (chunk = 0; chunk < 8; chunk = chunk + 1) begin
                g3[chunk] = g2[chunk]; p3[chunk] = p2[chunk];
                if (chunk >= 4) begin
                    g3[chunk] = g2[chunk] | (p2[chunk] & g2[chunk-4]);
                    p3[chunk] = p2[chunk] & p2[chunk-4];
                end
            end
            carry[0] = carry_in;
            for (chunk = 0; chunk < 8; chunk = chunk + 1) begin
                carry[chunk+1] = g3[chunk] | (p3[chunk] & carry_in);
                fast_add_carry[chunk*4 +: 4] = carry[chunk] ?
                    sum_one[chunk*4 +: 4] : sum_zero[chunk*4 +: 4];
            end
        end
`endif
    endfunction

    wire issue_is_shift = (issue_op_i == `RV32IM_OP_SLLI) ||
        (issue_op_i == `RV32IM_OP_SRLI) ||
        (issue_op_i == `RV32IM_OP_SRAI) ||
        (issue_op_i == `RV32IM_OP_SLL) ||
        (issue_op_i == `RV32IM_OP_SRL) ||
        (issue_op_i == `RV32IM_OP_SRA);
    wire [4:0] issue_shift_amount =
        ((issue_op_i == `RV32IM_OP_SLLI) ||
         (issue_op_i == `RV32IM_OP_SRLI) ||
         (issue_op_i == `RV32IM_OP_SRAI)) ?
        issue_imm_i[4:0] : issue_src2_value_i[4:0];

    wire [31:0] immediate_shift_left,immediate_shift_right;
    wire [31:0] register_shift_left,register_shift_right;
    wire shift_sign_fill=issue_src1_value_i[31] &&
        (issue_op_i==`RV32IM_OP_SRAI || issue_op_i==`RV32IM_OP_SRA);
    // Only one operation is accepted per ALU edge. Immediate and register
    // shifts share the barrel; the existing five-bit amount selects its input.
    // The original parallel implementation remains available by default.
    generate if(SHIFT_IMPL==0 && SHIFT_SHARED_BARREL!=0) begin:g_shared_barrel
        wire [31:0] shared_left,shared_right;
        rv32_frequency_barrel32 shared_barrel (
            .value_i(issue_src1_value_i),.amount_i(issue_shift_amount),.fill_i(shift_sign_fill),
            .left_o(shared_left),.right_o(shared_right));
        assign immediate_shift_left=shared_left;
        assign immediate_shift_right=shared_right;
        assign register_shift_left=shared_left;
        assign register_shift_right=shared_right;
    end else if(SHIFT_IMPL==0) begin:g_parallel_barrel
        rv32_frequency_barrel32 immediate_barrel (
            .value_i(issue_src1_value_i),.amount_i(issue_imm_i[4:0]),.fill_i(shift_sign_fill),
            .left_o(immediate_shift_left),.right_o(immediate_shift_right));
        rv32_frequency_barrel32 register_barrel (
            .value_i(issue_src1_value_i),.amount_i(issue_src2_value_i[4:0]),.fill_i(shift_sign_fill),
            .left_o(register_shift_left),.right_o(register_shift_right));
    end else begin:g_iterative_shift_values
        assign immediate_shift_left=issue_src1_value_i;
        assign immediate_shift_right=issue_src1_value_i;
        assign register_shift_left=issue_src1_value_i;
        assign register_shift_right=issue_src1_value_i;
    end endgenerate

    // Compare four-bit chunks in parallel, then combine high chunks before
    // low chunks. The issue path otherwise contains a 32-bit serial compare
    // between the RS operand mux and the branch redirect register.
    wire [7:0] cmp_eq0, cmp_lt0;
    wire [3:0] cmp_eq1, cmp_lt1;
    wire [1:0] cmp_eq2, cmp_lt2;
    wire cmp_equal, cmp_unsigned_lt, cmp_signed_lt;
    genvar cmp_chunk;
    generate
        for (cmp_chunk = 0; cmp_chunk < 8; cmp_chunk = cmp_chunk + 1) begin : g_cmp_chunk
            assign cmp_eq0[cmp_chunk] =
                issue_src1_value_i[cmp_chunk*4 +: 4] ==
                issue_src2_value_i[cmp_chunk*4 +: 4];
            assign cmp_lt0[cmp_chunk] =
                issue_src1_value_i[cmp_chunk*4 +: 4] <
                issue_src2_value_i[cmp_chunk*4 +: 4];
        end
        for (cmp_chunk = 0; cmp_chunk < 4; cmp_chunk = cmp_chunk + 1) begin : g_cmp_pair
            assign cmp_eq1[cmp_chunk] = cmp_eq0[2*cmp_chunk+1] && cmp_eq0[2*cmp_chunk];
            assign cmp_lt1[cmp_chunk] = cmp_lt0[2*cmp_chunk+1] ||
                (cmp_eq0[2*cmp_chunk+1] && cmp_lt0[2*cmp_chunk]);
        end
        for (cmp_chunk = 0; cmp_chunk < 2; cmp_chunk = cmp_chunk + 1) begin : g_cmp_quad
            assign cmp_eq2[cmp_chunk] = cmp_eq1[2*cmp_chunk+1] && cmp_eq1[2*cmp_chunk];
            assign cmp_lt2[cmp_chunk] = cmp_lt1[2*cmp_chunk+1] ||
                (cmp_eq1[2*cmp_chunk+1] && cmp_lt1[2*cmp_chunk]);
        end
    endgenerate
    assign cmp_equal = cmp_eq2[1] && cmp_eq2[0];
    assign cmp_unsigned_lt = cmp_lt2[1] || (cmp_eq2[1] && cmp_lt2[0]);
    assign cmp_signed_lt = (issue_src1_value_i[31] ^ issue_src2_value_i[31]) ?
        issue_src1_value_i[31] : cmp_unsigned_lt;

    wire result_cancel;
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(1)) result_cancel_guard (
        .packet_i(recovery_packet_i),.active_i(result_valid_reg || shift_busy),.tag_i(result_rob_tag_reg),.cancel_o(result_cancel));
    wire issue_cancel;
    generate if(ISSUE_RECOVERY_PREDECODE!=0 && SELECTIVE_RECOVERY!=0) begin:g_predecoded_issue_cancel
        // The caller carries the same registered-packet age predicate with
        // the selected payload. Qualify it with this unit's actual valid.
        assign issue_cancel=issue_valid_i && issue_cancel_i;
    end else begin:g_original_issue_cancel
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(1)) issue_cancel_guard (
        .packet_i(recovery_packet_i),.active_i(issue_valid_i),.tag_i(issue_rob_tag_i),.cancel_o(issue_cancel));
    end endgenerate
    wire result_visible = result_valid_reg && !result_cancel &&
        (!live_tag_valid_i || (result_rob_tag_reg == live_tag_i));
    assign exec_valid_o = result_visible;
    assign exec_saved_valid_o = result_valid_reg &&
        (!live_tag_valid_i || (result_rob_tag_reg == live_tag_i));
    // The canceled result is invisible before the clock. A qualified
    // retained older instruction may replace that result on this same edge.
    // Surviving older results still require the original output handshake.
    wire recovery_replace=(RECOVERY_OLDER_ISSUE!=0) && result_cancel;
    assign issue_ready_o = !flush_i && !issue_cancel &&
        (recovery_replace || (!result_cancel && !shift_busy &&
         (!result_valid_reg || exec_ready_i ||
          (live_tag_valid_i && (result_rob_tag_reg != live_tag_i)))));

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

    // Invalid execution data is not architectural state. Reset/flush only
    // clear result validity and shift control; every newly valid result has
    // a complete payload write on its original acceptance edge.
    wire payload_stale=live_tag_valid_i && result_rob_tag_reg!=live_tag_i;
    wire payload_cancel=result_valid_reg && payload_stale && !exec_ready_i;
    wire payload_accept=!reset_i && !flush_i &&
        (recovery_replace || (!shift_busy && !payload_cancel)) &&
        issue_ready_o && issue_valid_i;
    wire payload_shift=!reset_i && !flush_i && !result_cancel && shift_busy && !payload_stale;
    wire [31:0] shifted_payload=shift_right ?
        {(shift_arithmetic && result_value_reg[31]),result_value_reg[31:1]} :
        {result_value_reg[30:0],1'b0};
    wire [31:0] value_payload;
    wire value_write;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(2)) value_selector (
        .events_i({payload_accept,payload_shift}),.values_i({calc_value,shifted_payload}),
        .write_o(value_write),.value_o(value_payload));
    rv32_frequency_word_bank #(.WIDTH(32)) value_owner (
        .clk_i(clk_i),.write_i(value_write),.data_i(value_payload),.data_o(result_value_reg));

    // Capture on the original result acceptance edge, with the original stall,
    // stale-result and iterative-shift priority. No added execution cycle.
    generate if (FORWARD_METADATA != 0) begin : g_forward_metadata
        wire [31:0] source_pc_reg, pred_target_reg;
        wire pred_taken_reg;
        wire [1:0] pred_kind_reg;
        assign exec_source_pc_o = source_pc_reg;
        assign exec_pred_taken_o = pred_taken_reg;
        assign exec_pred_target_o = pred_target_reg;
        assign exec_pred_kind_o = pred_kind_reg;
        rv32_frequency_word_bank #(.WIDTH(67)) prediction_owner (
            .clk_i(clk_i),.write_i(payload_accept),
            .data_i({issue_pc_i,issue_pred_target_i,issue_pred_taken_i,issue_pred_kind_i}),
            .data_o({source_pc_reg,pred_target_reg,pred_taken_reg,pred_kind_reg}));
    end else begin : g_no_forward_metadata
        assign exec_source_pc_o = 32'b0;
        assign exec_pred_taken_o = 1'b0;
        assign exec_pred_target_o = 32'b0;
        assign exec_pred_kind_o = 2'b0;
    end endgenerate

    // Exclusive opcode classes select fixed arithmetic/logic results after
    // their networks. Each decoded class reaches <=16 data bits per leaf.
    wire [15:0] value_classes;
    wire [16*32-1:0] value_class_data;
    wire comparison_value=
        (issue_op_i==`RV32IM_OP_SLTI && $signed(issue_src1_value_i)<$signed(issue_imm_i)) ||
        (issue_op_i==`RV32IM_OP_SLTIU && issue_src1_value_i<issue_imm_i) ||
        (issue_op_i==`RV32IM_OP_SLT && cmp_signed_lt) ||
        (issue_op_i==`RV32IM_OP_SLTU && cmp_unsigned_lt);
    wire [31:0] pc_plus_four=issue_pc_i+32'd4;
    assign value_classes[0]=(issue_op_i==`RV32IM_OP_LUI);
    assign value_class_data[0*32 +: 32]=issue_imm_i;
    assign value_classes[1]=(issue_op_i==`RV32IM_OP_AUIPC);
    assign value_class_data[1*32 +: 32]=pc_relative_sum;
    assign value_classes[2]=(issue_op_i==`RV32IM_OP_JAL || issue_op_i==`RV32IM_OP_JALR);
    assign value_class_data[2*32 +: 32]=pc_plus_four;
    assign value_classes[3]=(issue_op_i==`RV32IM_OP_ADDI);
    assign value_class_data[3*32 +: 32]=address_sum;
    assign value_classes[4]=(issue_op_i==`RV32IM_OP_ADD || issue_op_i==`RV32IM_OP_SUB);
    assign value_class_data[4*32 +: 32]=integer_sum;
    assign value_classes[5]=(issue_op_i==`RV32IM_OP_XORI);
    assign value_class_data[5*32 +: 32]=issue_src1_value_i ^ issue_imm_i;
    assign value_classes[6]=(issue_op_i==`RV32IM_OP_ORI);
    assign value_class_data[6*32 +: 32]=issue_src1_value_i | issue_imm_i;
    assign value_classes[7]=(issue_op_i==`RV32IM_OP_ANDI);
    assign value_class_data[7*32 +: 32]=issue_src1_value_i & issue_imm_i;
    assign value_classes[8]=(issue_op_i==`RV32IM_OP_SLLI);
    assign value_class_data[8*32 +: 32]=immediate_shift_left;
    assign value_classes[9]=(issue_op_i==`RV32IM_OP_SRLI || issue_op_i==`RV32IM_OP_SRAI);
    assign value_class_data[9*32 +: 32]=immediate_shift_right;
    assign value_classes[10]=(issue_op_i==`RV32IM_OP_XOR);
    assign value_class_data[10*32 +: 32]=issue_src1_value_i ^ issue_src2_value_i;
    assign value_classes[11]=(issue_op_i==`RV32IM_OP_OR);
    assign value_class_data[11*32 +: 32]=issue_src1_value_i | issue_src2_value_i;
    assign value_classes[12]=(issue_op_i==`RV32IM_OP_AND);
    assign value_class_data[12*32 +: 32]=issue_src1_value_i & issue_src2_value_i;
    assign value_classes[13]=(issue_op_i==`RV32IM_OP_SLL);
    assign value_class_data[13*32 +: 32]=register_shift_left;
    assign value_classes[14]=(issue_op_i==`RV32IM_OP_SRL || issue_op_i==`RV32IM_OP_SRA);
    assign value_class_data[14*32 +: 32]=register_shift_right;
    assign value_classes[15]=(issue_op_i==`RV32IM_OP_SLTI || issue_op_i==`RV32IM_OP_SLTIU || issue_op_i==`RV32IM_OP_SLT || issue_op_i==`RV32IM_OP_SLTU);
    assign value_class_data[15*32 +: 32]={31'd0,comparison_value};

    wire  unused_value_class_selector_write_o;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(16),.PRIORITY(0)) value_class_selector (
        .events_i(value_classes),.values_i(value_class_data),.write_o(unused_value_class_selector_write_o),.value_o(calc_value));
    wire conditional_branch=(issue_op_i==`RV32IM_OP_BEQ || issue_op_i==`RV32IM_OP_BNE || issue_op_i==`RV32IM_OP_BLT || issue_op_i==`RV32IM_OP_BGE || issue_op_i==`RV32IM_OP_BLTU || issue_op_i==`RV32IM_OP_BGEU);
    wire jal=(issue_op_i==`RV32IM_OP_JAL);
    wire jalr=(issue_op_i==`RV32IM_OP_JALR);
    assign calc_is_load=(issue_op_i==`RV32IM_OP_LB || issue_op_i==`RV32IM_OP_LH || issue_op_i==`RV32IM_OP_LW || issue_op_i==`RV32IM_OP_LBU || issue_op_i==`RV32IM_OP_LHU);
    assign calc_is_store=(issue_op_i==`RV32IM_OP_SB || issue_op_i==`RV32IM_OP_SH || issue_op_i==`RV32IM_OP_SW);

    assign calc_rd_we=(|value_classes) || calc_is_load;
    assign calc_is_branch=conditional_branch || jal || jalr;
    assign calc_is_memory=calc_is_load || calc_is_store;
    assign calc_mem_size=issue_mem_size_i;
    assign calc_mem_unsigned=issue_mem_unsigned_i;
    assign calc_branch_taken=jal || jalr ||
        (issue_op_i==`RV32IM_OP_BEQ && cmp_equal) ||
        (issue_op_i==`RV32IM_OP_BNE && !cmp_equal) ||
        (issue_op_i==`RV32IM_OP_BLT && cmp_signed_lt) ||
        (issue_op_i==`RV32IM_OP_BGE && !cmp_signed_lt) ||
        (issue_op_i==`RV32IM_OP_BLTU && cmp_unsigned_lt) ||
        (issue_op_i==`RV32IM_OP_BGEU && !cmp_unsigned_lt);
    wire  unused_branch_target_selector_write_o;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(2),.PRIORITY(0)) branch_target_selector (
        .events_i({jalr,(conditional_branch || jal)}),
        .values_i({(address_sum & 32'hfffffffe),pc_relative_sum}),.write_o(unused_branch_target_selector_write_o),.value_o(calc_branch_target));
    wire  unused_branch_next_pc_selector_write_o;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(3),.PRIORITY(0)) branch_next_pc_selector (
        .events_i({jalr,(jal || (conditional_branch && calc_branch_taken)),
                   (conditional_branch && !calc_branch_taken)}),
        .values_i({(address_sum & 32'hfffffffe),pc_relative_sum,pc_plus_four}),
        .write_o(unused_branch_next_pc_selector_write_o),.value_o(calc_redirect_pc));
    wire [31:0] indirect_predicted_target={issue_pc_i[31:12],issue_pred_target_i[11:0]};
    // Direct-mode conditional/JAL targets are exact PC+decoded immediate.
    // For JALR only, reconstruct the page-qualified metadata. The frontend
    // forces an out-of-page raw prediction to a direction mismatch, so an
    // alias of these low bits can never conceal a wrong fetch target.
    wire predicted_target_mismatch=(COMPACT_PRED_TARGET!=0)?
        ((issue_op_i==`RV32IM_OP_JALR) && indirect_predicted_target!=calc_branch_target):
        (issue_pred_target_i!=calc_branch_target);
    assign calc_redirect_valid=calc_is_branch &&
        ((issue_pred_taken_i!=calc_branch_taken) ||
         (calc_branch_taken && predicted_target_mismatch));
    wire  unused_memory_address_selector_write_o;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(1)) memory_address_selector (
        .events_i(calc_is_memory),.values_i(address_sum),.write_o(unused_memory_address_selector_write_o),.value_o(calc_mem_addr));
    wire [1:0] store_fallback_views;
    rv32_frequency_control_tree #(.LEAVES(2)) store_fallback_tree (
        .signal_i(calc_is_store && issue_store_data_i==32'b0),.views_o(store_fallback_views));
    genvar store_word;
    generate for(store_word=0;store_word<2;store_word=store_word+1) begin:g_store_operand
        assign calc_store_data[store_word*16 +: 16]=store_fallback_views[store_word]?
            issue_src2_value_i[store_word*16 +: 16]:issue_store_data_i[store_word*16 +: 16];
    end endgenerate

    localparam integer RESULT_METADATA_WIDTH=PHYS_ADDR_WIDTH+TAG_WIDTH+EPOCH_WIDTH+1+1+1+32+1+32+1+1+1+32+2+1+32;
    rv32_frequency_word_bank #(.WIDTH(RESULT_METADATA_WIDTH)) result_metadata_owner (
        .clk_i(clk_i),.write_i(payload_accept),
        .data_i({issue_phys_rd_i,issue_rob_tag_i,issue_epoch_i,calc_rd_we,calc_is_branch,calc_branch_taken,calc_branch_target,calc_redirect_valid,calc_redirect_pc,calc_is_memory,calc_is_load,calc_is_store,calc_mem_addr,calc_mem_size,calc_mem_unsigned,calc_store_data}),.data_o({result_phys_rd_reg,result_rob_tag_reg,result_epoch_reg,result_rd_we_reg,result_is_branch_reg,result_branch_taken_reg,result_branch_target_reg,result_redirect_valid_reg,result_redirect_pc_reg,result_is_memory_reg,result_is_load_reg,result_is_store_reg,result_mem_addr_reg,result_mem_size_reg,result_mem_unsigned_reg,result_store_data_reg}));

    always @(posedge clk_i) begin
        if (reset_i || flush_i || (result_cancel && !payload_accept))
        begin
            result_valid_reg <= 1'b0;
            shift_busy <= 1'b0;
        end
        else
            if (shift_busy && !recovery_replace)
            begin
                if (live_tag_valid_i && (result_rob_tag_reg != live_tag_i))
                begin
                    shift_busy <= 1'b0;
                end
                else
                begin
                    shift_remaining <= shift_remaining - 1'b1;
                    if (shift_remaining == 5'd1)
                    begin
                        shift_busy <= 1'b0;
                        result_valid_reg <= 1'b1;
                    end
                end
            end
            else
                if (result_valid_reg && live_tag_valid_i && (result_rob_tag_reg != live_tag_i) && !exec_ready_i && !recovery_replace)
                begin
                    result_valid_reg <= 1'b0;
                end
                else
                    if (issue_ready_o)
                    begin
                        if (issue_valid_i)
                        begin
                            if ((SHIFT_IMPL == 1) && issue_is_shift &&
                            issue_target_live_i && issue_rob_tag_i[0])
                            begin
                                result_valid_reg <= (issue_shift_amount == 0);
                                shift_busy <= (issue_shift_amount != 0);
                                shift_remaining <= issue_shift_amount;
                                shift_right <= (issue_op_i == `RV32IM_OP_SRLI) ||
                                (issue_op_i == `RV32IM_OP_SRAI) ||
                                (issue_op_i == `RV32IM_OP_SRL) ||
                                (issue_op_i == `RV32IM_OP_SRA);
                                shift_arithmetic <= (issue_op_i == `RV32IM_OP_SRAI) ||
                                (issue_op_i == `RV32IM_OP_SRA);
                            end
                            else
                            begin
                                result_valid_reg <= issue_target_live_i && issue_rob_tag_i[0];
                                shift_busy <= 1'b0;
                            end
                        end
                        else
                            if (exec_ready_i)
                            begin
                                result_valid_reg <= 1'b0;
                            end
                    end
    end
endmodule
