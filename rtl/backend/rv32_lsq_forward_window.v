`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Exact relative byte routing for any pair of four-bit line offsets.
// Instead of sixteen repeated (load_offset+b)==(store_offset+j) comparisons,
// decode seven possible nonempty windows once and share across the four bytes.
// This adds no state, speculation, or new alignment assumption.
(* keep_hierarchy = 1 *)
module rv32_lsq_forward_window #(
    parameter integer STORE_OFFSET_PREDECODE=0
) (
    input wire [31:0] store_data_i,
    input wire [3:0] store_offset_i,store_mask_i,load_offset_i,load_mask_i,
    output wire [3:0] mask_o,
    output wire [31:0] data_o
);
    // Five bits exactly represent every difference in [-15,+15] modulo32.
    // Only differences -3..+3 can place a store byte in the four-byte window.
    wire [4:0] offset_delta={1'b0,load_offset_i}-{1'b0,store_offset_i};
    wire [6:0] alignments;
    wire [27:0] alignment_views;
    rv32_frequency_control_tree #(.WIDTH(7),.LEAVES(4)) alignment_tree (
        .signal_i(alignments),.views_o(alignment_views));
    genvar delta_id,load_byte,store_byte;
    generate
        for(delta_id=0;delta_id<7;delta_id=delta_id+1) begin:g_delta
            localparam [4:0] DELTA=delta_id-3;
            if(STORE_OFFSET_PREDECODE!=0) begin:g_predecoded
                // Stored offset and each constant are available before the
                // late selected load. The fifth bit retains line-boundary
                // exclusion; four-bit wrap would admit spurious matches.
                wire [4:0] expected_load_offset={1'b0,store_offset_i}+DELTA;
                assign alignments[delta_id]=!expected_load_offset[4] &&
                    load_offset_i==expected_load_offset[3:0];
            end else begin:g_original
                assign alignments[delta_id]=offset_delta==DELTA;
            end
        end
        for(load_byte=0;load_byte<4;load_byte=load_byte+1) begin:g_load_byte
            wire [3:0] byte_match_bits;
            wire [7:0] routed [0:3];
            for(store_byte=0;store_byte<4;store_byte=store_byte+1) begin:g_store_byte
                localparam integer ALIGNMENT=store_byte-load_byte+3;
                wire match_view;
                rv32_frequency_control_tree #(.LEAVES(1)) match_tree (
                    .signal_i(load_mask_i[load_byte] && store_mask_i[store_byte] &&
                              alignment_views[load_byte*7+ALIGNMENT]),.views_o(match_view));
                assign byte_match_bits[store_byte]=match_view;
                assign routed[store_byte]={8{match_view}} & store_data_i[store_byte*8 +: 8];
            end
            // There is at most one matching source byte for each output byte.
            assign mask_o[load_byte]=|byte_match_bits;
            assign data_o[load_byte*8 +: 8]=(routed[0] | routed[1]) | (routed[2] | routed[3]);
        end
    endgenerate
    initial if(STORE_OFFSET_PREDECODE!=0 && STORE_OFFSET_PREDECODE!=1)
        $fatal(1,"Store-offset predecode must be 0 or 1");
endmodule
