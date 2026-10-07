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
    parameter integer COMPACT_INDIRECT_BTB = 0,
    parameter integer COMPACT_BTB_ENTRIES = 64,
    parameter HYBRID_DIRECTION = 0,
    // Optional candidate-target contract: a conditional direct target can be
    // meaningful even when not taken. Caller selects it only when taken, and
    // omits unused direct targets from saved resolution metadata.
    parameter DIRECTION_INDEPENDENT_TARGET = 0,
    parameter integer NARROW_DIRECTION_READ = 0,
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
    output wire [1:0]  pred_component_directions_o,

    input  wire        feedback_valid_i,
    input  wire [31:0] feedback_pc_i,
    input  wire [1:0]  feedback_kind_i,
    input  wire        feedback_taken_i,
    input  wire [31:0] feedback_target_i,
    input  wire        feedback_pred_taken_i,
    input  wire [31:0] feedback_pred_target_i,
    input  wire [7:0]  feedback_training_index_i,
    input  wire [1:0]  feedback_component_directions_i,

    output wire [31:0] prediction_count_o,
    output wire [31:0] correct_count_o
);
    localparam integer BHT_ENTRIES = 256 >> BANK_BITS;
    // Two high metadata bits are available only with <=6 history bits.
    // Other modes retain the original predictor and full history encoding.
    localparam HYBRID_ACTIVE=(HYBRID_DIRECTION!=0) &&
        (DIRECT_BRANCH_TARGET==2) && (HISTORY_BITS<=6);
    localparam BTB_COMPACT_ACTIVE=(COMPACT_INDIRECT_BTB!=0) && (DIRECT_BRANCH_TARGET!=0);
    localparam integer BTB_TOTAL_ENTRIES=BTB_COMPACT_ACTIVE?COMPACT_BTB_ENTRIES:64;
    localparam integer BTB_ENTRIES=BTB_TOTAL_ENTRIES >> BANK_BITS;
    localparam integer BTB_TOTAL_INDEX_WIDTH=$clog2(BTB_TOTAL_ENTRIES);
    initial begin
        if(COMPACT_BTB_ENTRIES!=16 && COMPACT_BTB_ENTRIES!=32 && COMPACT_BTB_ENTRIES!=64)
            $fatal(1,"Compact BTB entries must be16/32/64");
    end
    localparam integer BTB_PAYLOAD_WIDTH=BTB_COMPACT_ACTIVE?39:58;
    // A predictor tag may alias; execution still compares the full resolved
    // target before retirement. Keep all entries, with an eight-bit folded
    // identity instead of twenty-four exact bits in indirect-only mode.
    function automatic [7:0] folded_btb_tag;
        input [31:0] pc;
        reg [31:0] identity;
        begin
            // Fold every PC bit above the chosen index. At64 entries this
            // reduces exactly to the original three-byte folded identity.
            identity=pc >> (BTB_TOTAL_INDEX_WIDTH+2);
            folded_btb_tag=identity[7:0] ^ identity[15:8] ^
                identity[23:16] ^ identity[31:24];
        end
    endfunction
    wire [BTB_PAYLOAD_WIDTH-1:0] btb_update_payload=BTB_PAYLOAD_WIDTH'(BTB_COMPACT_ACTIVE?
        58'({folded_btb_tag(feedback_pc_i),feedback_btb_target[31:1]}):
        {feedback_pc_i[31:8],feedback_btb_target,feedback_kind_i});
    wire [23:0] query_btb_identity=BTB_COMPACT_ACTIVE?
        {16'b0,folded_btb_tag(query_pc_i)}:query_pc_i[31:8];

    wire [1:0] bht [0:BHT_ENTRIES-1];
    wire bht_trained [0:BHT_ENTRIES-1];
    wire btb_valid [0:BTB_ENTRIES-1];
    wire [23:0] btb_tag [0:BTB_ENTRIES-1];
    wire [31:0] btb_target [0:BTB_ENTRIES-1];
    wire [1:0] btb_kind [0:BTB_ENTRIES-1];
    localparam integer BHT_DOMAINS=(BHT_ENTRIES+3)/4;
    localparam integer BTB_DOMAINS=(BTB_ENTRIES+3)/4;
    localparam integer BHT_INDEX_WIDTH=8-BANK_BITS;
    localparam integer BTB_INDEX_WIDTH=BTB_TOTAL_INDEX_WIDTH-BANK_BITS;
    wire [BHT_ENTRIES*3-1:0] bht_rows;
    wire [BTB_ENTRIES*59-1:0] btb_rows;
    wire [2:0] query_bht_word;
    wire [58:0] query_btb_word;
    wire [BHT_DOMAINS*BHT_INDEX_WIDTH-1:0] bht_write_queries;
    wire [BHT_DOMAINS-1:0] bht_write_events,bht_directions;
    wire [BTB_DOMAINS*BTB_INDEX_WIDTH-1:0] btb_write_queries;
    wire [BTB_DOMAINS*BTB_PAYLOAD_WIDTH-1:0] btb_write_payloads;
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
    rv32_frequency_control_tree #(.WIDTH(BTB_PAYLOAD_WIDTH),.LEAVES(BTB_DOMAINS)) btb_payload_tree (
        .signal_i(btb_update_payload),.views_o(btb_write_payloads));
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
            if(BTB_COMPACT_ACTIVE) begin:g_compact
                rv32_predictor_indirect_btb_row row (
                    .clk_i(clk_i),.reset_i(reset_views[BHT_ENTRIES+predictor_row]),.update_i(update),
                    .payload_i(btb_write_payloads[DOMAIN*BTB_PAYLOAD_WIDTH +: BTB_PAYLOAD_WIDTH]),
                    .valid_o(btb_valid[predictor_row]),.tag_o(btb_tag[predictor_row][7:0]),
                    .target_o(btb_target[predictor_row]));
                assign btb_tag[predictor_row][23:8]=16'b0;
                assign btb_kind[predictor_row]=`RV32IM_PRED_JALR;
            end else begin:g_full
                rv32_predictor_btb_row row (
                    .clk_i(clk_i),.reset_i(reset_views[BHT_ENTRIES+predictor_row]),.update_i(update),
                    .payload_i(btb_write_payloads[DOMAIN*BTB_PAYLOAD_WIDTH +: BTB_PAYLOAD_WIDTH]),
                    .valid_o(btb_valid[predictor_row]),.tag_o(btb_tag[predictor_row]),
                    .target_o(btb_target[predictor_row]),.kind_o(btb_kind[predictor_row]));
            end
            assign btb_rows[predictor_row*59 +: 59]={btb_valid[predictor_row],btb_tag[predictor_row],btb_target[predictor_row],btb_kind[predictor_row]};
        end
    endgenerate
    generate if(NARROW_DIRECTION_READ!=0) begin:g_narrow_bht_query
        rv32_frequency_narrow_array_read #(.WIDTH(3),.ENTRIES(BHT_ENTRIES),.INDEX_WIDTH(BHT_INDEX_WIDTH)) query (
            .rows_i(bht_rows),.index_i(query_bht_index),.value_o(query_bht_word));
    end else begin:g_regular_bht_query
        rv32_frequency_array_read #(.WIDTH(3),.ENTRIES(BHT_ENTRIES),.INDEX_WIDTH(BHT_INDEX_WIDTH)) query (
            .rows_i(bht_rows),.index_i(query_bht_index),.value_o(query_bht_word));
    end endgenerate
    rv32_frequency_array_read #(.WIDTH(59),.ENTRIES(BTB_ENTRIES),.INDEX_WIDTH(BTB_INDEX_WIDTH)) btb_query (
        .rows_i(btb_rows),.index_i(query_btb_index),.value_o(query_btb_word));

    wire [6:0] query_opcode = query_inst_i[6:0];
    localparam [7:0] HISTORY_MASK = (1 << HISTORY_BITS) - 1;
    wire [7:0] query_full_index = query_pc_i[9:2] ^
        ((DIRECT_BRANCH_TARGET == 2) ? ((query_history_i & HISTORY_MASK) << BANK_BITS) : 8'b0);
    wire [7-BANK_BITS:0] query_bht_index = query_full_index[7:BANK_BITS];
    assign pred_training_index_o = query_full_index;
    wire [BTB_INDEX_WIDTH-1:0] query_btb_index = query_pc_i[2+BANK_BITS +: BTB_INDEX_WIDTH];
    wire query_btb_match = query_btb_word[58] &&
                           (query_btb_word[57:34] == query_btb_identity);
    wire [31:0] jal_imm = {{11{query_inst_i[31]}}, query_inst_i[31],
                           query_inst_i[19:12], query_inst_i[20],
                           query_inst_i[30:21], 1'b0};
    wire [31:0] branch_imm = {{19{query_inst_i[31]}}, query_inst_i[31],
                              query_inst_i[7], query_inst_i[30:25],
                              query_inst_i[11:8], 1'b0};
    wire [7-BANK_BITS:0] feedback_bht_index = (DIRECT_BRANCH_TARGET == 2) ?
        feedback_training_index_i[7:BANK_BITS] : feedback_pc_i[9:2+BANK_BITS];
    wire [BTB_INDEX_WIDTH-1:0] feedback_btb_index = feedback_pc_i[2+BANK_BITS +: BTB_INDEX_WIDTH];
    wire feedback_btb_write = feedback_valid_i && feedback_taken_i &&
                             (((DIRECT_BRANCH_TARGET == 0) &&
                               (feedback_kind_i == `RV32IM_PRED_BRANCH)) ||
                              (feedback_kind_i == `RV32IM_PRED_JALR));
    wire [31:0] feedback_btb_target = (feedback_kind_i == `RV32IM_PRED_JALR) ?
                                    {feedback_target_i[31:1], 1'b0} : feedback_target_i;
    integer i;

    assign pred_bht_index_o = query_pc_i[7:2];
    assign pred_btb_index_o = query_pc_i[5:2];
    wire [2:0] query_bimodal_word;
    wire [1:0] query_choice;
    wire global_direction=query_bht_word[2]?query_bht_word[1]:branch_imm[31];
    wire bimodal_direction=query_bimodal_word[2]?query_bimodal_word[1]:branch_imm[31];
    wire hybrid_direction=query_choice[1]?global_direction:bimodal_direction;
    assign pred_component_directions_o=(HYBRID_ACTIVE && query_valid_i &&
        query_opcode==7'b1100011)?{global_direction,bimodal_direction}:2'b00;
    assign pred_counter_o=(HYBRID_ACTIVE && !query_choice[1])?
        query_bimodal_word[1:0]:query_bht_word[1:0];
    generate if(HYBRID_ACTIVE) begin:g_hybrid_direction
        localparam integer CHOICE_ENTRIES=64>>BANK_BITS;
        localparam integer CHOICE_INDEX_WIDTH=6-BANK_BITS;
        localparam integer CHOICE_DOMAINS=(CHOICE_ENTRIES+3)/4;
        wire [BHT_ENTRIES*3-1:0] bimodal_rows;
        wire [CHOICE_ENTRIES*2-1:0] choice_rows;
        wire [BHT_ENTRIES+CHOICE_ENTRIES-1:0] hybrid_reset_views;
        wire [BHT_DOMAINS*BHT_INDEX_WIDTH-1:0] bimodal_write_queries;
        wire [BHT_DOMAINS-1:0] bimodal_write_events,bimodal_directions;
        wire [CHOICE_DOMAINS*CHOICE_INDEX_WIDTH-1:0] choice_write_queries;
        wire [CHOICE_DOMAINS-1:0] choice_write_events,choice_global_correct;
        wire conditional_feedback=feedback_valid_i && feedback_kind_i==`RV32IM_PRED_BRANCH;
        wire choice_adjust=conditional_feedback &&
            (feedback_component_directions_i[1]!=feedback_component_directions_i[0]);
        wire global_correct=feedback_taken_i==feedback_component_directions_i[1];
        rv32_frequency_control_tree #(.LEAVES(BHT_ENTRIES+CHOICE_ENTRIES)) hybrid_reset_tree (
            .signal_i(reset_i),.views_o(hybrid_reset_views));
        rv32_frequency_control_tree #(.WIDTH(BHT_INDEX_WIDTH),.LEAVES(BHT_DOMAINS)) bimodal_address_tree (
            .signal_i(feedback_pc_i[9:2+BANK_BITS]),.views_o(bimodal_write_queries));
        rv32_frequency_control_tree #(.LEAVES(BHT_DOMAINS)) bimodal_event_tree (
            .signal_i(conditional_feedback),.views_o(bimodal_write_events));
        rv32_frequency_control_tree #(.LEAVES(BHT_DOMAINS)) bimodal_direction_tree (
            .signal_i(feedback_taken_i),.views_o(bimodal_directions));
        rv32_frequency_control_tree #(.WIDTH(CHOICE_INDEX_WIDTH),.LEAVES(CHOICE_DOMAINS)) choice_address_tree (
            .signal_i(feedback_pc_i[7:2+BANK_BITS]),.views_o(choice_write_queries));
        rv32_frequency_control_tree #(.LEAVES(CHOICE_DOMAINS)) choice_event_tree (
            .signal_i(choice_adjust),.views_o(choice_write_events));
        rv32_frequency_control_tree #(.LEAVES(CHOICE_DOMAINS)) choice_direction_tree (
            .signal_i(global_correct),.views_o(choice_global_correct));
        for(genvar bimodal_row=0;bimodal_row<BHT_ENTRIES;bimodal_row=bimodal_row+1) begin:g_bimodal_owner
            localparam integer DOMAIN=bimodal_row/4;
            wire [1:0] counter;
            wire trained;
            wire update=bimodal_write_events[DOMAIN] &&
                bimodal_write_queries[DOMAIN*BHT_INDEX_WIDTH +: BHT_INDEX_WIDTH]==bimodal_row;
            rv32_predictor_bht_row row (
                .clk_i(clk_i),.reset_i(hybrid_reset_views[bimodal_row]),.update_i(update),
                .taken_i(bimodal_directions[DOMAIN]),.counter_o(counter),.trained_o(trained));
            assign bimodal_rows[bimodal_row*3 +: 3]={trained,counter};
        end
        for(genvar choice_row=0;choice_row<CHOICE_ENTRIES;choice_row=choice_row+1) begin:g_choice_owner
            localparam integer DOMAIN=choice_row/4;
            wire update=choice_write_events[DOMAIN] &&
                choice_write_queries[DOMAIN*CHOICE_INDEX_WIDTH +: CHOICE_INDEX_WIDTH]==choice_row;
            rv32_predictor_choice_row row (
                .clk_i(clk_i),.reset_i(hybrid_reset_views[BHT_ENTRIES+choice_row]),
                .update_i(update),.global_correct_i(choice_global_correct[DOMAIN]),
                .counter_o(choice_rows[choice_row*2 +: 2]));
        end
        // All three tables query in parallel. Choice is a final direction mux,
        // never an extra serialized index lookup before either direction table.
        if(NARROW_DIRECTION_READ!=0) begin:g_narrow_bimodal_query
            rv32_frequency_narrow_array_read #(.WIDTH(3),.ENTRIES(BHT_ENTRIES),.INDEX_WIDTH(BHT_INDEX_WIDTH)) query (
                .rows_i(bimodal_rows),.index_i(query_pc_i[9:2+BANK_BITS]),.value_o(query_bimodal_word));
        end else begin:g_regular_bimodal_query
            rv32_frequency_array_read #(.WIDTH(3),.ENTRIES(BHT_ENTRIES),.INDEX_WIDTH(BHT_INDEX_WIDTH)) query (
                .rows_i(bimodal_rows),.index_i(query_pc_i[9:2+BANK_BITS]),.value_o(query_bimodal_word));
        end
        if(NARROW_DIRECTION_READ!=0) begin:g_narrow_choice_query
            rv32_frequency_narrow_array_read #(.WIDTH(2),.ENTRIES(CHOICE_ENTRIES),.INDEX_WIDTH(CHOICE_INDEX_WIDTH)) query (
                .rows_i(choice_rows),.index_i(query_pc_i[7:2+BANK_BITS]),.value_o(query_choice));
        end else begin:g_regular_choice_query
            rv32_frequency_array_read #(.WIDTH(2),.ENTRIES(CHOICE_ENTRIES),.INDEX_WIDTH(CHOICE_INDEX_WIDTH)) query (
                .rows_i(choice_rows),.index_i(query_pc_i[7:2+BANK_BITS]),.value_o(query_choice));
        end
    end else begin:g_no_hybrid_direction
        assign query_bimodal_word=3'b000;
        assign query_choice=2'b10;
    end endgenerate

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
                        if (HYBRID_ACTIVE ? hybrid_direction : global_direction) begin
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
    generate if(DIRECTION_INDEPENDENT_TARGET!=0 && DIRECT_BRANCH_TARGET!=0) begin:g_early_target
        // Kind/BTB query is independent of direction-table readout. Compute
        // a conditional target before the global/bimodal/choice decision;
        // frontend direction remains the final target-versus-sequential choice.
        assign target_classes[1]=pred_kind_o==`RV32IM_PRED_BRANCH;
        assign target_classes[2]=pred_kind_o==`RV32IM_PRED_JAL;
        assign target_classes[3]=pred_kind_o==`RV32IM_PRED_JALR && pred_btb_hit_o;
        assign target_classes[0]=!(|target_classes[3:1]);
    end else begin:g_qualified_target
        assign target_classes[0]=!pred_taken_o;
        assign target_classes[1]=pred_taken_o && pred_kind_o==`RV32IM_PRED_BRANCH &&
            ((DIRECT_BRANCH_TARGET!=0) || !pred_btb_hit_o);
        assign target_classes[2]=pred_taken_o && pred_kind_o==`RV32IM_PRED_JAL;
        assign target_classes[3]=pred_taken_o &&
            (pred_kind_o==`RV32IM_PRED_JALR ||
             (pred_kind_o==`RV32IM_PRED_BRANCH && DIRECT_BRANCH_TARGET==0 && pred_btb_hit_o));
    end endgenerate
    assign target_values={query_btb_word[33:2],direct_jal_pc,direct_branch_pc,default_next_pc};
    // The four legal target classes are exhaustive and mutually exclusive.
    wire  unused_target_selector_write_o;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(4),.PRIORITY(0)) target_selector (
        .events_i(target_classes),.values_i(target_values),.write_o(unused_target_selector_write_o),.value_o(pred_target_o));

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
