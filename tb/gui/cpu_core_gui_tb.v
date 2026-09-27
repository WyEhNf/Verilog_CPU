`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Interactive image runner used by tools/cpu_gui.py.  The GUI protocol is a
// compact, line-oriented stream so the browser frontend never needs to parse
// simulator-specific diagnostics.
module cpu_core_gui_tb #(
    parameter integer FE_WIDTH = 1,
    parameter integer BE_WIDTH = 1,
    parameter integer PHYS_REGS = 33,
    parameter integer ROB_ENTRIES = 2,
    parameter integer RS_ENTRIES = 1,
    parameter integer LSQ_ENTRIES = 1,
    parameter integer ENABLE_CACHE_STATS = 0,
    parameter integer ENABLE_CACHES = 0,
    parameter integer ENABLE_PREDICTOR = 0,
    parameter integer FETCH_QUEUE_DEPTH = 1,
    parameter integer MUL_IMPL = 2,
    parameter integer SHIFT_IMPL = 1,
    parameter integer PHYS_TAG_IMPL = 1,
    parameter integer CHECKPOINT_IMPL = 1,
    parameter integer COMPLETION_BYPASS = 1,
    parameter integer SERIAL_BACKEND = 1,
    parameter integer GENERATION_WIDTH = 3,
    parameter integer COMPLETION_DEPTH = 1
);
    reg clk;
    reg reset;
    wire halted;
    wire error;
    wire [7:0] return_value;
    wire [31:0] cycles;
    wire [31:0] instret;

    wire mem_i_req_valid, mem_i_req_ready, mem_i_resp_valid, mem_i_resp_ready;
    wire [31:0] mem_i_req_line_addr, mem_i_resp_line_addr;
    wire [127:0] mem_i_resp_data;
    wire [7:0] mem_i_req_id, mem_i_resp_id;
    wire mem_i_resp_error;
    wire mem_d_req_valid, mem_d_req_ready, mem_d_req_write;
    wire [31:0] mem_d_req_line_addr, mem_d_resp_line_addr;
    wire [127:0] mem_d_req_wdata, mem_d_resp_data;
    wire [15:0] mem_d_req_wmask;
    wire [7:0] mem_d_req_id, mem_d_resp_id;
    wire mem_d_resp_valid, mem_d_resp_ready, mem_d_resp_error;

    integer expected_value;
    integer max_cycles;
    integer max_no_retire_cycles;
    integer no_retire_cycles;
    integer trace_interval;
    integer trace_lane;
    integer finish_code;
    reg [31:0] last_instret;
    reg watchdog_expired;
    reg [1023:0] test_name;

    cpu_core #(
        .FE_WIDTH(FE_WIDTH), .BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS),
        .ROB_ENTRIES(ROB_ENTRIES), .RS_ENTRIES(RS_ENTRIES),
        .LSQ_ENTRIES(LSQ_ENTRIES), .ENABLE_CACHE_STATS(ENABLE_CACHE_STATS),
        .ENABLE_CACHES(ENABLE_CACHES), .ENABLE_PREDICTOR(ENABLE_PREDICTOR),
        .FETCH_QUEUE_DEPTH(FETCH_QUEUE_DEPTH), .MUL_IMPL(MUL_IMPL),
        .SHIFT_IMPL(SHIFT_IMPL), .PHYS_TAG_IMPL(PHYS_TAG_IMPL),
        .CHECKPOINT_IMPL(CHECKPOINT_IMPL), .COMPLETION_BYPASS(COMPLETION_BYPASS),
        .SERIAL_BACKEND(SERIAL_BACKEND), .GENERATION_WIDTH(GENERATION_WIDTH),
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
        max_cycles = 300000;
        max_no_retire_cycles = 100000;
        trace_interval = 25;
        no_retire_cycles = 0;
        finish_code = 0;
        last_instret = 0;
        watchdog_expired = 1'b0;
        test_name = "image";
        if ($value$plusargs("EXPECTED=%d", expected_value)) begin end
        if ($value$plusargs("MAX_CYCLES=%d", max_cycles)) begin end
        if ($value$plusargs("MAX_NO_RETIRE_CYCLES=%d", max_no_retire_cycles)) begin end
        if ($value$plusargs("TRACE_INTERVAL=%d", trace_interval)) begin end
        if ($value$plusargs("TEST=%s", test_name)) begin end
        if (trace_interval < 1) trace_interval = 1;

        $display("GUI|meta|test=%0s|fe=%0d|be=%0d|phys=%0d|rob=%0d|rs=%0d|lsq=%0d|caches=%0d|predictor=%0d|fq=%0d|mul=%0d|shift=%0d|phys_tag=%0d|checkpoint=%0d|completion_bypass=%0d|serial=%0d|generation=%0d|completion=%0d",
                 test_name, FE_WIDTH, BE_WIDTH, PHYS_REGS, ROB_ENTRIES,
                 RS_ENTRIES, LSQ_ENTRIES, ENABLE_CACHES, ENABLE_PREDICTOR,
                 FETCH_QUEUE_DEPTH, MUL_IMPL, SHIFT_IMPL, PHYS_TAG_IMPL,
                 CHECKPOINT_IMPL, COMPLETION_BYPASS, SERIAL_BACKEND,
                 GENERATION_WIDTH, COMPLETION_DEPTH);
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
            if (no_retire_cycles >= max_no_retire_cycles)
                watchdog_expired = 1'b1;
        end
        #1;
        if (watchdog_expired) begin
            $display("GUI|result|status=failed|reason=watchdog|cycles=%0d|instret=%0d|return=%0d|expected=%0d", cycles, instret, return_value, expected_value[7:0]);
            finish_code = 1;
        end else if (error) begin
            $display("GUI|result|status=failed|reason=architectural_error|cycles=%0d|instret=%0d|return=%0d|expected=%0d", cycles, instret, return_value, expected_value[7:0]);
            finish_code = 1;
        end else if (!halted) begin
            $display("GUI|result|status=failed|reason=timeout|cycles=%0d|instret=%0d|return=%0d|expected=%0d", cycles, instret, return_value, expected_value[7:0]);
            finish_code = 1;
        end else if (return_value !== expected_value[7:0]) begin
            $display("GUI|result|status=failed|reason=wrong_return|cycles=%0d|instret=%0d|return=%0d|expected=%0d", cycles, instret, return_value, expected_value[7:0]);
            finish_code = 1;
        end else begin
            $display("GUI|result|status=passed|reason=complete|cycles=%0d|instret=%0d|return=%0d|expected=%0d", cycles, instret, return_value, expected_value[7:0]);
        end
        $finish(finish_code);
    end

    always @(posedge clk) begin
        if (!reset) begin
            for (trace_lane = 0; trace_lane < BE_WIDTH; trace_lane = trace_lane + 1) begin
                if (dut.commit_valid[trace_lane])
                    $display("GUI|commit|cycle=%0d|lane=%0d|pc=%08x|inst=%08x|rd=%0d|we=%0d|value=%08x|store=%0d|store_addr=%08x|store_mask=%04x",
                             cycles, trace_lane,
                             dut.commit_pc[trace_lane*32 +: 32],
                             dut.commit_inst[trace_lane*32 +: 32],
                             dut.commit_rd[trace_lane*5 +: 5],
                             dut.commit_rd_we[trace_lane],
                             dut.commit_value[trace_lane*32 +: 32],
                             dut.commit_is_store[trace_lane],
                             dut.commit_store_addr[trace_lane*32 +: 32],
                             dut.commit_store_mask[trace_lane*16 +: 16]);
            end
            if (dut.redirect_valid)
                $display("GUI|redirect|cycle=%0d|pc=%08x|epoch=%0d|from=%08x", cycles, dut.redirect_pc, dut.redirect_epoch, dut.frontend.pc_reg);
            if (dut.dcache_req_valid && dut.dcache_req_ready)
                $display("GUI|memory|cycle=%0d|phase=request|load=%0d|store=%0d|addr=%08x|size=%0d|mask=%04x|data=%08x",
                         cycles, dut.dcache_req_load, dut.dcache_req_store,
                         dut.dcache_req_addr, dut.dcache_req_size,
                         dut.dcache_req_mask, dut.dcache_req_wdata[31:0]);
            if (dut.dcache_resp_valid && dut.dcache_resp_ready)
                $display("GUI|memory|cycle=%0d|phase=load_response|addr=%08x|data=%08x|error=%0d", cycles, dut.dcache_resp_addr, dut.dcache_resp_word, dut.dcache_resp_error);
            if (dut.dcache_store_ack_valid)
                $display("GUI|memory|cycle=%0d|phase=store_ack|error=%0d", cycles, dut.dcache_store_ack_error);
        end
    end

    generate if (SERIAL_BACKEND != 0) begin : g_gui_serial
        always @(posedge clk) begin
            if (!reset && (((cycles % trace_interval) == 0) ||
                           (|dut.commit_valid) || dut.redirect_valid ||
                           dut.dcache_req_valid || halted || error))
                $display("GUI|state|mode=serial|cycle=%0d|instret=%0d|pc=%08x|epoch=%0d|fetch_valid=%0h|fetch_ready=%0h|trace_valid=%0h|trace_ready=%0h|stage=%0d|op=%0d|inst=%08x|exec_pc=%08x|rs1=%0d|rs2=%0d|rd=%0d|src1=%08x|src2=%08x|result=%08x|mdu_busy=%0d|frontend_stall=%0d|if_req=%0d|if_resp=%0d|d_req=%0d|d_resp=%0d",
                         cycles, instret, dut.frontend.pc_reg, dut.frontend.epoch_reg,
                         dut.fetch_valid, dut.fetch_ready, dut.trace_valid, dut.trace_ready,
                         dut.g_serial_backend.backend.state,
                         dut.g_serial_backend.backend.op_reg,
                         dut.g_serial_backend.backend.inst_reg,
                         dut.g_serial_backend.backend.pc_reg,
                         dut.g_serial_backend.backend.rs1_reg,
                         dut.g_serial_backend.backend.rs2_reg,
                         dut.g_serial_backend.backend.rd_reg,
                         dut.g_serial_backend.backend.src1_reg,
                         dut.g_serial_backend.backend.src2_reg,
                         dut.g_serial_backend.backend.result_reg,
                         dut.g_serial_backend.backend.mdu_resp_valid,
                         dut.frontend_event_stall, mem_i_req_valid,
                         mem_i_resp_valid, mem_d_req_valid, mem_d_resp_valid);
        end
    end else begin : g_gui_ooo
        always @(posedge clk) begin
            if (!reset && (((cycles % trace_interval) == 0) ||
                           (|dut.commit_valid) || dut.redirect_valid ||
                           dut.dcache_req_valid || halted || error))
                $display("GUI|state|mode=ooo|cycle=%0d|instret=%0d|pc=%08x|epoch=%0d|fetch_valid=%0h|fetch_ready=%0h|trace_valid=%0h|trace_ready=%0h|rob_occ=%0d|rob_head=%0d|rob_tail=%0d|rs_occ=%0d|lsq_occ=%0d|free_phys=%0d|dispatch=%0h|issue=%0h|cdb=%0h|branch_pending=%0d|mdu_issue=%0d|mdu_busy=%0d|completion_occ=%0d|frontend_stall=%0d|if_req=%0d|if_resp=%0d|d_req=%0d|d_resp=%0d",
                         cycles, instret, dut.frontend.pc_reg, dut.frontend.epoch_reg,
                         dut.fetch_valid, dut.fetch_ready, dut.trace_valid, dut.trace_ready,
                         dut.g_ooo_backend.backend.rob_occupancy,
                         dut.g_ooo_backend.backend.rob_head,
                         dut.g_ooo_backend.backend.rob_tail,
                         dut.g_ooo_backend.backend.rs_occupancy,
                         dut.g_ooo_backend.backend.lsq_occupancy,
                         dut.g_ooo_backend.backend.free_count,
                         dut.g_ooo_backend.backend.dispatch_valid,
                         dut.g_ooo_backend.backend.rs_issue_valid,
                         dut.g_ooo_backend.backend.cdb_valid,
                         dut.g_ooo_backend.backend.branch_pending,
                         dut.g_ooo_backend.backend.mdu_issue_valid,
                         dut.g_ooo_backend.backend.mdu_completion_valid,
                         dut.g_ooo_backend.backend.completion.count_reg,
                         dut.frontend_event_stall, mem_i_req_valid,
                         mem_i_resp_valid, mem_d_req_valid, mem_d_resp_valid);
        end
    end endgenerate
endmodule
