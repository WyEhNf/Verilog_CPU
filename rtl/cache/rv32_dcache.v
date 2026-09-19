`timescale 1ns/1ps
`include "rv32im_defs.vh"

// 4 KiB direct-mapped write-back/write-allocate data cache. The initial
// implementation permits one outstanding miss and exposes a three-cycle hit
// pipeline. Store requests are expected only after ROB/LSQ commit.
/* verilator lint_off WIDTHEXPAND */
/* verilator lint_off WIDTHTRUNC */
/* verilator lint_off BLKSEQ */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off UNUSEDSIGNAL */
module rv32_dcache #(
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT
) (
    input  wire                     clk_i,
    input  wire                     reset_i,
    input  wire                     flush_i,

    input  wire                     dcache_req_valid_i,
    output wire                     dcache_req_ready_o,
    input  wire                     dcache_req_is_load_i,
    input  wire                     dcache_req_is_store_i,
    input  wire [31:0]              dcache_req_addr_i,
    input  wire [1:0]               dcache_req_size_i,
    input  wire                     dcache_req_unsigned_i,
    input  wire [15:0]              dcache_req_mask_i,
    input  wire [127:0]             dcache_req_wdata_i,
    input  wire [TAG_WIDTH-1:0]     dcache_req_rob_tag_i,
    input  wire [TAG_WIDTH-1:0]     dcache_req_lsq_tag_i,

    output wire                     dcache_resp_valid_o,
    input  wire                     dcache_resp_ready_i,
    output wire [TAG_WIDTH-1:0]     dcache_resp_lsq_tag_o,
    output wire [31:0]              dcache_resp_addr_o,
    output wire [127:0]             dcache_resp_line_data_o,
    output wire [31:0]              dcache_resp_word_data_o,
    output wire                     dcache_resp_line_valid_o,
    output wire                     dcache_resp_error_o,

    output wire                     dcache_store_ack_valid_o,
    input  wire                     dcache_store_ack_ready_i,
    output wire [TAG_WIDTH-1:0]     dcache_store_ack_lsq_tag_o,
    output wire                     dcache_store_ack_error_o,

    output wire                     mem_req_valid_o,
    input  wire                     mem_req_ready_i,
    output wire                     mem_req_write_o,
    output wire [31:0]              mem_req_line_addr_o,
    output wire [127:0]             mem_req_wdata_o,
    output wire [15:0]              mem_req_wmask_o,
    output wire [7:0]               mem_req_id_o,
    input  wire                     mem_resp_valid_i,
    output wire                     mem_resp_ready_o,
    input  wire [31:0]              mem_resp_line_addr_i,
    input  wire [127:0]             mem_resp_data_i,
    input  wire [7:0]               mem_resp_id_i,
    input  wire                     mem_resp_error_i,

    output reg                      event_request_o,
    output reg                      event_hit_o,
    output reg                      event_miss_o,
    output reg                      event_refill_o,
    output reg                      event_writeback_o,
    output reg                      event_stall_o
);
    reg valid_mem [0:255];
    reg dirty_mem [0:255];
    reg [19:0] tag_mem [0:255];
    reg [127:0] data_mem [0:255];

    reg s0_valid, s0_load, s0_store;
    reg [31:0] s0_addr;
    reg [1:0] s0_size;
    reg s0_unsigned;
    reg [15:0] s0_mask;
    reg [TAG_WIDTH-1:0] s0_rob;
    reg [127:0] s0_wdata;
    reg [TAG_WIDTH-1:0] s0_lsq;
    reg s1_valid, s1_load, s1_store, s1_hit;
    reg [31:0] s1_addr;
    reg [1:0] s1_size;
    reg s1_unsigned;
    reg [15:0] s1_mask;
    reg [TAG_WIDTH-1:0] s1_rob;
    reg [127:0] s1_wdata, s1_line;
    reg [TAG_WIDTH-1:0] s1_lsq;
    reg s2_valid, s2_load, s2_store, s2_hit;
    reg [31:0] s2_addr;
    reg [1:0] s2_size;
    reg s2_unsigned;
    reg [15:0] s2_mask;
    reg [TAG_WIDTH-1:0] s2_rob;
    reg [127:0] s2_wdata, s2_line;
    reg [TAG_WIDTH-1:0] s2_lsq;

    reg resp_valid_reg, resp_line_valid_reg, resp_error_reg;
    reg [TAG_WIDTH-1:0] resp_lsq_reg;
    reg [31:0] resp_addr_reg, resp_word_reg;
    reg [127:0] resp_line_reg;
    reg store_ack_valid_reg, store_ack_error_reg;
    reg [TAG_WIDTH-1:0] store_ack_lsq_reg;

    reg mshr_valid, mshr_writeback, mshr_req_sent, mshr_wait_resp;
    reg mshr_is_load, mshr_is_store, mshr_drop_response;
    reg [31:0] mshr_addr, mshr_line_addr, mshr_victim_addr;
    reg [1:0] mshr_size;
    reg mshr_unsigned;
    reg [15:0] mshr_mask;
    reg [127:0] mshr_wdata, mshr_victim_data;
    reg [TAG_WIDTH-1:0] mshr_lsq;

    wire pipeline_empty = !s0_valid && !s1_valid && !s2_valid;
    // Loads may occupy all three hit-pipeline stages concurrently.  Stores
    // remain exclusive because the stage-one SRAM read precedes the stage-two
    // merge/write; admitting a younger request beside a store would otherwise
    // need an explicit cache-line bypass network.
    wire store_in_pipeline = (s0_valid && s0_store) ||
                             (s1_valid && s1_store) ||
                             (s2_valid && s2_store);
    wire pipeline_output_blocked =
        (s2_valid && s2_load && resp_valid_reg && !dcache_resp_ready_i) ||
        (s2_valid && s2_store && store_ack_valid_reg && !dcache_store_ack_ready_i);
    wire request_fire = dcache_req_valid_i && dcache_req_ready_o;
    wire mem_req_fire = mem_req_valid_o && mem_req_ready_i;
    wire mem_resp_match = mshr_valid && mshr_wait_resp &&
                          (mem_resp_line_addr_i == (mshr_writeback ? mshr_victim_addr : mshr_line_addr)) &&
                          (mem_resp_id_i == mshr_lsq[7:0]);
    wire mem_resp_fire = mem_resp_valid_i && mem_resp_ready_o;

    assign dcache_req_ready_o = !reset_i && !flush_i && !mshr_valid &&
                                !pipeline_output_blocked && !store_in_pipeline &&
                                (!dcache_req_is_store_i || pipeline_empty);
    assign dcache_resp_valid_o = resp_valid_reg;
    assign dcache_resp_lsq_tag_o = resp_lsq_reg;
    assign dcache_resp_addr_o = resp_addr_reg;
    assign dcache_resp_line_data_o = resp_line_reg;
    assign dcache_resp_word_data_o = resp_word_reg;
    assign dcache_resp_line_valid_o = resp_line_valid_reg;
    assign dcache_resp_error_o = resp_error_reg;
    assign dcache_store_ack_valid_o = store_ack_valid_reg;
    assign dcache_store_ack_lsq_tag_o = store_ack_lsq_reg;
    assign dcache_store_ack_error_o = store_ack_error_reg;

    assign mem_req_valid_o = mshr_valid && !mshr_req_sent && !mshr_wait_resp;
    assign mem_req_write_o = mshr_writeback;
    assign mem_req_line_addr_o = mshr_writeback ? mshr_victim_addr : mshr_line_addr;
    assign mem_req_wdata_o = mshr_victim_data;
    assign mem_req_wmask_o = 16'hffff;
    assign mem_req_id_o = mshr_lsq[7:0];
    assign mem_resp_ready_o = mem_resp_match;

    function [31:0] extract_value;
        input [127:0] line_data;
        input [31:0] address;
        input [1:0] size;
        input unsigned_load;
        integer first;
        integer count;
        reg [31:0] value;
        begin
            first = address[3:0];
            case (size)
                `RV32IM_MEM_BYTE: count = 1;
                `RV32IM_MEM_HALF: count = 2;
                default: count = 4;
            endcase
            value = line_data >> (first*8);
            case (count)
                1: begin
                    if (!unsigned_load && value[7]) value = {{24{1'b1}}, value[7:0]};
                    else value = {24'd0, value[7:0]};
                end
                2: begin
                    if (!unsigned_load && value[15]) value = {{16{1'b1}}, value[15:0]};
                    else value = {16'd0, value[15:0]};
                end
                default: value = value;
            endcase
            extract_value = value;
        end
    endfunction

    function [127:0] merge_store;
        input [127:0] line_data;
        input [127:0] store_data;
        input [15:0] mask;
        integer n;
        reg [127:0] merged;
        begin
            merged = line_data;
            for (n = 0; n < 16; n = n + 1)
                if (mask[n]) merged = (merged & ~(128'hff << (n*8))) |
                                      (store_data & (128'hff << (n*8)));
            merge_store = merged;
        end
    endfunction

    integer i;
    integer idx;
    reg [127:0] merged_line;
    always @(posedge clk_i) begin
        if (reset_i) begin
            s0_valid <= 1'b0; s1_valid <= 1'b0; s2_valid <= 1'b0;
            resp_valid_reg <= 1'b0; store_ack_valid_reg <= 1'b0;
            mshr_valid <= 1'b0; mshr_req_sent <= 1'b0; mshr_wait_resp <= 1'b0;
            mshr_writeback <= 1'b0; mshr_drop_response <= 1'b0;
            event_request_o <= 1'b0; event_hit_o <= 1'b0; event_miss_o <= 1'b0;
            event_refill_o <= 1'b0; event_writeback_o <= 1'b0; event_stall_o <= 1'b0;
            for (i = 0; i < 256; i = i + 1) begin
                valid_mem[i] <= 1'b0; dirty_mem[i] <= 1'b0;
                tag_mem[i] <= 20'd0; data_mem[i] <= 128'd0;
            end
        end else begin
            event_request_o <= request_fire;
            event_hit_o <= 1'b0; event_miss_o <= 1'b0; event_refill_o <= 1'b0;
            event_writeback_o <= 1'b0;
            event_stall_o <= dcache_req_valid_i && !dcache_req_ready_o;

            if (resp_valid_reg && dcache_resp_ready_i) resp_valid_reg <= 1'b0;
            if (store_ack_valid_reg && dcache_store_ack_ready_i) store_ack_valid_reg <= 1'b0;

            if (flush_i) begin
                // A store reaches this interface only after ROB commit.  It
                // is therefore architectural and must survive a redirect;
                // speculative load state may be discarded instead.
                s0_valid <= s0_valid && s0_store;
                s1_valid <= s1_valid && s1_store;
                s2_valid <= s2_valid && s2_store;
                if (mshr_valid && mshr_is_load) mshr_drop_response <= 1'b1;
                resp_valid_reg <= 1'b0;

                // Complete a store already in the final pipeline stage even
                // on the redirect cycle.  A miss remains owned by the MSHR;
                // the normal path holds any store behind an older response.
                if (s2_valid && s2_store && !mshr_valid) begin
                    if (s2_hit) begin
                        event_hit_o <= 1'b1;
                        merged_line = merge_store(s2_line, s2_wdata, s2_mask);
                        data_mem[s2_addr[11:4]] <= merged_line;
                        dirty_mem[s2_addr[11:4]] <= 1'b1;
                        store_ack_valid_reg <= 1'b1;
                        store_ack_lsq_reg <= s2_lsq;
                        store_ack_error_reg <= 1'b0;
                        s2_valid <= 1'b0;
                    end else begin
                        event_miss_o <= 1'b1;
                        mshr_valid <= 1'b1;
                        mshr_req_sent <= 1'b0;
                        mshr_wait_resp <= 1'b0;
                        mshr_is_load <= 1'b0;
                        mshr_is_store <= 1'b1;
                        mshr_drop_response <= 1'b0;
                        mshr_addr <= s2_addr;
                        mshr_line_addr <= {s2_addr[31:4],4'b0};
                        mshr_size <= s2_size;
                        mshr_unsigned <= s2_unsigned;
                        mshr_mask <= s2_mask;
                        mshr_wdata <= s2_wdata;
                        mshr_lsq <= s2_lsq;
                        mshr_victim_addr <= {tag_mem[s2_addr[11:4]], s2_addr[11:4], 4'b0};
                        mshr_victim_data <= data_mem[s2_addr[11:4]];
                        mshr_writeback <= valid_mem[s2_addr[11:4]] && dirty_mem[s2_addr[11:4]];
                        valid_mem[s2_addr[11:4]] <= 1'b0;
                        s2_valid <= 1'b0;
                    end
                end
            end else if (mshr_valid) begin
                // A miss owns the sole refill port.  Preserve every younger
                // hit-pipeline stage and resume it after refill; dropping the
                // stages here loses requests when load hits are pipelined.
                s0_valid <= s0_valid;
                s1_valid <= s1_valid;
                s2_valid <= s2_valid;
            end else if (pipeline_output_blocked) begin
                // The response registers are elastic.  Freeze the pipeline
                // only when the relevant output cannot be replaced this edge.
                s0_valid <= s0_valid;
                s1_valid <= s1_valid;
                s2_valid <= s2_valid;
            end else begin
                s2_valid <= s1_valid;
                s2_load <= s1_load; s2_store <= s1_store; s2_hit <= s1_hit;
                s2_addr <= s1_addr; s2_size <= s1_size; s2_unsigned <= s1_unsigned;
                s2_mask <= s1_mask; s2_rob <= s1_rob; s2_wdata <= s1_wdata;
                s2_line <= s1_line; s2_lsq <= s1_lsq;
                s1_valid <= s0_valid;
                s1_load <= s0_load; s1_store <= s0_store;
                s1_addr <= s0_addr; s1_size <= s0_size; s1_unsigned <= s0_unsigned;
                s1_mask <= s0_mask; s1_rob <= s0_rob; s1_wdata <= s0_wdata; s1_lsq <= s0_lsq;
                idx = s0_addr[11:4];
                s1_hit <= valid_mem[idx] && (tag_mem[idx] == s0_addr[31:12]);
                s1_line <= data_mem[idx];
                s0_valid <= request_fire;
                if (request_fire) begin
                    s0_load <= dcache_req_is_load_i; s0_store <= dcache_req_is_store_i;
                    s0_addr <= dcache_req_addr_i; s0_size <= dcache_req_size_i;
                    s0_unsigned <= dcache_req_unsigned_i; s0_mask <= dcache_req_mask_i;
                    s0_rob <= dcache_req_rob_tag_i; s0_wdata <= dcache_req_wdata_i;
                    s0_lsq <= dcache_req_lsq_tag_i;
                end

                if (s2_valid && !mshr_valid) begin
                    if (s2_hit) begin
                        event_hit_o <= 1'b1;
                        if (s2_load) begin
                            resp_valid_reg <= 1'b1; resp_lsq_reg <= s2_lsq; resp_addr_reg <= s2_addr;
                            resp_line_reg <= s2_line; resp_word_reg <= extract_value(s2_line, s2_addr, s2_size, s2_unsigned);
                            resp_line_valid_reg <= 1'b1; resp_error_reg <= 1'b0;
                        end else if (s2_store) begin
                            merged_line = merge_store(s2_line, s2_wdata, s2_mask);
                            data_mem[s2_addr[11:4]] <= merged_line; dirty_mem[s2_addr[11:4]] <= 1'b1;
                            store_ack_valid_reg <= 1'b1; store_ack_lsq_reg <= s2_lsq; store_ack_error_reg <= 1'b0;
                        end
                    end else begin
                        event_miss_o <= 1'b1;
                        mshr_valid <= 1'b1; mshr_req_sent <= 1'b0; mshr_wait_resp <= 1'b0;
                        mshr_is_load <= s2_load; mshr_is_store <= s2_store; mshr_drop_response <= 1'b0;
                        mshr_addr <= s2_addr; mshr_line_addr <= {s2_addr[31:4],4'b0}; mshr_size <= s2_size;
                        mshr_unsigned <= s2_unsigned; mshr_mask <= s2_mask;
                        mshr_wdata <= s2_wdata; mshr_lsq <= s2_lsq;
                        mshr_victim_addr <= {tag_mem[s2_addr[11:4]], s2_addr[11:4], 4'b0};
                        mshr_victim_data <= data_mem[s2_addr[11:4]];
                        mshr_writeback <= valid_mem[s2_addr[11:4]] && dirty_mem[s2_addr[11:4]];
                        valid_mem[s2_addr[11:4]] <= 1'b0;
                    end
                end
            end

            if (mem_req_fire) begin
                mshr_req_sent <= 1'b1; mshr_wait_resp <= 1'b1;
                if (mshr_writeback) event_writeback_o <= 1'b1;
            end
            if (mem_resp_fire) begin
                mshr_req_sent <= 1'b0; mshr_wait_resp <= 1'b0;
                if (mshr_writeback) begin
                    if (mem_resp_error_i) begin
                        mshr_valid <= 1'b0;
                        if (mshr_is_load && !mshr_drop_response) begin
                            resp_valid_reg <= 1'b1; resp_lsq_reg <= mshr_lsq; resp_addr_reg <= mshr_addr;
                            resp_line_reg <= 128'd0; resp_word_reg <= 32'd0; resp_line_valid_reg <= 1'b0; resp_error_reg <= 1'b1;
                        end else if (mshr_is_store) begin
                            store_ack_valid_reg <= 1'b1; store_ack_lsq_reg <= mshr_lsq; store_ack_error_reg <= 1'b1;
                        end
                    end else begin
                        mshr_writeback <= 1'b0;
                    end
                end else begin
                    mshr_valid <= 1'b0;
                    if (!mem_resp_error_i) begin
                        event_refill_o <= 1'b1;
                        idx = mshr_line_addr[11:4];
                        data_mem[idx] <= mem_resp_data_i; tag_mem[idx] <= mshr_line_addr[31:12];
                        valid_mem[idx] <= 1'b1; dirty_mem[idx] <= 1'b0;
                        if (!mshr_drop_response) begin
                            if (mshr_is_load) begin
                                resp_valid_reg <= 1'b1; resp_lsq_reg <= mshr_lsq; resp_addr_reg <= mshr_addr;
                                resp_line_reg <= mem_resp_data_i; resp_word_reg <= extract_value(mem_resp_data_i, mshr_addr, mshr_size, mshr_unsigned);
                                resp_line_valid_reg <= 1'b1; resp_error_reg <= 1'b0;
                            end else if (mshr_is_store) begin
                                merged_line = merge_store(mem_resp_data_i, mshr_wdata, mshr_mask);
                                data_mem[idx] <= merged_line; dirty_mem[idx] <= 1'b1;
                                store_ack_valid_reg <= 1'b1; store_ack_lsq_reg <= mshr_lsq; store_ack_error_reg <= 1'b0;
                            end
                        end
                    end else if (!mshr_drop_response) begin
                        if (mshr_is_load) begin
                            resp_valid_reg <= 1'b1; resp_lsq_reg <= mshr_lsq; resp_addr_reg <= mshr_addr;
                            resp_line_reg <= 128'd0; resp_word_reg <= 32'd0; resp_line_valid_reg <= 1'b0; resp_error_reg <= 1'b1;
                        end else if (mshr_is_store) begin
                            store_ack_valid_reg <= 1'b1; store_ack_lsq_reg <= mshr_lsq; store_ack_error_reg <= 1'b1;
                        end
                    end
                end
            end
        end
    end

    initial begin
        if (TAG_WIDTH < 8) begin
            $display("ERROR: D-cache TAG_WIDTH must be at least 8");
            $finish;
        end
    end
endmodule
