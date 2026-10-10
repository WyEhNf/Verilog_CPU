`timescale 1ns/1ps

// Four original prefix-priority grants are onehot0 by construction. Prepare
// complete region equalities before late target selection; no grant selects
// the original all-zero target, so its region equality must also be retained.
(* keep_hierarchy = 1 *)
module rv32_icache_control_region_query #(
    parameter integer REGION_BITS=12,WAYS=2,DOMAINS=16
) (
    input wire [127:0] candidates_i,
    input wire [3:0] grants_i,
    input wire [WAYS*REGION_BITS-1:0] prefixes_i,
    output wire [WAYS*DOMAINS-1:0] matches_o
);
    wire [4*WAYS*REGION_BITS-1:0] candidate_views;
    for(genvar candidate=0;candidate<4;candidate=candidate+1) begin:g_candidate
        rv32_frequency_control_tree #(.WIDTH(REGION_BITS),.LEAVES(WAYS)) target_tree (
            .signal_i(candidates_i[candidate*32+32-REGION_BITS +: REGION_BITS]),
            .views_o(candidate_views[candidate*WAYS*REGION_BITS +: WAYS*REGION_BITS]));
    end
    for(genvar way=0;way<WAYS;way=way+1) begin:g_way
        wire [4*REGION_BITS-1:0] prefix_views;
        wire [3:0] equalities;
        wire selected;
        rv32_frequency_control_tree #(.WIDTH(REGION_BITS),.LEAVES(4)) prefix_tree (
            .signal_i(prefixes_i[way*REGION_BITS +: REGION_BITS]),.views_o(prefix_views));
        for(genvar candidate=0;candidate<4;candidate=candidate+1) begin:g_match
            assign equalities[candidate]=prefix_views[candidate*REGION_BITS +: REGION_BITS]==
                candidate_views[(candidate*WAYS+way)*REGION_BITS +: REGION_BITS];
        end
        assign selected=(|(equalities & grants_i)) ||
            (!(|grants_i) && prefixes_i[way*REGION_BITS +: REGION_BITS]==0);
        rv32_frequency_control_tree #(.LEAVES(DOMAINS)) match_tree (
            .signal_i(selected),.views_o(matches_o[way*DOMAINS +: DOMAINS]));
    end
    initial if(REGION_BITS<1 || REGION_BITS>27 || WAYS<1 || WAYS>2 || DOMAINS<1)
        $fatal(1,"Control region query requires complete region and original cache ways/domains");
endmodule
