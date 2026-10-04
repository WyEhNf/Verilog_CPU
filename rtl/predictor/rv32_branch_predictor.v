`timescale 1ns/1ps
`include "rv32im_defs.vh"

// 256-entry bimodal predictor plus a 64-entry direct-mapped BTB.
// Table updates use accepted resolution feedback from the backend.
/* verilator lint_off UNUSEDSIGNAL */
module rv32_branch_predictor #(
    // A bank stores the high index bits; its caller routes low-bit ownership.
    // BANK_BITS=0 preserves the standalone full-table predictor interface.
    parameter integer BANK_BITS = 0,
    parameter integer DIRECT_BRANCH_TARGET = 0,
    parameter integer HISTORY_BITS = 6
) (
    input  wire        clk_i,
    input  wire        reset_i,

    input  wire        query_valid_i,
    input  wire [31:0] query_pc_i,
    input  wire [31:0] query_inst_i,
    input  wire [7:0]  query_history_i,
    output wire [7:0]  pred_training_index_o,
    output reg          pred_taken_o,
    output wire [31:0] pred_target_o,
    output reg  [1:0]  pred_kind_o,
    output reg          pred_btb_hit_o,
    output wire [5:0]  pred_bht_index_o,
    output wire [3:0]  pred_btb_index_o,
    output wire [1:0]  pred_counter_o,

    input  wire        feedback_valid_i,
    input  wire [31:0] feedback_pc_i,
    input  wire [1:0]  feedback_kind_i,
    input  wire        feedback_taken_i,
    input  wire [31:0] feedback_target_i,
    input  wire        feedback_pred_taken_i,
    input  wire [31:0] feedback_pred_target_i,
    input  wire [7:0]  feedback_training_index_i,

    output wire [31:0] prediction_count_o,
    output wire [31:0] correct_count_o
);
    localparam integer BHT_ENTRIES = 256 >> BANK_BITS;
    localparam integer BTB_ENTRIES = 64 >> BANK_BITS;

    wire [1:0] bht [0:BHT_ENTRIES-1];
    wire bht_trained [0:BHT_ENTRIES-1];
    wire btb_valid [0:BTB_ENTRIES-1];
    wire [23:0] btb_tag [0:BTB_ENTRIES-1];
    wire [31:0] btb_target [0:BTB_ENTRIES-1];
    wire [1:0] btb_kind [0:BTB_ENTRIES-1];
    localparam integer BHT_DOMAINS=(BHT_ENTRIES+3)/4;
    localparam integer BTB_DOMAINS=(BTB_ENTRIES+3)/4;
    localparam integer BHT_INDEX_WIDTH=8-BANK_BITS;
    localparam integer BTB_INDEX_WIDTH=6-BANK_BITS;
    wire [BHT_ENTRIES*3-1:0] bht_rows;
    wire [BTB_ENTRIES*59-1:0] btb_rows;
    wire [2:0] query_bht_word;
    wire [58:0] query_btb_word;
    wire [BHT_DOMAINS*BHT_INDEX_WIDTH-1:0] bht_write_queries;
    wire [BHT_DOMAINS-1:0] bht_write_events,bht_directions;
    wire [BTB_DOMAINS*BTB_INDEX_WIDTH-1:0] btb_write_queries;
    wire [BTB_DOMAINS*58-1:0] btb_write_payloads;
    wire [BTB_DOMAINS-1:0] btb_write_events;
    wire [BHT_ENTRIES+BTB_ENTRIES+4-1:0] reset_views;
    rv32_frequency_control_tree #(.LEAVES(BHT_ENTRIES+BTB_ENTRIES+4)) reset_tree (
        .signal_i(reset_i),.views_o(reset_views));
    rv32_frequency_control_tree #(.WIDTH(BHT_INDEX_WIDTH),.LEAVES(BHT_DOMAINS)) bht_address_tree (
        .signal_i(feedback_bht_index),.views_o(bht_write_queries));
    rv32_frequency_control_tree #(.LEAVES(BHT_DOMAINS)) bht_event_tree (
        .signal_i(feedback_valid_i && feedback_kind_i==`RV32IM_PRED_BRANCH),.views_o(bht_write_events));
    rv32_frequency_control_tree #(.LEAVES(BHT_DOMAINS)) bht_direction_tree (
        .signal_i(feedback_taken_i),.views_o(bht_directions));
    rv32_frequency_control_tree #(.WIDTH(BTB_INDEX_WIDTH),.LEAVES(BTB_DOMAINS)) btb_address_tree (
        .signal_i(feedback_btb_index),.views_o(btb_write_queries));
    rv32_frequency_control_tree #(.LEAVES(BTB_DOMAINS)) btb_event_tree (
        .signal_i(feedback_btb_write),.views_o(btb_write_events));
    rv32_frequency_control_tree #(.WIDTH(58),.LEAVES(BTB_DOMAINS)) btb_payload_tree (
        .signal_i({feedback_pc_i[31:8],feedback_btb_target,feedback_kind_i}),.views_o(btb_write_payloads));
    genvar predictor_row;
    generate
        for(predictor_row=0;predictor_row<BHT_ENTRIES;predictor_row=predictor_row+1) begin:g_bht_owner
            localparam integer DOMAIN=predictor_row/4;
            wire update=bht_write_events[DOMAIN] &&
                bht_write_queries[DOMAIN*BHT_INDEX_WIDTH +: BHT_INDEX_WIDTH]==predictor_row;
            rv32_predictor_bht_row row (
                .clk_i(clk_i),.reset_i(reset_views[predictor_row]),.update_i(update),
                .taken_i(bht_directions[DOMAIN]),.counter_o(bht[predictor_row]),.trained_o(bht_trained[predictor_row]));
            assign bht_rows[predictor_row*3 +: 3]={bht_trained[predictor_row],bht[predictor_row]};
        end
        for(predictor_row=0;predictor_row<BTB_ENTRIES;predictor_row=predictor_row+1) begin:g_btb_owner
            localparam integer DOMAIN=predictor_row/4;
            wire update=btb_write_events[DOMAIN] &&
                btb_write_queries[DOMAIN*BTB_INDEX_WIDTH +: BTB_INDEX_WIDTH]==predictor_row;
            rv32_predictor_btb_row row (
                .clk_i(clk_i),.reset_i(reset_views[BHT_ENTRIES+predictor_row]),.update_i(update),
                .payload_i(btb_write_payloads[DOMAIN*58 +: 58]),.valid_o(btb_valid[predictor_row]),
                .tag_o(btb_tag[predictor_row]),.target_o(btb_target[predictor_row]),.kind_o(btb_kind[predictor_row]));
            assign btb_rows[predictor_row*59 +: 59]={btb_valid[predictor_row],btb_tag[predictor_row],btb_target[predictor_row],btb_kind[predictor_row]};
        end
    endgenerate
    rv32_frequency_array_read #(.WIDTH(3),.ENTRIES(BHT_ENTRIES),.INDEX_WIDTH(BHT_INDEX_WIDTH)) bht_query (
        .rows_i(bht_rows),.index_i(query_bht_index),.value_o(query_bht_word));
    rv32_frequency_array_read #(.WIDTH(59),.ENTRIES(BTB_ENTRIES),.INDEX_WIDTH(BTB_INDEX_WIDTH)) btb_query (
        .rows_i(btb_rows),.index_i(query_btb_index),.value_o(query_btb_word));

    wire [6:0] query_opcode = query_inst_i[6:0];
    localparam [7:0] HISTORY_MASK = (1 << HISTORY_BITS) - 1;
    wire [7:0] query_full_index = query_pc_i[9:2] ^
        ((DIRECT_BRANCH_TARGET == 2) ? ((query_history_i & HISTORY_MASK) << BANK_BITS) : 8'b0);
    wire [7-BANK_BITS:0] query_bht_index = query_full_index[7:BANK_BITS];
    assign pred_training_index_o = query_full_index;
    wire [5-BANK_BITS:0] query_btb_index = query_pc_i[7:2+BANK_BITS];
    wire query_btb_match = query_btb_word[58] &&
                           (query_btb_word[57:34] == query_pc_i[31:8]);
    wire [31:0] jal_imm = {{11{query_inst_i[31]}}, query_inst_i[31],
                           query_inst_i[19:12], query_inst_i[20],
                           query_inst_i[30:21], 1'b0};
    wire [31:0] branch_imm = {{19{query_inst_i[31]}}, query_inst_i[31],
                              query_inst_i[7], query_inst_i[30:25],
                              query_inst_i[11:8], 1'b0};
    wire [7-BANK_BITS:0] feedback_bht_index = (DIRECT_BRANCH_TARGET == 2) ?
        feedback_training_index_i[7:BANK_BITS] : feedback_pc_i[9:2+BANK_BITS];
    wire [5-BANK_BITS:0] feedback_btb_index = feedback_pc_i[7:2+BANK_BITS];
    wire feedback_btb_write = feedback_valid_i && feedback_taken_i &&
                             (((DIRECT_BRANCH_TARGET == 0) &&
                               (feedback_kind_i == `RV32IM_PRED_BRANCH)) ||
                              (feedback_kind_i == `RV32IM_PRED_JALR));
    wire [31:0] feedback_btb_target = (feedback_kind_i == `RV32IM_PRED_JALR) ?
                                    {feedback_target_i[31:1], 1'b0} : feedback_target_i;
    integer i;

    assign pred_bht_index_o = query_pc_i[7:2];
    assign pred_btb_index_o = query_pc_i[5:2];
    assign pred_counter_o = query_bht_word[1:0];

    always @* begin
        pred_taken_o = 1'b0;
        pred_kind_o = `RV32IM_PRED_NONE;
        pred_btb_hit_o = 1'b0;

        if (query_valid_i) begin
            case (query_opcode)
                7'b1100011: begin
                    pred_kind_o = `RV32IM_PRED_BRANCH;
                    pred_btb_hit_o = query_btb_match &&
                                     (query_btb_word[1:0] == `RV32IM_PRED_BRANCH);
                    if (DIRECT_BRANCH_TARGET != 0) begin
                        // RV32 conditional targets are PC+decoded immediate;
                        // a BTB miss/alias must not discard a trained direction.
                        // Keep BTFNT on a cold BHT row, but after training use
                        // its counter regardless of indirect-target residency.
                        if (query_bht_word[2] ? query_bht_word[1] : branch_imm[31]) begin
                            pred_taken_o = 1'b1;
                        end
                    end else if (query_bht_word[1] && pred_btb_hit_o) begin
                        pred_taken_o = 1'b1;
                    end else if (!pred_btb_hit_o && branch_imm[31]) begin
                        // Backward-taken/forward-not-taken gives a cold loop a
                        // useful target before its first BTB allocation.
                        pred_taken_o = 1'b1;
                    end
                end
                7'b1101111: begin
                    pred_kind_o = `RV32IM_PRED_JAL;
                    pred_taken_o = 1'b1;
                end
                7'b1100111: begin
                    if (query_inst_i[14:12] == 3'b000) begin
                        pred_kind_o = `RV32IM_PRED_JALR;
                        pred_btb_hit_o = query_btb_match &&
                                         (query_btb_word[1:0] == `RV32IM_PRED_JALR);
                        if (pred_btb_hit_o) begin
                            pred_taken_o = 1'b1;
                        end
                    end
                end
                default: begin end
            endcase
        end
    end



    wire [3:0] target_classes;
    wire [127:0] target_values;
    wire [31:0] default_next_pc=query_pc_i+32'd4;
    wire [31:0] direct_branch_pc=query_pc_i+branch_imm;
    wire [31:0] direct_jal_pc=query_pc_i+jal_imm;
    assign target_classes[0]=!pred_taken_o;
    assign target_classes[1]=pred_taken_o && pred_kind_o==`RV32IM_PRED_BRANCH &&
        ((DIRECT_BRANCH_TARGET!=0) || !pred_btb_hit_o);
    assign target_classes[2]=pred_taken_o && pred_kind_o==`RV32IM_PRED_JAL;
    assign target_classes[3]=pred_taken_o &&
        (pred_kind_o==`RV32IM_PRED_JALR ||
         (pred_kind_o==`RV32IM_PRED_BRANCH && DIRECT_BRANCH_TARGET==0 && pred_btb_hit_o));
    assign target_values={query_btb_word[33:2],direct_jal_pc,direct_branch_pc,default_next_pc};
    // The four legal target classes are exhaustive and mutually exclusive.
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(4),.PRIORITY(0)) target_selector (
        .events_i(target_classes),.values_i(target_values),.write_o(),.value_o(pred_target_o));

    wire prediction_write=reset_i || feedback_valid_i;
    wire correct_event=feedback_valid_i && (feedback_pred_taken_i==feedback_taken_i) &&
        (!feedback_taken_i || feedback_pred_target_i==feedback_target_i);
    wire correct_write=reset_i || correct_event;
    wire [31:0] prediction_increment=prediction_count_o+32'd1;
    wire [31:0] correct_increment=correct_count_o+32'd1;
    wire [31:0] prediction_next,correct_next;
    genvar counter_word;
    generate for(counter_word=0;counter_word<2;counter_word=counter_word+1) begin:g_counter_word
        assign prediction_next[counter_word*16 +: 16]=reset_views[BHT_ENTRIES+BTB_ENTRIES+counter_word] ?
            16'b0 : prediction_increment[counter_word*16 +: 16];
        assign correct_next[counter_word*16 +: 16]=reset_views[BHT_ENTRIES+BTB_ENTRIES+2+counter_word] ?
            16'b0 : correct_increment[counter_word*16 +: 16];
    end endgenerate
    rv32_frequency_word_bank #(.WIDTH(32)) prediction_count_owner (
        .clk_i(clk_i),.write_i(prediction_write),.data_i(prediction_next),.data_o(prediction_count_o));
    rv32_frequency_word_bank #(.WIDTH(32)) correct_count_owner (
        .clk_i(clk_i),.write_i(correct_write),.data_i(correct_next),.data_o(correct_count_o));

endmodule
/* verilator lint_on UNUSEDSIGNAL */


// Saturating direction counter preserves weakly-taken reset and first
// training behavior. Every row owns three reset/update state bits.
module rv32_predictor_bht_row (
    input wire clk_i,reset_i,update_i,taken_i,
    output reg [1:0] counter_o,
    output reg trained_o
);
    always @(posedge clk_i) begin
        if(reset_i) begin counter_o<=2'b10;trained_o<=0;end
        else if(update_i) begin
            trained_o<=1;
            if(taken_i) begin
                if(counter_o!=2'b11) counter_o<=counter_o+2'b01;
            end else if(counter_o!=2'b00) counter_o<=counter_o-2'b01;
        end
    end
endmodule

// BTB payload is meaningful only while valid and tag/kind match. Reset
// invalidates it; the original single accepted feedback owns every write.
module rv32_predictor_btb_row (
    input wire clk_i,reset_i,update_i,
    input wire [57:0] payload_i,
    output reg valid_o,
    output wire [23:0] tag_o,
    output wire [31:0] target_o,
    output wire [1:0] kind_o
);
    wire [57:0] payload;
    rv32_frequency_word_bank #(.WIDTH(58)) payload_owner (
        .clk_i(clk_i),.write_i(!reset_i && update_i),.data_i(payload_i),.data_o(payload));
    assign {tag_o,target_o,kind_o}=payload;
    always @(posedge clk_i) begin
        if(reset_i) valid_o<=0;
        else if(update_i) valid_o<=1;
    end
endmodule
