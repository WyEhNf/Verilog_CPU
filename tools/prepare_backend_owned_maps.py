"""Row-owned R-stage metadata and D-stage maps, source preparation only."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


OWNERS = r'''
    // R-stage metadata and D-stage maps are payloads. A valid ROB/LSQ
    // transaction always allocates these rows before a consumer can use them.
    // Reset clears the transaction validity in its owner, not these payloads.
    localparam integer MAP_DOMAINS=4;
    localparam integer R_META_WIDTH=2+((RS_ISSUE_METADATA==0)?100:0)+
        ((PREDICTOR_META!=0)?16:0);
    wire [MAP_DOMAINS*BE_WIDTH-1:0] r_map_writes,d_map_writes;
    wire [MAP_DOMAINS*BE_WIDTH*ROB_SLOT_WIDTH-1:0] r_map_slots,d_rob_map_slots;
    wire [MAP_DOMAINS*BE_WIDTH*LSQ_SLOT_WIDTH-1:0] d_lsq_map_slots;
    wire [MAP_DOMAINS*BE_WIDTH*R_META_WIDTH-1:0] r_map_values;
    wire [MAP_DOMAINS*BE_WIDTH*TAG_WIDTH-1:0] d_rob_map_values;
    wire [MAP_DOMAINS*BE_WIDTH*PAW-1:0] d_lsq_map_values;
    wire [BE_WIDTH*ROB_SLOT_WIDTH-1:0] r_slot_input,d_rob_slot_input;
    wire [BE_WIDTH*LSQ_SLOT_WIDTH-1:0] d_lsq_slot_input;
    wire [BE_WIDTH*R_META_WIDTH-1:0] r_metadata_input;
    wire [ROB_ENTRIES-1:0] error_reset_views,error_response_views;
    wire [MAP_DOMAINS*ROB_SLOT_WIDTH-1:0] error_slot_views;
    wire error_response=lsq_load_complete_valid && lsq_load_complete_ready &&
        lsq_load_complete_error && lsq_load_complete_tag[0] &&
        lsq_load_complete_tag[3 +: ROB_SLOT_WIDTH]<ROB_ENTRIES &&
        rob_entry_valid[lsq_load_complete_tag[3 +: ROB_SLOT_WIDTH]] &&
        lsq_load_complete_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]==
        rob_entry_generation[lsq_load_complete_tag[3 +: ROB_SLOT_WIDTH]*ROB_GENERATION_WIDTH +: ROB_GENERATION_WIDTH];
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(MAP_DOMAINS)) r_write_tree (
        .signal_i(dispatch_valid & rob_alloc_fire & {BE_WIDTH{!reset_i}}),.views_o(r_map_writes));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(MAP_DOMAINS)) d_write_tree (
        .signal_i(d_valid & lsq_alloc_fire & {BE_WIDTH{!reset_i}}),.views_o(d_map_writes));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*ROB_SLOT_WIDTH),.LEAVES(MAP_DOMAINS)) r_slot_tree (
        .signal_i(r_slot_input),.views_o(r_map_slots));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*ROB_SLOT_WIDTH),.LEAVES(MAP_DOMAINS)) d_rob_slot_tree (
        .signal_i(d_rob_slot_input),.views_o(d_rob_map_slots));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*LSQ_SLOT_WIDTH),.LEAVES(MAP_DOMAINS)) d_lsq_slot_tree (
        .signal_i(d_lsq_slot_input),.views_o(d_lsq_map_slots));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*R_META_WIDTH),.LEAVES(MAP_DOMAINS)) r_value_tree (
        .signal_i(r_metadata_input),.views_o(r_map_values));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*TAG_WIDTH),.LEAVES(MAP_DOMAINS)) d_rob_value_tree (
        .signal_i(lsq_alloc_tag),.views_o(d_rob_map_values));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PAW),.LEAVES(MAP_DOMAINS)) d_lsq_value_tree (
        .signal_i(d_new_phys),.views_o(d_lsq_map_values));
    rv32_frequency_control_tree #(.LEAVES(ROB_ENTRIES)) error_reset_tree (
        .signal_i(reset_i),.views_o(error_reset_views));
    rv32_frequency_control_tree #(.LEAVES(ROB_ENTRIES)) error_response_tree (
        .signal_i(error_response),.views_o(error_response_views));
    rv32_frequency_control_tree #(.WIDTH(ROB_SLOT_WIDTH),.LEAVES(MAP_DOMAINS)) error_slot_tree (
        .signal_i(lsq_load_complete_tag[3 +: ROB_SLOT_WIDTH]),.views_o(error_slot_views));
    genvar map_row,map_lane_id;
    generate
        for(map_lane_id=0;map_lane_id<BE_WIDTH;map_lane_id=map_lane_id+1) begin:g_map_input
            assign r_slot_input[map_lane_id*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]=
                rob_alloc_tag[map_lane_id*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
            assign d_rob_slot_input[map_lane_id*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]=
                d_tag[map_lane_id*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
            assign d_lsq_slot_input[map_lane_id*LSQ_SLOT_WIDTH +: LSQ_SLOT_WIDTH]=
                lsq_alloc_tag[map_lane_id*TAG_WIDTH+3 +: LSQ_SLOT_WIDTH];
            assign r_metadata_input[map_lane_id*R_META_WIDTH +: 2]=trace_mem_size_i[map_lane_id*2 +: 2];
            if(RS_ISSUE_METADATA==0) begin:g_legacy
                assign r_metadata_input[map_lane_id*R_META_WIDTH+2 +: 100]={
                    trace_mem_unsigned_i[map_lane_id],trace_pred_kind_i[map_lane_id*2 +: 2],
                    trace_pred_target_i[map_lane_id*32 +: 32],trace_pred_taken_i[map_lane_id],
                    trace_imm_i[map_lane_id*32 +: 32],trace_pc_i[map_lane_id*32 +: 32]};
            end
            if(PREDICTOR_META!=0) begin:g_history
                assign r_metadata_input[map_lane_id*R_META_WIDTH+2+((RS_ISSUE_METADATA==0)?100:0) +: 16]=
                    trace_pred_metadata_i[map_lane_id*16 +: 16];
            end
        end
        for(map_row=0;map_row<ROB_ENTRIES;map_row=map_row+1) begin:g_rob_map_row
            localparam integer DOMAIN=(map_row*MAP_DOMAINS)/ROB_ENTRIES;
            wire [BE_WIDTH-1:0] r_matches,d_matches;
            wire r_write,d_write;
            wire [R_META_WIDTH-1:0] r_value,r_saved;
            wire [TAG_WIDTH-1:0] d_value;
            for(map_lane_id=0;map_lane_id<BE_WIDTH;map_lane_id=map_lane_id+1) begin:g_match
                assign r_matches[map_lane_id]=r_map_writes[DOMAIN*BE_WIDTH+map_lane_id] &&
                    r_map_slots[(DOMAIN*BE_WIDTH+map_lane_id)*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]==map_row;
                assign d_matches[map_lane_id]=d_map_writes[DOMAIN*BE_WIDTH+map_lane_id] &&
                    d_rob_map_slots[(DOMAIN*BE_WIDTH+map_lane_id)*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]==map_row;
            end
            rv32_frequency_event_select #(.WIDTH(R_META_WIDTH),.EVENTS(BE_WIDTH)) r_select (
                .events_i(r_matches),.values_i(r_map_values[DOMAIN*BE_WIDTH*R_META_WIDTH +: BE_WIDTH*R_META_WIDTH]),
                .write_o(r_write),.value_o(r_value));
            rv32_frequency_word_bank #(.WIDTH(R_META_WIDTH)) r_owner (
                .clk_i(clk_i),.write_i(r_write),.data_i(r_value),.data_o(r_saved));
            assign rob_mem_size_mem[map_row]=r_saved[0 +: 2];
            if(RS_ISSUE_METADATA==0) begin:g_legacy
                assign {rob_mem_unsigned_mem[map_row],rob_pred_kind_mem[map_row],rob_pred_target_mem[map_row],
                    rob_pred_taken_mem[map_row],rob_imm_mem[map_row],rob_pc_mem[map_row]}=r_saved[2 +: 100];
            end else begin:g_inline
                assign rob_mem_unsigned_mem[map_row]=0;
                assign rob_pred_kind_mem[map_row]=0;
                assign rob_pred_target_mem[map_row]=0;
                assign rob_pred_taken_mem[map_row]=0;
                assign rob_imm_mem[map_row]=0;
                assign rob_pc_mem[map_row]=0;
            end
            if(PREDICTOR_META!=0) begin:g_history
                assign rob_pred_metadata_mem[map_row]=r_saved[2+((RS_ISSUE_METADATA==0)?100:0) +: 16];
            end else begin:g_no_history
                assign rob_pred_metadata_mem[map_row]=0;
            end
            rv32_frequency_event_select #(.WIDTH(TAG_WIDTH),.EVENTS(BE_WIDTH)) d_select (
                .events_i(d_matches),.values_i(d_rob_map_values[DOMAIN*BE_WIDTH*TAG_WIDTH +: BE_WIDTH*TAG_WIDTH]),
                .write_o(d_write),.value_o(d_value));
            rv32_frequency_word_bank #(.WIDTH(TAG_WIDTH)) d_owner (
                .clk_i(clk_i),.write_i(d_write),.data_i(d_value),.data_o(rob_to_lsq_mem[map_row]));
            reg error_q;
            assign load_error_mem[map_row]=error_q;
            always @(posedge clk_i) begin
                if(error_reset_views[map_row]) error_q<=1'b0;
                else if(error_response_views[map_row] &&
                        error_slot_views[DOMAIN*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]==map_row) error_q<=1'b1;
                else if(r_write) error_q<=1'b0;
            end
        end
        for(map_row=0;map_row<LSQ_ENTRIES;map_row=map_row+1) begin:g_lsq_phys_row
            localparam integer DOMAIN=(map_row*MAP_DOMAINS)/LSQ_ENTRIES;
            wire [BE_WIDTH-1:0] matches;
            wire write_enable;
            wire [PAW-1:0] next_phys;
            for(map_lane_id=0;map_lane_id<BE_WIDTH;map_lane_id=map_lane_id+1) begin:g_match
                assign matches[map_lane_id]=d_map_writes[DOMAIN*BE_WIDTH+map_lane_id] &&
                    d_lsq_map_slots[(DOMAIN*BE_WIDTH+map_lane_id)*LSQ_SLOT_WIDTH +: LSQ_SLOT_WIDTH]==map_row;
            end
            rv32_frequency_event_select #(.WIDTH(PAW),.EVENTS(BE_WIDTH)) selector (
                .events_i(matches),.values_i(d_lsq_map_values[DOMAIN*BE_WIDTH*PAW +: BE_WIDTH*PAW]),
                .write_o(write_enable),.value_o(next_phys));
            rv32_frequency_word_bank #(.WIDTH(PAW)) owner (
                .clk_i(clk_i),.write_i(write_enable),.data_i(next_phys),.data_o(lsq_phys_mem[map_row]));
        end
    endgenerate
'''


def own(t):
    names=['rob_to_lsq_mem','lsq_phys_mem','rob_pc_mem','load_error_mem','rob_imm_mem',
           'rob_pred_taken_mem','rob_pred_target_mem','rob_pred_kind_mem',
           'rob_mem_size_mem','rob_mem_unsigned_mem','rob_pred_metadata_mem']
    import re
    for name in names:
        pattern=r'    reg (\[[^\n]*?\] )?'+name+r' (\[0:[^\n]*\]);'
        t,n=re.subn(pattern,lambda m:'    wire '+(m[1] or '')+name+' '+m[2]+';',t)
        if n!=1: raise ValueError('Missing payload declaration '+name)
    start=t.index('    integer d_map_lane,d_map_reset;')
    stop=t.index('\n    assign rob_store_ack_valid',start)
    t=t[:start]+OWNERS+t[stop:]
    start=t.index('            for (map_index = 0; map_index < ROB_ENTRIES;')
    stop=t.index('\n        end else begin',start)
    t=t[:start]+t[stop:]
    start=t.index('            for (map_lane = 0; map_lane < BE_WIDTH;')
    stop=t.index('\n        end\n    end\nendmodule',start)
    t=t[:start]+t[stop:]
    # Remove obsolete procedural loop temporaries; never rewrite a comparison.
    for decl in ['    integer map_index;\n','    integer map_lane;\n','    integer map_rob_slot;\n',
                 '    integer map_lsq_slot;\n','    integer map_phys_slot;\n']:
        t=change(t,decl,'')
    return t


if __name__=='__main__':
    prepare('AN_backend_owned_transaction_maps',ROOT/'AM_valid_alu_redirect_ownership',
            {'rtl/backend/rv32_backend_joint.v':own},
            'AM plus row-local highest-lane R metadata and D ROB/LSQ mappings, conditional removal of unused legacy metadata, no payload reset and bounded selects; same capture edges/no extra registers or cycles; error flags retain reset and allocation-clear/error-set order with ROB generation qualification; source only, no EDA')
