"""Local cache metadata/reset and Dcache byte ownership, source only/no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


ICACHE_METADATA = r'''
    wire [CACHE_LINES+CACHE_SETS-1:0] metadata_reset;
    wire [CACHE_LINES-1:0] metadata_refill;
    wire [CACHE_SETS-1:0] metadata_hit_lru,metadata_refill_lru;
    rv32_frequency_control_tree #(.LEAVES(CACHE_LINES+CACHE_SETS)) metadata_reset_tree (
        .signal_i(reset_i),.views_o(metadata_reset));
    rv32_frequency_control_tree #(.LEAVES(CACHE_LINES)) metadata_refill_tree (
        .signal_i(refill_array_write),.views_o(metadata_refill));
    rv32_frequency_control_tree #(.LEAVES(CACHE_SETS)) metadata_hit_lru_tree (
        .signal_i(hit_array_read),.views_o(metadata_hit_lru));
    rv32_frequency_control_tree #(.LEAVES(CACHE_SETS)) metadata_refill_lru_tree (
        .signal_i(refill_array_write),.views_o(metadata_refill_lru));
    genvar metadata_entry,metadata_set;
    generate
        for(metadata_entry=0;metadata_entry<CACHE_LINES;metadata_entry=metadata_entry+1) begin:g_valid_owner
            reg valid_q;
            assign valid_bits[metadata_entry]=valid_q;
            always @(posedge clk_i) begin
                if(metadata_reset[metadata_entry]) valid_q<=1'b0;
                else if(metadata_refill[metadata_entry] && refill_entry==metadata_entry) valid_q<=1'b1;
            end
        end
        for(metadata_set=0;metadata_set<CACHE_SETS;metadata_set=metadata_set+1) begin:g_lru_owner
            reg lru_q;
            assign lru_mem[metadata_set]=lru_q;
            always @(posedge clk_i) begin
                if(metadata_reset[CACHE_LINES+metadata_set]) lru_q<=1'b0;
                else if(CACHE_WAYS==2) begin
                    // Successful refill is later than same-edge hit in the
                    // original process and therefore retains higher priority.
                    if(metadata_refill_lru[metadata_set] && refill_set==metadata_set) lru_q<=~refill_entry[0];
                    else if(metadata_hit_lru[metadata_set] && request_set==metadata_set) lru_q<=~request_entry[0];
                end
            end
        end
    endgenerate
'''


def icache(t):
    t=change(t,'reg [CACHE_LINES-1:0] valid_bits;','wire [CACHE_LINES-1:0] valid_bits;')
    t=change(t,'reg lru_mem [0:CACHE_SETS-1];','wire lru_mem [0:CACHE_SETS-1];')
    t=change(t,'    integer reset_index;',ICACHE_METADATA+'\n    integer reset_index;')
    for old in [
        "            valid_bits <= {CACHE_LINES{1'b0}};\n",
        "            for (reset_index = 0; reset_index < CACHE_SETS; reset_index = reset_index + 1)\n                lru_mem[reset_index] <= 1'b0;\n",
        "                        if (CACHE_WAYS == 2)\n                            lru_mem[request_set] <= ~request_entry[0];\n",
        "                    valid_bits[refill_entry] <= 1'b1;\n",
        "                    if (CACHE_WAYS == 2)\n                        lru_mem[refill_set] <= ~refill_entry[0];\n",
    ]: t=change(t,old,'')
    return t


def dcache_banks(t):
    t=change(t,'    genvar row, set_id;',
        '''    localparam integer RESET_DOMAINS=GROUP_ROWS+GROUP_ROWS/CACHE_WAYS+1;
    wire [RESET_DOMAINS-1:0] reset_views;
    rv32_frequency_control_tree #(.LEAVES(RESET_DOMAINS)) reset_tree (
        .signal_i(reset_i),.views_o(reset_views));
    genvar row, set_id;''')
    t=change(t,'            if (!reset_i && query_fire_i)',
             '            if (!reset_views[RESET_DOMAINS-1] && query_fire_i)')
    t=change(t,"                if (reset_i) begin\n                    valid_o[row] <= 1'b0;",
             "                if (reset_views[row]) begin\n                    valid_o[row] <= 1'b0;")
    t=change(t,"                if (reset_i) lru_o[set_id] <= 1'b0;",
             "                if (reset_views[GROUP_ROWS+set_id]) lru_o[set_id] <= 1'b0;")
    start=t.index('    genvar byte_id;',t.index('module rv32_dcache_mshr_data_bank'))
    stop=t.index('    initial begin',start)
    byte_owners=r'''    wire [15:0] zero_views;
    rv32_frequency_control_tree #(.LEAVES(16)) zero_tree (
        .signal_i(reset_i || write_zero),.views_o(zero_views));
    genvar byte_id;
    generate for(byte_id=0;byte_id<16;byte_id=byte_id+1) begin:g_byte
        wire write_enable;
        wire [7:0] next_byte,saved_byte;
        wire update=write_word || (merge_word && write_mask_i[byte_id]);
        rv32_frequency_event_select #(.WIDTH(8),.EVENTS(2)) selector (
            .events_i({zero_views[byte_id],update}),
            .values_i({8'b0,write_data_i[byte_id*8 +: 8]}),
            .write_o(write_enable),.value_o(next_byte));
        rv32_frequency_word_bank #(.WIDTH(8)) owner (
            .clk_i(clk_i),.write_i(write_enable),.data_i(next_byte),.data_o(saved_byte));
        assign data_o[byte_id*8 +: 8]=saved_byte;
    end endgenerate
'''
    t=t[:start]+byte_owners+t[stop:]
    t=change(t,'    output reg [127:0] data_o','    output wire [127:0] data_o')
    return t


if __name__=='__main__':
    prepare('AV_cache_row_and_byte_controls',ROOT/'AU1_rs_local_wake_broadcasts',{
        'rtl/cache/rv32_icache_nonblocking.v':icache,
        'rtl/cache/rv32_dcache_control_banks.v':dcache_banks,
    },'AU1 plus Icache valid/LRU row owners with distributed reset/refill/hit events and refill-over-hit priority, Dcache metadata row/set/query reset domains and MSHR byte event owners; preserve reset-to-zero and zero>write>merge priority, original macros/interface/edge semantics; no FF/cycles added and no EDA')
