"""Preserve both queue-age mask and explicit slot widths in DM; source only."""
from prepare_staged_frequency_candidate import ROOT,change,prepare


def widths(t):
    t=change(t, '    localparam integer REPORT_AGE_MODULUS=1<<SLOT_WIDTH;',
        '''    // entry_age first masks by LSQ_ENTRIES-1, then truncates to
    // SLOT_WIDTH. Keep their effective power-of-two modulus, including N=1.
    localparam integer REPORT_AGE_MODULUS=
        (LSQ_ENTRIES<(1<<SLOT_WIDTH))?LSQ_ENTRIES:(1<<SLOT_WIDTH);''')
    t=change(t, '''    wire [REPORT_BOUND_WIDTH-1:0] report_end=
        {{(REPORT_BOUND_WIDTH-SLOT_WIDTH){1'b0}},head_reg}+''',
        '''    wire [SLOT_WIDTH-1:0] report_head=head_reg & (REPORT_AGE_MODULUS-1);
    wire [REPORT_BOUND_WIDTH-1:0] report_end=
        {{(REPORT_BOUND_WIDTH-SLOT_WIDTH){1'b0}},report_head}+''')
    t=change(t, '''                // Head query matches the original entry_age domain. Use
                // ROW_MOD so the algebra also retains explicit slot widths.
                wire wrapped=ROW_MOD<head_query_views[report_row*SLOT_WIDTH +: SLOT_WIDTH];''',
        '''                // Match the original queue mask and destination width
                // in both head and row. No tail/occupancy invariant is used.
                wire wrapped=ROW_MOD<
                    (head_query_views[report_row*SLOT_WIDTH +: SLOT_WIDTH] & (REPORT_AGE_MODULUS-1));''')
    return t


if __name__=='__main__':
    prepare('DM1_lsq_report_bound_widths',ROOT/'DM_lsq_report_bounds',
        {'rtl/backend/rv32_lsq.v':widths},
        'Retain the exact old masked-and-truncated queue-age modulus, including one-entry queues and explicit slot widths, in the shared report boundary algebra; source-reviewed correction before any HDL test.')
