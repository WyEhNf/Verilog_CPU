"""Bound PRF query/word/bypass loads without changing read timing, no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


QUERIES = r'''
    localparam integer READ_DOMAINS=4;
    wire [2*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] read_phys_local;
    wire [READ_DOMAINS*2*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] read_domain_queries;
    generate if(READ_MUX_IMPL!=0) begin:g_query_domains
        wire [(READ_DOMAINS+1)*2*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] queries;
        rv32_frequency_control_tree #(.WIDTH(2*BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(READ_DOMAINS+1)) query_tree (
            .signal_i(read_phys_i),.views_o(queries));
        assign read_domain_queries=queries[0 +: READ_DOMAINS*2*BE_WIDTH*PHYS_ADDR_WIDTH];
        assign read_phys_local=queries[READ_DOMAINS*2*BE_WIDTH*PHYS_ADDR_WIDTH +: 2*BE_WIDTH*PHYS_ADDR_WIDTH];
    end else begin:g_legacy_query
        rv32_frequency_control_tree #(.WIDTH(2*BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(1)) query_tree (
            .signal_i(read_phys_i),.views_o(read_phys_local));
        assign read_domain_queries=0;
    end endgenerate
'''


READS = r'''
    // Four query domains decode physical words independently. Data and ready
    // use separate bounded select leaves; the reductions have explicit depth.
    localparam integer READ_ROWS=(PHYS_REGS<=1)?1:(1<<$clog2(PHYS_REGS));
    genvar rp,row,wl,read_node;
    generate if(READ_MUX_IMPL!=0) begin:g_parallel_read
        for(rp=0;rp<2*BE_WIDTH;rp=rp+1) begin:g_port
            wire [PHYS_ADDR_WIDTH-1:0] address=read_phys_local[rp*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
            wire legal=address!=0 && address<PHYS_REGS;
            wire [31:0] stored_tree [1:2*READ_ROWS-1];
            wire ready_tree [1:2*READ_ROWS-1];
            wire [BE_WIDTH-1:0] bypass_match;
            wire [31:0] bypass_value;
            wire bypass_write,bypass_select;
            for(row=0;row<READ_ROWS;row=row+1) begin:g_word
                if(row>0 && row<PHYS_REGS) begin:g_present
                    localparam integer DOMAIN=(row*READ_DOMAINS)/PHYS_REGS;
                    wire selected=read_domain_queries[(DOMAIN*2*BE_WIDTH+rp)*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==row;
                    wire [1:0] select_views;
                    rv32_frequency_control_tree #(.LEAVES(2)) selection_tree (
                        .signal_i(selected),.views_o(select_views));
                    assign stored_tree[READ_ROWS+row]={32{select_views[0]}} & value[row];
                    assign ready_tree[READ_ROWS+row]=select_views[1] && ready[row];
                end else begin:g_zero_or_padding
                    assign stored_tree[READ_ROWS+row]=0;
                    assign ready_tree[READ_ROWS+row]=0;
                end
            end
            for(read_node=1;read_node<READ_ROWS;read_node=read_node+1) begin:g_reduce
                assign stored_tree[read_node]=stored_tree[2*read_node] | stored_tree[2*read_node+1];
                assign ready_tree[read_node]=ready_tree[2*read_node] | ready_tree[2*read_node+1];
            end
            for(wl=0;wl<BE_WIDTH;wl=wl+1) begin:g_bypass
                assign bypass_match[wl]=legal && write_valid_i[wl] &&
                    write_phys_i[wl*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==address;
            end
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(BE_WIDTH)) bypass_selector (
                .events_i(bypass_match),.values_i(write_data_i),.write_o(bypass_write),.value_o(bypass_value));
            rv32_frequency_control_tree #(.LEAVES(1)) bypass_choice_tree (
                .signal_i(bypass_write),.views_o(bypass_select));
            always @* begin
                read_data_o[rp*32 +: 32]=bypass_select?bypass_value:stored_tree[1];
                read_ready_o[rp]=(address==0) || ready_tree[1] || bypass_write;
            end
        end
'''


def bounded(t):
    start=t.index('    wire [2*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] read_phys_local;')
    stop=t.index('    genvar owner_row,owner_lane;',start)
    t=t[:start]+QUERIES+t[stop:]
    t=change(t,'    generate if(LOCAL_VALUE_ROWS!=0) begin:g_local_storage\n',
        '''    generate if(LOCAL_VALUE_ROWS!=0) begin:g_local_storage
        wire [PHYS_REGS-1:0] reset_views;
        rv32_frequency_control_tree #(.LEAVES(PHYS_REGS)) reset_tree (
            .signal_i(reset_i),.views_o(reset_views));
''')
    t=change(t,'.clk_i(clk_i),.reset_i(reset_i),.alloc_i(|allocations),.write_matches_i(writes),',
             '.clk_i(clk_i),.reset_i(reset_views[owner_row]),.alloc_i(|allocations),.write_matches_i(writes),')
    start=t.index('    // Decode each read word once')
    stop=t.index('    end else begin : g_original_read',start)
    return t[:start]+READS+t[stop:]


if __name__=='__main__':
    prepare('AP_prf_bounded_query_and_read',ROOT/'AO_lsq_local_metadata_owners',
            {'rtl/rv32_physical_register_file.v':bounded},
            'AO plus four grouped PRF word queries and independent bypass query, separated bounded value/ready selects, balanced stored-data/ready reductions and highest-lane bounded WB bypass; row-local reset; preserve P0/out-of-range/WB-over-allocation behavior with no FF/cycle change; no EDA')
