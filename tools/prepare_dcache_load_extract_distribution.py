"""Source-only repair of measured Dcache byte-offset and waiter mux loads."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


EXTRACT = '''

// Full 128-bit logical shift semantics, retaining zero fill even for an
// unaligned byte window near the end of a line. Only bits needed by the
// eventual 32-bit result are routed through the four byte-offset stages.
// Each amount leaf owns at most sixteen actual mux bits; no state/cycle.
module rv32_frequency_line_extract32 (
    input wire [127:0] line_i,
    input wire [3:0] offset_i,
    input wire [1:0] size_i,
    input wire unsigned_i,
    output wire [31:0] value_o
);
    wire [87:0] shift64;
    wire [55:0] shift32;
    wire [39:0] shift16;
    wire [31:0] shifted;
    wire [5:0] amount64;
    wire [3:0] amount32;
    wire [2:0] amount16;
    wire [1:0] amount8;
    rv32_frequency_control_tree #(.LEAVES(6)) amount64_tree (
        .signal_i(offset_i[3]),.views_o(amount64));
    rv32_frequency_control_tree #(.LEAVES(4)) amount32_tree (
        .signal_i(offset_i[2]),.views_o(amount32));
    rv32_frequency_control_tree #(.LEAVES(3)) amount16_tree (
        .signal_i(offset_i[1]),.views_o(amount16));
    rv32_frequency_control_tree #(.LEAVES(2)) amount8_tree (
        .signal_i(offset_i[0]),.views_o(amount8));
    genvar bit_id;
    generate
        for(bit_id=0;bit_id<88;bit_id=bit_id+1) begin:g_shift64
            if(bit_id+64<128) begin:g_data
                assign shift64[bit_id]=amount64[bit_id/16]?line_i[bit_id+64]:line_i[bit_id];
            end else begin:g_zero
                assign shift64[bit_id]=!amount64[bit_id/16] && line_i[bit_id];
            end
        end
        for(bit_id=0;bit_id<56;bit_id=bit_id+1) begin:g_shift32
            assign shift32[bit_id]=amount32[bit_id/16]?shift64[bit_id+32]:shift64[bit_id];
        end
        for(bit_id=0;bit_id<40;bit_id=bit_id+1) begin:g_shift16
            assign shift16[bit_id]=amount16[bit_id/16]?shift32[bit_id+16]:shift32[bit_id];
        end
        for(bit_id=0;bit_id<32;bit_id=bit_id+1) begin:g_shift8
            assign shifted[bit_id]=amount8[bit_id/16]?shift16[bit_id+8]:shift16[bit_id];
        end
    endgenerate
    // RV32IM_MEM_BYTE=0, RV32IM_MEM_HALF=1; both remaining codes
    // retain the former function's default full-word behavior.
    wire [7:0] format_views;
    rv32_frequency_control_tree #(.WIDTH(4),.LEAVES(2)) format_tree (
        .signal_i({size_i==2'd0,size_i==2'd1,
                   !unsigned_i && shifted[7],!unsigned_i && shifted[15]}),
        .views_o(format_views));
    generate for(bit_id=0;bit_id<32;bit_id=bit_id+1) begin:g_format
        wire byte_load,half_load,byte_sign,half_sign;
        assign {byte_load,half_load,byte_sign,half_sign}=format_views[(bit_id/16)*4 +: 4];
        if(bit_id<8) begin:g_low
            assign value_o[bit_id]=shifted[bit_id];
        end else if(bit_id<16) begin:g_byte_extend
            assign value_o[bit_id]=byte_load?byte_sign:shifted[bit_id];
        end else begin:g_half_extend
            assign value_o[bit_id]=byte_load?byte_sign:(half_load?half_sign:shifted[bit_id]);
        end
    end endgenerate
endmodule
'''


def common(source):
    if 'module rv32_frequency_line_extract32' in source:
        raise ValueError('Already has load extraction owner')
    return source + EXTRACT


def dcache(source):
    source=change(source,'''    wire [31:0] response_hit_word=extract_value(data_rdata,core_req_addr,core_req_size,core_req_unsigned);
    wire [31:0] response_deferred_word=extract_value(data_rdata,resp_addr_reg,resp_size_reg,resp_unsigned_reg);''','''    // Share the same extracted word between immediate and captured hit
    // replies. Byte-offset fanout stays bounded inside each routing unit.
    wire [31:0] response_hit_word,response_deferred_word;
    rv32_frequency_line_extract32 hit_extract (
        .line_i(data_rdata),.offset_i(core_req_addr[3:0]),
        .size_i(core_req_size),.unsigned_i(core_req_unsigned),.value_o(response_hit_word));
    rv32_frequency_line_extract32 deferred_extract (
        .line_i(data_rdata),.offset_i(resp_addr_reg[3:0]),
        .size_i(resp_size_reg),.unsigned_i(resp_unsigned_reg),.value_o(response_deferred_word));''')
    start=source.index('    function [31:0] extract_value;')
    end=source.index('    endfunction',start)+len('    endfunction')
    source=source[:start]+source[end:]
    source=change(source,'    wire [127:0] waiter_store_fill=merge_store(mem_resp_data_i,query_response_mshr_wdata,query_response_mshr_mask);','''    wire [127:0] waiter_store_fill=merge_store(mem_resp_data_i,query_response_mshr_wdata,query_response_mshr_mask);
    // A response-store flag formerly controlled 128 mux bits for every
    // waiter group. Each waiter now receives eight sixteen-bit leaves.''')
    source=change(source,'''        rv32_frequency_event_select #(.WIDTH(128),.EVENTS(2)) line_selector (
            .events_i({response_fill && !waiter_store[waiter_row],local_fill && !waiter_store[waiter_row]}),
            .values_i({(store_event?waiter_store_fill:mem_resp_data_i),query_local_mshr_wdata}),''','''        wire [7:0] store_data_views;
        wire [127:0] response_line;
        rv32_frequency_control_tree #(.LEAVES(8)) store_data_tree (
            .signal_i(store_event),.views_o(store_data_views));
        for(genvar line_word=0;line_word<8;line_word=line_word+1) begin:g_response_word
            assign response_line[line_word*16 +: 16]=store_data_views[line_word]?
                waiter_store_fill[line_word*16 +: 16]:mem_resp_data_i[line_word*16 +: 16];
        end
        rv32_frequency_event_select #(.WIDTH(128),.EVENTS(2)) line_selector (
            .events_i({response_fill && !waiter_store[waiter_row],local_fill && !waiter_store[waiter_row]}),
            .values_i({response_line,query_local_mshr_wdata}),''')
    source=change(source,'    wire response_data_write;','''    wire [31:0] response_memory_word,response_waiter_word,response_forward_word;
    rv32_frequency_line_extract32 memory_extract (
        .line_i(mem_resp_data_i),.offset_i(query_response_mshr_addr[3:0]),
        .size_i(query_response_mshr_size),.unsigned_i(query_response_mshr_unsigned),.value_o(response_memory_word));
    rv32_frequency_line_extract32 waiter_extract (
        .line_i(query_waiter_load_waiter_line),.offset_i(query_waiter_load_waiter_addr[3:0]),
        .size_i(query_waiter_load_waiter_size),.unsigned_i(query_waiter_load_waiter_unsigned),.value_o(response_waiter_word));
    rv32_frequency_line_extract32 forward_extract (
        .line_i(query_matching_mshr_wdata),.offset_i(core_req_addr[3:0]),
        .size_i(core_req_size),.unsigned_i(core_req_unsigned),.value_o(response_forward_word));
    wire response_data_write;''')
    replacements={
        'extract_value(mem_resp_data_i,query_response_mshr_addr,query_response_mshr_size,query_response_mshr_unsigned)':'response_memory_word',
        'extract_value(query_waiter_load_waiter_line,query_waiter_load_waiter_addr,query_waiter_load_waiter_size,query_waiter_load_waiter_unsigned)':'response_waiter_word',
        'extract_value(query_matching_mshr_wdata,core_req_addr,core_req_size,core_req_unsigned)':'response_forward_word',
        'extract_value(data_rdata,core_req_addr,core_req_size,core_req_unsigned)':'response_hit_word',
        'extract_value(data_rdata,resp_addr_reg,resp_size_reg,resp_unsigned_reg)':'response_deferred_word',
    }
    for old,new in replacements.items():
        source=change(source,old,new)
    if 'extract_value' in source:
        raise ValueError('Unconverted load-extraction use')
    return source


if __name__=='__main__':
    prepare('CG_dcache_load_extract_distribution',ROOT/'CF_dcache_compact_metadata_distribution',{
        'rtl/common/rv32_asap7_fanout.v':common,
        'rtl/cache/rv32_dcache_nonblocking.v':dcache,
    },'CF plus byte-offset load extraction with 88/56/40/32-bit truncated stages, at most16 amount-mux bits per leaf, same full logical shift/size/unsigned behavior; five unique extraction units reused by output/capture. Waiter response store-data control split into16-bit leaves. No FF/cycle/protocol/SRAM changes, no EDA/simulation, independent unadopted candidate.')
