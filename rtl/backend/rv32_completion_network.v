`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Completion/CDB network. Producer inputs are ordered by source index and
// accepted into a small FIFO; output lanes drain the FIFO in order. This
// keeps completion deterministic and prevents an ungranted result from being
// overwritten by a later producer.
module rv32_completion_network #(
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer SOURCES = 5,
    parameter integer FIFO_DEPTH = 16,
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT,
    parameter integer SLOT_WIDTH = (FIFO_DEPTH <= 1) ? 1 : $clog2(FIFO_DEPTH),
    parameter integer COUNT_WIDTH = (FIFO_DEPTH <= 1) ? 1 : $clog2(FIFO_DEPTH + 1)
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         flush_i,
    input  wire [SOURCES-1:0]           producer_valid_i,
    output reg  [SOURCES-1:0]           producer_ready_o,
    input  wire [(SOURCES*TAG_WIDTH)-1:0] producer_tag_i,
    input  wire [(SOURCES*PHYS_ADDR_WIDTH)-1:0] producer_phys_rd_i,
    input  wire [(SOURCES*32)-1:0]       producer_value_i,
    input  wire [(SOURCES*32)-1:0]       producer_addr_i,
    input  wire [(SOURCES*32)-1:0]       producer_branch_target_i,
    input  wire [(SOURCES*128)-1:0]      producer_store_data_i,
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
    output reg  [(BE_WIDTH*128)-1:0]     cdb_store_data_o,
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
    output wire [COUNT_WIDTH-1:0]       occupancy_o
);
    reg valid_mem [0:FIFO_DEPTH-1];
    reg [TAG_WIDTH-1:0] tag_mem [0:FIFO_DEPTH-1];
    reg [PHYS_ADDR_WIDTH-1:0] phys_mem [0:FIFO_DEPTH-1];
    reg [31:0] value_mem [0:FIFO_DEPTH-1];
    reg [31:0] addr_mem [0:FIFO_DEPTH-1];
    reg [31:0] branch_target_mem [0:FIFO_DEPTH-1];
    reg [127:0] store_data_mem [0:FIFO_DEPTH-1];
    reg rd_we_mem [0:FIFO_DEPTH-1];
    reg store_mem [0:FIFO_DEPTH-1];
    reg branch_mem [0:FIFO_DEPTH-1];
    reg branch_taken_mem [0:FIFO_DEPTH-1];
    reg redirect_mem [0:FIFO_DEPTH-1];
    reg memory_mem [0:FIFO_DEPTH-1];
    reg load_mem [0:FIFO_DEPTH-1];
    reg live_mem [0:FIFO_DEPTH-1];
    reg [SLOT_WIDTH-1:0] head_reg, tail_reg;
    reg [COUNT_WIDTH-1:0] count_reg;
    integer source;
    integer lane;
    integer slot;
    integer enq_count;
    integer pop_count;
    integer free_slots;
    integer enq_slot;
    integer pop_slot;
    reg prefix_open;
    reg [BE_WIDTH-1:0] pop_fire;
    reg [SOURCES-1:0] source_fire;
    wire [COUNT_WIDTH-1:0] occupancy_wire = count_reg;
    assign occupancy_o = occupancy_wire;

    always @* begin
        producer_ready_o = {SOURCES{1'b0}};
        source_fire = {SOURCES{1'b0}};
        prefix_open = 1'b1;
        enq_count = 0;
        free_slots = FIFO_DEPTH - count_reg;
        for (source = 0; source < SOURCES; source = source + 1) begin
            if (prefix_open && producer_valid_i[source] && producer_target_live_i[source] && (enq_count < free_slots)) begin
                producer_ready_o[source] = !flush_i;
                source_fire[source] = !flush_i;
                enq_count = enq_count + 1;
            end else if (producer_valid_i[source]) begin
                prefix_open = 1'b0;
            end
        end

        cdb_valid_o = {BE_WIDTH{1'b0}};
        cdb_tag_o = {(BE_WIDTH*TAG_WIDTH){1'b0}};
        cdb_phys_rd_o = {(BE_WIDTH*PHYS_ADDR_WIDTH){1'b0}};
        cdb_value_o = {(BE_WIDTH*32){1'b0}};
        cdb_addr_o = {(BE_WIDTH*32){1'b0}};
        cdb_branch_target_o = {(BE_WIDTH*32){1'b0}};
        cdb_store_data_o = {(BE_WIDTH*128){1'b0}};
        cdb_rd_we_o = {BE_WIDTH{1'b0}};
        cdb_is_store_o = {BE_WIDTH{1'b0}};
        cdb_is_branch_o = {BE_WIDTH{1'b0}};
        cdb_branch_taken_o = {BE_WIDTH{1'b0}};
        cdb_redirect_valid_o = {BE_WIDTH{1'b0}};
        cdb_is_memory_o = {BE_WIDTH{1'b0}};
        cdb_is_load_o = {BE_WIDTH{1'b0}};
        pop_fire = {BE_WIDTH{1'b0}};
        pop_count = 0;
        for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
            pop_slot = head_reg + pop_count;
            if (pop_slot >= FIFO_DEPTH) pop_slot = pop_slot - FIFO_DEPTH;
            if (!flush_i && valid_mem[pop_slot] && live_mem[pop_slot] &&
                (!live_tag_valid_i || tag_mem[pop_slot] == live_tag_i)) begin
                cdb_valid_o[lane] = 1'b1;
                cdb_tag_o[(lane*TAG_WIDTH) +: TAG_WIDTH] = tag_mem[pop_slot];
                cdb_phys_rd_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] = phys_mem[pop_slot];
                cdb_value_o[(lane*32) +: 32] = value_mem[pop_slot];
                cdb_addr_o[(lane*32) +: 32] = addr_mem[pop_slot];
                cdb_branch_target_o[(lane*32) +: 32] = branch_target_mem[pop_slot];
                cdb_store_data_o[(lane*128) +: 128] = store_data_mem[pop_slot];
                cdb_rd_we_o[lane] = rd_we_mem[pop_slot] && !store_mem[pop_slot];
                cdb_is_store_o[lane] = store_mem[pop_slot];
                cdb_is_branch_o[lane] = branch_mem[pop_slot];
                cdb_branch_taken_o[lane] = branch_taken_mem[pop_slot];
                cdb_redirect_valid_o[lane] = redirect_mem[pop_slot];
                cdb_is_memory_o[lane] = memory_mem[pop_slot];
                cdb_is_load_o[lane] = load_mem[pop_slot];
                if (cdb_ready_i[lane]) begin
                    pop_fire[lane] = 1'b1;
                    pop_count = pop_count + 1;
                end else begin
                    lane = BE_WIDTH;
                end
            end else if (valid_mem[pop_slot]) begin
                // Stale/invalid head entries are discarded before arbitration.
                pop_fire[lane] = 1'b1;
                pop_count = pop_count + 1;
            end
            else begin
                lane = BE_WIDTH;
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

    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            head_reg <= 0;
            tail_reg <= 0;
            count_reg <= 0;
            for (slot = 0; slot < FIFO_DEPTH; slot = slot + 1) begin
                valid_mem[slot] <= 1'b0;
                live_mem[slot] <= 1'b0;
            end
        end else begin
            for (lane = 0; lane < BE_WIDTH; lane = lane + 1) begin
                if (pop_fire[lane]) begin
                    pop_slot = head_reg + lane;
                    if (pop_slot >= FIFO_DEPTH) pop_slot = pop_slot - FIFO_DEPTH;
                    valid_mem[pop_slot] <= 1'b0;
                    live_mem[pop_slot] <= 1'b0;
                end
            end
            enq_slot = tail_reg;
            for (source = 0; source < SOURCES; source = source + 1) begin
                if (source_fire[source]) begin
                    if (enq_slot >= FIFO_DEPTH) enq_slot = enq_slot - FIFO_DEPTH;
                    valid_mem[enq_slot] <= 1'b1;
                    live_mem[enq_slot] <= producer_target_live_i[source] && producer_tag_i[(source*TAG_WIDTH)];
                    tag_mem[enq_slot] <= producer_tag_i[(source*TAG_WIDTH) +: TAG_WIDTH];
                    phys_mem[enq_slot] <= producer_phys_rd_i[(source*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH];
                    value_mem[enq_slot] <= producer_value_i[(source*32) +: 32];
                    addr_mem[enq_slot] <= producer_addr_i[(source*32) +: 32];
                    branch_target_mem[enq_slot] <= producer_branch_target_i[(source*32) +: 32];
                    store_data_mem[enq_slot] <= producer_store_data_i[(source*128) +: 128];
                    rd_we_mem[enq_slot] <= producer_rd_we_i[source];
                    store_mem[enq_slot] <= producer_is_store_i[source];
                    branch_mem[enq_slot] <= producer_is_branch_i[source];
                    branch_taken_mem[enq_slot] <= producer_branch_taken_i[source];
                    redirect_mem[enq_slot] <= producer_redirect_valid_i[source];
                    memory_mem[enq_slot] <= producer_is_memory_i[source];
                    load_mem[enq_slot] <= producer_is_load_i[source];
                    enq_slot = enq_slot + 1;
                end
            end
            head_reg <= head_reg + pop_count;
            if (head_reg + pop_count >= FIFO_DEPTH) head_reg <= head_reg + pop_count - FIFO_DEPTH;
            tail_reg <= tail_reg + enq_count;
            if (tail_reg + enq_count >= FIFO_DEPTH) tail_reg <= tail_reg + enq_count - FIFO_DEPTH;
            count_reg <= count_reg - pop_count + enq_count;
        end
    end
endmodule
