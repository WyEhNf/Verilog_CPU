`timescale 1ns/1ps
`include "rv32im_defs.vh"

// 1 KiB direct-mapped instruction cache with 16-byte lines.  Hit delivery is
// exactly three rising edges after request acceptance when not backpressured.
/* verilator lint_off UNUSEDSIGNAL */
module rv32_icache #(
    parameter integer EPOCH_WIDTH = `RV32IM_EPOCH_WIDTH,
    // Distributed/tag-first implementation used by the performance profile:
    // a hit is registered directly from the request edge and a miss allocates
    // the MSHR immediately.  Set to zero for the original three-stage SRAM
    // timing model.
    parameter integer FAST_HIT = 0
) (
    input  wire                       clk_i,
    input  wire                       reset_i,
    input  wire [EPOCH_WIDTH-1:0]     current_epoch_i,

    input  wire                       if_req_valid_i,
    output wire                       if_req_ready_o,
    input  wire [31:0]                if_req_pc_i,
    input  wire [EPOCH_WIDTH-1:0]     if_req_epoch_i,

    output wire                       if_resp_valid_o,
    input  wire                       if_resp_ready_i,
    output wire [31:0]                if_resp_pc_o,
    output wire [31:0]                if_resp_line_addr_o,
    output wire [127:0]               if_resp_line_data_o,
    output wire [EPOCH_WIDTH-1:0]     if_resp_epoch_o,
    output wire                       if_resp_error_o,

    output wire                       mem_req_valid_o,
    input  wire                       mem_req_ready_i,
    output wire [31:0]                mem_req_line_addr_o,
    output wire [7:0]                 mem_req_id_o,
    input  wire                       mem_resp_valid_i,
    output wire                       mem_resp_ready_o,
    input  wire [31:0]                mem_resp_line_addr_i,
    input  wire [127:0]               mem_resp_data_i,
    input  wire [7:0]                 mem_resp_id_i,
    input  wire                       mem_resp_error_i,

    output reg                        event_request_o,
    output reg                        event_hit_o,
    output reg                        event_miss_o,
    output reg                        event_refill_o,
    output reg                        event_stall_o
);
    reg valid_mem [0:63];
    reg [21:0] tag_mem [0:63];
    reg [127:0] data_mem [0:63];

    reg s0_valid;
    reg [31:0] s0_pc;
    reg [EPOCH_WIDTH-1:0] s0_epoch;
    reg s1_valid;
    reg [31:0] s1_pc;
    reg [EPOCH_WIDTH-1:0] s1_epoch;
    reg s1_hit;
    reg [127:0] s1_data;
    reg s2_valid;
    reg [31:0] s2_pc;
    reg [EPOCH_WIDTH-1:0] s2_epoch;
    reg s2_hit;
    reg [127:0] s2_data;

    reg resp_valid_reg;
    reg [31:0] resp_pc_reg;
    reg [31:0] resp_line_addr_reg;
    reg [127:0] resp_data_reg;
    reg [EPOCH_WIDTH-1:0] resp_epoch_reg;
    reg resp_error_reg;

    reg miss_reserved;
    reg mshr_valid;
    reg mshr_req_sent;
    reg [31:0] mshr_pc;
    reg [31:0] mshr_line_addr;
    reg [EPOCH_WIDTH-1:0] mshr_epoch;

    wire [5:0] req_index = if_req_pc_i[9:4];
    wire [21:0] req_tag = if_req_pc_i[31:10];
    wire req_lookup_hit = valid_mem[req_index] && (tag_mem[req_index] == req_tag);
    wire pipeline_empty = !s0_valid && !s1_valid && !s2_valid;
    wire resp_live = resp_valid_reg && (resp_epoch_reg == current_epoch_i);
    wire resp_slot_free = !resp_valid_reg || !resp_live || if_resp_ready_i;
    wire pipeline_advance = resp_slot_free &&
                            !(s2_valid && !s2_hit && mshr_valid);
    wire request_admissible = req_lookup_hit || (pipeline_empty && !resp_valid_reg);
    wire request_fire = if_req_valid_i && if_req_ready_o;
    wire request_is_miss = request_fire && !req_lookup_hit;
    wire refill_live = (mshr_epoch == current_epoch_i);
    wire refill_output_free = resp_slot_free || !refill_live;
    wire mem_resp_match = (mem_resp_line_addr_i == mshr_line_addr) &&
                          (mem_resp_id_i[EPOCH_WIDTH-1:0] == mshr_epoch);

    assign if_req_ready_o = (FAST_HIT != 0) ?
                            (!reset_i && !miss_reserved && resp_slot_free) :
                            (!reset_i && !miss_reserved && pipeline_advance &&
                             (!if_req_valid_i || request_admissible));
    assign if_resp_valid_o = resp_live;
    assign if_resp_pc_o = resp_pc_reg;
    assign if_resp_line_addr_o = resp_line_addr_reg;
    assign if_resp_line_data_o = resp_data_reg;
    assign if_resp_epoch_o = resp_epoch_reg;
    assign if_resp_error_o = resp_error_reg;

    assign mem_req_valid_o = mshr_valid && !mshr_req_sent;
    assign mem_req_line_addr_o = mshr_line_addr;
    assign mem_req_id_o = {{(8-EPOCH_WIDTH){1'b0}}, mshr_epoch};
    assign mem_resp_ready_o = mshr_valid && mshr_req_sent && refill_output_free;

    integer i;
    always @(posedge clk_i) begin
        if (reset_i) begin
            s0_valid <= 1'b0;
            s1_valid <= 1'b0;
            s2_valid <= 1'b0;
            resp_valid_reg <= 1'b0;
            resp_pc_reg <= 32'd0;
            resp_line_addr_reg <= 32'd0;
            resp_data_reg <= 128'd0;
            resp_epoch_reg <= {EPOCH_WIDTH{1'b0}};
            resp_error_reg <= 1'b0;
            miss_reserved <= 1'b0;
            mshr_valid <= 1'b0;
            mshr_req_sent <= 1'b0;
            mshr_pc <= 32'd0;
            mshr_line_addr <= 32'd0;
            mshr_epoch <= {EPOCH_WIDTH{1'b0}};
            event_request_o <= 1'b0;
            event_hit_o <= 1'b0;
            event_miss_o <= 1'b0;
            event_refill_o <= 1'b0;
            event_stall_o <= 1'b0;
            for (i = 0; i < 64; i = i + 1) begin
                valid_mem[i] <= 1'b0;
                tag_mem[i] <= 22'd0;
                data_mem[i] <= 128'd0;
            end
        end else begin
            event_request_o <= request_fire;
            event_hit_o <= 1'b0;
            event_miss_o <= 1'b0;
            event_refill_o <= 1'b0;
            event_stall_o <= if_req_valid_i && !if_req_ready_o;

            if (resp_slot_free)
                resp_valid_reg <= 1'b0;

            if ((FAST_HIT == 0) && request_is_miss)
                miss_reserved <= 1'b1;

            if (FAST_HIT != 0) begin
                // The small 1 KiB array is implemented as a tag-first
                // distributed lookup in this profile.  Register a hit in one
                // edge, or reserve the single miss slot without spending the
                // three legacy lookup stages.
                if (request_fire) begin
                    if (req_lookup_hit) begin
                        event_hit_o <= 1'b1;
                        if (if_req_epoch_i == current_epoch_i) begin
                            resp_valid_reg <= 1'b1;
                            resp_pc_reg <= if_req_pc_i;
                            resp_line_addr_reg <= {if_req_pc_i[31:4], 4'b0000};
                            resp_data_reg <= data_mem[req_index];
                            resp_epoch_reg <= if_req_epoch_i;
                            resp_error_reg <= 1'b0;
                        end
                    end else begin
                        event_miss_o <= 1'b1;
                        miss_reserved <= 1'b1;
                        mshr_valid <= 1'b1;
                        mshr_req_sent <= 1'b0;
                        mshr_pc <= if_req_pc_i;
                        mshr_line_addr <= {if_req_pc_i[31:4], 4'b0000};
                        mshr_epoch <= if_req_epoch_i;
                    end
                end
            end else if (pipeline_advance) begin
                if (s2_valid) begin
                    if (s2_hit) begin
                        event_hit_o <= 1'b1;
                        if (s2_epoch == current_epoch_i) begin
                            resp_valid_reg <= 1'b1;
                            resp_pc_reg <= s2_pc;
                            resp_line_addr_reg <= {s2_pc[31:4], 4'b0000};
                            resp_data_reg <= s2_data;
                            resp_epoch_reg <= s2_epoch;
                            resp_error_reg <= 1'b0;
                        end
                    end else begin
                        event_miss_o <= 1'b1;
                        mshr_valid <= 1'b1;
                        mshr_req_sent <= 1'b0;
                        mshr_pc <= s2_pc;
                        mshr_line_addr <= {s2_pc[31:4], 4'b0000};
                        mshr_epoch <= s2_epoch;
                    end
                end

                s2_valid <= s1_valid;
                s2_pc <= s1_pc;
                s2_epoch <= s1_epoch;
                s2_hit <= s1_hit;
                s2_data <= s1_data;

                s1_valid <= s0_valid;
                s1_pc <= s0_pc;
                s1_epoch <= s0_epoch;
                s1_hit <= valid_mem[s0_pc[9:4]] &&
                          (tag_mem[s0_pc[9:4]] == s0_pc[31:10]);
                s1_data <= data_mem[s0_pc[9:4]];

                s0_valid <= request_fire;
                s0_pc <= if_req_pc_i;
                s0_epoch <= if_req_epoch_i;
            end

            if (mem_req_valid_o && mem_req_ready_i)
                mshr_req_sent <= 1'b1;

            if (mem_resp_valid_i && mem_resp_ready_o) begin
                mshr_valid <= 1'b0;
                mshr_req_sent <= 1'b0;
                miss_reserved <= 1'b0;
                event_refill_o <= !mem_resp_error_i && mem_resp_match;
                if (!mem_resp_error_i && mem_resp_match) begin
                    valid_mem[mshr_line_addr[9:4]] <= 1'b1;
                    tag_mem[mshr_line_addr[9:4]] <= mshr_line_addr[31:10];
                    data_mem[mshr_line_addr[9:4]] <= mem_resp_data_i;
                end
                if (refill_live) begin
                    resp_valid_reg <= 1'b1;
                    resp_pc_reg <= mshr_pc;
                    resp_line_addr_reg <= mshr_line_addr;
                    resp_data_reg <= mem_resp_data_i;
                    resp_epoch_reg <= mshr_epoch;
                    resp_error_reg <= mem_resp_error_i || !mem_resp_match;
                end
            end
        end
    end
endmodule
/* verilator lint_on UNUSEDSIGNAL */
