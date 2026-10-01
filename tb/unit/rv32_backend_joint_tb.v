`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32_backend_joint_tb #(
    parameter integer BE_WIDTH = 1,
    parameter integer STORE_BUFFERED_RETIRE = 0,
    parameter integer COMPLETION_BYPASS = 0,
    parameter integer LSQ_STORE_ADMISSION_BYPASS = 0,
    parameter integer PREDICTOR_META = 0,
    parameter integer ASAP7_FANOUT_BUFFERS = 0,
    parameter integer ROB_CONTROL_REGISTER_BANKS = 0,
    parameter integer CHECKPOINT_IMPL = 0,
    parameter integer RAT_RECOVERY_IMPL = 0,
    parameter integer EARLY_STORE_ADDRESS = 0,
    parameter integer RS_ISSUE_METADATA = 0,
    parameter integer SHARED_ADDRESS_DIRECTED = 0
);
    initial $display("B09_TB_START");
    initial begin
        #10000;
        $display("FAIL: B-09 backend joint timeout");
        $finish(1);
    end
    localparam integer TAGW = 16;
    integer shared_store_slot, shared_rs_slot, shared_wait, shared_lane;
    reg shared_early_seen, shared_disjoint_seen, shared_rs_retained, shared_regular_store;
    reg clk, reset, flush;
    reg trace_valid;
    wire trace_ready;
    reg [31:0] trace_pc, trace_inst, trace_imm;
    reg [5:0] trace_op;
    reg [4:0] trace_rd, trace_rs1, trace_rs2;
    reg trace_rd_we, trace_rs1_used, trace_rs2_used;
    reg trace_load, trace_store, trace_branch, trace_halt, trace_error;
    reg [1:0] trace_size;
    reg trace_unsigned;
    reg [127:0] trace_store_data;
    reg trace_pred_taken;
    reg [31:0] trace_pred_target;
    reg [1:0] trace_pred_kind;
    wire req_valid, req_ready, req_load, req_store, req_unsigned;
    wire [31:0] req_addr;
    wire [1:0] req_size;
    wire [15:0] req_mask;
    wire [127:0] req_wdata;
    wire [TAGW-1:0] req_rob_tag, req_lsq_tag;
    reg resp_valid, resp_line_valid, resp_error;
    reg [TAGW-1:0] resp_lsq_tag;
    reg [31:0] resp_addr, resp_word;
    reg [127:0] resp_line;
    reg store_ack_valid, store_ack_error;
    reg [TAGW-1:0] store_ack_lsq_tag;
    reg inject_load_error, inject_store_error;
    reg defer_load_response, held_load_valid, completion_collision_seen;
    reg [TAGW-1:0] held_load_lsq_tag;
    reg [31:0] held_load_addr, held_load_word;
    reg [127:0] held_load_line;
    reg commit_ready;
    wire commit_valid, commit_rd_we, commit_store;
    wire [BE_WIDTH-1:0] commit_valid_all, commit_rd_we_all;
    wire [BE_WIDTH*32-1:0] commit_pc_all, commit_value_all;
    wire [31:0] commit_pc, commit_inst, commit_value, commit_store_addr;
    assign commit_valid = commit_valid_all[0];
    assign commit_rd_we = commit_rd_we_all[0];
    assign commit_pc = commit_pc_all[0 +: 32];
    assign commit_value = commit_value_all[0 +: 32];
    wire [4:0] commit_rd;
    wire [15:0] commit_store_mask;
    wire [127:0] commit_store_data;
    wire [TAGW-1:0] commit_tag;
    wire redirect_valid, halted, error;
    wire [31:0] redirect_pc;
    wire [31:0] return_value;
    integer bad, commit_count;
    integer history_write, history_read, history_lane;
    reg [31:0] history_pc [0:127];
    reg [31:0] history_value [0:127];
    reg history_rd_we [0:127];
    reg redirect_seen, younger_commit_seen;
    reg [31:0] redirect_pc_seen;
    reg free_list_error_seen;
    integer recovery_branch_slot;
    reg [5:0] recovery_branch_phys;
    reg [7:0] memory [0:255];
    integer i;
    wire feedback_valid;
    wire [15:0] feedback_metadata;
    wire [7:0] recovery_history;
    reg [15:0] expected_metadata_mem [0:7];
    reg recovery_metadata_check;
    reg [7:0] expected_recovery_history;
    integer metadata_lane;
    function [15:0] metadata_for_pc;
        input [31:0] pc;
        metadata_for_pc = pc[15:0] ^ 16'he35a;
    endfunction
    always @(posedge clk) begin
        recovery_metadata_check <= 0;
        if (reset) begin
            for (metadata_lane=0; metadata_lane<8; metadata_lane=metadata_lane+1)
                expected_metadata_mem[metadata_lane] <= 0;
        end else begin
            if (feedback_valid && feedback_metadata !== ((PREDICTOR_META != 0) ?
                expected_metadata_mem[dut.branch_feedback_slot] : 16'b0))
                $fatal(1, "Backend feedback lost query-time metadata");
            if (PREDICTOR_META != 0 && dut.rob_recovery_accept && dut.branch_pending) begin
                recovery_metadata_check <= 1;
                expected_recovery_history <= (dut.branch_pending_kind == `RV32IM_PRED_BRANCH) ?
                    {expected_metadata_mem[dut.branch_pending_tag[5:3]][14:8], dut.branch_pending_taken} :
                    expected_metadata_mem[dut.branch_pending_tag[5:3]][15:8];
            end
            for (metadata_lane=0; metadata_lane<BE_WIDTH; metadata_lane=metadata_lane+1)
                if (dut.dispatch_valid[metadata_lane] && dut.rob_alloc_fire[metadata_lane])
                    expected_metadata_mem[dut.rob_alloc_tag[metadata_lane*TAGW+3 +: 3]] <=
                        metadata_for_pc(dut.trace_pc_i[metadata_lane*32 +: 32]);
        end
    end
    always @(negedge clk) if (recovery_metadata_check && recovery_history !== expected_recovery_history)
        $fatal(1, "Backend recovery history does not match retained branch checkpoint");

    // Check dispatch-time metadata by full generation tag, rather than using
    // the implementation's old ROB metadata arrays as the reference.
    reg inline_score_valid [0:7];
    reg [TAGW-1:0] inline_score_tag [0:7];
    reg [31:0] inline_score_pc [0:7];
    reg [69:0] inline_score_meta [0:7];
    reg [69:0] inline_actual_meta;
    integer inline_lane, inline_slot;
    integer inline_issue_checks, inline_feedback_checks;
    initial begin
        inline_issue_checks = 0;
        inline_feedback_checks = 0;
        if (dut.RS_ISSUE_METADATA != RS_ISSUE_METADATA)
            $fatal(1,"RS metadata parameter did not reach the backend");
    end
    always @(posedge clk) begin
        if (reset) begin
            for (inline_slot=0; inline_slot<8; inline_slot=inline_slot+1)
                inline_score_valid[inline_slot] <= 0;
        end else begin
            for (inline_lane=0; inline_lane<BE_WIDTH; inline_lane=inline_lane+1) begin
                if (dut.rs_issue_valid[inline_lane]) begin
                    inline_slot = dut.rs_issue_tag[inline_lane*TAGW+3 +: 3];
                    if (!inline_score_valid[inline_slot] ||
                        inline_score_tag[inline_slot] !== dut.rs_issue_tag[inline_lane*TAGW +: TAGW])
                        $fatal(1,"RS issue has no full-tag dispatch metadata");
                    inline_actual_meta = {dut.rs_issue_mem_unsigned[inline_lane],
                        dut.rs_issue_mem_size[inline_lane*2 +: 2],
                        dut.rs_issue_pred_kind[inline_lane*2 +: 2],
                        dut.rs_issue_pred_target[inline_lane*32 +: 32],
                        dut.rs_issue_pred_taken[inline_lane],dut.rs_issue_imm[inline_lane*32 +: 32]};
                    if (inline_actual_meta !== inline_score_meta[inline_slot])
                        $fatal(1,"RS issue metadata changed: mode=%0d slot=%0d",RS_ISSUE_METADATA,inline_slot);
                    inline_issue_checks = inline_issue_checks+1;
                end
            end
            if (feedback_valid) begin
                inline_slot = dut.branch_feedback_slot;
                if (dut.branch_feedback_pc_r !== inline_score_pc[inline_slot] ||
                    dut.branch_feedback_pred_taken_r !== inline_score_meta[inline_slot][32] ||
                    dut.branch_feedback_pred_target_r !== inline_score_meta[inline_slot][64:33] ||
                    dut.branch_feedback_kind_r !== inline_score_meta[inline_slot][66:65])
                    $fatal(1,"Branch feedback lost dispatch-time PC/prediction: mode=%0d",RS_ISSUE_METADATA);
                inline_feedback_checks = inline_feedback_checks+1;
            end
            if (dut.branch_pending) begin
                inline_slot = dut.branch_pending_tag[5:3];
                if (inline_score_tag[inline_slot] !== dut.branch_pending_tag ||
                    dut.branch_pending_source_pc !== inline_score_pc[inline_slot] ||
                    dut.branch_pending_pred_taken !== inline_score_meta[inline_slot][32] ||
                    dut.branch_pending_pred_target !== inline_score_meta[inline_slot][64:33] ||
                    dut.branch_pending_kind !== inline_score_meta[inline_slot][66:65])
                    $fatal(1,"Retained recovery branch lost its execution metadata");
            end
            for (inline_lane=0; inline_lane<BE_WIDTH; inline_lane=inline_lane+1) begin
                if (dut.dispatch_valid[inline_lane] && dut.rob_alloc_fire[inline_lane]) begin
                    inline_slot = dut.rob_alloc_tag[inline_lane*TAGW+3 +: 3];
                    inline_score_valid[inline_slot] <= 1;
                    inline_score_tag[inline_slot] <= dut.rob_alloc_tag[inline_lane*TAGW +: TAGW];
                    inline_score_pc[inline_slot] <= dut.trace_pc_i[inline_lane*32 +: 32];
                    inline_score_meta[inline_slot] <= {dut.trace_mem_unsigned_i[inline_lane],
                        dut.trace_mem_size_i[inline_lane*2 +: 2],dut.trace_pred_kind_i[inline_lane*2 +: 2],
                        dut.trace_pred_target_i[inline_lane*32 +: 32],dut.trace_pred_taken_i[inline_lane],
                        dut.trace_imm_i[inline_lane*32 +: 32]};
                end
            end
        end
    end

    assign req_ready = 1'b1;
    rv32_backend_joint #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(64), .ROB_ENTRIES(8), .RS_ENTRIES(4), .LSQ_ENTRIES(4), .LSQ_STORE_ADMISSION_BYPASS(LSQ_STORE_ADMISSION_BYPASS), .PREDICTOR_META(PREDICTOR_META), .ASAP7_FANOUT_BUFFERS(ASAP7_FANOUT_BUFFERS), .ROB_CONTROL_REGISTER_BANKS(ROB_CONTROL_REGISTER_BANKS), .CHECKPOINT_IMPL(CHECKPOINT_IMPL), .RAT_RECOVERY_IMPL(RAT_RECOVERY_IMPL), .EARLY_STORE_ADDRESS(EARLY_STORE_ADDRESS), .RS_ISSUE_METADATA(RS_ISSUE_METADATA), .STORE_BUFFERED_RETIRE(STORE_BUFFERED_RETIRE), .COMPLETION_BYPASS(COMPLETION_BYPASS), .TAG_WIDTH(TAGW)) dut (
        .trace_pred_metadata_i(metadata_for_pc(trace_pc)), .branch_feedback_valid_o(feedback_valid),
        .branch_feedback_metadata_o(feedback_metadata), .branch_recovery_history_o(recovery_history),
        .clk_i(clk), .reset_i(reset), .flush_i(flush), .trace_valid_i(trace_valid), .trace_ready_o(trace_ready), .trace_pc_i(trace_pc), .trace_inst_i(trace_inst), .trace_op_i(trace_op), .trace_imm_i(trace_imm), .trace_rd_i(trace_rd), .trace_rs1_i(trace_rs1), .trace_rs2_i(trace_rs2), .trace_rd_we_i(trace_rd_we), .trace_rs1_used_i(trace_rs1_used), .trace_rs2_used_i(trace_rs2_used), .trace_is_load_i(trace_load), .trace_is_store_i(trace_store), .trace_is_branch_i(trace_branch), .trace_is_halt_i(trace_halt), .trace_is_error_i(trace_error), .trace_mem_size_i(trace_size), .trace_mem_unsigned_i(trace_unsigned), .trace_store_data_i(trace_store_data), .trace_pred_taken_i(trace_pred_taken), .trace_pred_target_i(trace_pred_target), .trace_pred_kind_i(trace_pred_kind), .dcache_req_valid_o(req_valid), .dcache_req_ready_i(req_ready), .dcache_req_is_load_o(req_load), .dcache_req_is_store_o(req_store), .dcache_req_addr_o(req_addr), .dcache_req_size_o(req_size), .dcache_req_unsigned_o(req_unsigned), .dcache_req_mask_o(req_mask), .dcache_req_wdata_o(req_wdata), .dcache_req_rob_tag_o(req_rob_tag), .dcache_req_lsq_tag_o(req_lsq_tag), .dcache_resp_valid_i(resp_valid), .dcache_resp_ready_o(), .dcache_resp_lsq_tag_i(resp_lsq_tag), .dcache_resp_addr_i(resp_addr), .dcache_resp_line_data_i(resp_line), .dcache_resp_word_data_i(resp_word), .dcache_resp_line_valid_i(resp_line_valid), .dcache_resp_error_i(resp_error), .dcache_store_ack_valid_i(store_ack_valid), .dcache_store_ack_lsq_tag_i(store_ack_lsq_tag), .dcache_store_ack_error_i(store_ack_error), .commit_ready_i(commit_ready), .commit_valid_o(commit_valid_all), .commit_pc_o(commit_pc_all), .commit_inst_o(commit_inst), .commit_rd_o(commit_rd), .commit_rd_we_o(commit_rd_we_all), .commit_value_o(commit_value_all), .commit_is_store_o(commit_store), .commit_store_addr_o(commit_store_addr), .commit_store_mask_o(commit_store_mask), .commit_store_data_o(commit_store_data), .commit_tag_o(commit_tag), .redirect_valid_o(redirect_valid), .redirect_pc_o(redirect_pc), .halted_o(halted), .error_o(error), .return_value_o(return_value)
    );
    initial begin clk = 0; forever #5 clk = ~clk; end
    always @(posedge clk) begin
        resp_valid <= 1'b0;
        resp_error <= 1'b0;
        store_ack_valid <= 1'b0;
        store_ack_error <= 1'b0;
        if (req_valid && req_ready) begin
            if (req_load) begin
                if (defer_load_response) begin
                    held_load_valid <= 1'b1;
                    held_load_lsq_tag <= req_lsq_tag;
                    held_load_addr <= req_addr;
                    held_load_line <= {96'b0, memory[req_addr[7:0]+3], memory[req_addr[7:0]+2], memory[req_addr[7:0]+1], memory[req_addr[7:0]]};
                    held_load_word <= {memory[req_addr[7:0]+3], memory[req_addr[7:0]+2], memory[req_addr[7:0]+1], memory[req_addr[7:0]]};
                end else begin
                    resp_valid <= 1'b1;
                    resp_error <= inject_load_error;
                    resp_lsq_tag <= req_lsq_tag;
                    resp_addr <= req_addr;
                    resp_line_valid <= 1'b1;
                    resp_line <= {96'b0, memory[req_addr[7:0]+3], memory[req_addr[7:0]+2], memory[req_addr[7:0]+1], memory[req_addr[7:0]]};
                    resp_word <= {memory[req_addr[7:0]+3], memory[req_addr[7:0]+2], memory[req_addr[7:0]+1], memory[req_addr[7:0]]};
                end
            end else if (req_store) begin
                store_ack_valid <= 1'b1;
                store_ack_error <= inject_store_error;
                store_ack_lsq_tag <= req_lsq_tag;
                memory[req_addr[7:0]] <= req_wdata[7:0];
            end
        end
        if (reset) begin
            history_write = 0;
            history_read = 0;
        end else if (commit_ready) begin
            // Observe EVERY retired lane. The old scalar monitor silently
            // lost lane1+ when faster completion lets adjacent instructions
            // retire together; checking only head0 is not a multi-issue test.
            for (history_lane = 0; history_lane < BE_WIDTH; history_lane = history_lane + 1) begin
                if (commit_valid_all[history_lane]) begin
                    if (history_write >= 128) $fatal(1, "Commit history overflow");
                    history_pc[history_write] = commit_pc_all[history_lane*32 +: 32];
                    history_value[history_write] = commit_value_all[history_lane*32 +: 32];
                    history_rd_we[history_write] = commit_rd_we_all[history_lane];
                    history_write = history_write + 1;
                    if (commit_pc_all[history_lane*32 +: 32] == 32'h2c)
                        younger_commit_seen <= 1'b1;
                end
            end
            if (commit_valid) commit_count <= commit_count + 1;
        end
        if (redirect_valid) begin
            redirect_seen <= 1'b1;
            redirect_pc_seen <= redirect_pc;
        end
        if (dut.mdu_completion_valid && dut.lsq_load_complete_valid &&
            ((COMPLETION_BYPASS == 2) ||
             (dut.mdu_completion_ready && dut.lsq_load_complete_ready)))
            completion_collision_seen <= 1'b1;
    end

    task clear_trace;
        begin trace_valid=0; trace_pc=0; trace_inst=0; trace_op=0; trace_imm=0; trace_rd=0; trace_rs1=0; trace_rs2=0; trace_rd_we=0; trace_rs1_used=0; trace_rs2_used=0; trace_load=0; trace_store=0; trace_branch=0; trace_halt=0; trace_error=0; trace_size=`RV32IM_MEM_WORD; trace_unsigned=0; trace_store_data=0; trace_pred_taken=0; trace_pred_target=0; trace_pred_kind=0; end
    endtask
    task send_inst;
        input [31:0] pc; input [5:0] op; input [31:0] imm; input [4:0] rd; input [4:0] rs1; input [4:0] rs2; input rdwe; input rs1use; input rs2use; input isload; input isstore; input isbranch; input ishalt; input [127:0] sdata;
        begin
            while (!trace_ready) @(posedge clk);
            trace_pc=pc; trace_inst={26'b0,op}; trace_op=op; trace_imm=imm; trace_rd=rd; trace_rs1=rs1; trace_rs2=rs2; trace_rd_we=rdwe; trace_rs1_used=rs1use; trace_rs2_used=rs2use; trace_load=isload; trace_store=isstore; trace_branch=isbranch; trace_halt=ishalt; trace_store_data=sdata; trace_valid=1;
            @(posedge clk); #1; clear_trace();
        end
    endtask
    task send_mem;
        input [31:0] pc; input [5:0] op; input [31:0] imm; input [4:0] rd; input load; input store; input [1:0] size; input unsign; input [127:0] sdata;
        begin
            while (!trace_ready) @(posedge clk);
            trace_pc=pc; trace_inst={26'b0,op}; trace_op=op; trace_imm=imm; trace_rd=rd; trace_rs1=0; trace_rs2=0; trace_rd_we=load; trace_rs1_used=0; trace_rs2_used=0; trace_load=load; trace_store=store; trace_branch=0; trace_halt=0; trace_store_data=sdata; trace_size=size; trace_unsigned=unsign; trace_valid=1;
            @(posedge clk); #1; clear_trace();
        end
    endtask
    task expect_commit;
        input [31:0] pc; input [31:0] value; input rdwe;
        integer cycles;
        begin
            cycles=0;
            if (!commit_ready) begin
                // The blocked-head checks intentionally inspect a pending
                // commit without pretending an architectural handshake.
                while (!commit_valid && cycles < 100) begin @(posedge clk); #1; cycles=cycles+1; end
                if (!commit_valid || commit_pc !== pc || commit_value !== value || commit_rd_we !== rdwe) begin
                    $display("EXPECT_BLOCKED_FAIL pc=%h got_pc=%h cycles=%0d", pc, commit_pc, cycles);
                    bad=bad+1;
                end
                @(posedge clk); #1;
            end else begin
                while (history_read == history_write && cycles < 100) begin @(posedge clk); #1; cycles=cycles+1; end
                if (history_read == history_write) begin
                    $display("EXPECT_TIMEOUT pc=%h", pc); bad=bad+1;
                end else begin
                    if (history_pc[history_read] !== pc || history_value[history_read] !== value ||
                        history_rd_we[history_read] !== rdwe) begin
                        $display("EXPECT_FAIL pc=%h got_pc=%h got_value=%h got_rdwe=%b cycles=%0d", pc,
                            history_pc[history_read], history_value[history_read], history_rd_we[history_read], cycles);
                        bad=bad+1;
                    end
                    history_read = history_read + 1;
                end
            end
        end
    endtask
    task release_held_load_with_mul;
        begin
            while (!held_load_valid) begin @(posedge clk); #1; end
            // Hold the multiplier result for one edge while the delayed load
            // response enters the LSQ.  This creates simultaneous producer
            // handshakes independent of the multiplier's pipeline depth.
            if (COMPLETION_BYPASS == 2) begin
                // Block the actual shared completion handshake, not only
                // the MDU's private ready input. A direct CDB must never
                // publish a result that its producer has not relinquished.
                force dut.cdb_ready = 0;
                while (!dut.mdu_completion_valid) begin @(posedge clk); #1; end
            end else force dut.mdu_completion_ready = 1'b0;
            @(negedge clk);
            resp_valid=1'b1; resp_error=inject_load_error; resp_lsq_tag=held_load_lsq_tag;
            resp_addr=held_load_addr; resp_line_valid=1'b1; resp_line=held_load_line; resp_word=held_load_word;
            held_load_valid=1'b0;
            @(posedge clk); #1;
            if (COMPLETION_BYPASS == 2) release dut.cdb_ready;
            else release dut.mdu_completion_ready;
        end
    endtask

    task check_free_list;
        integer free_i;
        integer bitmap_count;
        integer rat_i;
        integer rob_i;
        reg [5:0] free_phys_i;
        begin
            if (((^dut.free_count) === 1'bx) || (dut.free_count > 63)) begin
                $display("FREE_LIST_COUNT_FAIL count=%0d", dut.free_count);
                bad=bad+1;
                free_list_error_seen=1'b1;
            end else begin
                bitmap_count=0;
                if (dut.rename.free_bitmap[0]) begin
                    $display("FREE_BITMAP_ZERO_FAIL");
                    bad=bad+1;
                    free_list_error_seen=1'b1;
                end
                for (free_i=1; free_i<64; free_i=free_i+1) begin
                    if (dut.rename.free_bitmap[free_i]) begin
                        bitmap_count=bitmap_count+1;
                        free_phys_i=free_i;
                        for (rat_i=0; rat_i<32; rat_i=rat_i+1) begin
                            if (free_phys_i == dut.rename.rat[rat_i]) begin
                                $display("FREE_BITMAP_RAT_FAIL phys=%0d architectural=%0d", free_phys_i, rat_i);
                                bad=bad+1;
                                free_list_error_seen=1'b1;
                            end
                        end
                        for (rob_i=0; rob_i<8; rob_i=rob_i+1) begin
                            if (dut.rob.valid_mem[rob_i] && (dut.rob.old_phys_mem[rob_i] != 0) &&
                                (free_phys_i == dut.rob.old_phys_mem[rob_i])) begin
                                $display("FREE_BITMAP_ROB_OLD_FAIL phys=%0d rob_slot=%0d", free_phys_i, rob_i);
                                bad=bad+1;
                                free_list_error_seen=1'b1;
                            end
                        end
                    end
                end
                if (bitmap_count != dut.free_count) begin
                    $display("FREE_BITMAP_COUNT_FAIL bitmap=%0d count=%0d", bitmap_count, dut.free_count);
                    bad=bad+1;
                    free_list_error_seen=1'b1;
                end
            end
        end
    endtask

    always @(negedge clk) begin
        if (!reset && !free_list_error_seen) check_free_list();
    end

    initial begin
        bad=0; commit_count=0; redirect_seen=0; younger_commit_seen=0; redirect_pc_seen=0; free_list_error_seen=0; recovery_branch_slot=0; recovery_branch_phys=0; reset=1; flush=0; commit_ready=1; resp_valid=0; resp_line_valid=1; resp_error=0; resp_lsq_tag=0; resp_addr=0; resp_word=0; resp_line=0; store_ack_valid=0; store_ack_error=0; store_ack_lsq_tag=0; inject_load_error=0; inject_store_error=0; defer_load_response=0; held_load_valid=0; held_load_lsq_tag=0; held_load_addr=0; held_load_word=0; held_load_line=0; completion_collision_seen=0; clear_trace();
        for (i=0; i<256; i=i+1) memory[i]=0;
        #12; reset=0; #1;
        // RAW chain through rename -> PRF -> RS wakeup -> ALU -> CDB -> ROB.
        send_inst(32'h0, `RV32IM_OP_ADDI, 5, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0);
        send_inst(32'h4, `RV32IM_OP_ADD, 0, 2, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0);
        expect_commit(32'h0, 5, 1);
        expect_commit(32'h4, 10, 1);
        // Three-cycle multiplier and iterative divider flow through the same CDB.
        send_inst(32'h8, `RV32IM_OP_MUL, 0, 3, 2, 1, 1, 1, 1, 0, 0, 0, 0, 0);
        expect_commit(32'h8, 50, 1);
        send_inst(32'hc, `RV32IM_OP_DIV, 0, 4, 3, 1, 1, 1, 1, 0, 0, 0, 0, 0);
        expect_commit(32'hc, 10, 1);
        // Precise store visibility and a load response from the responder.
        send_inst(32'h10, `RV32IM_OP_SW, 32'h20, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 128'h0000000000000000000000000000002a);
        expect_commit(32'h10, 0, 0);
        send_inst(32'h14, `RV32IM_OP_LW, 32'h20, 5, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0);
        expect_commit(32'h14, 32'h0000002a, 1);
        // Byte forwarding: a younger LB consumes one byte from an older
        // uncommitted SW without waiting for the cache request.
        send_mem(32'h40, `RV32IM_OP_SW, 32'h40, 0, 0, 1, `RV32IM_MEM_WORD, 0, 128'h000000000000000000000044332211);
        send_mem(32'h44, `RV32IM_OP_LBU, 32'h41, 6, 1, 0, `RV32IM_MEM_BYTE, 1, 0);
        expect_commit(32'h40, 0, 0);
        expect_commit(32'h44, 32'h00000022, 1);
        // WAW: both writes to x7 commit in order and the final value wins.
        send_inst(32'h18, `RV32IM_OP_ADDI, 7, 7, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0);
        send_inst(32'h1c, `RV32IM_OP_ADDI, 9, 7, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0);
        expect_commit(32'h18, 7, 1);
        expect_commit(32'h1c, 9, 1);
        // WAR: the older long-latency read keeps its pre-write physical
        // source while the younger instruction writes the same architectural
        // register.
        send_inst(32'h20, `RV32IM_OP_MUL, 0, 8, 7, 7, 1, 1, 1, 0, 0, 0, 0, 0);
        send_inst(32'h24, `RV32IM_OP_ADDI, 3, 7, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0);
        expect_commit(32'h20, 81, 1);
        expect_commit(32'h24, 3, 1);
        // Checkpoint recovery: taken BEQ is predicted not-taken, so the
        // younger instruction must be squashed before it can commit.
        send_inst(32'h28, `RV32IM_OP_BEQ, 8, 0, 0, 0, 0, 1, 1, 0, 0, 1, 0, 0);
        send_inst(32'h2c, `RV32IM_OP_ADDI, 99, 9, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0);
        expect_commit(32'h28, 0, 0);
        if (!redirect_seen || redirect_pc_seen !== 32'h30 || younger_commit_seen) begin
            $display("BRANCH_RECOVERY_FAIL seen=%b pc=%h younger=%b", redirect_seen, redirect_pc_seen, younger_commit_seen);
            bad=bad+1;
        end
        // HALT is precise at the ROB head and captures the computed value.
        send_inst(32'h30, `RV32IM_OP_ADD, 0, 0, 4, 0, 0, 1, 0, 0, 0, 0, 1, 0);
        expect_commit(32'h30, 10, 0);
        if (!halted || error || return_value != 8'd10) begin
            $display("HALT_FAIL halted=%b error=%b return=%0d", halted, error, return_value);
            bad=bad+1;
        end

        // Load response errors survive the completion network and become
        // architecturally visible only when the load reaches the ROB head.
        reset=1; inject_load_error=0; inject_store_error=0; clear_trace(); @(posedge clk); #1; reset=0; #1;
        commit_ready=0; inject_load_error=1;
        send_mem(32'h50, `RV32IM_OP_LW, 32'h60, 10, 1, 0, `RV32IM_MEM_WORD, 0, 0);
        expect_commit(32'h50, 0, 1);
        if (error) begin $display("LOAD_ERROR_EARLY_FAIL"); bad=bad+1; end
        commit_ready=1;
        expect_commit(32'h50, 0, 1);
        if (!error) begin $display("LOAD_ERROR_MISSING_FAIL"); bad=bad+1; end

        // Store acknowledgement errors follow the separate visibility
        // handshake and become precise when the store retires.
        reset=1; inject_load_error=0; inject_store_error=0; clear_trace(); @(posedge clk); #1; reset=0; #1;
        commit_ready=0; inject_store_error=1;
        // Posted ordinary stores may retire at LSQ admission. MMIO must
        // retain precise acknowledgement/error semantics even in that mode.
        send_mem(32'h54, `RV32IM_OP_SW, STORE_BUFFERED_RETIRE ? 32'h80000000 : 32'h64,
            0, 0, 1, `RV32IM_MEM_WORD, 0, 128'h55);
        expect_commit(32'h54, 0, 0);
        if (error) begin $display("STORE_ERROR_EARLY_FAIL"); bad=bad+1; end
        commit_ready=1;
        expect_commit(32'h54, 0, 0);
        if (!error) begin $display("STORE_ERROR_MISSING_FAIL"); bad=bad+1; end

        // Force a MUL result and an LSQ load result into the
        // completion network on the same cycle. FIFO mode accepts both;
        // a single direct CDB serializes them. Both retain their ROB order.
        reset=1; inject_store_error=0; defer_load_response=0; held_load_valid=0; completion_collision_seen=0; clear_trace(); @(posedge clk); #1; reset=0; #1;
        memory[8'h70]=8'h34; memory[8'h71]=0; memory[8'h72]=0; memory[8'h73]=0;
        send_inst(32'h60, `RV32IM_OP_ADDI, 6, 11, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0);
        send_inst(32'h64, `RV32IM_OP_ADDI, 7, 12, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0);
        expect_commit(32'h60, 6, 1);
        expect_commit(32'h64, 7, 1);
        defer_load_response=1;
        send_mem(32'h68, `RV32IM_OP_LW, 32'h70, 13, 1, 0, `RV32IM_MEM_WORD, 0, 0);
        send_inst(32'h6c, `RV32IM_OP_MUL, 0, 14, 11, 12, 1, 1, 1, 0, 0, 0, 0, 0);
        release_held_load_with_mul();
        defer_load_response=0;
        expect_commit(32'h68, 32'h34, 1);
        expect_commit(32'h6c, 42, 1);
        if (!completion_collision_seen) begin $display("COMPLETION_COLLISION_FAIL"); bad=bad+1; end

        // Recover a non-head JALR that writes a destination.  The restored
        // RAT must keep the branch's new mapping, and the free list must not
        // contain either live RAT mappings or old mappings owned by the two
        // surviving ROB entries.
        reset=1; defer_load_response=0; held_load_valid=0; clear_trace(); @(posedge clk); #1; reset=0; #1;
        send_inst(32'h70, `RV32IM_OP_ADDI, 32'h88, 20, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0);
        send_inst(32'h74, `RV32IM_OP_ADDI, 1, 22, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0);
        expect_commit(32'h70, 32'h88, 1);
        expect_commit(32'h74, 1, 1);
        commit_ready=0;
        send_inst(32'h80, `RV32IM_OP_DIV, 0, 22, 20, 22, 1, 1, 1, 0, 0, 0, 0, 0);
        send_inst(32'h84, `RV32IM_OP_JALR, 0, 23, 22, 0, 1, 1, 0, 0, 0, 1, 0, 0);
        recovery_branch_slot=dut.rob_tail-1;
        if (recovery_branch_slot < 0) recovery_branch_slot=recovery_branch_slot+8;
        recovery_branch_phys=dut.rob.new_phys_mem[recovery_branch_slot];
        send_inst(32'h88, `RV32IM_OP_ADDI, 99, 24, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0);
        redirect_seen=0;
        i=0;
        while (!redirect_seen && i<100) begin @(posedge clk); #1; i=i+1; end
        if (!redirect_seen || redirect_pc_seen !== 32'h88) begin
            $display("JALR_RECOVERY_FAIL seen=%b pc=%h", redirect_seen, redirect_pc_seen);
            bad=bad+1;
        end
        if (dut.rename.rat[23] !== recovery_branch_phys) begin
            $display("RECOVERY_BRANCH_MAP_FAIL rat=%0d expected=%0d", dut.rename.rat[23], recovery_branch_phys);
            bad=bad+1;
        end
        check_free_list();
        commit_ready=1;
        expect_commit(32'h80, 32'h88, 1);
        expect_commit(32'h84, 32'h88, 1);
        if (SHARED_ADDRESS_DIRECTED != 0) begin
            // The store's base comes from a delayed load after allocation;
            // its data comes from an independent worst-case-length DIV.
            // Mode 1 cannot probe this base at rename, while mode 2 must
            // publish it without consuming the still-data-waiting RS entry.
            reset=1; defer_load_response=0; held_load_valid=0; clear_trace();
            commit_ready=1; @(posedge clk); #1; reset=0;
            memory[8'h20]=8'h80; memory[8'h21]=0; memory[8'h22]=0; memory[8'h23]=0;
            memory[8'h40]=8'h5a; memory[8'h41]=0; memory[8'h42]=0; memory[8'h43]=0;
            send_inst(32'h100,`RV32IM_OP_ADDI,32'h7ffffffe,1,0,0,1,0,0,0,0,0,0,0);
            send_inst(32'h104,`RV32IM_OP_ADDI,2,2,0,0,1,0,0,0,0,0,0,0);
            expect_commit(32'h100,32'h7ffffffe,1);
            expect_commit(32'h104,2,1);
            commit_ready=0; defer_load_response=1;
            send_mem(32'h108,`RV32IM_OP_LW,32'h20,3,1,0,`RV32IM_MEM_WORD,0,0);
            send_inst(32'h10c,`RV32IM_OP_DIV,0,4,1,2,1,1,1,0,0,0,0,0);
            send_inst(32'h110,`RV32IM_OP_SW,4,0,3,4,0,1,1,0,1,0,0,0);
            shared_store_slot=-1;
            for (shared_rs_slot=0; shared_rs_slot<4; shared_rs_slot=shared_rs_slot+1)
                if (dut.lsq.valid_mem[shared_rs_slot] && dut.lsq.store_mem[shared_rs_slot])
                    shared_store_slot=shared_rs_slot;
            if (shared_store_slot<0 || dut.lsq.addr_ready_mem[shared_store_slot] ||
                ((EARLY_STORE_ADDRESS!=0) && dut.lsq.data_ready_mem[shared_store_slot]))
                $fatal(1,"shared AGU fixture did not allocate an unresolved store");
            send_mem(32'h114,`RV32IM_OP_LW,32'h40,5,1,0,`RV32IM_MEM_WORD,0,0);
            shared_wait=0;
            while (!held_load_valid && shared_wait<8) begin @(posedge clk); #1; shared_wait=shared_wait+1; end
            if (!held_load_valid || held_load_addr !== 32'h20)
                $fatal(1,"shared AGU fixture missing delayed base load");
            @(negedge clk); defer_load_response=0;
            resp_valid=1; resp_error=0; resp_lsq_tag=held_load_lsq_tag;
            resp_addr=held_load_addr; resp_line_valid=1; resp_line=held_load_line; resp_word=held_load_word;
            held_load_valid=0;
            @(posedge clk); #1;
            shared_early_seen=0; shared_disjoint_seen=0; shared_wait=0;
            while ((!dut.lsq.addr_ready_mem[shared_store_slot] ||
                    ((EARLY_STORE_ADDRESS==2) && !dut.lsq.data_ready_mem[shared_store_slot])) && shared_wait<24) begin
                if (dut.lsq.addr_ready_mem[shared_store_slot]) begin
                    shared_early_seen=1;
                    shared_rs_retained=0;
                    for (shared_rs_slot=0; shared_rs_slot<4; shared_rs_slot=shared_rs_slot+1)
                        if (dut.rs.valid_mem[shared_rs_slot] &&
                            dut.rs.rob_tag_mem[shared_rs_slot] == dut.lsq.rob_tag_mem[shared_store_slot])
                            shared_rs_retained=1;
                    shared_regular_store=0;
                    for (shared_lane=0; shared_lane<BE_WIDTH; shared_lane=shared_lane+1)
                        if (dut.alu_exec_valid[shared_lane] && dut.alu_exec_is_store[shared_lane] &&
                            dut.alu_exec_tag[shared_lane*TAGW +: TAGW] == dut.lsq.rob_tag_mem[shared_store_slot])
                            shared_regular_store=1;
                    if (dut.lsq.addr_mem[shared_store_slot] !== 32'h84 ||
                        dut.lsq.store_commit_mem[shared_store_slot] ||
                        (!shared_rs_retained && !shared_regular_store))
                        $fatal(1,"shared AGU state addr=%h commit=%b rs=%b data=%b alu_store=%b wait=%0d",
                            dut.lsq.addr_mem[shared_store_slot],dut.lsq.store_commit_mem[shared_store_slot],
                            shared_rs_retained,dut.lsq.data_ready_mem[shared_store_slot],
                            dut.alu_exec_is_store,shared_wait);
                end
                if (req_valid && req_load && req_addr==32'h40) shared_disjoint_seen=1;
                if (req_valid && req_store) $fatal(1,"shared AGU authorized a data-unready store");
                @(posedge clk); #1; shared_wait=shared_wait+1;
            end
            if ((EARLY_STORE_ADDRESS==2) ? (!shared_early_seen || !shared_disjoint_seen) :
                (shared_early_seen || shared_disjoint_seen))
                $fatal(1,"shared AGU mode=%0d early=%b disjoint=%b",EARLY_STORE_ADDRESS,
                    shared_early_seen,shared_disjoint_seen);
            commit_ready=1;
            expect_commit(32'h108,32'h80,1);
            expect_commit(32'h10c,32'h3fffffff,1);
            expect_commit(32'h110,0,0);
            expect_commit(32'h114,32'h5a,1);
            $display("PASS: shared store-address backend directed BE_WIDTH=%0d mode=%0d",BE_WIDTH,EARLY_STORE_ADDRESS);
        end
        if (bad != 0) begin $display("FAIL: B-09 backend joint BE_WIDTH=%0d checks=%0d", BE_WIDTH, bad); $finish(1); end
        if (inline_issue_checks == 0 || inline_feedback_checks == 0)
            $fatal(1,"Metadata scoreboard did not cover issue and branch feedback");
        $display("PASS: RS metadata scoreboard mode=%0d issues=%0d branches=%0d",
            RS_ISSUE_METADATA,inline_issue_checks,inline_feedback_checks);
        $display("PASS: B-09 backend joint BE_WIDTH=%0d", BE_WIDTH); $finish(0);
    end
endmodule
