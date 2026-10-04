"""Keep the reclaim predecode well-sized for PHYS_ADDR_WIDTH=1; no HDL/EDA."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def rob(source):
    source=change(source,'    localparam integer RECLAIM_HIGH_WIDTH=PHYS_ADDR_WIDTH-RECLAIM_LOW_WIDTH;',
                        '''    localparam integer RECLAIM_HIGH_WIDTH=PHYS_ADDR_WIDTH-RECLAIM_LOW_WIDTH;
    localparam integer RECLAIM_HIGH_SLICE_WIDTH=(RECLAIM_HIGH_WIDTH<1)?1:RECLAIM_HIGH_WIDTH;''')
    source=change(source,'            wire [PHYS_ADDR_WIDTH-1:0] destination=new_phys_mem[reclaim_decode_row];',
                        '''            wire [PHYS_ADDR_WIDTH-1:0] destination=new_phys_mem[reclaim_decode_row];
            wire [RECLAIM_HIGH_SLICE_WIDTH-1:0] high_destination=destination>>RECLAIM_LOW_WIDTH;''')
    source=change(source,'''                if(RECLAIM_HIGH_WIDTH>0) begin:g_present
                    assign high_decode[high_code]=reclaim_eligible[reclaim_decode_row] &&
                        destination[RECLAIM_LOW_WIDTH +: RECLAIM_HIGH_WIDTH]==RECLAIM_HIGH_WIDTH'(high_code);
                end else begin:g_single_code
                    assign high_decode[high_code]=reclaim_eligible[reclaim_decode_row];
                end''','''                // No zero-width part-select/cast even at PHYS_ADDR_WIDTH=1.
                // In that case the sole high_destination/code is constant0.
                assign high_decode[high_code]=reclaim_eligible[reclaim_decode_row] &&
                    high_destination==RECLAIM_HIGH_SLICE_WIDTH'(high_code);''')
    return source


if __name__=='__main__':
    prepare('CU1_rob_reclaim_width_guard',ROOT/'CU_rob_reclaim_predecode',{
        'rtl/backend/rv32_rob.v':rob,
    }, 'CU with nonzero high predecode slice width for PHYS_ADDR_WIDTH=1, represented by a shifted high address and a single zero code. Current PHYS64 circuit and all decoded destinations, eligibility and cycle/state behavior unchanged. No HDL/EDA tests; parameter/source preparation only.')
