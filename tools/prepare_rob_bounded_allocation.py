"""Bound ROB allocation payload selects and commit controls; no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


BANK = r'''
    genvar alloc_bank,alloc_source,alloc_word,alloc_node;
    localparam integer ALLOC_DATA_WIDTH=ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH+
        ((CHECKPOINT_IMPL==0)?CHECKPOINT_WIDTH:0);
    localparam integer ALLOC_DATA_WORDS=(ALLOC_DATA_WIDTH+31)/32;
    localparam integer ALLOC_DATA_LEAVES=1<<$clog2(BE_WIDTH);
    generate
        for(alloc_bank=0;alloc_bank<BE_WIDTH;alloc_bank=alloc_bank+1) begin:g_bank_allocation
            if(ALLOC_BANKED_WRITE!=0 && ROB_ENTRIES>=BE_WIDTH) begin:g_enabled
                wire [BE_WIDTH-1:0] matches,grants;
                wire [SLOT_WIDTH-1:0] slots [1:2*ALLOC_DATA_LEAVES-1];
                wire [ALLOC_DATA_WIDTH-1:0] packets [1:2*ALLOC_DATA_LEAVES-1];
                for(alloc_source=0;alloc_source<ALLOC_DATA_LEAVES;alloc_source=alloc_source+1) begin:g_source
                    if(alloc_source<BE_WIDTH) begin:g_present
                        wire [SLOT_WIDTH-1:0] target_slot=tail_reg+alloc_source;
                        wire [ALLOC_PACKET_WIDTH-1:0] full_payload={
                            alloc_is_store_i[alloc_source],alloc_is_branch_i[alloc_source],
                            alloc_is_halt_i[alloc_source],alloc_is_error_i[alloc_source],
                            alloc_pc_i[alloc_source*32 +: 32],alloc_inst_i[alloc_source*32 +: 32],
                            alloc_rd_i[alloc_source*5 +: 5],alloc_rd_we_i[alloc_source],
                            alloc_old_phys_i[alloc_source*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                            alloc_new_phys_i[alloc_source*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                            alloc_checkpoint_i[alloc_source*CHECKPOINT_WIDTH +: CHECKPOINT_WIDTH]};
                        wire [ALLOC_DATA_WIDTH-1:0] active_payload;
                        wire [ALLOC_DATA_WORDS-1:0] selected_words;
                        if(CHECKPOINT_IMPL==0) begin:g_with_checkpoint
                            assign active_payload=full_payload;
                        end else begin:g_without_checkpoint
                            assign active_payload=full_payload[CHECKPOINT_WIDTH +: ALLOC_PACKET_WIDTH-CHECKPOINT_WIDTH];
                        end
                        assign matches[alloc_source]=alloc_fire_o[alloc_source] &&
                            ((tail_reg+alloc_source)%BE_WIDTH)==alloc_bank;
                        if(alloc_source==BE_WIDTH-1) begin:g_last
                            assign grants[alloc_source]=matches[alloc_source];
                        end else begin:g_priority
                            assign grants[alloc_source]=matches[alloc_source] &&
                                !(|matches[BE_WIDTH-1:alloc_source+1]);
                        end
                        rv32_frequency_control_tree #(.LEAVES(ALLOC_DATA_WORDS)) selection_tree (
                            .signal_i(grants[alloc_source]),.views_o(selected_words));
                        assign slots[ALLOC_DATA_LEAVES+alloc_source]={SLOT_WIDTH{grants[alloc_source]}} & target_slot;
                        for(alloc_word=0;alloc_word<ALLOC_DATA_WORDS;alloc_word=alloc_word+1) begin:g_word
                            localparam integer LOW=alloc_word*32;
                            localparam integer BITS=ALLOC_DATA_WIDTH-LOW>=32 ? 32 : ALLOC_DATA_WIDTH-LOW;
                            assign packets[ALLOC_DATA_LEAVES+alloc_source][LOW +: BITS]=
                                {BITS{selected_words[alloc_word]}} & active_payload[LOW +: BITS];
                        end
                    end else begin:g_padding
                        assign slots[ALLOC_DATA_LEAVES+alloc_source]=0;
                        assign packets[ALLOC_DATA_LEAVES+alloc_source]=0;
                    end
                end
                for(alloc_node=1;alloc_node<ALLOC_DATA_LEAVES;alloc_node=alloc_node+1) begin:g_or
                    assign slots[alloc_node]=slots[2*alloc_node] | slots[2*alloc_node+1];
                    assign packets[alloc_node]=packets[2*alloc_node] | packets[2*alloc_node+1];
                end
                assign bank_alloc_fire[alloc_bank]=|matches;
                assign bank_alloc_slot[alloc_bank]=slots[1];
                if(CHECKPOINT_IMPL==0) begin:g_full_result
                    assign bank_alloc_packet[alloc_bank]=packets[1];
                end else begin:g_compact_result
                    assign bank_alloc_packet[alloc_bank]={packets[1],{CHECKPOINT_WIDTH{1'b0}}};
                end
            end else begin:g_disabled
                assign bank_alloc_fire[alloc_bank]=0;
                assign bank_alloc_slot[alloc_bank]=0;
                assign bank_alloc_packet[alloc_bank]=0;
            end
        end
    endgenerate
'''


def bounded(t):
    start=t.index('    genvar alloc_bank;')
    stop=t.index('\n    function [SLOT_WIDTH-1:0] advance_slot;',start)
    t=t[:start]+BANK+t[stop:]
    t=change(t,'wire [WRITE_DOMAINS*(BE_WIDTH+1)-1:0] local_commits;',
               'wire [WRITE_DOMAINS*BE_WIDTH-1:0] local_commits;\n    wire [WRITE_DOMAINS-1:0] local_store_sends;')
    t=change(t,'''        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH+1),.LEAVES(WRITE_DOMAINS)) commit_tree (
            .signal_i({commit_ready_i,commit_valid_o}),.views_o(local_commits));''',
               '''        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(WRITE_DOMAINS)) commit_tree (
            .signal_i(commit_valid_o & {BE_WIDTH{commit_ready_i}}),.views_o(local_commits));
        rv32_frequency_control_tree #(.LEAVES(WRITE_DOMAINS)) store_send_tree (
            .signal_i(store_commit_valid_o && store_commit_ready_i),.views_o(local_store_sends));''')
    t=change(t,'''                        local_commits[DOMAIN*(BE_WIDTH+1)+BE_WIDTH] &&
                        local_commits[DOMAIN*(BE_WIDTH+1)+command_lane] && commit_slot==command_row;''',
               '''                        local_commits[DOMAIN*BE_WIDTH+command_lane] && commit_slot==command_row;''')
    t=change(t,'wire sent=normal && store_commit_valid_o && store_commit_ready_i && row_commit_head==command_row;',
               'wire sent=normal && local_store_sends[DOMAIN] && row_commit_head==command_row;')
    return t


if __name__=='__main__':
    prepare('AG_bounded_rob_allocation',ROOT/'AF_row_local_rob_commands',
            {'rtl/backend/rv32_rob.v':bounded},
            'AF plus independent one-hot bank allocation selects with <=32-bit leaves and balanced OR trees, excluding unused checkpoint width; qualify commit/store-send once before bounded broadcast; no register/cycle change and no EDA run')
