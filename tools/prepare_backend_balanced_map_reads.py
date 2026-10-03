"""Bound and balance backend map queries; no RTL compiler or hardware tests."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


READS = r'''
    localparam integer ROB_MAP_READ_DOMAINS=(ROB_ENTRIES+3)/4;
    localparam integer LSQ_MAP_READ_DOMAINS=(LSQ_ENTRIES+3)/4;
    localparam integer ROB_MAP_READ_LEAVES=1<<$clog2(ROB_ENTRIES);
    localparam integer LSQ_MAP_READ_LEAVES=1<<$clog2(LSQ_ENTRIES);
    localparam integer ROB_MAP_READ_WORDS=(TAG_WIDTH+15)/16;
    localparam integer LSQ_MAP_READ_WORDS=(PAW+15)/16;
    wire [BE_WIDTH*ROB_SLOT_WIDTH-1:0] rob_map_query;
    wire [ROB_MAP_READ_DOMAINS*BE_WIDTH*ROB_SLOT_WIDTH-1:0] rob_map_query_views;
    wire [LSQ_MAP_READ_DOMAINS*LSQ_SLOT_WIDTH-1:0] lsq_map_query_views;
    wire [BE_WIDTH*TAG_WIDTH-1:0] alu_lsq_map_read;
    wire [PAW-1:0] load_phys_map_read;
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*ROB_SLOT_WIDTH),.LEAVES(ROB_MAP_READ_DOMAINS)) rob_map_query_tree (
        .signal_i(rob_map_query),.views_o(rob_map_query_views));
    rv32_frequency_control_tree #(.WIDTH(LSQ_SLOT_WIDTH),.LEAVES(LSQ_MAP_READ_DOMAINS)) lsq_map_query_tree (
        .signal_i(lsq_load_complete_lsq_tag[3 +: LSQ_SLOT_WIDTH]),.views_o(lsq_map_query_views));
    genvar map_query_lane,map_query_row,map_query_word,map_query_node;
    generate
        for(map_query_lane=0;map_query_lane<BE_WIDTH;map_query_lane=map_query_lane+1) begin:g_rob_map_read
            wire [TAG_WIDTH-1:0] reads [1:2*ROB_MAP_READ_LEAVES-1];
            assign rob_map_query[map_query_lane*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]=
                alu_exec_tag[map_query_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
            assign alu_lsq_map_read[map_query_lane*TAG_WIDTH +: TAG_WIDTH]=reads[1];
            for(map_query_row=0;map_query_row<ROB_MAP_READ_LEAVES;map_query_row=map_query_row+1) begin:g_row
                if(map_query_row<ROB_ENTRIES) begin:g_present
                    wire [ROB_MAP_READ_WORDS-1:0] selects;
                    wire hit=rob_map_query_views[((map_query_row/4)*BE_WIDTH+map_query_lane)*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]==map_query_row;
                    rv32_frequency_control_tree #(.LEAVES(ROB_MAP_READ_WORDS)) select_tree (
                        .signal_i(hit),.views_o(selects));
                    for(map_query_word=0;map_query_word<ROB_MAP_READ_WORDS;map_query_word=map_query_word+1) begin:g_word
                        localparam integer LOW=map_query_word*16;
                        localparam integer BITS=(TAG_WIDTH-LOW>=16)?16:TAG_WIDTH-LOW;
                        assign reads[ROB_MAP_READ_LEAVES+map_query_row][LOW +: BITS]=
                            {BITS{selects[map_query_word]}} & rob_to_lsq_mem[map_query_row][LOW +: BITS];
                    end
                end else begin:g_padding
                    assign reads[ROB_MAP_READ_LEAVES+map_query_row]=0;
                end
            end
            for(map_query_node=1;map_query_node<ROB_MAP_READ_LEAVES;map_query_node=map_query_node+1) begin:g_reduce
                assign reads[map_query_node]=reads[2*map_query_node] | reads[2*map_query_node+1];
            end
        end
        begin:g_lsq_phys_read
            wire [PAW-1:0] reads [1:2*LSQ_MAP_READ_LEAVES-1];
            assign load_phys_map_read=reads[1];
            for(map_query_row=0;map_query_row<LSQ_MAP_READ_LEAVES;map_query_row=map_query_row+1) begin:g_row
                if(map_query_row<LSQ_ENTRIES) begin:g_present
                    wire [LSQ_MAP_READ_WORDS-1:0] selects;
                    wire hit=lsq_map_query_views[(map_query_row/4)*LSQ_SLOT_WIDTH +: LSQ_SLOT_WIDTH]==map_query_row;
                    rv32_frequency_control_tree #(.LEAVES(LSQ_MAP_READ_WORDS)) select_tree (
                        .signal_i(hit),.views_o(selects));
                    for(map_query_word=0;map_query_word<LSQ_MAP_READ_WORDS;map_query_word=map_query_word+1) begin:g_word
                        localparam integer LOW=map_query_word*16;
                        localparam integer BITS=(PAW-LOW>=16)?16:PAW-LOW;
                        assign reads[LSQ_MAP_READ_LEAVES+map_query_row][LOW +: BITS]=
                            {BITS{selects[map_query_word]}} & lsq_phys_mem[map_query_row][LOW +: BITS];
                    end
                end else begin:g_padding
                    assign reads[LSQ_MAP_READ_LEAVES+map_query_row]=0;
                end
            end
            for(map_query_node=1;map_query_node<LSQ_MAP_READ_LEAVES;map_query_node=map_query_node+1) begin:g_reduce
                assign reads[map_query_node]=reads[2*map_query_node] | reads[2*map_query_node+1];
            end
        end
    endgenerate
'''


def queries(t):
    t=change(t,'    wire [PAW-1:0] lsq_phys_mem [0:LSQ_ENTRIES-1];',
               '    wire [PAW-1:0] lsq_phys_mem [0:LSQ_ENTRIES-1];\n'+READS)
    old='rob_to_lsq_mem[alu_exec_tag[io_lane*TAG_WIDTH + 3 +: ROB_SLOT_WIDTH]]'
    if t.count(old)!=2: raise ValueError('Expected both AGU/data map queries')
    t=t.replace(old,'alu_lsq_map_read[io_lane*TAG_WIDTH +: TAG_WIDTH]')
    return change(t,'lsq_phys_mem[lsq_load_complete_lsq_tag[3 +: LSQ_SLOT_WIDTH]]','load_phys_map_read')


if __name__=='__main__':
    prepare('AY_bounded_backend_map_queries',ROOT/'AX_branch_capture_payload_owner',
            {'rtl/backend/rv32_backend_joint.v':queries},
            'AX plus four-row query domains and sixteen-bit local one-hot selection, binary reduction of ROB-to-LSQ and LSQ-to-physical maps at unchanged cycles; share AGU/data tag read, leave all live/generation acceptance qualification unchanged; no new FF/cycles, no EDA')
