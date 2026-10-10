`timescale 1ns/1ps

// Compare complete tags before late candidate choice. No producer ownership,
// valid-state or shortened-generation assumption licenses these equalities.
(* keep_hierarchy = 1 *)
module rv32_completion_candidate_class #(
    parameter integer TAG_WIDTH=16,
    parameter integer LANES=2
) (
    input wire [TAG_WIDTH-1:0] head_tag_i,saved_tag_i,live_tag_i,
    input wire live_valid_i,head_choice_i,
    input wire [LANES*TAG_WIDTH-1:0] held_tags_i,
    output wire tag_eligible_o,
    output wire [LANES-1:0] held_equal_o
);
    wire head_eligible=head_tag_i[0] && (!live_valid_i || head_tag_i==live_tag_i);
    wire saved_eligible=saved_tag_i[0] && (!live_valid_i || saved_tag_i==live_tag_i);
    assign tag_eligible_o=head_choice_i ? head_eligible : saved_eligible;
    for(genvar lane=0;lane<LANES;lane=lane+1) begin:g_lane
        wire head_equal=head_tag_i==held_tags_i[lane*TAG_WIDTH +: TAG_WIDTH];
        wire saved_equal=saved_tag_i==held_tags_i[lane*TAG_WIDTH +: TAG_WIDTH];
        assign held_equal_o[lane]=head_choice_i ? head_equal : saved_equal;
    end
    initial if(TAG_WIDTH<1 || LANES<1) $fatal(1,"Complete candidate tag geometry required");
endmodule
