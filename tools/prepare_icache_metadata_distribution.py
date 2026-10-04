"""Prepare Icache tag/LRU/output distribution without invoking hardware tools."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def icache(source):
    source=change(source,'    reg [CACHE_TAG_WIDTH-1:0] tag_mem [0:CACHE_LINES-1];',
                        '    wire [CACHE_TAG_WIDTH-1:0] tag_mem [0:CACHE_LINES-1];')
    source=change(source,'    assign if_resp_line_data_o = resp_from_sram ? data_rdata : resp_data_reg;','''    wire [7:0] response_line_views;
    rv32_frequency_control_tree #(.LEAVES(8)) response_line_tree (
        .signal_i(resp_from_sram),.views_o(response_line_views));
    generate for(genvar output_word=0;output_word<8;output_word=output_word+1) begin:g_response_line
        assign if_resp_line_data_o[output_word*16 +: 16]=response_line_views[output_word]?
            data_rdata[output_word*16 +: 16]:resp_data_reg[output_word*16 +: 16];
    end endgenerate''')
    source=change(source,'    genvar metadata_entry,metadata_set;','''    // Final qualified write leaves alone did not bound the raw shared
    // entry/way inputs. Each query packet feeds only four existing rows.
    localparam integer TAG_WRITE_DOMAINS=(CACHE_LINES+3)/4;
    localparam integer TAG_WRITE_WIDTH=CACHE_ENTRY_WIDTH+CACHE_TAG_WIDTH;
    wire [TAG_WRITE_DOMAINS*TAG_WRITE_WIDTH-1:0] tag_write_views;
    rv32_frequency_control_tree #(.WIDTH(TAG_WRITE_WIDTH),.LEAVES(TAG_WRITE_DOMAINS)) tag_write_tree (
        .signal_i({refill_entry,mem_resp_line_addr_i[31:CACHE_SET_WIDTH+4]}),
        .views_o(tag_write_views));
    localparam integer LRU_QUERY_DOMAINS=(CACHE_SETS+3)/4;
    localparam integer LRU_QUERY_WIDTH=2*CACHE_SET_WIDTH+2;
    wire [LRU_QUERY_DOMAINS*LRU_QUERY_WIDTH-1:0] lru_query_views;
    rv32_frequency_control_tree #(.WIDTH(LRU_QUERY_WIDTH),.LEAVES(LRU_QUERY_DOMAINS)) lru_query_tree (
        .signal_i({refill_set,refill_entry[0],request_set,request_entry[0]}),
        .views_o(lru_query_views));
    genvar metadata_entry,metadata_set;''')
    source=change(source,'''            reg valid_q;
            assign valid_bits[metadata_entry]=valid_q;
            always @(posedge clk_i) begin
                if(metadata_reset[metadata_entry]) valid_q<=1'b0;
                else if(metadata_refill[metadata_entry] && refill_entry==metadata_entry) valid_q<=1'b1;
            end''','''            reg valid_q;
            wire [CACHE_ENTRY_WIDTH-1:0] local_refill_entry;
            wire [CACHE_TAG_WIDTH-1:0] local_refill_tag;
            wire tag_write;
            assign {local_refill_entry,local_refill_tag}=tag_write_views[(metadata_entry/4)*TAG_WRITE_WIDTH +: TAG_WRITE_WIDTH];
            assign tag_write=metadata_refill[metadata_entry] && local_refill_entry==metadata_entry;
            assign valid_bits[metadata_entry]=valid_q;
            always @(posedge clk_i) begin
                if(metadata_reset[metadata_entry]) valid_q<=1'b0;
                else if(tag_write) valid_q<=1'b1;
            end
            // Allocation writes all tag bits before valid exposes them.
            // The old unreset dynamic write has the same qualified edge.
            rv32_frequency_word_bank #(.WIDTH(CACHE_TAG_WIDTH)) tag_owner (
                .clk_i(clk_i),.write_i(tag_write),.data_i(local_refill_tag),.data_o(tag_mem[metadata_entry]));''')
    source=change(source,'''            reg lru_q;
            assign lru_mem[metadata_set]=lru_q;''','''            reg lru_q;
            wire [CACHE_SET_WIDTH-1:0] local_refill_set,local_request_set;
            wire local_refill_way,local_request_way;
            assign {local_refill_set,local_refill_way,local_request_set,local_request_way}=
                lru_query_views[(metadata_set/4)*LRU_QUERY_WIDTH +: LRU_QUERY_WIDTH];
            assign lru_mem[metadata_set]=lru_q;''')
    source=change(source,'if(metadata_refill_lru[metadata_set] && refill_set==metadata_set) lru_q<=~refill_entry[0];',
                        'if(metadata_refill_lru[metadata_set] && local_refill_set==metadata_set) lru_q<=~local_refill_way;')
    source=change(source,'else if(metadata_hit_lru[metadata_set] && request_set==metadata_set) lru_q<=~request_entry[0];',
                        'else if(metadata_hit_lru[metadata_set] && local_request_set==metadata_set) lru_q<=~local_request_way;')
    source=change(source,'''                if (!mem_resp_error_i && response_matches) begin
                    tag_mem[refill_entry] <=
                        mem_resp_line_addr_i[31:CACHE_SET_WIDTH+4];
                end''','''                // Tag payload belongs to the static row owners above.''')
    if 'tag_mem[refill_entry] <=' in source:
        raise ValueError('Dynamic Icache tag writer remains')
    return source


if __name__=='__main__':
    prepare('CH_icache_metadata_distribution',ROOT/'CG_dcache_load_extract_distribution',{
        'rtl/cache/rv32_icache_nonblocking.v':icache,
    },'CG plus static Icache tag owners on the original successful-refill edge, four-row entry/tag distribution, four-set LRU set/way distribution, and16-bit public response-line select groups. Preserve SRAM, no extra FF/cycle or priority changes. Source-only unadopted candidate, no HDL/EDA/simulation.')
