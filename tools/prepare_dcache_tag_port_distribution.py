"""Localize Dcache tag-SRAM command consumers from CS; no HDL/EDA."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def dcache(source):
    source=change(source,'''    wire [CACHE_ENTRY_WIDTH-1:0] tag_write_entry = local_array_write ?
        query_local_mshr_victim_entry : query_response_mshr_victim_entry;
    wire [CACHE_INDEX_WIDTH-1:0] tag_write_set = tag_write_entry / CACHE_WAYS;
    wire [CACHE_TAG_WIDTH-1:0] tag_write_value = local_array_write ?
        query_local_mshr_addr[31:CACHE_INDEX_WIDTH+4] :
        query_response_mshr_addr[31:CACHE_INDEX_WIDTH+4];''','''    localparam integer TAG_WRITE_INPUT_WIDTH=CACHE_ENTRY_WIDTH+CACHE_TAG_WIDTH;
    localparam integer TAG_WRITE_INPUT_WORDS=(TAG_WRITE_INPUT_WIDTH+15)/16;
    wire [CACHE_ENTRY_WIDTH-1:0] tag_write_entry;
    wire [CACHE_INDEX_WIDTH-1:0] tag_write_set=tag_write_entry/CACHE_WAYS;
    wire [CACHE_TAG_WIDTH-1:0] tag_write_value;
    wire [TAG_WRITE_INPUT_WIDTH-1:0] local_tag_input,response_tag_input,selected_tag_input;
    wire [TAG_WRITE_INPUT_WORDS-1:0] tag_write_source_views;
    assign local_tag_input={query_local_mshr_victim_entry,query_local_mshr_addr[31:CACHE_INDEX_WIDTH+4]};
    assign response_tag_input={query_response_mshr_victim_entry,query_response_mshr_addr[31:CACHE_INDEX_WIDTH+4]};
    assign {tag_write_entry,tag_write_value}=selected_tag_input;
    rv32_frequency_control_tree #(.LEAVES(TAG_WRITE_INPUT_WORDS)) tag_write_source_tree (
        .signal_i(local_array_write),.views_o(tag_write_source_views));
    generate for(genvar tag_input_word=0;tag_input_word<TAG_WRITE_INPUT_WORDS;tag_input_word=tag_input_word+1) begin:g_tag_input_word
        localparam integer LOW=tag_input_word*16;
        localparam integer BITS=(TAG_WRITE_INPUT_WIDTH-LOW>=16)?16:TAG_WRITE_INPUT_WIDTH-LOW;
        assign selected_tag_input[LOW +: BITS]=tag_write_source_views[tag_input_word]?
            local_tag_input[LOW +: BITS]:response_tag_input[LOW +: BITS];
    end endgenerate''')
    source=change(source,'        genvar hold_way;','''        localparam integer TAG_FORWARD_WIDTH=1+CACHE_WAYS+CACHE_INDEX_WIDTH+CACHE_TAG_WIDTH;
        wire [CACHE_WAYS*TAG_FORWARD_WIDTH-1:0] tag_forward_views;
        rv32_frequency_control_tree #(.WIDTH(TAG_FORWARD_WIDTH),.LEAVES(CACHE_WAYS)) tag_forward_tree (
            .signal_i({tag_array_write,tag_write_mask,tag_write_set,tag_write_value}),
            .views_o(tag_forward_views));
        genvar hold_way;''')
    source=change(source,'''            wire tag_forward=!local_reset && tag_array_write && query_valid && tag_write_mask[hold_way];
            wire demand_forward=tag_forward && tag_write_set==core_request_index;
            wire prefetch_forward=tag_forward && tag_write_set==core_prefetch_index;''','''            wire local_tag_write;
            wire [CACHE_WAYS-1:0] local_tag_mask;
            wire [CACHE_INDEX_WIDTH-1:0] local_tag_set;
            wire [CACHE_TAG_WIDTH-1:0] local_tag_value;
            assign {local_tag_write,local_tag_mask,local_tag_set,local_tag_value}=
                tag_forward_views[hold_way*TAG_FORWARD_WIDTH +: TAG_FORWARD_WIDTH];
            wire tag_forward=!local_reset && local_tag_write && query_valid && local_tag_mask[hold_way];
            wire demand_forward=tag_forward && local_tag_set==core_request_index;
            wire prefetch_forward=tag_forward && local_tag_set==core_prefetch_index;''')
    source=change(source,'.values_i({tag_write_value,demand_rdata[hold_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]})',
                         '.values_i({local_tag_value,demand_rdata[hold_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]})')
    source=change(source,'.values_i({tag_write_value,prefetch_rdata[hold_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]})',
                         '.values_i({local_tag_value,prefetch_rdata[hold_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]})')
    start=source.index('        sram_fakeram #(.DEPTH(CACHE_SETS), .WIDTH(CACHE_WAYS*CACHE_TAG_WIDTH),')
    end=source.index('        always @(posedge clk_i) begin',start)
    source=source[:start]+'''        // Each former word-wide SRAM way retains the SAME global write
        // mode even when its mask bit is zero: it must not become a read
        // during the other way's write. Only command distribution changes.
        localparam integer TAG_PORTS=2*CACHE_WAYS;
        wire [TAG_PORTS-1:0] tag_port_write,tag_port_enable,tag_port_address_select;
        wire [TAG_PORTS*CACHE_TAG_WIDTH-1:0] tag_port_data;
        rv32_frequency_control_tree #(.LEAVES(TAG_PORTS)) tag_port_write_tree (
            .signal_i(tag_array_write),.views_o(tag_port_write));
        rv32_frequency_control_tree #(.LEAVES(TAG_PORTS)) tag_port_enable_tree (
            .signal_i(!reset_i && (tag_array_write || input_fire)),.views_o(tag_port_enable));
        rv32_frequency_control_tree #(.LEAVES(TAG_PORTS)) tag_port_address_tree (
            .signal_i(tag_array_write),.views_o(tag_port_address_select));
        rv32_frequency_control_tree #(.WIDTH(CACHE_TAG_WIDTH),.LEAVES(TAG_PORTS)) tag_port_data_tree (
            .signal_i(tag_write_value),.views_o(tag_port_data));
        for(genvar tag_port_way=0;tag_port_way<CACHE_WAYS;tag_port_way=tag_port_way+1) begin:g_tag_port_way
            sram_fakeram #(.DEPTH(CACHE_SETS),.WIDTH(CACHE_TAG_WIDTH),
                          .WRITE_GRANULARITY(CACHE_TAG_WIDTH)) demand_tags (
                .clk(clk_i),.en(tag_port_enable[2*tag_port_way]),
                .we(tag_port_write[2*tag_port_way]),.wmask(tag_write_mask[tag_port_way]),
                .addr(tag_port_address_select[2*tag_port_way]?tag_write_set:cache_index(dcache_req_addr_i)),
                .wdata(tag_port_data[2*tag_port_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]),
                .rdata(demand_rdata[tag_port_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]));
            sram_fakeram #(.DEPTH(CACHE_SETS),.WIDTH(CACHE_TAG_WIDTH),
                          .WRITE_GRANULARITY(CACHE_TAG_WIDTH)) nextline_tags (
                .clk(clk_i),.en(tag_port_enable[2*tag_port_way+1]),
                .we(tag_port_write[2*tag_port_way+1]),.wmask(tag_write_mask[tag_port_way]),
                .addr(tag_port_address_select[2*tag_port_way+1]?tag_write_set:cache_index(input_prefetch_line)),
                .wdata(tag_port_data[(2*tag_port_way+1)*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]),
                .rdata(prefetch_rdata[tag_port_way*CACHE_TAG_WIDTH +: CACHE_TAG_WIDTH]));
        end
''' + source[end:]
    return source


if __name__=='__main__':
    prepare('CT_dcache_tag_port_distribution',ROOT/'CS_multiplier_consumer_distribution',{
        'rtl/cache/rv32_dcache_nonblocking.v':dcache,
    }, 'CS plus 16-bit local/refill tag input selection, way-local forwarding metadata, separate bounded write/enable/address/data domains per existing demand/nextline tag-SRAM way. Each way keeps original global write mode even on mask0, same synchronous read/hold and active edges, fixed data/tag bits, capacities, ownership priority and SRAM dimensions per word. No extra FF/cycle or hardware tests; actual macro mapping/area remains unverified.')
