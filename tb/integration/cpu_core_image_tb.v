`timescale 1ns/1ps

// JOIN-02 image runner.  The memory model loads an @address byte image and
// the testbench checks only architectural termination and a0[7:0].
module cpu_core_image_tb #(
    parameter integer FE_WIDTH = 1,
    parameter integer BE_WIDTH = 1,
    parameter integer PHYS_REGS = 48,
    parameter integer ROB_ENTRIES = 16,
    parameter integer RS_ENTRIES = 4,
    parameter integer LSQ_ENTRIES = 4,
    parameter integer ENABLE_CACHES = 1,
    parameter integer ENABLE_PREDICTOR = 1,
    parameter integer FETCH_QUEUE_DEPTH = 16,
    parameter integer MUL_IMPL = 0,
    parameter integer COMPLETION_DEPTH = (BE_WIDTH <= 1) ? 4 :
                                         ((BE_WIDTH == 2) ? 8 : 16)
);
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

    integer expected_value;
    integer max_cycles;
    integer max_no_retire_cycles;
    integer no_retire_cycles;
    integer finish_code;
    integer diag_slot;
    integer trace_file;
    integer trace_lane;
    reg [31:0] last_instret;
    reg trace_enable;
    reg watchdog_expired;
    reg [1023:0] test_name;
    reg [1023:0] trace_file_name;

    cpu_core #(
        .FE_WIDTH(FE_WIDTH),
        .BE_WIDTH(BE_WIDTH),
        .PHYS_REGS(PHYS_REGS),
        .ROB_ENTRIES(ROB_ENTRIES),
        .RS_ENTRIES(RS_ENTRIES),
        .LSQ_ENTRIES(LSQ_ENTRIES),
        .ENABLE_CACHES(ENABLE_CACHES),
        .ENABLE_PREDICTOR(ENABLE_PREDICTOR),
        .FETCH_QUEUE_DEPTH(FETCH_QUEUE_DEPTH),
        .MUL_IMPL(MUL_IMPL),
        .COMPLETION_DEPTH(COMPLETION_DEPTH)
    ) dut (
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
        expected_value = 0;
        max_cycles = 100000;
        max_no_retire_cycles = 100000;
        no_retire_cycles = 0;
        finish_code = 0;
        trace_file = 0;
        last_instret = 0;
        trace_enable = 1'b0;
        watchdog_expired = 1'b0;
        test_name = "image";
        trace_file_name = 0;
        if ($value$plusargs("EXPECTED=%d", expected_value)) begin end
        if ($value$plusargs("MAX_CYCLES=%d", max_cycles)) begin end
        if ($value$plusargs("MAX_NO_RETIRE_CYCLES=%d", max_no_retire_cycles)) begin end
        if ($value$plusargs("TEST=%s", test_name)) begin end
        if ($value$plusargs("COMMIT_TRACE=%s", trace_file_name)) begin
            trace_file = $fopen(trace_file_name, "w");
            if (trace_file == 0) begin
                $display("FAIL: cannot open CommitRecord trace file %0s", trace_file_name);
                $finish(1);
            end
        end
        if ($test$plusargs("TRACE")) trace_enable = 1'b1;
        reset = 1'b1;
        #12;
        reset = 1'b0;
        while (!halted && !error && !watchdog_expired && (cycles < max_cycles)) begin
            @(posedge clk);
            if (instret != last_instret) begin
                last_instret = instret;
                no_retire_cycles = 0;
            end else begin
                no_retire_cycles = no_retire_cycles + 1;
            end
            if (no_retire_cycles >= max_no_retire_cycles) begin
                watchdog_expired = 1'b1;
            end
        end
        #1;
        if (watchdog_expired) begin
            $display("FAIL: JOIN-02 image=%0s no-retirement watchdog cycles=%0d instret=%0d stagnant=%0d", test_name, cycles, instret, no_retire_cycles);
            $display("STATE: pc=%08x rob=%0d/%0d/%0d head_valid=%b head_ready=%b head_store=%b head_wait=%b head_sent=%b free=%0d rs=%0d lsq=%0d/%0d/%0d lsq_valid=%b lsq_store=%b lsq_addr=%b lsq_data=%b lsq_commit=%b lsq_sent=%b lsq_wait=%b dc_s0=%b dc_s1=%b dc_s2=%b dc_mshr=%b dc_ack=%b dc_resp=%b",
                     dut.frontend.pc_reg,
                     dut.backend.rob.head_reg, dut.backend.rob.tail_reg, dut.backend.rob.occupancy_reg,
                     dut.backend.rob.valid_mem[dut.backend.rob.head_reg],
                     dut.backend.rob.ready_mem[dut.backend.rob.head_reg],
                     dut.backend.rob.store_mem[dut.backend.rob.head_reg],
                     dut.backend.rob.store_wait_mem[dut.backend.rob.head_reg],
                     dut.backend.rob.store_sent_mem[dut.backend.rob.head_reg],
                     dut.backend.free_count, dut.backend.rs_occupancy,
                     dut.backend.lsq.head_reg, dut.backend.lsq.tail_reg, dut.backend.lsq_occupancy,
                     dut.backend.lsq.valid_mem[dut.backend.lsq.head_reg],
                     dut.backend.lsq.store_mem[dut.backend.lsq.head_reg],
                     dut.backend.lsq.addr_ready_mem[dut.backend.lsq.head_reg],
                     dut.backend.lsq.data_ready_mem[dut.backend.lsq.head_reg],
                     dut.backend.lsq.store_commit_mem[dut.backend.lsq.head_reg],
                     dut.backend.lsq.request_sent_mem[dut.backend.lsq.head_reg],
                     dut.backend.lsq.response_wait_mem[dut.backend.lsq.head_reg],
                     dut.dcache_debug_s0_valid, dut.dcache_debug_s1_valid,
                     dut.dcache_debug_s2_valid, dut.dcache_debug_mshr_valid,
                     dut.dcache_debug_ack_valid, dut.dcache_debug_resp_valid);
            $display("STATE: branch_pending=%b alu=%b mdu_pending=%b div_busy=%b div_result=%b completion=%0d/%0d/%0d prf_ready=%016x",
                     dut.backend.branch_pending, dut.backend.g_alu[0].alu.result_valid_reg,
                     dut.backend.mdu.pending_valid, !dut.backend.mdu_issue_ready,
                     dut.backend.mdu_completion_valid,
                     dut.backend.completion.head_reg, dut.backend.completion.tail_reg,
                     dut.backend.completion.count_reg, dut.backend.prf.ready);
            for (diag_slot = 0; diag_slot < ROB_ENTRIES; diag_slot = diag_slot + 1)
                if (dut.backend.rob.valid_mem[diag_slot])
                    $display("ROB[%0d] gen=%0h ready=%b pc=%08x inst=%08x rd=%0d oldp=%0d newp=%0d store=%b wait=%b sent=%b",
                             diag_slot, dut.backend.rob.generation_mem[diag_slot],
                             dut.backend.rob.ready_mem[diag_slot], dut.backend.rob.pc_mem[diag_slot],
                             dut.backend.rob.inst_mem[diag_slot], dut.backend.rob.rd_mem[diag_slot],
                             dut.backend.rob.old_phys_mem[diag_slot], dut.backend.rob.new_phys_mem[diag_slot],
                             dut.backend.rob.store_mem[diag_slot], dut.backend.rob.store_wait_mem[diag_slot],
                             dut.backend.rob.store_sent_mem[diag_slot]);
            for (diag_slot = 0; diag_slot < RS_ENTRIES; diag_slot = diag_slot + 1) begin
                if (dut.backend.rs.valid_mem[diag_slot])
                    $display("RS[%0d] rob=%04x pc=%08x op=%0d src1=%b/%04x src2=%b/%04x phys=%0d age=%0d",
                             diag_slot, dut.backend.rs.rob_tag_mem[diag_slot],
                             dut.backend.rs.pc_mem[diag_slot], dut.backend.rs.op_mem[diag_slot],
                             dut.backend.rs.src1_ready_mem[diag_slot], dut.backend.rs.src1_tag_mem[diag_slot],
                             dut.backend.rs.src2_ready_mem[diag_slot], dut.backend.rs.src2_tag_mem[diag_slot],
                             dut.backend.rs.phys_rd_mem[diag_slot], dut.backend.rs.age_mem[diag_slot]);
            end
            for (diag_slot = 0; diag_slot < LSQ_ENTRIES; diag_slot = diag_slot + 1) begin
                if (dut.backend.lsq.valid_mem[diag_slot])
                    $display("LSQ[%0d] gen=%0h rob=%04x load=%b store=%b addr=%b/%08x data=%b sent=%b wait=%b complete=%b commit=%b ack=%b",
                             diag_slot, dut.backend.lsq.generation_mem[diag_slot],
                             dut.backend.lsq.rob_tag_mem[diag_slot], dut.backend.lsq.load_mem[diag_slot],
                             dut.backend.lsq.store_mem[diag_slot], dut.backend.lsq.addr_ready_mem[diag_slot],
                             dut.backend.lsq.addr_mem[diag_slot], dut.backend.lsq.data_ready_mem[diag_slot],
                             dut.backend.lsq.request_sent_mem[diag_slot], dut.backend.lsq.response_wait_mem[diag_slot],
                             dut.backend.lsq.complete_mem[diag_slot], dut.backend.lsq.store_commit_mem[diag_slot],
                             dut.backend.lsq.store_ack_mem[diag_slot]);
            end
            for (diag_slot = 0; diag_slot < 16; diag_slot = diag_slot + 1)
                if (dut.backend.completion.valid_mem[diag_slot])
                    $display("CDBQ[%0d] tag=%04x live=%b phys=%0d value=%08x",
                             diag_slot, dut.backend.completion.tag_mem[diag_slot],
                             dut.backend.completion.live_mem[diag_slot],
                             dut.backend.completion.phys_mem[diag_slot],
                             dut.backend.completion.value_mem[diag_slot]);
            finish_code = 1;
        end else if (error) begin
            $display("FAIL: JOIN-02 image=%0s architectural error cycles=%0d instret=%0d", test_name, cycles, instret);
            finish_code = 1;
        end else if (!halted) begin
            $display("FAIL: JOIN-02 image=%0s timeout cycles=%0d instret=%0d limit=%0d", test_name, cycles, instret, max_cycles);
            finish_code = 1;
        end else if (return_value !== expected_value[7:0]) begin
            $display("FAIL: JOIN-02 image=%0s return=%0d expected=%0d cycles=%0d instret=%0d", test_name, return_value, expected_value[7:0], cycles, instret);
            finish_code = 1;
        end else begin
            $display("PASS: JOIN-02 image=%0s return=%0d cycles=%0d instret=%0d", test_name, return_value, cycles, instret);
        end
        if (trace_file != 0)
            $fclose(trace_file);
        $finish(finish_code);
    end

    always @(posedge clk) begin
        if (trace_file != 0) begin
            for (trace_lane = 0; trace_lane < BE_WIDTH; trace_lane = trace_lane + 1) begin
                if (dut.commit_valid[trace_lane]) begin
                    $fwrite(trace_file,
                            "{\"cycle\":%0d,\"lane\":%0d,\"valid\":true,\"pc\":%0d,\"inst\":%0d,\"rd\":%0d,\"rd_we\":%0d,\"value\":%0d,\"is_store\":%0d,\"store_addr\":%0d,\"store_mask\":%0d,\"store_data\":%0d,\"halted\":%0d,\"return_value\":%0d}\n",
                            cycles, trace_lane,
                            dut.commit_pc[trace_lane*32 +: 32],
                            dut.commit_inst[trace_lane*32 +: 32],
                            dut.commit_rd[trace_lane*5 +: 5],
                            dut.commit_rd_we[trace_lane],
                            dut.commit_value[trace_lane*32 +: 32],
                            dut.commit_is_store[trace_lane],
                            dut.commit_store_addr[trace_lane*32 +: 32],
                            dut.commit_store_mask[trace_lane*16 +: 16],
                            dut.commit_store_data[trace_lane*128 +: 128],
                            dut.commit_inst[trace_lane*32 +: 32] == 32'h0ff00513,
                            (dut.commit_inst[trace_lane*32 +: 32] == 32'h0ff00513) ?
                                dut.commit_value[trace_lane*32 +: 32] : 32'd0);
                end
            end
        end
        if (trace_enable && (cycles != 0) && ((cycles % 500) == 0))
            $display("TRACE: periodic cycles=%0d instret=%0d pc=%08x rob_head=%0d rob_tail=%0d rob_occ=%0d rob_tag=%04x rob_ready=%b rob_store=%b rob_wait=%b rob_sent=%b free_count=%0d restore=%b rs_occ=%0d lsq_head=%0d lsq_tail=%0d lsq_occ=%0d lsq_tag=%04x lsq_valid=%b lsq_store=%b lsq_addr=%b lsq_data=%b lsq_commit=%b lsq_sent=%b lsq_ack=%b lsq_ackvalid=%b lsq_commitready=%b fetch_valid=%b fetch_ready=%b trace_ready=%b", cycles, instret, dut.frontend.pc_reg, dut.backend.rob.head_reg, dut.backend.rob.tail_reg, dut.backend.rob.occupancy_reg, dut.backend.rob.generation_mem[dut.backend.rob.head_reg], dut.backend.rob.ready_mem[dut.backend.rob.head_reg], dut.backend.rob.store_mem[dut.backend.rob.head_reg], dut.backend.rob.store_wait_mem[dut.backend.rob.head_reg], dut.backend.rob.store_sent_mem[dut.backend.rob.head_reg], dut.backend.free_count, dut.backend.rob_checkpoint_restore_valid, dut.backend.rs_occupancy, dut.backend.lsq.head_reg, dut.backend.lsq.tail_reg, dut.backend.lsq_occupancy, dut.backend.lsq.rob_tag_mem[dut.backend.lsq.head_reg], dut.backend.lsq.valid_mem[dut.backend.lsq.head_reg], dut.backend.lsq.store_mem[dut.backend.lsq.head_reg], dut.backend.lsq.addr_ready_mem[dut.backend.lsq.head_reg], dut.backend.lsq.data_ready_mem[dut.backend.lsq.head_reg], dut.backend.lsq.store_commit_mem[dut.backend.lsq.head_reg], dut.backend.lsq.request_sent_mem[dut.backend.lsq.head_reg], dut.backend.lsq.store_ack_mem[dut.backend.lsq.head_reg], dut.backend.lsq.store_ack_valid_o, dut.backend.rob_store_commit_ready, dut.frontend.fetch_valid_o, dut.frontend.fetch_ready_i, dut.backend.trace_ready_o);
        if (trace_enable && (dut.backend.lsq_occupancy != 0) && !dut.backend.lsq.valid_mem[dut.backend.lsq.head_reg])
            $display("TRACE: LSQ_INVALID_HEAD cycles=%0d head=%0d tail=%0d occ=%0d robhead=%0d robocc=%0d allocfire=%b alloccount=%0d popvalid=%b storeack=%b", cycles, dut.backend.lsq.head_reg, dut.backend.lsq.tail_reg, dut.backend.lsq_occupancy, dut.backend.rob.head_reg, dut.backend.rob.occupancy_reg, dut.backend.lsq_alloc_fire, dut.backend.lsq_alloc_count, dut.backend.lsq_store_ack_valid, dut.dcache_store_ack_valid);
        if (trace_enable && (cycles >= 2985) && (cycles < 3020))
            $display("TRACE: LSQ_WINDOW cycles=%0d head=%0d tail=%0d occ=%0d validhead=%b allocfire=%b alloccount=%0d alloccalc=%0d popcalc=%0d recovery=%b", cycles, dut.backend.lsq.head_reg, dut.backend.lsq.tail_reg, dut.backend.lsq_occupancy, dut.backend.lsq.valid_mem[dut.backend.lsq.head_reg], dut.backend.lsq_alloc_fire, dut.backend.lsq_alloc_count, dut.backend.lsq.alloc_count_calc, dut.backend.lsq.pop_count_calc, dut.backend.lsq.recovery_valid_i);
        if (trace_enable && dut.commit_valid)
            $display("TRACE: pc=%08x inst=%08x rd=%0d we=%b value=%08x store=%b", dut.commit_pc,
                     dut.commit_inst, dut.commit_rd, dut.commit_rd_we,
                     dut.commit_value, dut.commit_is_store);
        if (trace_enable && dut.dcache_req_valid)
            $display("TRACE: dreq load=%b store=%b addr=%08x mask=%04x data=%08x ready=%b", dut.dcache_req_load,
                     dut.dcache_req_store, dut.dcache_req_addr, dut.dcache_req_mask,
                     dut.dcache_req_wdata[31:0], dut.dcache_req_ready);
        if (trace_enable && dut.mem_d_req_valid)
            $display("TRACE: mem-d write=%b line=%08x id=%02x ready=%b", dut.mem_d_req_write,
                     dut.mem_d_req_line_addr, dut.mem_d_req_id, dut.mem_d_req_ready);
        if (trace_enable && dut.mem_d_resp_valid)
            $display("TRACE: mem-d response line=%08x id=%02x error=%b ready=%b", dut.mem_d_resp_line_addr,
                     dut.mem_d_resp_id, dut.mem_d_resp_error, dut.mem_d_resp_ready);
        if (trace_enable && dut.dcache_store_ack_valid)
            $display("TRACE: dcache store-ack lsq=%04x error=%b", dut.dcache_store_ack_lsq_tag, dut.dcache_store_ack_error);
        if (trace_enable && dut.dcache_resp_valid)
            $display("TRACE: dcache load-resp lsq=%04x addr=%08x value=%08x error=%b", dut.dcache_resp_lsq_tag,
                     dut.dcache_resp_addr, dut.dcache_resp_word, dut.dcache_resp_error);
        if (trace_enable && (dut.dcache_debug_s0_valid || dut.dcache_debug_s1_valid ||
            dut.dcache_debug_s2_valid || dut.dcache_debug_mshr_valid || dut.dcache_debug_ack_valid))
            $display("TRACE: dcstate s0=%b/%b s1=%b/%b s2=%b/%b hit=%b mshr=%b ack=%b resp=%b",
                     dut.dcache_debug_s0_valid, dut.dcache_debug_s0_store,
                     dut.dcache_debug_s1_valid, dut.dcache_debug_s1_store,
                     dut.dcache_debug_s2_valid, dut.dcache_debug_s2_store,
                     dut.dcache_debug_s2_hit, dut.dcache_debug_mshr_valid,
                     dut.dcache_debug_ack_valid, dut.dcache_debug_resp_valid);
        if (trace_enable && (dut.redirect_valid || dut.backend.rob_recovery_accept || dut.backend.branch_pending))
            $display("TRACE: control redirect=%b pc=%08x epoch=%0d recovery=%b pending=%b frontend_pc=%08x epoch=%0d", dut.redirect_valid,
                     dut.redirect_pc, dut.redirect_epoch, dut.backend.rob_recovery_accept, dut.backend.branch_pending,
                     dut.frontend.pc_reg, dut.frontend.epoch_reg);
        if (trace_enable && dut.backend.branch_pending)
            $display("TRACE: rob pending_tag=%04x head=%0d tail=%0d occ=%0d headpc=%08x headinst=%08x commit=%b ctag=%04x cval=%08x ready=%b valid=%b rstore=%b swait=%b ssent=%b recovery=%b completion=%b/%04x rsocc=%0d lsqhead=%0d lsqtail=%0d lsqocc=%0d rv=%b rtag=%04x rhead=%0d rocc=%0d lsqv=%b lsqs=%b lsqa=%b lsqd=%b lsqc=%b lqtag=%04x lqreq=%b lqwait=%b cand=%b svalid=%b sready=%b", dut.backend.branch_pending_tag,
                     dut.backend.rob.head_reg, dut.backend.rob.tail_reg, dut.backend.rob.occupancy_reg,
                     dut.backend.rob.pc_mem[dut.backend.rob.head_reg], dut.backend.rob.inst_mem[dut.backend.rob.head_reg],
                     dut.backend.rob_commit_valid, dut.backend.rob_commit_tag, dut.backend.rob_commit_value,
                     dut.backend.rob.ready_mem[dut.backend.rob.head_reg], dut.backend.rob.valid_mem[dut.backend.rob.head_reg],
                     dut.backend.rob.store_mem[dut.backend.rob.head_reg], dut.backend.rob.store_wait_mem[dut.backend.rob.head_reg], dut.backend.rob.store_sent_mem[dut.backend.rob.head_reg], dut.backend.rob.recovery_found,
                     dut.backend.rob_completion_valid, dut.backend.rob_completion_tag, dut.backend.rs_occupancy, dut.backend.lsq.head_reg, dut.backend.lsq.tail_reg, dut.backend.lsq_occupancy, dut.backend.lsq.recovery_valid_i, dut.backend.lsq.recovery_tag_i, dut.backend.lsq.recovery_head_i, dut.backend.lsq.recovery_occupancy_i,
                     dut.backend.lsq.valid_mem[dut.backend.lsq.head_reg], dut.backend.lsq.store_mem[dut.backend.lsq.head_reg],
                     dut.backend.lsq.addr_ready_mem[dut.backend.lsq.head_reg], dut.backend.lsq.data_ready_mem[dut.backend.lsq.head_reg],
                     dut.backend.lsq.store_commit_mem[dut.backend.lsq.head_reg], dut.backend.lsq.rob_tag_mem[dut.backend.lsq.head_reg], dut.backend.lsq.request_sent_mem[dut.backend.lsq.head_reg], dut.backend.lsq.response_wait_mem[dut.backend.lsq.head_reg], dut.backend.lsq.candidate_found,
                     dut.backend.rob_store_commit_valid, dut.backend.rob_store_commit_ready);
    end

endmodule
