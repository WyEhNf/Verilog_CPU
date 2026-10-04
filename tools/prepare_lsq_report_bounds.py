"""Factor exact LSQ report membership into one unwrapped endpoint; no HDL tools."""
from prepare_staged_frequency_candidate import ROOT,change,prepare


def bounds(t):
    t=change(t, '''    localparam integer REPORT_WORDS=(REPORT_WIDTH+15)/16;
    localparam integer ACK_WORDS=(ACK_WIDTH+15)/16;''',
        '''    localparam integer REPORT_WORDS=(REPORT_WIDTH+15)/16;
    localparam integer ACK_WORDS=(ACK_WIDTH+15)/16;
    localparam integer REPORT_BOUND_WIDTH=((COUNT_WIDTH>SLOT_WIDTH)?COUNT_WIDTH:SLOT_WIDTH)+1;
    localparam integer REPORT_BOUND_DOMAINS=(LSQ_ENTRIES+3)/4;
    localparam integer REPORT_AGE_MODULUS=1<<SLOT_WIDTH;
    // For fixed row r and modulo M: (r-head) mod M < count iff
    // head+count > r (r>=head), or > M+r (r<head). Keep the sum unwrapped.
    // This preserves the original guard without a head/tail state invariant.
    wire [REPORT_BOUND_WIDTH-1:0] report_end=
        {{(REPORT_BOUND_WIDTH-SLOT_WIDTH){1'b0}},head_reg}+
        {{(REPORT_BOUND_WIDTH-COUNT_WIDTH){1'b0}},occupancy_reg};
    wire [REPORT_BOUND_DOMAINS*REPORT_BOUND_WIDTH-1:0] report_bound_views;
    rv32_frequency_control_tree #(.WIDTH(REPORT_BOUND_WIDTH),.LEAVES(REPORT_BOUND_DOMAINS)) report_bound_tree (
        .signal_i(report_end),.views_o(report_bound_views));''')
    t=change(t, '''                assign report_valid_tree[REPORT_ROWS+report_row]=entry_age[report_row]<occupancy_reg &&
                    valid_mem[report_row] && load_mem[report_row] && complete_mem[report_row] && !load_reported_mem[report_row];''',
        '''                localparam integer ROW_MOD=report_row%REPORT_AGE_MODULUS;
                wire [REPORT_BOUND_WIDTH-1:0] row_end=
                    report_bound_views[(report_row/4)*REPORT_BOUND_WIDTH +: REPORT_BOUND_WIDTH];
                // Head query matches the original entry_age domain. Use
                // ROW_MOD so the algebra also retains explicit slot widths.
                wire wrapped=ROW_MOD<head_query_views[report_row*SLOT_WIDTH +: SLOT_WIDTH];
                wire row_in_report_range=wrapped ?
                    (row_end>REPORT_AGE_MODULUS+ROW_MOD) : (row_end>ROW_MOD);
                assign report_valid_tree[REPORT_ROWS+report_row]=row_in_report_range &&
                    valid_mem[report_row] && load_mem[report_row] && complete_mem[report_row] && !load_reported_mem[report_row];''')
    return t


if __name__=='__main__':
    prepare('DM_lsq_report_bounds',ROOT/'DL1_store_rs_link_domains',
        {'rtl/backend/rv32_lsq.v':bounds},
        'Replace only report age<count subtraction predicates with a shared widened head+count endpoint and fixed circular row thresholds, exact for empty/full/count overflow without trusting tail state; inherit linked store ownership and DH/DI/DJ/DK.')
