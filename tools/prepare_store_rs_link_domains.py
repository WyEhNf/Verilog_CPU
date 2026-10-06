"""Bound store-link input groups without per-row tree duplication; no HDL tools."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def domains(t):
    start=t.index('module rv32_store_rs_links #(')
    owner=t[start:]
    owner=change(owner, '    localparam integer LANE_WIDTH=LSQ_SW+RS_SW+2;',
        '''    localparam integer LANE_WIDTH=LSQ_SW+RS_SW+2;
    localparam integer DOMAINS=(LSQ_ENTRIES+3)/4;''')
    owner=change(owner, 'wire [LSQ_ENTRIES*BE_WIDTH*LANE_WIDTH-1:0] allocation_views;',
        'wire [DOMAINS*BE_WIDTH*LANE_WIDTH-1:0] allocation_views;')
    owner=change(owner, 'wire [LSQ_ENTRIES*RS_ENTRIES-1:0] release_views;',
        'wire [DOMAINS*RS_ENTRIES-1:0] release_views;')
    owner=change(owner, 'wire [LSQ_ENTRIES-1:0] reset_views,flush_views,recovery_views;',
        '''// Each control/field leaf reaches at most four short link owners.
    wire [DOMAINS-1:0] reset_views,flush_views,recovery_views;''')
    assert owner.count('.LEAVES(LSQ_ENTRIES)')==5
    owner=owner.replace('.LEAVES(LSQ_ENTRIES)','.LEAVES(DOMAINS)')
    owner=change(owner,'allocation_views[(row*BE_WIDTH+lane)*LANE_WIDTH +: LANE_WIDTH]',
        'allocation_views[((row/4)*BE_WIDTH+lane)*LANE_WIDTH +: LANE_WIDTH]')
    owner=change(owner,'release_views[row*RS_ENTRIES+entry]',
        'release_views[(row/4)*RS_ENTRIES+entry]')
    for name in ('reset','flush','recovery'):
        owner=change(owner,f'{name}_views[row]',f'{name}_views[row/4]')
    return t[:start]+owner


if __name__=='__main__':
    prepare('DL1_store_rs_link_domains',ROOT/'DL_store_rs_links',
        {'rtl/backend/rv32_store_address_select.v':domains},
        'Keep dispatch-owned store/RS links while grouping allocation/release/control input distribution into four-row domains; avoid surplus preserved tree cells and retain 80-bit lifetime state.')
