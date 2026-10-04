"""Replace LSQ tournament age comparisons by circular keys; no HDL/EDA."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def lsq(source):
    source=change(source,'    wire [SLOT_WIDTH-1:0] entry_age [0:LSQ_ENTRIES-1];',
        '''    wire [SLOT_WIDTH-1:0] entry_age [0:LSQ_ENTRIES-1];
    // For ascending physical rows, age order is (row<head, row).
    // Only the wrap bit needs to traverse a balanced tournament: the
    // physical order of its left/right subtrees is already static.
    localparam integer CIRCULAR_ORDER_POWER2=((LSQ_ENTRIES & (LSQ_ENTRIES-1))==0);
    wire [7*LSQ_ENTRIES-1:0] circular_wrap_views;
    wire pick_wrap [1:2*LSQ_ENTRIES-1];
    generate for(genvar wrap_row=0;wrap_row<LSQ_ENTRIES;wrap_row=wrap_row+1) begin:g_circular_key
        rv32_frequency_control_tree #(.LEAVES(7)) wrap_tree (
            .signal_i(wrap_row<head_query_views[wrap_row*SLOT_WIDTH +: SLOT_WIDTH]),
            .views_o(circular_wrap_views[wrap_row*7 +: 7]));
        assign pick_wrap[LSQ_ENTRIES+wrap_row]=circular_wrap_views[wrap_row*7];
    end endgenerate''')
    source=change(source,'''                (!pick_valid[2*pick_node+1] || (pick_age[2*pick_node] <= pick_age[2*pick_node+1]));''',
        '''                (!pick_valid[2*pick_node+1] ||
                 (CIRCULAR_ORDER_POWER2 ? (!pick_wrap[2*pick_node] || pick_wrap[2*pick_node+1]) :
                  (pick_age[2*pick_node] <= pick_age[2*pick_node+1])));''')
    source=change(source,'            assign pick_age[pick_node] = choose_left ? pick_age[2*pick_node] : pick_age[2*pick_node+1];',
        '''            assign pick_age[pick_node] = choose_left ? pick_age[2*pick_node] : pick_age[2*pick_node+1];
            assign pick_wrap[pick_node] = choose_left ? pick_wrap[2*pick_node] : pick_wrap[2*pick_node+1];''')
    source=change(source,'            wire [SLOT_WIDTH-1:0] byte_age [1:2*LSQ_ENTRIES-1];',
        '''            wire [SLOT_WIDTH-1:0] byte_age [1:2*LSQ_ENTRIES-1];
            wire byte_wrap [1:2*LSQ_ENTRIES-1];''')
    source=change(source,'                assign byte_age[LSQ_ENTRIES+forward_slot] = entry_age[forward_slot];',
        '''                assign byte_age[LSQ_ENTRIES+forward_slot] = entry_age[forward_slot];
                assign byte_wrap[LSQ_ENTRIES+forward_slot] = circular_wrap_views[forward_slot*7+1+forward_byte];''')
    source=change(source,'''                    (!byte_valid[2*forward_node+1] || (byte_age[2*forward_node] >= byte_age[2*forward_node+1]));''',
        '''                    (!byte_valid[2*forward_node+1] ||
                     (CIRCULAR_ORDER_POWER2 ? (byte_wrap[2*forward_node] && !byte_wrap[2*forward_node+1]) :
                      (byte_age[2*forward_node] >= byte_age[2*forward_node+1])));''')
    source=change(source,'                assign byte_age[forward_node] = choose_left ? byte_age[2*forward_node] : byte_age[2*forward_node+1];',
        '''                assign byte_age[forward_node] = choose_left ? byte_age[2*forward_node] : byte_age[2*forward_node+1];
                assign byte_wrap[forward_node] = choose_left ? byte_wrap[2*forward_node] : byte_wrap[2*forward_node+1];''')
    source=change(source,'    wire [SLOT_WIDTH-1:0] report_slot_tree [1:2*REPORT_ROWS-1],report_age_tree [1:2*REPORT_ROWS-1];',
        '''    wire [SLOT_WIDTH-1:0] report_slot_tree [1:2*REPORT_ROWS-1];
    wire report_wrap_tree [1:2*REPORT_ROWS-1];''')
    source=change(source,'                assign report_age_tree[REPORT_ROWS+report_row]=entry_age[report_row];',
        '                assign report_wrap_tree[REPORT_ROWS+report_row]=circular_wrap_views[report_row*7+5];')
    source=change(source,'                assign report_age_tree[REPORT_ROWS+report_row]=0;',
        '                assign report_wrap_tree[REPORT_ROWS+report_row]=0;')
    source=change(source,'''                (!report_valid_tree[2*report_node+1] || report_age_tree[2*report_node]<=report_age_tree[2*report_node+1]);''',
        '''                (!report_valid_tree[2*report_node+1] ||
                 !report_wrap_tree[2*report_node] || report_wrap_tree[2*report_node+1]);''')
    source=change(source,'            assign report_age_tree[report_node]=choose_left?report_age_tree[2*report_node]:report_age_tree[2*report_node+1];',
        '            assign report_wrap_tree[report_node]=choose_left?report_wrap_tree[2*report_node]:report_wrap_tree[2*report_node+1];')
    source=change(source,'    wire [SLOT_WIDTH-1:0] recovery_kill_age_tree [1:2*LSQ_ENTRIES-1];',
        '''    wire [SLOT_WIDTH-1:0] recovery_kill_age_tree [1:2*LSQ_ENTRIES-1];
    wire recovery_kill_wrap_tree [1:2*LSQ_ENTRIES-1];''')
    source=change(source,'''             recovery_kill_age_tree[2*trim_node]<=recovery_kill_age_tree[2*trim_node+1]);''',
        '''             (CIRCULAR_ORDER_POWER2 ? (!recovery_kill_wrap_tree[2*trim_node] || recovery_kill_wrap_tree[2*trim_node+1]) :
              recovery_kill_age_tree[2*trim_node]<=recovery_kill_age_tree[2*trim_node+1]));''')
    source=change(source,'        assign recovery_kill_age_tree[trim_node]=choose_left?recovery_kill_age_tree[2*trim_node]:recovery_kill_age_tree[2*trim_node+1];',
        '''        assign recovery_kill_age_tree[trim_node]=choose_left?recovery_kill_age_tree[2*trim_node]:recovery_kill_age_tree[2*trim_node+1];
        assign recovery_kill_wrap_tree[trim_node]=choose_left?recovery_kill_wrap_tree[2*trim_node]:recovery_kill_wrap_tree[2*trim_node+1];''')
    source=change(source,'        assign recovery_kill_age_tree[LSQ_ENTRIES+metadata_row]=lsq_age;',
        '''        assign recovery_kill_age_tree[LSQ_ENTRIES+metadata_row]=lsq_age;
        assign recovery_kill_wrap_tree[LSQ_ENTRIES+metadata_row]=circular_wrap_views[metadata_row*7+6];''')
    return source


if __name__=='__main__':
    prepare('DC_lsq_circular_priority',ROOT/'DB_load_local_wake',
        {'rtl/backend/rv32_lsq.v':lsq},
        'Circular LSQ report/pick/recovery oldest and four per-byte youngest forward tournaments use one-bit wrap keys; nonpower2 unpadded trees retain original age comparison; eligibility/age payload/state/edges unchanged; no HDL/EDA tests')
