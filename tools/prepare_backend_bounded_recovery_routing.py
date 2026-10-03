"""Bound branch recovery ROB/PRF routing while preserving all packet values."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


COMPLETION = r'''
    localparam integer ROB_COMPLETION_PACKET_WIDTH=TAG_WIDTH+103;
    localparam integer ROB_COMPLETION_PACKET_WORDS=(ROB_COMPLETION_PACKET_WIDTH+15)/16;
    wire [BE_WIDTH-1:0] completion_recovery_modes;
    rv32_frequency_control_tree #(.LEAVES(BE_WIDTH)) completion_recovery_tree (
        .signal_i(branch_pending),.views_o(completion_recovery_modes));
    genvar routed_lane,routed_word;
    generate for(routed_lane=0;routed_lane<BE_WIDTH;routed_lane=routed_lane+1) begin:g_rob_completion_route
        wire [ROB_SLOT_WIDTH-1:0] normal_slot=rob_wb_tag[routed_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
        wire normal_in_range=normal_slot<ROB_ENTRIES;
        wire normal_error=rob_wb_valid[routed_lane] && normal_in_range &&
            (load_error_mem[normal_slot] || completion_live_load_error[routed_lane]);
        wire [1:0] normal_size=rob_mem_size_mem[normal_slot];
        wire [3:0] normal_mask=(rob_wb_valid[routed_lane] && normal_in_range && cdb_is_store[routed_lane])?
            ((normal_size==`RV32IM_MEM_BYTE)?4'b0001:((normal_size==`RV32IM_MEM_HALF)?4'b0011:4'b1111)):4'b0;
        wire [ROB_COMPLETION_PACKET_WIDTH-1:0] normal_packet={
            (rob_wb_valid[routed_lane] && cdb_ready[routed_lane]),rob_wb_valid[routed_lane],normal_error,
            rob_wb_tag[routed_lane*TAG_WIDTH +: TAG_WIDTH],rob_wb_value[routed_lane*32 +: 32],
            cdb_addr[routed_lane*32 +: 32],normal_mask,cdb_store_data[routed_lane*32 +: 32]};
        wire [ROB_COMPLETION_PACKET_WIDTH-1:0] recovery_packet,routed_packet;
        if(routed_lane==0) begin:g_branch
            assign recovery_packet={1'b1,1'b1,1'b0,recovery_tag_views[0 +: TAG_WIDTH],branch_pending_value,
                32'b0,4'b0,32'b0};
        end else if(routed_lane-1<CDB_WIDTH-1) begin:g_shifted
            localparam integer SOURCE=routed_lane-1;
            wire accepted=rob_wb_valid[SOURCE] && cdb_ready[SOURCE];
            wire [ROB_SLOT_WIDTH-1:0] slot=rob_wb_tag[SOURCE*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
            wire in_range=slot<ROB_ENTRIES;
            wire error=(load_error_mem[slot] || completion_live_load_error[SOURCE]) && in_range;
            wire [1:0] size=rob_mem_size_mem[slot];
            wire [3:0] mask=(in_range && cdb_is_store[SOURCE])?
                ((size==`RV32IM_MEM_BYTE)?4'b0001:((size==`RV32IM_MEM_HALF)?4'b0011:4'b1111)):4'b0;
            wire [63:0] store_payload;
            rv32_frequency_event_select #(.WIDTH(64),.EVENTS(1)) store_selector (
                .events_i(in_range),.values_i({cdb_addr[SOURCE*32 +: 32],cdb_store_data[SOURCE*32 +: 32]}),
                .write_o(),.value_o(store_payload));
            rv32_frequency_event_select #(.WIDTH(ROB_COMPLETION_PACKET_WIDTH),.EVENTS(1)) accepted_selector (
                .events_i(accepted),
                .values_i({1'b1,1'b1,error,rob_wb_tag[SOURCE*TAG_WIDTH +: TAG_WIDTH],rob_wb_value[SOURCE*32 +: 32],
                    store_payload[63:32],mask,store_payload[31:0]}),.write_o(),.value_o(recovery_packet));
        end else begin:g_unavailable
            assign recovery_packet=0;
        end
        wire [ROB_COMPLETION_PACKET_WORDS-1:0] mode_views;
        rv32_frequency_control_tree #(.LEAVES(ROB_COMPLETION_PACKET_WORDS)) lane_mode_tree (
            .signal_i(completion_recovery_modes[routed_lane]),.views_o(mode_views));
        for(routed_word=0;routed_word<ROB_COMPLETION_PACKET_WORDS;routed_word=routed_word+1) begin:g_word
            localparam integer LOW=routed_word*16;
            localparam integer BITS=(ROB_COMPLETION_PACKET_WIDTH-LOW>=16)?16:ROB_COMPLETION_PACKET_WIDTH-LOW;
            assign routed_packet[LOW +: BITS]=mode_views[routed_word]?
                recovery_packet[LOW +: BITS]:normal_packet[LOW +: BITS];
        end
        assign {completion_valid_r[routed_lane],completion_done_r[routed_lane],completion_error_r[routed_lane],
            completion_tag_r[routed_lane*TAG_WIDTH +: TAG_WIDTH],completion_value_r[routed_lane*32 +: 32],
            completion_store_addr_r[routed_lane*32 +: 32],completion_store_mask_r[routed_lane*4 +: 4],
            completion_store_data_r[routed_lane*32 +: 32]}=routed_packet;
    end endgenerate
'''


PRF = r'''            if(io_lane==CDB_WIDTH-1) begin:g_branch_link_route
                localparam integer PHYS_WORDS=(PAW+15)/16;
                wire [PHYS_WORDS+2:0] link_views;
                rv32_frequency_control_tree #(.LEAVES(PHYS_WORDS+3)) link_tree (
                    .signal_i(branch_pending && branch_pending_rd_we),.views_o(link_views));
                assign prf_write_valid[io_lane]=link_views[PHYS_WORDS+2] || completion_prf_write_valid[io_lane];
                for(link_word=0;link_word<PHYS_WORDS;link_word=link_word+1) begin:g_phys_word
                    localparam integer LOW=link_word*16;
                    localparam integer BITS=(PAW-LOW>=16)?16:PAW-LOW;
                    assign prf_write_phys[io_lane*PAW+LOW +: BITS]=link_views[link_word]?
                        branch_pending_phys[LOW +: BITS]:completion_prf_write_phys[io_lane*PAW+LOW +: BITS];
                end
                for(link_word=0;link_word<2;link_word=link_word+1) begin:g_value_word
                    assign prf_write_data[io_lane*32+link_word*16 +: 16]=link_views[PHYS_WORDS+link_word]?
                        branch_pending_value[link_word*16 +: 16]:completion_prf_write_data[io_lane*32+link_word*16 +: 16];
                end
            end else begin:g_normal_link_route
                assign prf_write_valid[io_lane]=completion_prf_write_valid[io_lane];
                assign prf_write_phys[io_lane*PAW +: PAW]=completion_prf_write_phys[io_lane*PAW +: PAW];
                assign prf_write_data[io_lane*32 +: 32]=completion_prf_write_data[io_lane*32 +: 32];
            end
'''


def routing(t):
    for old in ['    reg [BE_WIDTH-1:0] completion_valid_r, completion_done_r, completion_error_r;',
                '    reg [BE_WIDTH*TAG_WIDTH-1:0] completion_tag_r;',
                '    reg [BE_WIDTH*32-1:0] completion_value_r, completion_store_addr_r;',
                '    reg [BE_WIDTH*4-1:0] completion_store_mask_r;',
                '    reg [BE_WIDTH*32-1:0] completion_store_data_r;']:
        t=change(t,old,old.replace('reg ','wire ',1))
    for old in ['    integer completion_lane;\n','    integer completion_source;\n','    integer completion_slot;\n']:
        t=change(t,old,'')
    a=t.index('    always @* begin\n        completion_valid_r =')
    b=t.index('    // R-stage metadata',a)
    t=t[:a]+COMPLETION+'\n'+t[b:]
    t=change(t,'    genvar io_lane;','    genvar io_lane,link_word;')
    a=t.index('            assign prf_write_valid[io_lane] =')
    b=t.index('        end\n    endgenerate',a)
    return t[:a]+PRF+t[b:]


if __name__=='__main__':
    prepare('BH_bounded_backend_recovery_routing',ROOT/'BG_bounded_cache_response_outputs',
            {'rtl/backend/rv32_backend_joint.v':routing},
            'BG plus ROB completion normal/recovery routing and branch-link PRF writeback with sixteen-bit final mode/qualification leaves; preserve lane-zero recovery, shifted accepted CDB sources, narrow error/mask conditions and zero inactive shifted packet values; no new FF/cycles and no EDA')
