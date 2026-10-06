"""Own Icache response/stream payloads at existing edges, no EDA."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


OWNERS = r'''
    localparam integer RESPONSE_META_WIDTH=65+EPOCH_WIDTH;
    wire response_hit_write=!reset_i && hit_array_read;
    wire [2*RESPONSE_META_WIDTH-1:0] response_metadata_values={
        mem_resp_error_i || !response_matches,
        (response_promoted?lookup_req_epoch:mshr_demand_epoch[response_index]),
        (response_promoted?mem_resp_line_addr_i:mshr_line[response_index]),
        (response_promoted?lookup_req_pc:mshr_pc[response_index]),
        1'b0,lookup_req_epoch,request_line,lookup_req_pc};
    wire response_metadata_write;
    wire [RESPONSE_META_WIDTH-1:0] response_metadata_next,response_metadata_saved;
    rv32_frequency_event_select #(.WIDTH(RESPONSE_META_WIDTH),.EVENTS(2)) response_metadata_selector (
        .events_i({response_memory_write,response_hit_write}),.values_i(response_metadata_values),
        .write_o(response_metadata_write),.value_o(response_metadata_next));
    rv32_frequency_word_bank #(.WIDTH(RESPONSE_META_WIDTH)) response_metadata_owner (
        .clk_i(clk_i),.write_i(response_metadata_write),.data_i(response_metadata_next),.data_o(response_metadata_saved));
    assign {resp_error_reg,resp_epoch_reg,resp_line_reg,resp_pc_reg}=response_metadata_saved;

    wire stream_start=!reset_i && stream_reset;
    wire stream_control_start=!reset_i && control_target_allocate;
    wire stream_line_write;
    wire [31:0] stream_line_next;
    wire [3*32-1:0] stream_line_values={
        ({control_target[31:4],4'b0}+32'd16),request_line+32'd16,prefetch_next_line+32'd16};
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(3)) stream_line_selector (
        .events_i({stream_control_start,stream_start,!reset_i && prefetch_step}),.values_i(stream_line_values),
        .write_o(stream_line_write),.value_o(stream_line_next));
    rv32_frequency_word_bank #(.WIDTH(32)) stream_line_owner (
        .clk_i(clk_i),.write_i(stream_line_write),.data_i(stream_line_next),.data_o(prefetch_next_line));
    wire stream_epoch_write;
    wire [EPOCH_WIDTH-1:0] stream_epoch_next;
    rv32_frequency_event_select #(.WIDTH(EPOCH_WIDTH),.EVENTS(2)) stream_epoch_selector (
        .events_i({stream_control_start,stream_start}),.values_i({current_epoch_i,lookup_req_epoch}),
        .write_o(stream_epoch_write),.value_o(stream_epoch_next));
    rv32_frequency_word_bank #(.WIDTH(EPOCH_WIDTH)) stream_epoch_owner (
        .clk_i(clk_i),.write_i(stream_epoch_write),.data_i(stream_epoch_next),.data_o(prefetch_epoch));
    rv32_frequency_word_bank #(.WIDTH(32)) demand_line_owner (
        .clk_i(clk_i),.write_i(!reset_i && stream_request),.data_i(request_line),.data_o(last_demand_line));
'''


def lifecycle(t):
    fields=['resp_pc_reg','resp_line_reg','resp_epoch_reg','resp_error_reg',
            'prefetch_next_line','prefetch_epoch','last_demand_line']
    for name in fields:
        pattern=r'    reg (\[[^\n]*?\] )?'+name+';'
        t,n=re.subn(pattern,lambda m:'    wire '+(m[1] or '')+name+';',t)
        if n!=1: raise ValueError('Missing cache controller payload '+name)
    t=change(t,'    integer prefetch_remaining;',
        '''    // Positive stream occupancy is bounded by both parameters. The
    // extra sign bit preserves old signed comparisons; unsupported negative
    // distances keep the original 32-bit signed behavior rather than wrap.
    localparam integer STREAM_MAX=(PREFETCH_DISTANCE<MSHR_ENTRIES-1)?PREFETCH_DISTANCE:MSHR_ENTRIES-1;
    localparam integer STREAM_COUNT_WIDTH=(STREAM_MAX<0)?32:((STREAM_MAX<1)?2:$clog2(STREAM_MAX+1)+1);
    reg signed [STREAM_COUNT_WIDTH-1:0] prefetch_remaining;''')
    start=t.index('    always @(posedge clk_i) begin\n        if (reset_i) begin\n            resp_valid_reg')
    stop=t.index('\n    // Constant row indices',start)
    commands=t[start:stop]
    for name in fields:
        pattern=r'^            *'+name+r'\s*<=\s*[^;]*;\n'
        commands,n=re.subn(pattern,'',commands,flags=re.M)
        if n<2: raise ValueError('Expected reset and payload writes '+name)
        if re.search(r'\b'+name+r'\s*<=',commands):
            raise ValueError('Preserve and review any remaining payload NBA '+name)
    return t[:start]+OWNERS+'\n'+commands+t[stop:]


if __name__=='__main__':
    prepare('AW1_icache_response_and_stream_owners',ROOT/'AV_cache_row_and_byte_controls',
            {'rtl/cache/rv32_icache_nonblocking.v':lifecycle},
            'AV plus Icache response PC/line/epoch/error and prefetch/demand stream payload local owners with no invalid payload reset; keep hit<memory response and step<new stream<control-stream order and original valid/freeze identity, narrow signed bounded stream occupancy; no new FF/cycles and no EDA, invalid outputs require existing valid qualification')
