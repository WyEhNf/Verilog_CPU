`timescale 1ns/1ps
`include "rv32im_defs.vh"

// JOIN-02 image runner.  The memory model loads an @address byte image and
// the testbench checks only architectural termination and a0[7:0].
module cpu_core_image_tb #(
    parameter integer FE_WIDTH = 1,
    parameter integer BE_WIDTH = 1,
    parameter integer PHYS_REGS = 48,
    parameter integer ROB_ENTRIES = 16,
    parameter integer RS_ENTRIES = 4,
    parameter integer LSQ_ENTRIES = 4,
    parameter integer INT_ISSUE_WIDTH = (BE_WIDTH < 2) ? BE_WIDTH : 2,
    parameter integer CDB_WIDTH = (BE_WIDTH < 2) ? BE_WIDTH : 2,
    parameter integer ENABLE_CACHE_STATS = 0,
    parameter integer ENABLE_CACHES = 1,
    parameter integer ICACHE_FAST_HIT = 1,
    parameter integer ICACHE_COMBINATIONAL_HIT = 0,
    parameter integer ICACHE_PREFETCH = 1,
    parameter integer ICACHE_MSHRS = 8,
    parameter integer DCACHE_MSHRS = 4,
    parameter integer DCACHE_LINES = 256,
    parameter integer DCACHE_INDEX_HASH = 0,
    parameter integer DCACHE_REQUEST_PIPELINE = 0,
    parameter integer RAM_SIZE_BYTES = 1048576,
    parameter integer LEGACY_SENTINEL_HALT = 1,
    parameter integer MEMORY_LATENCY = 50,
    parameter integer I_MEMORY_OUTSTANDING = 8,
    parameter integer D_MEMORY_OUTSTANDING = 4,
    parameter integer ENABLE_PREDICTOR = 1,
    parameter integer FETCH_QUEUE_DEPTH = 16,
    parameter integer MUL_IMPL = 0,
    parameter integer SHIFT_IMPL = 0,
    parameter integer PHYS_TAG_IMPL = 0,
    parameter integer CHECKPOINT_IMPL = 0,
    parameter integer STORE_BUFFERED_RETIRE = 1,
    parameter integer COMPLETION_BYPASS = 0,
    parameter integer SERIAL_BACKEND = 0,
    parameter integer GENERATION_WIDTH = `RV32IM_ROB_GENERATION_WIDTH,
    parameter integer COMPLETION_DEPTH = (BE_WIDTH <= 1) ? 4 :
                                         ((BE_WIDTH == 2) ? 8 : 16)
);
    reg clk;
    reg reset;
    wire halted;
    wire error;
    wire [31:0] return_value;
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
        .INT_ISSUE_WIDTH(INT_ISSUE_WIDTH),
        .CDB_WIDTH(CDB_WIDTH),
        .ENABLE_CACHE_STATS(ENABLE_CACHE_STATS),
        .ENABLE_CACHES(ENABLE_CACHES),
        .ICACHE_FAST_HIT(ICACHE_FAST_HIT),
        .ICACHE_COMBINATIONAL_HIT(ICACHE_COMBINATIONAL_HIT),
        .ICACHE_PREFETCH(ICACHE_PREFETCH),
        .ICACHE_MSHRS(ICACHE_MSHRS),
        .DCACHE_MSHRS(DCACHE_MSHRS),
        .DCACHE_LINES(DCACHE_LINES),
        .DCACHE_INDEX_HASH(DCACHE_INDEX_HASH),
        .DCACHE_REQUEST_PIPELINE(DCACHE_REQUEST_PIPELINE),
        .RAM_SIZE_BYTES(RAM_SIZE_BYTES),
        .LEGACY_SENTINEL_HALT(LEGACY_SENTINEL_HALT),
        .ENABLE_PREDICTOR(ENABLE_PREDICTOR),
        .FETCH_QUEUE_DEPTH(FETCH_QUEUE_DEPTH),
        .MUL_IMPL(MUL_IMPL),
        .SHIFT_IMPL(SHIFT_IMPL),
        .PHYS_TAG_IMPL(PHYS_TAG_IMPL),
        .CHECKPOINT_IMPL(CHECKPOINT_IMPL),
        .STORE_BUFFERED_RETIRE(STORE_BUFFERED_RETIRE),
        .COMPLETION_BYPASS(COMPLETION_BYPASS),
        .SERIAL_BACKEND(SERIAL_BACKEND),
        .GENERATION_WIDTH(GENERATION_WIDTH),
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

    rv32im_memory_model #(
        .MEMORY_SIZE(RAM_SIZE_BYTES),
        .LATENCY(MEMORY_LATENCY),
        .I_OUTSTANDING(I_MEMORY_OUTSTANDING),
        .D_OUTSTANDING(D_MEMORY_OUTSTANDING)
    ) memory (
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
        $display("EVAL_MEMORY: unified=1 latency=%0d i_outstanding=%0d d_outstanding=%0d line_bytes=16",
                 MEMORY_LATENCY, I_MEMORY_OUTSTANDING, D_MEMORY_OUTSTANDING);
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
            $display("STATE: pc=%08x fetch_valid=%b fetch_ready=%b trace_ready=%b dreq=%b dresp=%b store_ack=%b",
                     dut.frontend.pc_reg, dut.frontend.fetch_valid_o,
                     dut.frontend.fetch_ready_i, dut.trace_ready,
                     dut.dcache_req_valid, dut.dcache_resp_valid,
                     dut.dcache_store_ack_valid);
            $display("STATE_ICACHE: epoch=%0d req_valid=%b req_ready=%b req_pc=%08x resp_valid=%b mem_req_valid=%b mem_req_ready=%b mem_req_addr=%08x mem_req_id=%02x mem_resp_valid=%b mem_resp_ready=%b mem_resp_addr=%08x mem_resp_id=%02x resp_slot=%b prefetch_active=%b remaining=%0d",
                     dut.frontend_epoch,
                     dut.if_req_valid, dut.if_req_ready, dut.if_req_pc,
                     dut.if_resp_valid,
                     dut.ic_mem_req_valid, dut.ic_mem_req_ready,
                     dut.ic_mem_req_line_addr, dut.ic_mem_req_id,
                     dut.ic_mem_resp_valid, dut.ic_mem_resp_ready,
                     dut.ic_mem_resp_line_addr, dut.ic_mem_resp_id,
                     dut.g_cached_memory.g_nonblocking_icache.icache.resp_valid_reg,
                     dut.g_cached_memory.g_nonblocking_icache.icache.prefetch_active,
                     dut.g_cached_memory.g_nonblocking_icache.icache.prefetch_remaining);
            for (diag_slot = 0; diag_slot < ICACHE_MSHRS; diag_slot = diag_slot + 1)
                if (dut.g_cached_memory.g_nonblocking_icache.icache.mshr_valid[diag_slot])
                    $display("STATE_ICACHE_MSHR: slot=%0d sent=%b prefetch=%b pc=%08x line=%08x demand_epoch=%0d txn_epoch=%0d",
                             diag_slot,
                             dut.g_cached_memory.g_nonblocking_icache.icache.mshr_sent[diag_slot],
                             dut.g_cached_memory.g_nonblocking_icache.icache.mshr_prefetch[diag_slot],
                             dut.g_cached_memory.g_nonblocking_icache.icache.mshr_pc[diag_slot],
                             dut.g_cached_memory.g_nonblocking_icache.icache.mshr_line[diag_slot],
                             dut.g_cached_memory.g_nonblocking_icache.icache.mshr_demand_epoch[diag_slot],
                             dut.g_cached_memory.g_nonblocking_icache.icache.mshr_txn_epoch[diag_slot]);
            $display("STATE_BACKEND: rob=%0d rs=%0d lsq=%0d issue=%b branch_pending=%b branch_tag=%04x recovery_accept=%b mdu_busy=%b commit=%b redirect=%b",
                     dut.perf_rob_occupancy, dut.perf_rs_occupancy,
                     dut.perf_lsq_occupancy, dut.perf_issue_valid,
                     dut.perf_branch_pending,
                     dut.g_ooo_backend.backend.branch_pending_tag,
                     dut.g_ooo_backend.backend.rob_recovery_accept,
                     dut.perf_mdu_busy,
                     dut.commit_valid, dut.redirect_valid);
            $display("STATE_ROB: head=%0d tail=%0d completion_head=%0d completion_tail=%0d completion_count=%0d",
                     dut.g_ooo_backend.backend.rob.head_reg,
                     dut.g_ooo_backend.backend.rob.tail_reg,
                     dut.g_ooo_backend.backend.completion.head_reg,
                     dut.g_ooo_backend.backend.completion.tail_reg,
                     dut.g_ooo_backend.backend.completion.count_reg);
            $display("STATE_RENAME: rat_x1=%0d free=%b ready=%b producer_tag=%04x free_count=%0d",
                     dut.g_ooo_backend.backend.rename.rat[1],
                     dut.g_ooo_backend.backend.rename.free_bitmap[
                         dut.g_ooo_backend.backend.rename.rat[1]],
                     dut.g_ooo_backend.backend.prf.ready[
                         dut.g_ooo_backend.backend.rename.rat[1]],
                     dut.g_ooo_backend.backend.phys_tag_mem[
                         dut.g_ooo_backend.backend.rename.rat[1]],
                     dut.g_ooo_backend.backend.free_count);
            for (diag_slot = 0; diag_slot < ROB_ENTRIES; diag_slot = diag_slot + 1)
                if (dut.g_ooo_backend.backend.rob.valid_mem[diag_slot])
                    $display("STATE_ROB_ENTRY: slot=%0d ready=%b pc=%08x inst=%08x gen=%0d",
                             diag_slot,
                             dut.g_ooo_backend.backend.rob.ready_mem[diag_slot],
                             dut.g_ooo_backend.backend.rob.pc_mem[diag_slot],
                             dut.g_ooo_backend.backend.rob.inst_mem[diag_slot],
                             dut.g_ooo_backend.backend.rob.generation_mem[diag_slot]);
            $display("STATE_LSQ: head=%0d tail=%0d",
                     dut.g_ooo_backend.backend.lsq.head_reg,
                     dut.g_ooo_backend.backend.lsq.tail_reg);
            for (diag_slot = 0; diag_slot < LSQ_ENTRIES; diag_slot = diag_slot + 1)
                if (dut.g_ooo_backend.backend.lsq.valid_mem[diag_slot])
                    $display("STATE_LSQ_ENTRY: slot=%0d load=%b store=%b addr_ready=%b data_ready=%b sent=%b wait=%b complete=%b committed=%b ack=%b addr=%08x rob_tag=%04x gen=%0d",
                             diag_slot,
                             dut.g_ooo_backend.backend.lsq.load_mem[diag_slot],
                             dut.g_ooo_backend.backend.lsq.store_mem[diag_slot],
                             dut.g_ooo_backend.backend.lsq.addr_ready_mem[diag_slot],
                             dut.g_ooo_backend.backend.lsq.data_ready_mem[diag_slot],
                             dut.g_ooo_backend.backend.lsq.request_sent_mem[diag_slot],
                             dut.g_ooo_backend.backend.lsq.response_wait_mem[diag_slot],
                             dut.g_ooo_backend.backend.lsq.complete_mem[diag_slot],
                             dut.g_ooo_backend.backend.lsq.store_commit_mem[diag_slot],
                             dut.g_ooo_backend.backend.lsq.store_ack_mem[diag_slot],
                             dut.g_ooo_backend.backend.lsq.addr_mem[diag_slot],
                             dut.g_ooo_backend.backend.lsq.rob_tag_mem[diag_slot],
                             dut.g_ooo_backend.backend.lsq.generation_mem[diag_slot]);
            for (diag_slot = 0; diag_slot < RS_ENTRIES; diag_slot = diag_slot + 1)
                if (dut.g_ooo_backend.backend.rs.valid_mem[diag_slot])
                    $display("STATE_RS_ENTRY: slot=%0d op=%0d src1_ready=%b src2_ready=%b tag=%04x src1_tag=%04x src2_tag=%04x",
                             diag_slot,
                             dut.g_ooo_backend.backend.rs.op_mem[diag_slot],
                             dut.g_ooo_backend.backend.rs.src1_ready_mem[diag_slot],
                             dut.g_ooo_backend.backend.rs.src2_ready_mem[diag_slot],
                             dut.g_ooo_backend.backend.rs.rob_tag_mem[diag_slot],
                             dut.g_ooo_backend.backend.rs.src1_tag_mem[diag_slot],
                             dut.g_ooo_backend.backend.rs.src2_tag_mem[diag_slot]);
            finish_code = 1;
        end else if (error) begin
            $display("FAIL: JOIN-02 image=%0s architectural error cycles=%0d instret=%0d", test_name, cycles, instret);
            finish_code = 1;
        end else if (!halted) begin
            $display("FAIL: JOIN-02 image=%0s timeout cycles=%0d instret=%0d limit=%0d", test_name, cycles, instret, max_cycles);
            finish_code = 1;
        end else if ((LEGACY_SENTINEL_HALT == 0) &&
                     (!memory.mmio_exit_valid ||
                      (memory.mmio_exit_code !== return_value))) begin
            $display("FAIL: JOIN-02 image=%0s MMIO exit missing/mismatched valid=%b bus_code=%08x cpu_code=%08x",
                     test_name, memory.mmio_exit_valid, memory.mmio_exit_code, return_value);
            finish_code = 1;
        end else if (return_value !== expected_value[31:0]) begin
            $display("FAIL: JOIN-02 image=%0s return=%0d expected=%0d cycles=%0d instret=%0d", test_name, return_value, expected_value, cycles, instret);
            finish_code = 1;
        end else begin
            $display("PASS: JOIN-02 image=%0s return=%0d cycles=%0d instret=%0d", test_name, return_value, cycles, instret);
        end
        if (ENABLE_CACHE_STATS != 0) begin
            $display("PERF: fe_empty=%0d be_stall=%0d no_commit=%0d commit_active=%0d issue=%0d rob_full=%0d rs_full=%0d lsq_full=%0d branch_pending=%0d mdu_busy=%0d",
                     dut.perf_frontend_empty_cycles, dut.perf_backend_stall_cycles,
                     dut.perf_no_commit_cycles, dut.perf_commit_active_cycles,
                     dut.perf_issue_count, dut.perf_rob_full_cycles,
                     dut.perf_rs_full_cycles, dut.perf_lsq_full_cycles,
                     dut.perf_branch_pending_cycles, dut.perf_mdu_busy_cycles);
            $display("PERF_CACHE: i_req=%0d i_hit=%0d i_miss=%0d i_refill=%0d i_stall=%0d d_req=%0d d_hit=%0d d_miss=%0d d_refill=%0d d_wb=%0d d_stall=%0d i_mem=%0d d_mem_read=%0d d_mem_write=%0d",
                     dut.perf_i_requests, dut.perf_i_hits, dut.perf_i_misses,
                     dut.perf_i_refills, dut.perf_i_stalls, dut.perf_d_requests,
                     dut.perf_d_hits, dut.perf_d_misses, dut.perf_d_refills,
                     dut.perf_d_writebacks, dut.perf_d_stalls,
                     dut.perf_i_mem_requests, dut.perf_d_mem_reads,
                     dut.perf_d_mem_writes);
            $display("PERF_PRED: resolved=%0d correct=%0d mispredict=%0d",
                     dut.pred_count, dut.pred_correct,
                     dut.pred_count - dut.pred_correct);
        end
        if (trace_file != 0)
            $fclose(trace_file);
        $finish(finish_code);
    end

    generate if (SERIAL_BACKEND == 0) begin : g_lsq_integrity_check
        integer live_count, offset, slot_index;
        reg ring_error;
        reg previous_recovery;
        reg [31:0] previous_recovery_tag;
        always @(posedge clk) begin
            if (!reset && $test$plusargs("CHECK_LSQ")) begin
                live_count = 0;
                ring_error = 1'b0;
                for (offset = 0; offset < LSQ_ENTRIES; offset = offset + 1) begin
                    slot_index = (dut.g_ooo_backend.backend.lsq.head_reg + offset) % LSQ_ENTRIES;
                    if (dut.g_ooo_backend.backend.lsq.valid_mem[slot_index]) live_count = live_count + 1;
                    if (dut.g_ooo_backend.backend.lsq.valid_mem[slot_index] !=
                        (offset < dut.g_ooo_backend.backend.lsq.occupancy_reg)) ring_error = 1'b1;
                end
                if (ring_error || live_count != dut.g_ooo_backend.backend.lsq.occupancy_reg) begin
                    $display("FAIL: LSQ ring invariant cycle=%0d head=%0d tail=%0d count=%0d live=%0d previous_recovery=%b tag=%x",
                             cycles, dut.g_ooo_backend.backend.lsq.head_reg,
                             dut.g_ooo_backend.backend.lsq.tail_reg,
                             dut.g_ooo_backend.backend.lsq.occupancy_reg, live_count,
                             previous_recovery, previous_recovery_tag);
                    for (offset = 0; offset < LSQ_ENTRIES; offset = offset + 1)
                        $display("LSQ_RING: slot=%0d valid=%b load=%b store=%b reported=%b committed=%b rob=%x",
                                 offset, dut.g_ooo_backend.backend.lsq.valid_mem[offset],
                                 dut.g_ooo_backend.backend.lsq.load_mem[offset],
                                 dut.g_ooo_backend.backend.lsq.store_mem[offset],
                                 dut.g_ooo_backend.backend.lsq.load_reported_mem[offset],
                                 dut.g_ooo_backend.backend.lsq.store_commit_mem[offset],
                                 dut.g_ooo_backend.backend.lsq.rob_tag_mem[offset]);
                    $finish(1);
                end
            end
            previous_recovery <= dut.g_ooo_backend.backend.rob_recovery_accept;
            previous_recovery_tag <= dut.g_ooo_backend.backend.branch_pending_tag;
        end
    end endgenerate

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
            $display("TRACE: periodic cycles=%0d instret=%0d pc=%08x fetch_valid=%b fetch_ready=%b trace_ready=%b",
                     cycles, instret, dut.frontend.pc_reg, dut.frontend.fetch_valid_o,
                     dut.frontend.fetch_ready_i, dut.trace_ready);
        if (trace_enable && dut.commit_valid)
            $display("TRACE: pc=%08x inst=%08x rd=%0d we=%b value=%08x store=%b", dut.commit_pc,
                     dut.commit_inst, dut.commit_rd, dut.commit_rd_we,
                     dut.commit_value, dut.commit_is_store);
        if (trace_enable && dut.dcache_req_valid)
            $display("TRACE: cycle=%0d dreq load=%b store=%b addr=%08x mask=%04x data=%08x ready=%b", cycles, dut.dcache_req_load,
                     dut.dcache_req_store, dut.dcache_req_addr, dut.dcache_req_mask,
                     dut.dcache_req_wdata[31:0], dut.dcache_req_ready);
        if (trace_enable && dut.mem_i_req_valid)
            $display("TRACE: cycle=%0d mem-i line=%08x id=%02x ready=%b", cycles,
                     dut.mem_i_req_line_addr, dut.mem_i_req_id,
                     dut.mem_i_req_ready);
        if (trace_enable && dut.mem_i_resp_valid)
            $display("TRACE: cycle=%0d mem-i response line=%08x id=%02x error=%b ready=%b", cycles,
                     dut.mem_i_resp_line_addr, dut.mem_i_resp_id,
                     dut.mem_i_resp_error, dut.mem_i_resp_ready);
        if (trace_enable && dut.mem_d_req_valid)
            $display("TRACE: cycle=%0d mem-d write=%b line=%08x id=%02x ready=%b", cycles, dut.mem_d_req_write,
                     dut.mem_d_req_line_addr, dut.mem_d_req_id, dut.mem_d_req_ready);
        if (trace_enable && dut.mem_d_resp_valid)
            $display("TRACE: cycle=%0d mem-d response line=%08x id=%02x error=%b ready=%b", cycles, dut.mem_d_resp_line_addr,
                     dut.mem_d_resp_id, dut.mem_d_resp_error, dut.mem_d_resp_ready);
        if (trace_enable && dut.dcache_store_ack_valid)
            $display("TRACE: cycle=%0d dcache store-ack lsq=%04x error=%b", cycles, dut.dcache_store_ack_lsq_tag, dut.dcache_store_ack_error);
        if (trace_enable && dut.dcache_resp_valid)
            $display("TRACE: cycle=%0d dcache load-resp lsq=%04x addr=%08x value=%08x error=%b", cycles, dut.dcache_resp_lsq_tag,
                     dut.dcache_resp_addr, dut.dcache_resp_word, dut.dcache_resp_error);
        if (trace_enable && (dut.dcache_debug_s0_valid || dut.dcache_debug_s1_valid ||
            dut.dcache_debug_s2_valid || dut.dcache_debug_mshr_valid || dut.dcache_debug_ack_valid))
            $display("TRACE: dcstate s0=%b/%b s1=%b/%b s2=%b/%b hit=%b mshr=%b ack=%b resp=%b",
                     dut.dcache_debug_s0_valid, dut.dcache_debug_s0_store,
                     dut.dcache_debug_s1_valid, dut.dcache_debug_s1_store,
                     dut.dcache_debug_s2_valid, dut.dcache_debug_s2_store,
                     dut.dcache_debug_s2_hit, dut.dcache_debug_mshr_valid,
                     dut.dcache_debug_ack_valid, dut.dcache_debug_resp_valid);
        if (trace_enable && dut.redirect_valid)
            $display("TRACE: control redirect=%b pc=%08x epoch=%0d frontend_pc=%08x frontend_epoch=%0d alu_tags=%h alu_valid=%b alu_flush=%b branch_tag=%h rob_head=%0d rat1=%0d free1=%b reclaim1=%b",
                     dut.redirect_valid, dut.redirect_pc, dut.redirect_epoch,
                     dut.frontend.pc_reg, dut.frontend.epoch_reg,
                     dut.g_ooo_backend.backend.alu_exec_tag,
                     dut.g_ooo_backend.backend.alu_exec_valid,
                     dut.g_ooo_backend.backend.alu_flush_r,
                     dut.g_ooo_backend.backend.branch_pending_tag,
                     dut.g_ooo_backend.backend.rob_head,
                     dut.g_ooo_backend.backend.rename.rat[1],
                     dut.g_ooo_backend.backend.rename.free_bitmap[
                         dut.g_ooo_backend.backend.rename.rat[1]],
                     dut.g_ooo_backend.backend.rob_recovery_reclaim_bitmap[
                         dut.g_ooo_backend.backend.rename.rat[1]]);
        if (trace_enable && !dut.g_ooo_backend.backend.branch_pending &&
            (|(dut.g_ooo_backend.backend.alu_exec_valid &
               dut.g_ooo_backend.backend.alu_exec_redirect_valid)))
            $display("TRACE: branch capture tags=%h valid=%b redirect=%b rob_head=%0d",
                     dut.g_ooo_backend.backend.alu_exec_tag,
                     dut.g_ooo_backend.backend.alu_exec_valid,
                     dut.g_ooo_backend.backend.alu_exec_redirect_valid,
                     dut.g_ooo_backend.backend.rob_head);
    end

endmodule
