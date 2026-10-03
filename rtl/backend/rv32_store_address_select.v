`timescale 1ns/1ps

// Select one pending store whose existing RS base operand is ready. Select
// oldest in the circular LSQ, then lowest RS slot for deterministic duplicate
// tags. Only the address is published; this never dequeues RS work, produces
// a completion, marks store data ready or authorizes a memory write.
module rv32_store_address_select #(
    parameter integer LSQ_ENTRIES = 16,
    parameter integer RS_ENTRIES = 16,
    parameter integer TAG_WIDTH = 17,
    parameter integer ROB_TAG_WIDTH = TAG_WIDTH,
    parameter integer HEAD_WIDTH = (LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES)
) (
    input wire [HEAD_WIDTH-1:0] head_i,
    input wire [LSQ_ENTRIES-1:0] pending_i,
    input wire [LSQ_ENTRIES*TAG_WIDTH-1:0] lsq_tag_i,
    input wire [LSQ_ENTRIES*ROB_TAG_WIDTH-1:0] store_rob_tag_i,
    input wire [RS_ENTRIES-1:0] base_ready_i,
    input wire [RS_ENTRIES*ROB_TAG_WIDTH-1:0] rs_rob_tag_i,
    input wire [RS_ENTRIES*32-1:0] base_value_i,
    output wire valid_o,
    output wire [TAG_WIDTH-1:0] lsq_tag_o,
    output wire [ROB_TAG_WIDTH-1:0] rob_tag_o,
    output wire [31:0] base_value_o
);
    wire [LSQ_ENTRIES-1:0] eligible, upper, choices, first;
    wire upper_found = |upper;
    wire [RS_ENTRIES-1:0] base_match, base_first;
    genvar row, entry, bit_id;
    generate
        for (row = 0; row < LSQ_ENTRIES; row = row + 1) begin : g_store
            wire [RS_ENTRIES-1:0] rs_matches;
            for (entry = 0; entry < RS_ENTRIES; entry = entry + 1) begin : g_rs_match
                assign rs_matches[entry] = base_ready_i[entry] &&
                    store_rob_tag_i[row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH] ==
                    rs_rob_tag_i[entry*ROB_TAG_WIDTH +: ROB_TAG_WIDTH];
            end
            assign eligible[row] = pending_i[row] && (|rs_matches);
            assign upper[row] = eligible[row] && row >= head_i;
            assign choices[row] = upper_found ? upper[row] : eligible[row];
            if (row == 0) assign first[row] = choices[row];
            else assign first[row] = choices[row] && !(|choices[row-1:0]);
        end
        for (bit_id = 0; bit_id < TAG_WIDTH; bit_id = bit_id + 1) begin : g_lsq_tag
            wire [LSQ_ENTRIES-1:0] column;
            for (row = 0; row < LSQ_ENTRIES; row = row + 1) begin : g_row
                assign column[row] = first[row] && lsq_tag_i[row*TAG_WIDTH+bit_id];
            end
            assign lsq_tag_o[bit_id] = |column;
        end
        for (bit_id = 0; bit_id < ROB_TAG_WIDTH; bit_id = bit_id + 1) begin : g_rob_tag
            wire [LSQ_ENTRIES-1:0] column;
            for (row = 0; row < LSQ_ENTRIES; row = row + 1) begin : g_row
                assign column[row] = first[row] && store_rob_tag_i[row*ROB_TAG_WIDTH+bit_id];
            end
            assign rob_tag_o[bit_id] = |column;
        end
        for (entry = 0; entry < RS_ENTRIES; entry = entry + 1) begin : g_base_pick
            assign base_match[entry] = valid_o && base_ready_i[entry] &&
                rs_rob_tag_i[entry*ROB_TAG_WIDTH +: ROB_TAG_WIDTH] == rob_tag_o;
            if (entry == 0) assign base_first[entry] = base_match[entry];
            else assign base_first[entry] = base_match[entry] && !(|base_match[entry-1:0]);
        end
        for (bit_id = 0; bit_id < 32; bit_id = bit_id + 1) begin : g_base_value
            wire [RS_ENTRIES-1:0] column;
            for (entry = 0; entry < RS_ENTRIES; entry = entry + 1) begin : g_entry
                assign column[entry] = base_first[entry] && base_value_i[entry*32+bit_id];
            end
            assign base_value_o[bit_id] = |column;
        end
    endgenerate
    assign valid_o = |first;
    initial begin
        if (LSQ_ENTRIES < 1 || (LSQ_ENTRIES & (LSQ_ENTRIES-1)) != 0 ||
            RS_ENTRIES < 1 || TAG_WIDTH < 1 || ROB_TAG_WIDTH < 1) begin
            $display("ERROR: invalid shared store-address selector geometry");
            $finish;
        end
    end
endmodule
