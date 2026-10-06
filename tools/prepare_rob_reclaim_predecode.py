"""Bound ROB reclaim destination decode consumers from CT; no HDL/EDA."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def rob(source):
    source=change(source,'    wire [PHYS_REGS-1:0] reclaim_bitmap;','''    wire [PHYS_REGS-1:0] reclaim_bitmap;
    localparam integer RECLAIM_LOW_WIDTH=(PHYS_ADDR_WIDTH/2<1)?1:PHYS_ADDR_WIDTH/2;
    localparam integer RECLAIM_HIGH_WIDTH=PHYS_ADDR_WIDTH-RECLAIM_LOW_WIDTH;
    localparam integer RECLAIM_LOW_CODES=1<<RECLAIM_LOW_WIDTH;
    localparam integer RECLAIM_HIGH_CODES=1<<RECLAIM_HIGH_WIDTH;
    wire [ROB_ENTRIES*PHYS_REGS-1:0] reclaim_row_destinations;''')
    anchor='        for (reclaim_phys = 0; reclaim_phys < RECLAIM_LEAVES; reclaim_phys = reclaim_phys + 1) begin : g_reclaim_phys'
    source=change(source,anchor,'''        // Qualify the small high predecode before the cross-product. With
        // PHYS64 each eligibility source owns eight decode consumers rather
        // than one comparison/qualification gate for every physical register.
        // Kept inversion boundaries retain the two predecode domains through
        // course ABC; each current predecode bit has <=eight final consumers.
        for(genvar reclaim_decode_row=0;reclaim_decode_row<ROB_ENTRIES;reclaim_decode_row=reclaim_decode_row+1) begin:g_reclaim_destination_row
            wire [PHYS_ADDR_WIDTH-1:0] destination=new_phys_mem[reclaim_decode_row];
            wire [RECLAIM_LOW_CODES-1:0] low_decode,low_views;
            wire [RECLAIM_HIGH_CODES-1:0] high_decode,high_views;
            for(genvar low_code=0;low_code<RECLAIM_LOW_CODES;low_code=low_code+1) begin:g_low_code
                assign low_decode[low_code]=destination[0 +: RECLAIM_LOW_WIDTH]==RECLAIM_LOW_WIDTH'(low_code);
            end
            for(genvar high_code=0;high_code<RECLAIM_HIGH_CODES;high_code=high_code+1) begin:g_high_code
                if(RECLAIM_HIGH_WIDTH>0) begin:g_present
                    assign high_decode[high_code]=reclaim_eligible[reclaim_decode_row] &&
                        destination[RECLAIM_LOW_WIDTH +: RECLAIM_HIGH_WIDTH]==RECLAIM_HIGH_WIDTH'(high_code);
                end else begin:g_single_code
                    assign high_decode[high_code]=reclaim_eligible[reclaim_decode_row];
                end
            end
            rv32_frequency_control_tree #(.WIDTH(RECLAIM_LOW_CODES),.LEAVES(1)) low_decode_tree (
                .signal_i(low_decode),.views_o(low_views));
            rv32_frequency_control_tree #(.WIDTH(RECLAIM_HIGH_CODES),.LEAVES(1)) high_decode_tree (
                .signal_i(high_decode),.views_o(high_views));
            for(genvar destination_phys=0;destination_phys<PHYS_REGS;destination_phys=destination_phys+1) begin:g_destination
                if(destination_phys==0) begin:g_zero
                    assign reclaim_row_destinations[reclaim_decode_row*PHYS_REGS+destination_phys]=1'b0;
                end else begin:g_register
                    assign reclaim_row_destinations[reclaim_decode_row*PHYS_REGS+destination_phys]=
                        low_views[destination_phys%RECLAIM_LOW_CODES] && high_views[destination_phys/RECLAIM_LOW_CODES];
                end
            end
        end
''' + anchor)
    source=change(source,'''                    assign destination_matches[reclaim_match] = reclaim_eligible[reclaim_match] &&
                        (new_phys_mem[reclaim_match] == reclaim_phys);''','''                    assign destination_matches[reclaim_match]=
                        reclaim_row_destinations[reclaim_match*PHYS_REGS+reclaim_phys];''')
    return source


if __name__=='__main__':
    prepare('CU_rob_reclaim_predecode',ROOT/'CT_dcache_tag_port_distribution',{
        'rtl/backend/rv32_rob.v':rob,
    }, 'CT plus per-row split physical-destination predecode: eligible-qualified high codes and low codes protected by kept functional inversion boundaries, then bounded cross-product. Same valid/rd_we/age eligibility, nonzero physical destination, all-row OR and distinct-bit balanced count, including duplicate destinations and out-of-range addresses. No extra FF/SRAM/cycles or hardware tests; source-only candidate.')
