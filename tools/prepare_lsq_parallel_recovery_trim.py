"""Parallelize LSQ recovery trimming; source-only, never invoke HDL tools."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def lsq(source):
    source=change(source,'    wire [RECOVERY_ARITH_WIDTH-1:0] payload_branch_age=payload_recovery_age(recovery_tag_i);','''    wire [RECOVERY_ARITH_WIDTH-1:0] payload_branch_age=payload_recovery_age(recovery_tag_i);
    localparam integer OWNER_RECOVERY_WIDTH=ROB_SLOT_WIDTH+RECOVERY_ARITH_WIDTH+16;
    wire [LSQ_ENTRIES*OWNER_RECOVERY_WIDTH-1:0] owner_recovery_views;
    rv32_frequency_control_tree #(.WIDTH(OWNER_RECOVERY_WIDTH),.LEAVES(LSQ_ENTRIES)) owner_recovery_tree (
        .signal_i({recovery_head_i,payload_branch_age,recovery_occupancy_i}),.views_o(owner_recovery_views));
    function [RECOVERY_ARITH_WIDTH-1:0] payload_owner_recovery_age;
        input [ROB_TAG_WIDTH-1:0] tag;
        input [ROB_SLOT_WIDTH-1:0] local_head;
        reg [RECOVERY_ARITH_WIDTH-1:0] difference;
        begin
            difference=tag[3 +: ROB_SLOT_WIDTH]-local_head;
            if(((ROB_ENTRIES & (ROB_ENTRIES-1))!=0) && difference[RECOVERY_ARITH_WIDTH-1])
                difference=difference+ROB_ENTRIES;
            payload_owner_recovery_age=difference;
        end
    endfunction
    // Count retained live rows and locate the oldest killed row in parallel.
    // Four merge levels replace sixteen conditional integer accumulations
    // for the current queue, on the same recovery edge and with no new FF.
    wire [COUNT_WIDTH-1:0] recovery_keep_tree [1:2*LSQ_ENTRIES-1];
    wire recovery_kill_tree [1:2*LSQ_ENTRIES-1];
    wire [SLOT_WIDTH-1:0] recovery_kill_age_tree [1:2*LSQ_ENTRIES-1];
    wire [SLOT_WIDTH-1:0] recovery_kill_slot_tree [1:2*LSQ_ENTRIES-1];
    generate for(genvar trim_node=1;trim_node<LSQ_ENTRIES;trim_node=trim_node+1) begin:g_recovery_trim
        wire choose_left=recovery_kill_tree[2*trim_node] &&
            (!recovery_kill_tree[2*trim_node+1] ||
             recovery_kill_age_tree[2*trim_node]<=recovery_kill_age_tree[2*trim_node+1]);
        assign recovery_keep_tree[trim_node]=recovery_keep_tree[2*trim_node]+recovery_keep_tree[2*trim_node+1];
        assign recovery_kill_tree[trim_node]=recovery_kill_tree[2*trim_node] || recovery_kill_tree[2*trim_node+1];
        assign recovery_kill_age_tree[trim_node]=choose_left?recovery_kill_age_tree[2*trim_node]:recovery_kill_age_tree[2*trim_node+1];
        assign recovery_kill_slot_tree[trim_node]=choose_left?recovery_kill_slot_tree[2*trim_node]:recovery_kill_slot_tree[2*trim_node+1];
    end endgenerate''')
    source=change(source,'''            wire [RECOVERY_ARITH_WIDTH-1:0] row_age=payload_recovery_age(rob_tag_mem[payload_row]);
            assign result_events[1]=enabled && response_fire && response_slot_views[payload_row*SLOT_WIDTH +: SLOT_WIDTH]==payload_row &&
                (!recovery || !(row_age>payload_branch_age && row_age<recovery_occupancy_i));''','''            wire [ROB_SLOT_WIDTH-1:0] local_recovery_head;
            wire [RECOVERY_ARITH_WIDTH-1:0] local_branch_age;
            wire [15:0] local_recovery_occupancy;
            assign {local_recovery_head,local_branch_age,local_recovery_occupancy}=
                owner_recovery_views[payload_row*OWNER_RECOVERY_WIDTH +: OWNER_RECOVERY_WIDTH];
            wire [RECOVERY_ARITH_WIDTH-1:0] row_age=payload_owner_recovery_age(rob_tag_mem[payload_row],local_recovery_head);
            assign result_events[1]=enabled && response_fire && response_slot_views[payload_row*SLOT_WIDTH +: SLOT_WIDTH]==payload_row &&
                (!recovery || !(row_age>local_branch_age && row_age<local_recovery_occupancy));''')
    source=change(source,'''        wire [RECOVERY_ARITH_WIDTH-1:0] row_rob_age=payload_recovery_age(rob_tag_mem[metadata_row]);
        wire kill=lsq_age<occupancy_reg && valid_mem[metadata_row] &&
            !(store_mem[metadata_row] && store_commit_mem[metadata_row]) &&
            !(load_mem[metadata_row] && retired_mem[metadata_row]) &&
            row_rob_age>payload_branch_age && row_rob_age<recovery_occupancy_i;
        wire response_allowed=!(row_rob_age>payload_branch_age && row_rob_age<recovery_occupancy_i);''','''        wire [ROB_SLOT_WIDTH-1:0] local_recovery_head;
        wire [RECOVERY_ARITH_WIDTH-1:0] local_branch_age;
        wire [15:0] local_recovery_occupancy;
        assign {local_recovery_head,local_branch_age,local_recovery_occupancy}=
            owner_recovery_views[metadata_row*OWNER_RECOVERY_WIDTH +: OWNER_RECOVERY_WIDTH];
        wire [RECOVERY_ARITH_WIDTH-1:0] row_rob_age=payload_owner_recovery_age(rob_tag_mem[metadata_row],local_recovery_head);
        wire kill=lsq_age<occupancy_reg && valid_mem[metadata_row] &&
            !(store_mem[metadata_row] && store_commit_mem[metadata_row]) &&
            !(load_mem[metadata_row] && retired_mem[metadata_row]) &&
            row_rob_age>local_branch_age && row_rob_age<local_recovery_occupancy;
        wire response_allowed=!(row_rob_age>local_branch_age && row_rob_age<local_recovery_occupancy);
        assign recovery_keep_tree[LSQ_ENTRIES+metadata_row]=
            (lsq_age<occupancy_reg && valid_mem[metadata_row] && !kill)?1:0;
        assign recovery_kill_tree[LSQ_ENTRIES+metadata_row]=kill;
        assign recovery_kill_age_tree[LSQ_ENTRIES+metadata_row]=lsq_age;
        assign recovery_kill_slot_tree[LSQ_ENTRIES+metadata_row]=metadata_row;''')
    start=source.index('            recovery_keep_count = 0;')
    end=source.index('            for (update_slot = 0;',start)
    scan=source[start:end]
    if scan.count('recovery_keep_count = recovery_keep_count + 1;')!=1 or scan.count('recovery_first_killed = scan;')!=1:
        raise ValueError('Unexpected recovery scan')
    source=source[:start]+'''            recovery_keep_count = recovery_keep_tree[1];
            recovery_first_killed = recovery_kill_tree[1]?recovery_kill_slot_tree[1]:tail_reg;
            recovery_kill_found = recovery_kill_tree[1];
'''+source[end:]
    return source


if __name__=='__main__':
    prepare('CL_lsq_parallel_recovery_trim',ROOT/'CK_lsq_selection_query_distribution',{
        'rtl/backend/rv32_lsq.v':lsq,
    },'CK plus distributed row-local recovery boundaries and balanced live-retention sum/oldest-killed selection replacing head-relative16-step conditional integer scan. Same predicate, committed-store/retired-load protection, invalid-hole handling, tail fallback, occupancy and edge. No FF/cycle/SRAM change; unadopted source-only candidate, no HDL/EDA/simulation.')
