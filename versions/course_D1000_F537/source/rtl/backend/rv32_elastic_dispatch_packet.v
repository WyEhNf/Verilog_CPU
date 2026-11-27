`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Two bundle entries break the D-resource/PRF path from R acceptance.
// R allocates ROB/physical destinations once. D emits the entire oldest
// bundle only when both its actual RS and LSQ demands fit the saved free
// counts. Recovery retains only full-generation-live, older ROB tags.
module rv32_elastic_dispatch_packet #(
    parameter integer FULL_REPLACE=0,
    parameter integer LANES=2,PAYLOAD_WIDTH=160,TAG_WIDTH=16,ROB_ENTRIES=32,
    parameter integer SW=(ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES),
    parameter integer GW=TAG_WIDTH-SW-3
) (
    input wire clk_i,reset_i,flush_i,hold_i,recovery_i,
    input wire [SW-1:0] recovery_head_i,
    input wire [TAG_WIDTH-1:0] recovery_tag_i,
    input wire [15:0] recovery_occupancy_i,
    input wire [ROB_ENTRIES-1:0] rob_valid_i,
    input wire [ROB_ENTRIES*GW-1:0] rob_generation_i,
    input wire [LANES-1:0] valid_i,
    input wire [LANES*TAG_WIDTH-1:0] tag_i,
    input wire [LANES*PAYLOAD_WIDTH-1:0] data_i,
    output wire ready_o,
    output wire [LANES-1:0] valid_o,
    output wire [LANES*TAG_WIDTH-1:0] tag_o,
    output wire [LANES*PAYLOAD_WIDTH-1:0] data_o,
    // Caller guarantees consume_i when this credit is asserted. It is a
    // saved-capacity proof, not a late consume/PRF combinational ready path.
    input wire replace_credit_i,
    input wire consume_i
);
    wire unused_recovery_tag_i_bits = &{1'b0, recovery_tag_i};

    reg [1:0] count;
    reg read_slot,write_slot;
    reg [LANES-1:0] valids [0:1];
    wire [TAG_WIDTH-1:0] tags [0:2*LANES-1];
    wire [PAYLOAD_WIDTH-1:0] payloads [0:2*LANES-1];
    wire [LANES-1:0] recovery_keep [0:1];
    wire [ROB_ENTRIES*(GW+1)-1:0] live_rows;
    wire normal=!reset_i && !flush_i && !hold_i && !recovery_i;
    // At full occupancy read_slot==write_slot. The old head is consumed
    // before this edge; nonblocking writes replace it as the new tail. The
    // existing pop-then-push validity priority deliberately makes push win.
    assign ready_o=normal && (count<2 ||
        ((FULL_REPLACE!=0) && count==2 && replace_credit_i));
    wire push=(|valid_i) && ready_o;
    wire pop=normal && count!=0 && consume_i;
    wire [SW-1:0] branch_age=recovery_tag_i[3 +: SW]-recovery_head_i;
    genvar rob_row,row,lane,word;
    generate for(rob_row=0;rob_row<ROB_ENTRIES;rob_row=rob_row+1) begin:g_live_row
        assign live_rows[rob_row*(GW+1) +: GW+1]={rob_valid_i[rob_row],rob_generation_i[rob_row*GW +: GW]};
    end endgenerate
    localparam integer OUTPUT_WORDS=(PAYLOAD_WIDTH+TAG_WIDTH+15)/16;
    wire [LANES*OUTPUT_WORDS-1:0] read_views;
    rv32_frequency_control_tree #(.LEAVES(LANES*OUTPUT_WORDS)) read_tree (
        .signal_i(read_slot),.views_o(read_views));
    generate
        for(row=0;row<2;row=row+1) begin:g_row
            for(lane=0;lane<LANES;lane=lane+1) begin:g_lane
                wire [TAG_WIDTH-1:0] tag=tags[row*LANES+lane];
                wire unused_tag_bits = &{1'b0, tag};

                wire [SW-1:0] slot=tag[3 +: SW];
                wire [SW-1:0] age=slot-recovery_head_i;
                wire [GW:0] live;
                rv32_frequency_array_read #(.WIDTH(GW+1),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SW)) live_reader (
                    .rows_i(live_rows),.index_i(slot),.value_o(live));
                assign recovery_keep[row][lane]=valids[row][lane] && tag[0] &&
                    live[GW] && tag[3+SW +: GW]==live[0 +: GW] &&
                    age<branch_age && 16'(age)<recovery_occupancy_i;
                rv32_frequency_word_bank #(.WIDTH(TAG_WIDTH+PAYLOAD_WIDTH)) packet_owner (
                    .clk_i(clk_i),.write_i(push && write_slot==row && valid_i[lane]),
                    .data_i({tag_i[lane*TAG_WIDTH +: TAG_WIDTH],data_i[lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]}),
                    .data_o({tags[row*LANES+lane],payloads[row*LANES+lane]}));
            end
        end
        for(lane=0;lane<LANES;lane=lane+1) begin:g_output
            wire [TAG_WIDTH+PAYLOAD_WIDTH-1:0] selected;
            wire [TAG_WIDTH+PAYLOAD_WIDTH-1:0] first={tags[lane],payloads[lane]};
            wire [TAG_WIDTH+PAYLOAD_WIDTH-1:0] second={tags[LANES+lane],payloads[LANES+lane]};
            for(word=0;word<OUTPUT_WORDS;word=word+1) begin:g_word
                localparam integer LOW=16*word;
                localparam integer BITS=TAG_WIDTH+PAYLOAD_WIDTH-LOW>=16?16:TAG_WIDTH+PAYLOAD_WIDTH-LOW;
                assign selected[LOW +: BITS]=read_views[lane*OUTPUT_WORDS+word]?
                    second[LOW +: BITS]:first[LOW +: BITS];
            end
            assign {tag_o[lane*TAG_WIDTH +: TAG_WIDTH],data_o[lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]}=selected;
            assign valid_o[lane]=normal && count!=0 && (read_slot?valids[1][lane]:valids[0][lane]);
        end
    endgenerate
    wire keep_first=|recovery_keep[read_slot];
    wire keep_second=(count==2) && (|recovery_keep[!read_slot]);
    always @(posedge clk_i) begin
        if(reset_i || flush_i)
        begin
            count<=0;
            read_slot<=0;
            write_slot<=0;
            valids[0]<=0;
            valids[1]<=0;
        end
        else
            if(recovery_i)
            begin
                valids[0]<=recovery_keep[0];
                valids[1]<=recovery_keep[1];
                if(count==0 || (!keep_first && !keep_second))
                begin
                    count<=0;
                    read_slot<=0;
                    write_slot<=0;
                    valids[0]<=0;
                    valids[1]<=0;
                end
                else
                    if(keep_first && keep_second)
                    begin
                        count<=2;
                    end
                    else
                        if(keep_first)
                        begin
                            count<=1;
                            write_slot<=!read_slot;
                            valids[!read_slot]<=0;
                        end
                        else
                        begin
                            count<=1;
                            read_slot<=!read_slot;
                            write_slot<=read_slot;
                            valids[read_slot]<=0;
                        end
            end
            else
                if(!hold_i)
                begin
                    case({push,pop})
                    2'b10:count<=count+1'b1;
                    2'b01:count<=count-1'b1;
                    default:count<=count;
                    endcase
                    if(pop)
                    begin
                        valids[read_slot]<=0;
                        read_slot<=!read_slot;
                    end
                    if(push)
                    begin
                        valids[write_slot]<=valid_i;
                        write_slot<=!write_slot;
                    end
                end
    end
endmodule
