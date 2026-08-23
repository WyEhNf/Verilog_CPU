`timescale 1ns/1ps
`include "rv32im_defs.vh"

module rv32im_defs_tb;
    reg [31:0] pc;
    reg [31:0] inst;
    reg        pred_taken;
    reg [31:0] pred_target;
    reg [1:0]  pred_kind;
    reg        btb_hit;
    reg [3:0]  epoch;
    reg [`RV32IM_FETCH_PACKET_WIDTH-1:0] packed_fetch;
    reg [`RV32IM_ROB_TAG_WIDTH_DEFAULT-1:0] tag_a;
    reg [`RV32IM_ROB_TAG_WIDTH_DEFAULT-1:0] tag_b;
    wire tag_lhs_live;
    wire tag_rhs_live;
    wire tag_match;

    rv32im_tag_compare tag_compare (
        .lhs_i(tag_a), .rhs_i(tag_b),
        .lhs_live_o(tag_lhs_live), .rhs_live_o(tag_rhs_live), .match_o(tag_match)
    );

    initial begin
        pc = 32'h00001000;
        inst = 32'h00c58533;
        pred_taken = 1'b1;
        pred_target = 32'h00002000;
        pred_kind = `RV32IM_PRED_BRANCH;
        btb_hit = 1'b1;
        epoch = 4'h9;
        packed_fetch = `RV32IM_FETCH_PACKET_PACK(pc, inst, pred_taken, pred_target, pred_kind, btb_hit, epoch);
        if (packed_fetch !== {epoch, btb_hit, pred_kind, pred_target, pred_taken, inst, pc}) begin
            $display("FAIL: FetchPacket pack order");
            $finish(1);
        end

        tag_a = `RV32IM_ROB_TAG_PACK(1'b1, 2'd2, 5'd17, 8'ha5);
        tag_b = `RV32IM_ROB_TAG_PACK(1'b1, 2'd2, 5'd17, 8'ha5);
        #1;
        if (!tag_lhs_live || !tag_rhs_live || !tag_match) begin
            $display("FAIL: live ROB tag comparison");
            $finish(1);
        end
        tag_b = `RV32IM_ROB_TAG_PACK(1'b1, 2'd2, 5'd17, 8'ha6);
        #1;
        if (tag_match) begin
            $display("FAIL: stale generation was accepted");
            $finish(1);
        end
        tag_b = `RV32IM_ROB_TAG_PACK(1'b0, 2'd2, 5'd17, 8'ha5);
        #1;
        if (tag_match || tag_rhs_live) begin
            $display("FAIL: invalid tag was accepted");
            $finish(1);
        end
        if (`RV32IM_PRIORITY_HALT_ERROR <= `RV32IM_PRIORITY_FLUSH ||
            `RV32IM_PRIORITY_FLUSH <= `RV32IM_PRIORITY_REDIRECT ||
            `RV32IM_PRIORITY_REDIRECT <= `RV32IM_PRIORITY_WRITEBACK ||
            `RV32IM_PRIORITY_WRITEBACK <= `RV32IM_PRIORITY_COMMIT ||
            `RV32IM_PRIORITY_COMMIT <= `RV32IM_PRIORITY_STORE_VISIBILITY) begin
            $display("FAIL: control priority ordering");
            $finish(1);
        end
        $display("PASS: H-01/S-01 definitions, packet order, tag generation, and priority");
        $finish(0);
    end
endmodule
