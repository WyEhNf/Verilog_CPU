`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Optional pipelined single-issue backend with a small completion queue.
// Architectural registers replace renaming and reservation stations.
module rv32_inorder_backend #(
    parameter integer BE_WIDTH = 1,
    parameter integer SHIFT_IMPL = 1,
    parameter integer SHIFT_SHARED_BARREL = 1,
    parameter integer ROB_ENTRIES = 4,
    parameter integer TAG_WIDTH = 11+$clog2(ROB_ENTRIES)
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
    output reg  [31:0]                  return_value_o,
    output wire                         branch_feedback_valid_o,
    output wire [31:0]                  branch_feedback_pc_o,
    output wire [1:0]                   branch_feedback_kind_o,
    output wire                         branch_feedback_taken_o,
    output wire [31:0]                  branch_feedback_target_o,
    output wire                         branch_feedback_pred_taken_o,
    output wire [31:0]                  branch_feedback_pred_target_o
);
    // Instructions issue in order. Only completion may pass an older load/MDU.
    // A branch resolves before another instruction can enter on a redirect;
    // consequently there is no younger execution state to roll back.
    localparam integer SW = $clog2(ROB_ENTRIES);
    localparam integer CW = $clog2(ROB_ENTRIES+1);
    reg [SW-1:0] head, tail;
    reg [CW-1:0] count;
    reg [ROB_ENTRIES-1:0] valid, done, writes, loads, stores, halts, faults;
    reg [7:0] generation [0:ROB_ENTRIES-1];
    reg [31:0] pc [0:ROB_ENTRIES-1], inst [0:ROB_ENTRIES-1];
    reg [4:0] rd [0:ROB_ENTRIES-1];
    wire [31:0] value [0:ROB_ENTRIES-1];
    wire [31:0] store_addr [0:ROB_ENTRIES-1];
    reg [1:0] store_size [0:ROB_ENTRIES-1];
    wire [31:0] registers [1:31];
    reg [31:1] register_valid;
    wire [32*32-1:0] register_rows;
    wire [31:0] rf_src1, rf_src2;
    assign register_rows[31:0]=32'b0;
    rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(32),.INDEX_WIDTH(5)) read_rs1 (
        .rows_i(register_rows),.index_i(trace_rs1_i[4:0]),.value_o(rf_src1));
    rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(32),.INDEX_WIDTH(5)) read_rs2 (
        .rows_i(register_rows),.index_i(trace_rs2_i[4:0]),.value_o(rf_src2));
    reg [3:0] epoch;
    reg stop_issue;

    function automatic [TAG_WIDTH-1:0] row_tag;
        input [SW-1:0] slot;
        begin row_tag = {generation[slot], slot, 2'b00, 1'b1}; end
    endfunction
    wire [TAG_WIDTH-1:0] alloc_tag = {generation[tail]+8'd1,tail,2'b00,1'b1};
    wire [SW-1:0] alu_slot, mdu_slot, load_slot;
    wire [TAG_WIDTH-1:0] alu_tag, mdu_tag;
    wire alu_valid, alu_ready, alu_issue_ready, mdu_ready, mdu_valid;
    wire [31:0] alu_value, mdu_value, alu_addr, alu_store_word;
    wire alu_load, alu_store, alu_memory, alu_branch, alu_taken, alu_redirect;
    wire [31:0] alu_target, alu_redirect_pc, alu_pc, alu_pred_target;
    wire alu_pred_taken, alu_unsigned;
    wire [1:0] alu_size, alu_pred_kind;
    assign alu_slot = alu_tag[3 +: SW];
    assign mdu_slot = mdu_tag[3 +: SW];
    assign load_slot = dcache_resp_lsq_tag_i[3 +: SW];
    wire alu_live = alu_valid && valid[alu_slot] && row_tag(alu_slot)==alu_tag;
    wire mdu_live = mdu_valid && valid[mdu_slot] && row_tag(mdu_slot)==mdu_tag;
    wire load_live = dcache_resp_valid_i && valid[load_slot] && loads[load_slot] &&
        row_tag(load_slot)==dcache_resp_lsq_tag_i;
    wire alu_fire = alu_live && alu_ready;

    // Committed stores retain their own generation until the matching ACK.
    // ROB slots can be reused without confusing a late store acknowledgement.
    reg [1:0] sb_valid, sb_sent, sb_done;
    reg sb_head, sb_tail;
    reg [1:0] sb_count;
    reg [7:0] sb_generation [0:1];
    reg [31:0] sb_addr [0:1], sb_word [0:1];
    reg [1:0] sb_size [0:1];
    function automatic [TAG_WIDTH-1:0] sb_tag;
        input slot;
        begin sb_tag = {{(TAG_WIDTH-12){1'b0}},sb_generation[slot],slot,2'b01,1'b1}; end
    endfunction
    wire sb_pop = sb_valid[sb_head] && sb_done[sb_head];
    reg sb_pick_valid, sb_pick, load_blocked;
    integer scan;
    reg scan_sb;
    always @* begin
        sb_pick_valid=1'b0;
        sb_pick=sb_head;
        load_blocked=1'b0;
        for(scan=0;scan<ROB_ENTRIES;scan=scan+1)
            if(valid[scan] && stores[scan]) load_blocked=1'b1;
        for(scan=0;scan<2;scan=scan+1) begin
            scan_sb=sb_head ^ (scan!=0);
            if(sb_valid[scan_sb] && !sb_done[scan_sb]) begin
                if(!sb_sent[scan_sb] || sb_addr[scan_sb][31:4]==alu_addr[31:4] ||
                   sb_addr[scan_sb]==32'h80000000) load_blocked=1'b1;
                if(!sb_pick_valid && !sb_sent[scan_sb] &&
                   (sb_addr[scan_sb]!=32'h80000000 || scan==0)) begin
                    sb_pick_valid=1'b1;
                    sb_pick=scan_sb;
                end
            end
        end
    end
    wire load_request = alu_live && alu_load && !load_blocked && !sb_pick_valid;
    assign dcache_req_valid_o = !halted_o && !error_o && (sb_pick_valid || load_request);
    assign dcache_req_is_load_o = !sb_pick_valid;
    assign dcache_req_is_store_o = sb_pick_valid;
    assign dcache_req_addr_o = sb_pick_valid ? sb_addr[sb_pick] : alu_addr;
    assign dcache_req_size_o = sb_pick_valid ? sb_size[sb_pick] : alu_size;
    assign dcache_req_unsigned_o = !sb_pick_valid && alu_unsigned;
    wire [31:0] request_store_word = sb_word[sb_pick];
    wire [15:0] request_base_mask = sb_size[sb_pick]==`RV32IM_MEM_BYTE ? 16'h0001 :
        sb_size[sb_pick]==`RV32IM_MEM_HALF ? 16'h0003 : 16'h000f;
    assign dcache_req_mask_o = sb_pick_valid ? request_base_mask << sb_addr[sb_pick][3:0] : 16'b0;
    assign dcache_req_wdata_o = {96'b0,request_store_word} << (sb_addr[sb_pick][3:0]*8);
    assign dcache_req_rob_tag_o = sb_pick_valid ? sb_tag(sb_pick) : alu_tag;
    assign dcache_req_lsq_tag_o = dcache_req_rob_tag_o;
    assign dcache_resp_ready_o = 1'b1;
    wire sb_send = dcache_req_valid_o && dcache_req_ready_i && sb_pick_valid;
    assign alu_ready = !alu_load || (load_request && dcache_req_ready_i && !halted_o && !error_o);

    // Last event wins in program-age order. Selection leaves drive sixteen
    // data bits, avoiding a wide priority mux controlled by an unbuffered match.
    wire [ROB_ENTRIES*32-1:0] completion_rows;
    wire [ROB_ENTRIES-1:0] completion_ready;
    wire [2*(ROB_ENTRIES+1)-1:0] operand_events;
    wire [2*(ROB_ENTRIES+1)*32-1:0] operand_values;
    wire [31:0] selected_src1, selected_src2;
    wire [31:0] src1,src2;
    wire [3:0] source_needed_views;
    wire [ROB_ENTRIES-1:0] source1_writers,source2_writers;
    wire [SW-1:0] age_slots [0:ROB_ENTRIES-1];
    genvar operand_row,operand_age,source_word;
    generate for(operand_row=0;operand_row<ROB_ENTRIES;operand_row=operand_row+1) begin:g_completion_row
        wire a=alu_fire && !alu_memory && alu_slot==SW'(operand_row);
        wire m=mdu_live && mdu_slot==SW'(operand_row);
        wire l=load_live && load_slot==SW'(operand_row);
        assign completion_ready[operand_row]=done[operand_row] || a || m || l;
        rv32_frequency_event_select #(.WIDTH(32),.EVENTS(4),.PRIORITY(1)) result_bypass (
            .events_i({l,m,a,1'b1}),
            .values_i({dcache_resp_word_data_i,mdu_value,alu_value,value[operand_row]}),
            .write_o(),.value_o(completion_rows[operand_row*32 +: 32]));
    end endgenerate
    generate for(operand_age=0;operand_age<ROB_ENTRIES;operand_age=operand_age+1) begin:g_operand_age
        wire [SW-1:0] slot=head+SW'(operand_age);
        assign age_slots[operand_age]=slot;
        wire writer=CW'(operand_age)<count && valid[slot] && writes[slot] && rd[slot]!=0;
        assign source1_writers[operand_age]=writer && rd[slot]==trace_rs1_i[4:0];
        assign source2_writers[operand_age]=writer && rd[slot]==trace_rs2_i[4:0];
        assign operand_events[operand_age+1]=source1_writers[operand_age];
        assign operand_events[(ROB_ENTRIES+1)+operand_age+1]=source2_writers[operand_age];
        wire [31:0] age_value;
        rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SW)) age_value_reader (
            .rows_i(completion_rows),.index_i(slot),.value_o(age_value));
        assign operand_values[(operand_age+1)*32 +: 32]=age_value;
        assign operand_values[((ROB_ENTRIES+1)+operand_age+1)*32 +: 32]=age_value;
    end endgenerate
    assign operand_events[0]=1'b1;
    assign operand_events[ROB_ENTRIES+1]=1'b1;
    assign operand_values[31:0]=rf_src1;
    assign operand_values[(ROB_ENTRIES+1)*32 +: 32]=rf_src2;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(ROB_ENTRIES+1),.PRIORITY(1)) select_rs1 (
        .events_i(operand_events[0 +: ROB_ENTRIES+1]),.values_i(operand_values[0 +: 32*(ROB_ENTRIES+1)]),
        .write_o(),.value_o(selected_src1));
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(ROB_ENTRIES+1),.PRIORITY(1)) select_rs2 (
        .events_i(operand_events[ROB_ENTRIES+1 +: ROB_ENTRIES+1]),
        .values_i(operand_values[32*(ROB_ENTRIES+1) +: 32*(ROB_ENTRIES+1)]),
        .write_o(),.value_o(selected_src2));
    reg src1_ready,src2_ready;
    integer ready_age;
    always @* begin
        src1_ready=1'b1;src2_ready=1'b1;
        for(ready_age=0;ready_age<ROB_ENTRIES;ready_age=ready_age+1) begin
            if(source1_writers[ready_age]) src1_ready=completion_ready[age_slots[ready_age]];
            if(source2_writers[ready_age]) src2_ready=completion_ready[age_slots[ready_age]];
        end
        if(!trace_rs1_used_i[0] || trace_rs1_i[4:0]==0) src1_ready=1'b1;
        if(!trace_rs2_used_i[0] || trace_rs2_i[4:0]==0) src2_ready=1'b1;
    end
    rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(2)) source_needed_tree (
        .signal_i({trace_rs2_used_i[0] && trace_rs2_i[4:0]!=0,
                   trace_rs1_used_i[0] && trace_rs1_i[4:0]!=0}),.views_o(source_needed_views));
    generate for(source_word=0;source_word<2;source_word=source_word+1) begin:g_source_word
        assign src1[source_word*16 +: 16]={16{source_needed_views[2*source_word]}} & selected_src1[source_word*16 +: 16];
        assign src2[source_word*16 +: 16]={16{source_needed_views[2*source_word+1]}} & selected_src2[source_word*16 +: 16];
    end endgenerate
    wire is_mdu = trace_op_i[0 +: `RV32IM_OP_WIDTH]>=`RV32IM_OP_MUL &&
        trace_op_i[0 +: `RV32IM_OP_WIDTH]<=`RV32IM_OP_REMU;
    wire issue_enable = count<CW'(ROB_ENTRIES) && src1_ready && src2_ready && !stop_issue &&
        !halted_o && !error_o && !flush_i && !reset_i && !redirect_valid_o &&
        (!alu_valid || alu_ready);
    assign trace_ready_o = {{(BE_WIDTH-1){1'b0}},issue_enable && (is_mdu ? mdu_ready : alu_issue_ready)};
    wire input_fire = trace_valid_i[0] && trace_ready_o[0];
    wire [1:0] launch_views;
    rv32_frequency_control_tree #(.LEAVES(2)) launch_tree (
        .signal_i(trace_valid_i[0] && issue_enable),.views_o(launch_views));

    rv32i_alu #(.TAG_WIDTH(TAG_WIDTH),.PHYS_ADDR_WIDTH(5),.ROB_ENTRIES(ROB_ENTRIES),
        .SHIFT_IMPL(SHIFT_IMPL),.SHIFT_SHARED_BARREL(SHIFT_SHARED_BARREL),.FORWARD_METADATA(1)) alu (
        .clk_i(clk_i),.reset_i(reset_i),.flush_i(flush_i),.recovery_packet_i('0),.issue_cancel_i(1'b0),
        .issue_valid_i(launch_views[0] && !is_mdu),.issue_ready_o(alu_issue_ready),
        .issue_op_i(trace_op_i[0 +: `RV32IM_OP_WIDTH]),.issue_pc_i(trace_pc_i[31:0]),
        .issue_imm_i(trace_imm_i[31:0]),.issue_src1_value_i(src1),.issue_src2_value_i(src2),
        .issue_store_data_i(src2),.issue_phys_rd_i(trace_rd_i[4:0]),.issue_rob_tag_i(alloc_tag),
        .issue_epoch_i(epoch),.issue_target_live_i(1'b1),.issue_pred_taken_i(trace_pred_taken_i[0]),
        .issue_pred_target_i(trace_pred_target_i[31:0]),.issue_pred_kind_i(trace_pred_kind_i[1:0]),
        .issue_mem_size_i(trace_mem_size_i[1:0]),.issue_mem_unsigned_i(trace_mem_unsigned_i[0]),
        .exec_valid_o(alu_valid),.exec_ready_i(alu_ready),.exec_value_o(alu_value),.exec_rob_tag_o(alu_tag),
        .exec_is_branch_o(alu_branch),.exec_branch_taken_o(alu_taken),.exec_branch_target_o(alu_target),
        .exec_redirect_valid_o(alu_redirect),.exec_redirect_pc_o(alu_redirect_pc),
        .exec_is_memory_o(alu_memory),.exec_is_load_o(alu_load),.exec_is_store_o(alu_store),
        .exec_mem_addr_o(alu_addr),.exec_mem_size_o(alu_size),.exec_mem_unsigned_o(alu_unsigned),
        .exec_store_data_o(alu_store_word),.exec_source_pc_o(alu_pc),.exec_pred_taken_o(alu_pred_taken),
        .exec_pred_target_o(alu_pred_target),.exec_pred_kind_o(alu_pred_kind),
        .live_tag_valid_i(1'b0),.live_tag_i({TAG_WIDTH{1'b0}}),
        .exec_saved_valid_o(),.exec_phys_rd_o(),.exec_epoch_o(),.exec_rd_we_o());
    rv32m_mdu_iterative #(.TAG_WIDTH(TAG_WIDTH),.PHYS_ADDR_WIDTH(5),.ROB_ENTRIES(ROB_ENTRIES)) mdu (
        .clk_i(clk_i),.reset_i(reset_i),.flush_i(flush_i),.recovery_packet_i('0),
        .req_valid_i(launch_views[1] && is_mdu),.req_ready_o(mdu_ready),
        .req_op_i(trace_op_i[0 +: `RV32IM_OP_WIDTH]),.req_src1_i(src1),.req_src2_i(src2),
        .req_rob_tag_i(alloc_tag),.req_phys_rd_i(trace_rd_i[4:0]),.req_target_live_i(1'b1),
        .resp_valid_o(mdu_valid),.resp_ready_i(1'b1),.resp_value_o(mdu_value),.resp_rob_tag_o(mdu_tag),
        .live_tag_valid_i(1'b0),.live_tag_i({TAG_WIDTH{1'b0}}),
        .occupied_o(),.resp_phys_rd_o(),.resp_rd_we_o());

    // Redirect suppresses allocation on the same edge. Older completions and
    // committed stores survive; they precede this branch in program order.
    // Branches are never memory results, so their ready is unconditional.
    // Keeping cache readiness out of these paths also avoids a frontend-
    // predictor-cache arbitration loop through the redirect epoch.
    assign redirect_valid_o = alu_live && alu_branch && alu_redirect;
    assign redirect_pc_o = alu_redirect_pc;
    assign redirect_epoch_o = epoch+1'b1;
    assign branch_feedback_valid_o = alu_live && alu_branch;
    assign branch_feedback_pc_o = alu_pc;
    assign branch_feedback_kind_o = alu_pred_kind;
    assign branch_feedback_taken_o = alu_taken;
    assign branch_feedback_target_o = alu_target;
    assign branch_feedback_pred_taken_o = alu_pred_taken;
    assign branch_feedback_pred_target_o = alu_pred_target;

    wire retire_valid = valid[head] && done[head] && !halted_o && !error_o &&
        (!stores[head] || faults[head] || sb_count<2) &&
        (!halts[head] || sb_count==0);
    wire retire = retire_valid && commit_ready_i;
    wire sb_push = retire && stores[head] && !faults[head];
    wire [15:0] retire_base_mask = store_size[head]==`RV32IM_MEM_BYTE ? 16'h0001 :
        store_size[head]==`RV32IM_MEM_HALF ? 16'h0003 : 16'h000f;
    assign commit_valid_o = {{(BE_WIDTH-1){1'b0}},retire_valid};
    assign commit_pc_o = {{(BE_WIDTH-1)*32{1'b0}},pc[head]};
    assign commit_inst_o = {{(BE_WIDTH-1)*32{1'b0}},inst[head]};
    assign commit_rd_o = {{(BE_WIDTH-1)*5{1'b0}},rd[head]};
    assign commit_rd_we_o = {{(BE_WIDTH-1){1'b0}},writes[head] && !faults[head]};
    assign commit_value_o = {{(BE_WIDTH-1)*32{1'b0}},value[head]};
    assign commit_is_store_o = {{(BE_WIDTH-1){1'b0}},stores[head]};
    assign commit_store_addr_o = {{(BE_WIDTH-1)*32{1'b0}},store_addr[head]};
    assign commit_store_mask_o = {{(BE_WIDTH-1)*16{1'b0}},retire_base_mask << store_addr[head][3:0]};
    assign commit_store_data_o = {{(BE_WIDTH-1)*128{1'b0}},
        {96'b0,value[head]} << (store_addr[head][3:0]*8)};
    assign commit_tag_o = {{(BE_WIDTH-1)*TAG_WIDTH{1'b0}},row_tag(head)};

    wire [8*5-1:0] register_write_indices;
    wire [7:0] register_write_enables;
    rv32_frequency_control_tree #(.WIDTH(5),.LEAVES(8)) register_index_tree (
        .signal_i(rd[head]),.views_o(register_write_indices));
    rv32_frequency_control_tree #(.LEAVES(8)) register_write_tree (
        .signal_i(retire && writes[head] && !faults[head]),.views_o(register_write_enables));
    genvar rf_row,result_row;
    generate for(rf_row=1;rf_row<32;rf_row=rf_row+1) begin:g_register_row
        wire write=register_write_enables[rf_row/4] && register_write_indices[(rf_row/4)*5 +: 5]==5'(rf_row);
        wire [1:0] initialized;
        rv32_frequency_control_tree #(.LEAVES(2)) initialized_tree (
            .signal_i(register_valid[rf_row]),.views_o(initialized));
        rv32_frequency_word_bank #(.WIDTH(32)) owner (
            .clk_i(clk_i),.write_i(write),.data_i(value[head]),.data_o(registers[rf_row]));
        for(genvar rf_word=0;rf_word<2;rf_word=rf_word+1) begin:g_word
            assign register_rows[rf_row*32+rf_word*16 +: 16]=
                {16{initialized[rf_word]}} & registers[rf_row][rf_word*16 +: 16];
        end
        always @(posedge clk_i)
            if(reset_i || flush_i) register_valid[rf_row]<=1'b0;
            else if(write) register_valid[rf_row]<=1'b1;
    end endgenerate
    wire [1:0] store_result_views;
    wire [31:0] alu_retire_value;
    rv32_frequency_control_tree #(.LEAVES(2)) store_result_tree (
        .signal_i(alu_store),.views_o(store_result_views));
    generate for(genvar result_word=0;result_word<2;result_word=result_word+1) begin:g_alu_retire_word
        assign alu_retire_value[result_word*16 +: 16]=store_result_views[result_word] ?
            alu_store_word[result_word*16 +: 16] : alu_value[result_word*16 +: 16];
    end endgenerate
    generate for(result_row=0;result_row<ROB_ENTRIES;result_row=result_row+1) begin:g_result_row
        wire a=alu_fire && !alu_load && alu_slot==SW'(result_row);
        wire m=mdu_live && mdu_slot==SW'(result_row);
        wire l=load_live && load_slot==SW'(result_row);
        wire write;
        wire [31:0] next_value;
        rv32_frequency_event_select #(.WIDTH(32),.EVENTS(3),.PRIORITY(1)) selector (
            .events_i({l,m,a}),.values_i({dcache_resp_word_data_i,mdu_value,
                alu_retire_value}),.write_o(write),.value_o(next_value));
        rv32_frequency_word_bank #(.WIDTH(32)) owner (
            .clk_i(clk_i),.write_i(write),.data_i(next_value),.data_o(value[result_row]));
        rv32_frequency_word_bank #(.WIDTH(32)) store_address_owner (
            .clk_i(clk_i),.write_i(a && alu_store),.data_i(alu_addr),.data_o(store_addr[result_row]));
    end endgenerate
    integer row;
    always @(posedge clk_i) begin
        if(reset_i || flush_i) begin
            head<=0; tail<=0; count<=0;
            valid<=0; done<=0; writes<=0; loads<=0; stores<=0; halts<=0; faults<=0;
            epoch<=0; stop_issue<=0;
            halted_o<=0; error_o<=0; return_value_o<=0;
            sb_head<=0; sb_tail<=0; sb_count<=0; sb_valid<=0; sb_sent<=0; sb_done<=0;
            for(row=0;row<ROB_ENTRIES;row=row+1) generation[row]<=0;
            for(row=0;row<2;row=row+1) sb_generation[row]<=0;
        end else begin
            if(redirect_valid_o) epoch<=epoch+1'b1;
            if(alu_fire) begin
                if(!alu_load) done[alu_slot]<=1'b1;
                if(alu_store) begin
                    store_size[alu_slot]<=alu_size;
                end
            end
            if(mdu_live) done[mdu_slot]<=1'b1;
            if(load_live) begin
                done[load_slot]<=1'b1;
                faults[load_slot]<=faults[load_slot] || dcache_resp_error_i;
            end
            if(retire) begin
                valid[head]<=1'b0;
                head<=head+1'b1;
                if(halts[head]) begin halted_o<=1'b1; return_value_o<=value[head]; end
                if(faults[head]) error_o<=1'b1;
            end
            if(input_fire) begin
                valid[tail]<=1'b1; done[tail]<=1'b0;
                generation[tail]<=generation[tail]+8'd1;
                pc[tail]<=trace_pc_i[31:0]; inst[tail]<=trace_inst_i[31:0]; rd[tail]<=trace_rd_i[4:0];
                writes[tail]<=trace_rd_we_i[0] && trace_rd_i[4:0]!=0 && !trace_is_store_i[0];
                loads[tail]<=trace_is_load_i[0]; stores[tail]<=trace_is_store_i[0];
                halts[tail]<=trace_is_halt_i[0]; faults[tail]<=trace_is_error_i[0];
                if(trace_is_halt_i[0] || trace_is_error_i[0]) stop_issue<=1'b1;
                tail<=tail+1'b1;
            end
            case({input_fire,retire})
                2'b10: count<=count+1'b1;
                2'b01: count<=count-1'b1;
                default: count<=count;
            endcase
            if(sb_send) sb_sent[sb_pick]<=1'b1;
            for(row=0;row<2;row=row+1)
                if(dcache_store_ack_valid_i && sb_valid[row] &&
                   (sb_sent[row] || (sb_send && sb_pick==1'(row))) &&
                   dcache_store_ack_lsq_tag_i==sb_tag(1'(row))) begin
                    sb_done[row]<=1'b1;
                    if(dcache_store_ack_error_i) error_o<=1'b1;
                end
            if(sb_pop) begin sb_valid[sb_head]<=1'b0; sb_head<=~sb_head; end
            if(sb_push) begin
                sb_valid[sb_tail]<=1'b1; sb_sent[sb_tail]<=1'b0; sb_done[sb_tail]<=1'b0;
                sb_addr[sb_tail]<=store_addr[head]; sb_word[sb_tail]<=value[head];
                sb_size[sb_tail]<=store_size[head]; sb_generation[sb_tail]<=sb_generation[sb_tail]+8'd1;
                sb_tail<=~sb_tail;
            end
            case({sb_push,sb_pop})
                2'b10: sb_count<=sb_count+1'b1;
                2'b01: sb_count<=sb_count-1'b1;
                default: sb_count<=sb_count;
            endcase
        end
    end
    initial begin
        if(BE_WIDTH!=1 || ROB_ENTRIES<4 || (ROB_ENTRIES & (ROB_ENTRIES-1))!=0 ||
           TAG_WIDTH!=SW+11) begin
            $display("ERROR: inorder backend requires BE1, power-of-two ROB>=4 and full generation tags");
            $finish(1);
        end
    end
    wire unused_inputs = &{1'b0,trace_is_branch_i,trace_store_data_i,dcache_resp_addr_i,
        dcache_resp_line_data_i,dcache_resp_line_valid_i};
endmodule
