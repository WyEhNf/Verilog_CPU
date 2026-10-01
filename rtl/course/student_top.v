`timescale 1ns/1ps
// Course-compatible AXI4-Lite top. Extra observation ports are simulation
// diagnostics only; official sim.cpp uses the unmodified AXI interface.
module student_top #(
    parameter integer FE_WIDTH = 4, BE_WIDTH = 4,
    parameter integer PHYS_REGS = 64, ROB_ENTRIES = 32,
    parameter integer RS_ENTRIES = 16, LSQ_ENTRIES = 8,
    parameter integer LSQ_STORE_ADMISSION_BYPASS = 0,
    parameter integer EARLY_STORE_ADDRESS = 0,
    parameter integer RS_ISSUE_METADATA = 0,
    parameter integer PREDICTOR_DIRECT_BRANCH_TARGET = 0,
    parameter integer PREDICTOR_HISTORY_BITS = 6,
    parameter integer ASAP7_FANOUT_BUFFERS = 0,
    parameter integer ROB_CONTROL_REGISTER_BANKS = 0,
    parameter integer INT_ISSUE_WIDTH = 4, CDB_WIDTH = 4,
    parameter integer ICACHE_MSHRS = 8, ICACHE_LINES = 64, ICACHE_WAYS = 2,
    parameter integer DCACHE_MSHRS = 4, DCACHE_LINES = 1024, DCACHE_WAYS = 2,
    parameter integer DCACHE_INDEX_HASH = 1, DCACHE_REQUEST_PIPELINE = 0,
    parameter integer DCACHE_STORE_MERGE_DELAY = 16,
    parameter integer DCACHE_TAG_SRAM = 0,
    parameter integer DCACHE_STATIC_UPDATES = 0,
    parameter integer FETCH_QUEUE_DEPTH = 16, COMPLETION_DEPTH = 16,
    parameter integer CHECKPOINT_IMPL = 1, MUL_IMPL = 0, SHIFT_IMPL = 0,
    parameter integer RAT_RECOVERY_IMPL = 0,
    parameter integer PHYS_TAG_IMPL = 0, GENERATION_WIDTH = 8,
    parameter integer STORE_BUFFERED_RETIRE = 1, COMPLETION_BYPASS = 0,
    parameter integer SERIAL_BACKEND = 0, ENABLE_CACHE_STATS = 1,
    parameter integer READ_LINES = 16, WRITE_LINES = 8, WORD_QUEUE = 64,
    parameter integer AXI_RESPONSE_FIFO_DEPTH = 0
) (
    input wire clock, reset,
    output wire [31:0] araddr, output wire arvalid, input wire arready,
    input wire [31:0] rdata, input wire [1:0] rresp, input wire rvalid, output wire rready,
    output wire [31:0] awaddr, output wire awvalid, input wire awready,
    output wire [31:0] wdata, output wire [3:0] wstrb, output wire wvalid, input wire wready,
    input wire [1:0] bresp, input wire bvalid, output wire bready,
    output wire [31:0] debug_instret, debug_core_cycles,
    output wire debug_error
);
    wire iv, ir, ov, ore, oe, dv, dr, dw, dsv, dsr, dse;
    wire [31:0] ia, oa, da, dsa;
    wire [7:0] iid, oid, did, dsid;
    wire [127:0] od, dd, dsd;
    wire [15:0] dm;
    cpu_core #(.FE_WIDTH(FE_WIDTH), .BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS),
        .ROB_ENTRIES(ROB_ENTRIES), .RS_ENTRIES(RS_ENTRIES), .LSQ_ENTRIES(LSQ_ENTRIES),
        .LSQ_STORE_ADMISSION_BYPASS(LSQ_STORE_ADMISSION_BYPASS),
        .EARLY_STORE_ADDRESS(EARLY_STORE_ADDRESS),
        .RS_ISSUE_METADATA(RS_ISSUE_METADATA),
        .PREDICTOR_DIRECT_BRANCH_TARGET(PREDICTOR_DIRECT_BRANCH_TARGET),
        .PREDICTOR_HISTORY_BITS(PREDICTOR_HISTORY_BITS),
        .ASAP7_FANOUT_BUFFERS(ASAP7_FANOUT_BUFFERS),
        .ROB_CONTROL_REGISTER_BANKS(ROB_CONTROL_REGISTER_BANKS),
        .INT_ISSUE_WIDTH(INT_ISSUE_WIDTH), .CDB_WIDTH(CDB_WIDTH),
        .ICACHE_MSHRS(ICACHE_MSHRS), .ICACHE_LINES(ICACHE_LINES), .ICACHE_WAYS(ICACHE_WAYS),
        .DCACHE_MSHRS(DCACHE_MSHRS), .DCACHE_LINES(DCACHE_LINES), .DCACHE_WAYS(DCACHE_WAYS),
        .DCACHE_INDEX_HASH(DCACHE_INDEX_HASH), .DCACHE_REQUEST_PIPELINE(DCACHE_REQUEST_PIPELINE),
        .DCACHE_STORE_MERGE_DELAY(DCACHE_STORE_MERGE_DELAY),
        .DCACHE_TAG_SRAM(DCACHE_TAG_SRAM),
        .DCACHE_STATIC_UPDATES(DCACHE_STATIC_UPDATES),
        .FETCH_QUEUE_DEPTH(FETCH_QUEUE_DEPTH), .COMPLETION_DEPTH(COMPLETION_DEPTH),
        .CHECKPOINT_IMPL(CHECKPOINT_IMPL), .MUL_IMPL(MUL_IMPL), .SHIFT_IMPL(SHIFT_IMPL),
        .RAT_RECOVERY_IMPL(RAT_RECOVERY_IMPL),
        .PHYS_TAG_IMPL(PHYS_TAG_IMPL), .GENERATION_WIDTH(GENERATION_WIDTH),
        .STORE_BUFFERED_RETIRE(STORE_BUFFERED_RETIRE), .COMPLETION_BYPASS(COMPLETION_BYPASS),
        .SERIAL_BACKEND(SERIAL_BACKEND), .ENABLE_CACHE_STATS(ENABLE_CACHE_STATS),
        .RAM_SIZE_BYTES(268435456), .LEGACY_SENTINEL_HALT(0)) core (
        .clk(clock), .reset(reset), .instret(debug_instret), .cycles(debug_core_cycles),
        .error(debug_error),
        .mem_i_req_valid(iv), .mem_i_req_ready(ir), .mem_i_req_line_addr(ia), .mem_i_req_id(iid),
        .mem_i_resp_valid(ov), .mem_i_resp_ready(ore), .mem_i_resp_line_addr(oa),
        .mem_i_resp_data(od), .mem_i_resp_id(oid), .mem_i_resp_error(oe),
        .mem_d_req_valid(dv), .mem_d_req_ready(dr), .mem_d_req_write(dw),
        .mem_d_req_line_addr(da), .mem_d_req_wdata(dd), .mem_d_req_wmask(dm), .mem_d_req_id(did),
        .mem_d_resp_valid(dsv), .mem_d_resp_ready(dsr), .mem_d_resp_line_addr(dsa),
        .mem_d_resp_data(dsd), .mem_d_resp_id(dsid), .mem_d_resp_error(dse)
    );
    rv32_axi_lite_bridge #(.READ_LINES(READ_LINES), .WRITE_LINES(WRITE_LINES),
        .WORD_QUEUE(WORD_QUEUE), .RESPONSE_FIFO_DEPTH(AXI_RESPONSE_FIFO_DEPTH)) bus (
        .clock(clock), .reset(reset), .i_req_valid(iv), .i_req_ready(ir), .i_req_addr(ia), .i_req_id(iid),
        .i_resp_valid(ov), .i_resp_ready(ore), .i_resp_addr(oa), .i_resp_data(od),
        .i_resp_id(oid), .i_resp_error(oe), .d_req_valid(dv), .d_req_ready(dr),
        .d_req_write(dw), .d_req_addr(da), .d_req_data(dd), .d_req_mask(dm), .d_req_id(did),
        .d_resp_valid(dsv), .d_resp_ready(dsr), .d_resp_addr(dsa), .d_resp_data(dsd),
        .d_resp_id(dsid), .d_resp_error(dse),
        .araddr(araddr), .arvalid(arvalid), .arready(arready), .rdata(rdata), .rresp(rresp),
        .rvalid(rvalid), .rready(rready), .awaddr(awaddr), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wvalid(wvalid), .wready(wready),
        .bresp(bresp), .bvalid(bvalid), .bready(bready)
    );
endmodule
