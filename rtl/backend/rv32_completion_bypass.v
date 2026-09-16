`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Storage-free completion arbiter for the minimum-area, single-issue profile.
// Execution producers already retain their registered result until ready, so
// a second copy in a completion FIFO is unnecessary.  The oldest source by
// fixed producer order drives CDB lane zero; stale results are drained without
// becoming visible architecturally.
module rv32_completion_bypass #(
    parameter integer BE_WIDTH = 1,
    parameter integer SOURCES = 5,
    parameter integer FIFO_DEPTH = 1,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT,
    parameter integer COUNT_WIDTH = (FIFO_DEPTH <= 1) ? 1 : $clog2(FIFO_DEPTH + 1)
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         flush_i,
    input  wire                         kill_valid_i,
    input  wire [FIFO_DEPTH-1:0]        kill_mask_i,
    input  wire [SOURCES-1:0]           producer_valid_i,
    output reg  [SOURCES-1:0]           producer_ready_o,
    input  wire [(SOURCES*TAG_WIDTH)-1:0] producer_tag_i,
    input  wire [(SOURCES*PHYS_ADDR_WIDTH)-1:0] producer_phys_rd_i,
    input  wire [(SOURCES*32)-1:0]       producer_value_i,
    input  wire [(SOURCES*32)-1:0]       producer_addr_i,
    input  wire [(SOURCES*32)-1:0]       producer_branch_target_i,
    input  wire [(SOURCES*32)-1:0]       producer_store_data_i,
    input  wire [SOURCES-1:0]           producer_rd_we_i,
    input  wire [SOURCES-1:0]           producer_is_store_i,
    input  wire [SOURCES-1:0]           producer_is_branch_i,
    input  wire [SOURCES-1:0]           producer_branch_taken_i,
    input  wire [SOURCES-1:0]           producer_redirect_valid_i,
    input  wire [SOURCES-1:0]           producer_is_memory_i,
    input  wire [SOURCES-1:0]           producer_is_load_i,
    input  wire [SOURCES-1:0]           producer_target_live_i,
    input  wire                         live_tag_valid_i,
    input  wire [TAG_WIDTH-1:0]         live_tag_i,

    output reg  [BE_WIDTH-1:0]          cdb_valid_o,
    input  wire [BE_WIDTH-1:0]          cdb_ready_i,
    output reg  [(BE_WIDTH*TAG_WIDTH)-1:0] cdb_tag_o,
    output reg  [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] cdb_phys_rd_o,
    output reg  [(BE_WIDTH*32)-1:0]      cdb_value_o,
    output reg  [(BE_WIDTH*32)-1:0]      cdb_addr_o,
    output reg  [(BE_WIDTH*32)-1:0]      cdb_branch_target_o,
    output reg  [(BE_WIDTH*32)-1:0]      cdb_store_data_o,
    output reg  [BE_WIDTH-1:0]          cdb_rd_we_o,
    output reg  [BE_WIDTH-1:0]          cdb_is_store_o,
    output reg  [BE_WIDTH-1:0]          cdb_is_branch_o,
    output reg  [BE_WIDTH-1:0]          cdb_branch_taken_o,
    output reg  [BE_WIDTH-1:0]          cdb_redirect_valid_o,
    output reg  [BE_WIDTH-1:0]          cdb_is_memory_o,
    output reg  [BE_WIDTH-1:0]          cdb_is_load_o,

    output wire [BE_WIDTH-1:0]          prf_write_valid_o,
    output wire [(BE_WIDTH*TAG_WIDTH)-1:0] prf_write_tag_o,
    output wire [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] prf_write_phys_rd_o,
    output wire [(BE_WIDTH*32)-1:0]      prf_write_value_o,
    output wire [BE_WIDTH-1:0]          rob_ready_valid_o,
    output wire [(BE_WIDTH*TAG_WIDTH)-1:0] rob_ready_tag_o,
    output wire [(BE_WIDTH*32)-1:0]      rob_ready_value_o,
    output wire [BE_WIDTH-1:0]          wakeup_valid_o,
    output wire [(BE_WIDTH*TAG_WIDTH)-1:0] wakeup_tag_o,
    output wire [(BE_WIDTH*32)-1:0]      wakeup_value_o,
    output wire [FIFO_DEPTH-1:0]        entry_valid_o,
    output wire [(FIFO_DEPTH*TAG_WIDTH)-1:0] entry_tag_o,
    output wire [COUNT_WIDTH-1:0]       occupancy_o
);
    integer source;
    reg selected;
    reg [TAG_WIDTH-1:0] source_tag;

    always @* begin
        producer_ready_o = {SOURCES{1'b0}};
        cdb_valid_o = {BE_WIDTH{1'b0}};
        cdb_tag_o = {(BE_WIDTH*TAG_WIDTH){1'b0}};
        cdb_phys_rd_o = {(BE_WIDTH*PHYS_ADDR_WIDTH){1'b0}};
        cdb_value_o = {(BE_WIDTH*32){1'b0}};
        cdb_addr_o = {(BE_WIDTH*32){1'b0}};
        cdb_branch_target_o = {(BE_WIDTH*32){1'b0}};
        cdb_store_data_o = {(BE_WIDTH*32){1'b0}};
        cdb_rd_we_o = {BE_WIDTH{1'b0}};
        cdb_is_store_o = {BE_WIDTH{1'b0}};
        cdb_is_branch_o = {BE_WIDTH{1'b0}};
        cdb_branch_taken_o = {BE_WIDTH{1'b0}};
        cdb_redirect_valid_o = {BE_WIDTH{1'b0}};
        cdb_is_memory_o = {BE_WIDTH{1'b0}};
        cdb_is_load_o = {BE_WIDTH{1'b0}};
        selected = 1'b0;
        source_tag = {TAG_WIDTH{1'b0}};
        for (source = 0; source < SOURCES; source = source + 1) begin
            source_tag = producer_tag_i[(source*TAG_WIDTH) +: TAG_WIDTH];
            if (producer_valid_i[source] &&
                (!producer_target_live_i[source] ||
                 (live_tag_valid_i && source_tag != live_tag_i))) begin
                producer_ready_o[source] = !flush_i;
            end else if (!selected && producer_valid_i[source]) begin
                selected = 1'b1;
                cdb_valid_o[0] = !flush_i;
                cdb_tag_o[0 +: TAG_WIDTH] = source_tag;
                cdb_phys_rd_o[0 +: PHYS_ADDR_WIDTH] =
                    producer_phys_rd_i[(source*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH];
                cdb_value_o[0 +: 32] = producer_value_i[(source*32) +: 32];
                cdb_addr_o[0 +: 32] = producer_addr_i[(source*32) +: 32];
                cdb_branch_target_o[0 +: 32] = producer_branch_target_i[(source*32) +: 32];
                cdb_store_data_o[0 +: 32] = producer_store_data_i[(source*32) +: 32];
                cdb_rd_we_o[0] = producer_rd_we_i[source] && !producer_is_store_i[source];
                cdb_is_store_o[0] = producer_is_store_i[source];
                cdb_is_branch_o[0] = producer_is_branch_i[source];
                cdb_branch_taken_o[0] = producer_branch_taken_i[source];
                cdb_redirect_valid_o[0] = producer_redirect_valid_i[source];
                cdb_is_memory_o[0] = producer_is_memory_i[source];
                cdb_is_load_o[0] = producer_is_load_i[source];
                producer_ready_o[source] = !flush_i && cdb_ready_i[0];
            end
        end
    end

    assign prf_write_valid_o = cdb_valid_o & cdb_rd_we_o;
    assign prf_write_tag_o = cdb_tag_o;
    assign prf_write_phys_rd_o = cdb_phys_rd_o;
    assign prf_write_value_o = cdb_value_o;
    assign rob_ready_valid_o = cdb_valid_o;
    assign rob_ready_tag_o = cdb_tag_o;
    assign rob_ready_value_o = cdb_value_o;
    assign wakeup_valid_o = cdb_valid_o & cdb_rd_we_o;
    assign wakeup_tag_o = cdb_tag_o;
    assign wakeup_value_o = cdb_value_o;
    assign entry_valid_o = {FIFO_DEPTH{1'b0}};
    assign entry_tag_o = {(FIFO_DEPTH*TAG_WIDTH){1'b0}};
    assign occupancy_o = {COUNT_WIDTH{1'b0}};

    // These ports remain for interface compatibility with the queued network.
    wire unused_inputs = clk_i ^ reset_i ^ kill_valid_i ^
        (|kill_mask_i);
endmodule
