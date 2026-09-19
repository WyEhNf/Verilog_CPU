`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32_backend_joint_tb #(
    parameter integer BE_WIDTH = 1,
    parameter integer STORE_BUFFERED_RETIRE = 0
);
    initial $display("B09_TB_START");
    initial begin
        #10000;
        $display("FAIL: B-09 backend joint timeout");
        $finish(1);
    end
    localparam integer TAGW = 16;
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
    wire [31:0] commit_pc, commit_inst, commit_value, commit_store_addr;
    wire [4:0] commit_rd;
    wire [15:0] commit_store_mask;
    wire [127:0] commit_store_data;
    wire [TAGW-1:0] commit_tag;
    wire redirect_valid, halted, error;
    wire [31:0] redirect_pc;
    wire [7:0] return_value;
    integer bad, commit_count;
    reg redirect_seen, younger_commit_seen;
    reg [31:0] redirect_pc_seen;
    reg free_list_error_seen;
    integer recovery_branch_slot;
    reg [5:0] recovery_branch_phys;
    reg [7:0] memory [0:255];
    integer i;

    assign req_ready = 1'b1;
    rv32_backend_joint #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(64), .ROB_ENTRIES(8), .RS_ENTRIES(4), .LSQ_ENTRIES(4), .STORE_BUFFERED_RETIRE(STORE_BUFFERED_RETIRE), .TAG_WIDTH(TAGW)) dut (
        .clk_i(clk), .reset_i(reset), .flush_i(flush), .trace_valid_i(trace_valid), .trace_ready_o(trace_ready), .trace_pc_i(trace_pc), .trace_inst_i(trace_inst), .trace_op_i(trace_op), .trace_imm_i(trace_imm), .trace_rd_i(trace_rd), .trace_rs1_i(trace_rs1), .trace_rs2_i(trace_rs2), .trace_rd_we_i(trace_rd_we), .trace_rs1_used_i(trace_rs1_used), .trace_rs2_used_i(trace_rs2_used), .trace_is_load_i(trace_load), .trace_is_store_i(trace_store), .trace_is_branch_i(trace_branch), .trace_is_halt_i(trace_halt), .trace_is_error_i(trace_error), .trace_mem_size_i(trace_size), .trace_mem_unsigned_i(trace_unsigned), .trace_store_data_i(trace_store_data), .trace_pred_taken_i(trace_pred_taken), .trace_pred_target_i(trace_pred_target), .trace_pred_kind_i(trace_pred_kind), .dcache_req_valid_o(req_valid), .dcache_req_ready_i(req_ready), .dcache_req_is_load_o(req_load), .dcache_req_is_store_o(req_store), .dcache_req_addr_o(req_addr), .dcache_req_size_o(req_size), .dcache_req_unsigned_o(req_unsigned), .dcache_req_mask_o(req_mask), .dcache_req_wdata_o(req_wdata), .dcache_req_rob_tag_o(req_rob_tag), .dcache_req_lsq_tag_o(req_lsq_tag), .dcache_resp_valid_i(resp_valid), .dcache_resp_ready_o(), .dcache_resp_lsq_tag_i(resp_lsq_tag), .dcache_resp_addr_i(resp_addr), .dcache_resp_line_data_i(resp_line), .dcache_resp_word_data_i(resp_word), .dcache_resp_line_valid_i(resp_line_valid), .dcache_resp_error_i(resp_error), .dcache_store_ack_valid_i(store_ack_valid), .dcache_store_ack_lsq_tag_i(store_ack_lsq_tag), .dcache_store_ack_error_i(store_ack_error), .commit_ready_i(commit_ready), .commit_valid_o(commit_valid), .commit_pc_o(commit_pc), .commit_inst_o(commit_inst), .commit_rd_o(commit_rd), .commit_rd_we_o(commit_rd_we), .commit_value_o(commit_value), .commit_is_store_o(commit_store), .commit_store_addr_o(commit_store_addr), .commit_store_mask_o(commit_store_mask), .commit_store_data_o(commit_store_data), .commit_tag_o(commit_tag), .redirect_valid_o(redirect_valid), .redirect_pc_o(redirect_pc), .halted_o(halted), .error_o(error), .return_value_o(return_value)
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
        if (commit_valid && commit_ready) begin
            commit_count <= commit_count + 1;
            if (commit_pc == 32'h2c) younger_commit_seen <= 1'b1;
        end
        if (redirect_valid) begin
            redirect_seen <= 1'b1;
            redirect_pc_seen <= redirect_pc;
        end
        if (dut.mdu_completion_valid && dut.mdu_completion_ready &&
            dut.lsq_load_complete_valid && dut.lsq_load_complete_ready)
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
            while (!commit_valid && cycles < 100) begin @(posedge clk); #1; cycles=cycles+1; end
            if (!commit_valid || commit_pc !== pc || commit_value !== value || commit_rd_we !== rdwe) begin
                $display("EXPECT_FAIL pc=%h got_valid=%b got_pc=%h got_value=%h got_rdwe=%b cycles=%0d", pc, commit_valid, commit_pc, commit_value, commit_rd_we, cycles);
                bad=bad+1;
            end
            if (cycles >= 100) begin
                $display("EXPECT_TIMEOUT pc=%h", pc);
                bad=bad+1;
            end
            @(posedge clk); #1;
        end
    endtask
    task release_held_load_with_mul;
        begin
            while (!held_load_valid) begin @(posedge clk); #1; end
            while (!dut.mdu.gen_wallace_multiplier.multiplier.s2_valid) begin @(posedge clk); #1; end
            @(negedge clk);
            resp_valid=1'b1; resp_error=inject_load_error; resp_lsq_tag=held_load_lsq_tag;
            resp_addr=held_load_addr; resp_line_valid=1'b1; resp_line=held_load_line; resp_word=held_load_word;
            held_load_valid=1'b0;
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
        send_mem(32'h54, `RV32IM_OP_SW, 32'h64, 0, 0, 1, `RV32IM_MEM_WORD, 0, 128'h55);
        expect_commit(32'h54, 0, 0);
        if (error) begin $display("STORE_ERROR_EARLY_FAIL"); bad=bad+1; end
        commit_ready=1;
        expect_commit(32'h54, 0, 0);
        if (!error) begin $display("STORE_ERROR_MISSING_FAIL"); bad=bad+1; end

        // Force a three-stage MUL result and an LSQ load result into the
        // completion network on the same cycle. Both must be accepted and
        // retain their ROB order through the single-lane CDB.
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
        if (bad != 0) begin $display("FAIL: B-09 backend joint BE_WIDTH=%0d checks=%0d", BE_WIDTH, bad); $finish(1); end
        $display("PASS: B-09 backend joint BE_WIDTH=%0d", BE_WIDTH); $finish(0);
    end
endmodule
