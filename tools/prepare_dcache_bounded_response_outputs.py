"""Bound Dcache bypass/deferred response output selection; source only."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


OUTPUTS = r'''
    localparam integer RESPONSE_TAG_WORDS=(TAG_WIDTH+15)/16;
    localparam integer RESPONSE_OUTPUT_WORDS=RESPONSE_TAG_WORDS+13;
    wire [2*RESPONSE_OUTPUT_WORDS-1:0] response_output_views;
    rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(RESPONSE_OUTPUT_WORDS)) response_output_tree (
        .signal_i({resp_from_sram,bypass_load_hit}),.views_o(response_output_views));
    wire [31:0] response_hit_word=extract_value(data_rdata,core_req_addr,core_req_size,core_req_unsigned);
    wire [31:0] response_deferred_word=extract_value(data_rdata,resp_addr_reg,resp_size_reg,resp_unsigned_reg);
    genvar response_word;
    generate
        for(response_word=0;response_word<RESPONSE_TAG_WORDS;response_word=response_word+1) begin:g_response_tag_word
            localparam integer LOW=response_word*16;
            localparam integer BITS=(TAG_WIDTH-LOW>=16)?16:TAG_WIDTH-LOW;
            assign dcache_resp_lsq_tag_o[LOW +: BITS]=response_output_views[2*response_word]?
                core_req_lsq_tag[LOW +: BITS]:resp_lsq_reg[LOW +: BITS];
        end
        for(response_word=0;response_word<2;response_word=response_word+1) begin:g_response_address_word
            assign dcache_resp_addr_o[response_word*16 +: 16]=response_output_views[2*(RESPONSE_TAG_WORDS+response_word)]?
                core_req_addr[response_word*16 +: 16]:resp_addr_reg[response_word*16 +: 16];
        end
        for(response_word=0;response_word<8;response_word=response_word+1) begin:g_response_line_word
            wire bypass=response_output_views[2*(RESPONSE_TAG_WORDS+2+response_word)];
            wire deferred=response_output_views[2*(RESPONSE_TAG_WORDS+2+response_word)+1];
            assign dcache_resp_line_data_o[response_word*16 +: 16]=(bypass || deferred)?
                data_rdata[response_word*16 +: 16]:resp_line_reg[response_word*16 +: 16];
        end
        for(response_word=0;response_word<2;response_word=response_word+1) begin:g_response_value_word
            wire bypass=response_output_views[2*(RESPONSE_TAG_WORDS+10+response_word)];
            wire deferred=response_output_views[2*(RESPONSE_TAG_WORDS+10+response_word)+1];
            assign dcache_resp_word_data_o[response_word*16 +: 16]=bypass?
                response_hit_word[response_word*16 +: 16]:(deferred?
                    response_deferred_word[response_word*16 +: 16]:resp_word_reg[response_word*16 +: 16]);
        end
    endgenerate
    assign dcache_resp_line_valid_o=response_output_views[2*(RESPONSE_OUTPUT_WORDS-1)] || resp_line_valid_reg;
    assign dcache_resp_error_o=!response_output_views[2*(RESPONSE_OUTPUT_WORDS-1)] && resp_error_reg;
'''


def output_muxes(t):
    a=t.index('    assign dcache_resp_lsq_tag_o = bypass_load_hit')
    b=t.index('    // The synchronous tag query',a)
    t=t[:a]+OUTPUTS+t[b:]
    t=change(t,'    assign dcache_store_ack_lsq_tag_o = bypass_store_ack ? core_req_lsq_tag : ack_lsq_reg;\n',r'''    wire [RESPONSE_TAG_WORDS:0] ack_output_views;
    rv32_frequency_control_tree #(.LEAVES(RESPONSE_TAG_WORDS+1)) ack_output_tree (
        .signal_i(bypass_store_ack),.views_o(ack_output_views));
    generate for(response_word=0;response_word<RESPONSE_TAG_WORDS;response_word=response_word+1) begin:g_ack_tag_word
        localparam integer LOW=response_word*16;
        localparam integer BITS=(TAG_WIDTH-LOW>=16)?16:TAG_WIDTH-LOW;
        assign dcache_store_ack_lsq_tag_o[LOW +: BITS]=ack_output_views[response_word]?
            core_req_lsq_tag[LOW +: BITS]:ack_lsq_reg[LOW +: BITS];
    end endgenerate
''')
    return change(t,'assign dcache_store_ack_error_o = !bypass_store_ack && ack_error_reg;',
                    'assign dcache_store_ack_error_o = !ack_output_views[RESPONSE_TAG_WORDS] && ack_error_reg;')


if __name__=='__main__':
    prepare('BG_bounded_cache_response_outputs',ROOT/'BF1_bounded_cache_payload_queries',
            {'rtl/cache/rv32_dcache_nonblocking.v':output_muxes},
            'BF1 plus bounded sixteen-bit output selection for Dcache hit/deferred SRAM/held response line, extracted word, address, LSQ tag and store ACK; preserve hit bypass priority, deferred-size identity and valid/backpressure cycles; no new FF/cycles and no EDA')
