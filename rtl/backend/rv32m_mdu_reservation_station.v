`timescale 1ns/1ps
`include "rv32im_defs.vh"

// One-entry MDU reservation station.  It holds a tagged multiply/divide
// issue packet until the selected unit accepts it, while the units retain
// their own in-flight and completion state.
module rv32m_mdu_reservation_station #(
    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT,
    parameter integer MUL_IMPL = 0,
    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT,
    parameter integer SELECTIVE_RECOVERY = 0,
    parameter RECOVERY_OLDER_ISSUE = 0,
    parameter ISSUE_RECOVERY_PREDECODE = 0,
    parameter integer RECOVERY_WIDTH = 1+2*((ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES))+$clog2(ROB_ENTRIES+1)
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         flush_i,
    input  wire [RECOVERY_WIDTH-1:0]    recovery_packet_i,
    input  wire                         issue_valid_i,
    input  wire                         issue_cancel_i,
    output wire                         issue_ready_o,
    input  wire [`RV32IM_OP_WIDTH-1:0]  issue_op_i,
    input  wire [31:0]                  issue_src1_i,
    input  wire [31:0]                  issue_src2_i,
    input  wire [TAG_WIDTH-1:0]         issue_rob_tag_i,
    input  wire [PHYS_ADDR_WIDTH-1:0]   issue_phys_rd_i,
    input  wire                         issue_target_live_i,
    output wire                         completion_valid_o,
    input  wire                         completion_ready_i,
    output wire [31:0]                  completion_value_o,
    output wire [TAG_WIDTH-1:0]         completion_rob_tag_o,
    output wire [PHYS_ADDR_WIDTH-1:0]   completion_phys_rd_o,
    output wire                         completion_rd_we_o,
    output wire                         busy_o,
    input  wire                         live_tag_valid_i,
    input  wire [TAG_WIDTH-1:0]         live_tag_i
);
    reg pending_valid;
    wire [`RV32IM_OP_WIDTH-1:0] pending_op;
    wire [31:0] pending_src1, pending_src2;
    wire [TAG_WIDTH-1:0] pending_tag;
    wire [PHYS_ADDR_WIDTH-1:0] pending_phys;
    wire pending_live;
    wire [2:0] inflight_count;
    wire mul_occupied,div_occupied;
    wire [3*RECOVERY_WIDTH-1:0] recovery_views;
    wire unused_recovery_views_bits = &{1'b0, recovery_views};

    rv32_frequency_control_tree #(.WIDTH(RECOVERY_WIDTH),.LEAVES(3)) recovery_tree (
        .signal_i(recovery_packet_i),.views_o(recovery_views));
    wire pending_cancel;
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(0)) pending_cancel_guard (
        .packet_i(recovery_views[0 +: RECOVERY_WIDTH]),.active_i(pending_valid),.tag_i(pending_tag),.cancel_o(pending_cancel));

    wire issue_is_mul = (issue_op_i == `RV32IM_OP_MUL) || (issue_op_i == `RV32IM_OP_MULH) ||
        (issue_op_i == `RV32IM_OP_MULHSU) || (issue_op_i == `RV32IM_OP_MULHU);
    wire issue_is_div = (issue_op_i == `RV32IM_OP_DIV) || (issue_op_i == `RV32IM_OP_DIVU) ||
        (issue_op_i == `RV32IM_OP_REM) || (issue_op_i == `RV32IM_OP_REMU);
    wire mul_req_valid = pending_valid && !pending_cancel && ((pending_op == `RV32IM_OP_MUL) || (pending_op == `RV32IM_OP_MULH) ||
        (pending_op == `RV32IM_OP_MULHSU) || (pending_op == `RV32IM_OP_MULHU));
    wire div_req_valid = pending_valid && !pending_cancel && ((pending_op == `RV32IM_OP_DIV) || (pending_op == `RV32IM_OP_DIVU) ||
        (pending_op == `RV32IM_OP_REM) || (pending_op == `RV32IM_OP_REMU));
    wire mul_req_ready, div_req_ready;
    wire mul_resp_valid, div_resp_valid;
    wire [31:0] mul_resp_value, div_resp_value;
    wire [TAG_WIDTH-1:0] mul_resp_tag, div_resp_tag;
    wire [PHYS_ADDR_WIDTH-1:0] mul_resp_phys, div_resp_phys;
    wire mul_resp_rd_we, div_resp_rd_we;
    wire mul_resp_ready = completion_ready_i;
    wire div_resp_ready = completion_ready_i && !mul_resp_valid;
    wire unused_div_resp_ready_bits = &{1'b0, div_resp_ready};

    wire unit_req_fire = (mul_req_valid && mul_req_ready) ||
                         (div_req_valid && div_req_ready);
    wire completion_fire = completion_valid_o && completion_ready_i;
    wire unused_completion_fire_bits = &{1'b0, completion_fire};

    // Refill the one-entry launch buffer on the same edge that the current
    // request enters its execution unit.  The pipelined Wallace multiplier
    // can therefore sustain one request per cycle instead of one every two.
    wire issue_cancel;
    generate if(ISSUE_RECOVERY_PREDECODE!=0 && SELECTIVE_RECOVERY!=0) begin:g_predecoded_issue_cancel
        // The caller carries the same registered-packet age predicate with
        // the selected payload. Qualify it with this unit's actual valid.
        assign issue_cancel=issue_valid_i && issue_cancel_i;
    end else begin:g_original_issue_cancel
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH(1)) issue_cancel_guard (
        .packet_i(recovery_views[0 +: RECOVERY_WIDTH]),
        .active_i(issue_valid_i),.tag_i(issue_rob_tag_i),.cancel_o(issue_cancel));
    end endgenerate
    assign issue_ready_o = !flush_i &&
                           (!(SELECTIVE_RECOVERY != 0) || !recovery_packet_i[RECOVERY_WIDTH-1] ||
                            ((RECOVERY_OLDER_ISSUE!=0) && !issue_cancel)) &&
                           (!pending_valid || unit_req_fire ||
                            ((RECOVERY_OLDER_ISSUE!=0) && pending_cancel)) &&
                           (issue_is_mul || issue_is_div);
    assign completion_valid_o = mul_resp_valid || div_resp_valid;
    localparam integer COMPLETION_PAYLOAD_WIDTH=33+TAG_WIDTH+PHYS_ADDR_WIDTH;
    localparam integer COMPLETION_WORDS=(COMPLETION_PAYLOAD_WIDTH+15)/16;
    wire [COMPLETION_PAYLOAD_WIDTH-1:0] mul_payload,div_payload,completion_payload;
    wire [COMPLETION_WORDS-1:0] completion_source_views;
    assign mul_payload={mul_resp_value,mul_resp_tag,mul_resp_phys,mul_resp_rd_we};
    assign div_payload={div_resp_value,div_resp_tag,div_resp_phys,div_resp_rd_we};
    assign {completion_value_o,completion_rob_tag_o,completion_phys_rd_o,completion_rd_we_o}=completion_payload;
    rv32_frequency_control_tree #(.LEAVES(COMPLETION_WORDS)) completion_source_tree (
        .signal_i(mul_resp_valid),.views_o(completion_source_views));
    generate for(genvar completion_word=0;completion_word<COMPLETION_WORDS;completion_word=completion_word+1) begin:g_completion_word
        localparam integer LOW=completion_word*16;
        localparam integer BITS=(COMPLETION_PAYLOAD_WIDTH-LOW>=16)?16:COMPLETION_PAYLOAD_WIDTH-LOW;
        assign completion_payload[LOW +: BITS]=completion_source_views[completion_word]?
            mul_payload[LOW +: BITS]:div_payload[LOW +: BITS];
    end endgenerate
    // Selectively canceled requests do not produce fake completions.
    // Their physical stage occupancy is the authority for the busy counter.
    assign busy_o = pending_valid || ((SELECTIVE_RECOVERY != 0) ?
        (mul_occupied || div_occupied) : (inflight_count != 0));

    generate
        if (MUL_IMPL == 0) begin : gen_wallace_multiplier
            rv32m_multiplier #(.TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PHYS_ADDR_WIDTH), .ROB_ENTRIES(ROB_ENTRIES), .SELECTIVE_RECOVERY(SELECTIVE_RECOVERY)) multiplier (
                .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .recovery_packet_i(recovery_views[1*RECOVERY_WIDTH +: RECOVERY_WIDTH]), .occupied_o(mul_occupied), .req_valid_i(mul_req_valid), .req_ready_o(mul_req_ready),
                .req_op_i(pending_op), .req_src1_i(pending_src1), .req_src2_i(pending_src2), .req_rob_tag_i(pending_tag), .req_phys_rd_i(pending_phys), .req_target_live_i(pending_live),
                .resp_valid_o(mul_resp_valid), .resp_ready_i(mul_resp_ready), .resp_value_o(mul_resp_value), .resp_rob_tag_o(mul_resp_tag), .resp_phys_rd_o(mul_resp_phys), .resp_rd_we_o(mul_resp_rd_we), .live_tag_valid_i(live_tag_valid_i), .live_tag_i(live_tag_i)
            );
        end else if (MUL_IMPL == 1) begin : gen_radix4_multiplier
            rv32m_multiplier_radix4 #(.TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PHYS_ADDR_WIDTH), .ROB_ENTRIES(ROB_ENTRIES), .SELECTIVE_RECOVERY(SELECTIVE_RECOVERY)) multiplier (
                .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .recovery_packet_i(recovery_views[1*RECOVERY_WIDTH +: RECOVERY_WIDTH]), .occupied_o(mul_occupied), .req_valid_i(mul_req_valid), .req_ready_o(mul_req_ready),
                .req_op_i(pending_op), .req_src1_i(pending_src1), .req_src2_i(pending_src2), .req_rob_tag_i(pending_tag), .req_phys_rd_i(pending_phys), .req_target_live_i(pending_live),
                .resp_valid_o(mul_resp_valid), .resp_ready_i(mul_resp_ready), .resp_value_o(mul_resp_value), .resp_rob_tag_o(mul_resp_tag), .resp_phys_rd_o(mul_resp_phys), .resp_rd_we_o(mul_resp_rd_we), .live_tag_valid_i(live_tag_valid_i), .live_tag_i(live_tag_i)
            );
        end else begin : gen_unified_mdu
            rv32m_mdu_iterative #(.TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PHYS_ADDR_WIDTH), .ROB_ENTRIES(ROB_ENTRIES), .SELECTIVE_RECOVERY(SELECTIVE_RECOVERY)) unified (
                .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .recovery_packet_i(recovery_views[1*RECOVERY_WIDTH +: RECOVERY_WIDTH]), .occupied_o(mul_occupied),
                .req_valid_i(pending_valid && !pending_cancel), .req_ready_o(mul_req_ready),
                .req_op_i(pending_op), .req_src1_i(pending_src1), .req_src2_i(pending_src2),
                .req_rob_tag_i(pending_tag), .req_phys_rd_i(pending_phys),
                .req_target_live_i(pending_live), .resp_valid_o(mul_resp_valid),
                .resp_ready_i(mul_resp_ready), .resp_value_o(mul_resp_value),
                .resp_rob_tag_o(mul_resp_tag), .resp_phys_rd_o(mul_resp_phys),
                .resp_rd_we_o(mul_resp_rd_we), .live_tag_valid_i(live_tag_valid_i),
                .live_tag_i(live_tag_i)
            );
            assign div_req_ready = mul_req_ready;
            assign div_resp_valid = 1'b0;
            assign div_resp_value = 32'b0;
            assign div_resp_tag = {TAG_WIDTH{1'b0}};
            assign div_resp_phys = {PHYS_ADDR_WIDTH{1'b0}};
            assign div_resp_rd_we = 1'b0;
            assign div_occupied = 1'b0;
        end
    endgenerate
    generate
    if (MUL_IMPL < 2) begin : gen_divider
    rv32m_divider #(.TAG_WIDTH(TAG_WIDTH), .PHYS_ADDR_WIDTH(PHYS_ADDR_WIDTH), .ROB_ENTRIES(ROB_ENTRIES), .SELECTIVE_RECOVERY(SELECTIVE_RECOVERY)) divider (
        .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .recovery_packet_i(recovery_views[2*RECOVERY_WIDTH +: RECOVERY_WIDTH]), .occupied_o(div_occupied), .req_valid_i(div_req_valid), .req_ready_o(div_req_ready),
        .req_op_i(pending_op), .req_src1_i(pending_src1), .req_src2_i(pending_src2), .req_rob_tag_i(pending_tag), .req_phys_rd_i(pending_phys), .req_target_live_i(pending_live),
        .resp_valid_o(div_resp_valid), .resp_ready_i(div_resp_ready), .resp_value_o(div_resp_value), .resp_rob_tag_o(div_resp_tag), .resp_phys_rd_o(div_resp_phys), .resp_rd_we_o(div_resp_rd_we), .live_tag_valid_i(live_tag_valid_i), .live_tag_i(live_tag_i)
    );
    end
    endgenerate

    // The existing one-entry buffer refills on the original issue edge.
    // Clear and capture are mutually exclusive, with payload reset retained.
    localparam integer LAUNCH_PAYLOAD_WIDTH=`RV32IM_OP_WIDTH+65+TAG_WIDTH+PHYS_ADDR_WIDTH;
    wire launch_clear=reset_i || flush_i;
    wire launch_capture=!launch_clear && issue_valid_i && issue_ready_o;
    wire launch_write;
    wire [LAUNCH_PAYLOAD_WIDTH-1:0] launch_next,launch_payload;
    assign {pending_op,pending_src1,pending_src2,pending_tag,pending_phys,pending_live}=launch_payload;
    rv32_frequency_event_select #(.WIDTH(LAUNCH_PAYLOAD_WIDTH),.EVENTS(2),.PRIORITY(0)) launch_selector (
        .events_i({launch_clear,launch_capture}),
        .values_i({{LAUNCH_PAYLOAD_WIDTH{1'b0}},
                   {issue_op_i,issue_src1_i,issue_src2_i,issue_rob_tag_i,issue_phys_rd_i,issue_target_live_i}}),
        .write_o(launch_write),.value_o(launch_next));
    rv32_frequency_word_bank #(.WIDTH(LAUNCH_PAYLOAD_WIDTH)) launch_owner (
        .clk_i(clk_i),.write_i(launch_write),.data_i(launch_next),.data_o(launch_payload));

    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            pending_valid <= 1'b0;

        end else begin
            if (pending_cancel || (pending_valid && ((mul_req_valid && mul_req_ready) || (div_req_valid && div_req_ready))))
                pending_valid <= 1'b0;
            if (issue_valid_i && issue_ready_o) begin
                pending_valid <= 1'b1;

            end

        end
    end
    generate if(SELECTIVE_RECOVERY==0) begin:g_legacy_busy_count
        reg [2:0] count;
        assign inflight_count=count;
        always @(posedge clk_i) begin
            if(reset_i || flush_i) count<=0;
            else case({unit_req_fire,completion_fire})
                2'b10: count<=count+1'b1;
                2'b01: count<=count-1'b1;
                default: count<=count;
            endcase
        end
    end else begin:g_owned_busy
        assign inflight_count=3'b0;
    end endgenerate
endmodule
