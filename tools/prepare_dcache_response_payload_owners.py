"""Own Dcache response and acknowledgement payloads at their original edge."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


OWNERS = r'''
    localparam integer DCACHE_RESPONSE_META_WIDTH=TAG_WIDTH+34;
    wire response_hit_capture=!reset_i && static_request_action==4'd1;
    wire response_forward_capture=!reset_i && static_request_action==4'd3;
    wire response_waiter_capture=!reset_i && waiter_load_consume;
    wire response_victim_failure=!reset_i && mem_resp_valid_i && mem_resp_ready_o &&
        mshr_writeback[response_index] && (mem_resp_error_i || !response_matches);
    wire response_failed_load=response_victim_failure && !mshr_store[response_index];
    wire response_failed_store=response_victim_failure && mshr_store[response_index];
    wire response_demand_capture=!reset_i && demand_response_fire;
    wire response_metadata_write;
    wire [DCACHE_RESPONSE_META_WIDTH-1:0] response_metadata_next,response_metadata_saved;
    rv32_frequency_event_select #(.WIDTH(DCACHE_RESPONSE_META_WIDTH),.EVENTS(5)) response_metadata_selector (
        .events_i({response_demand_capture,response_failed_load,response_waiter_capture,response_forward_capture,response_hit_capture}),
        .values_i({
            mshr_lsq[response_index],mshr_addr[response_index],(!mem_resp_error_i && response_matches),(mem_resp_error_i || !response_matches),
            mshr_lsq[response_index],mshr_addr[response_index],1'b0,1'b1,
            waiter_lsq[waiter_load_ready_index],waiter_addr[waiter_load_ready_index],!waiter_error[waiter_load_ready_index],waiter_error[waiter_load_ready_index],
            core_req_lsq_tag,core_req_addr,1'b1,1'b0,
            core_req_lsq_tag,core_req_addr,1'b1,1'b0}),
        .write_o(response_metadata_write),.value_o(response_metadata_next));
    rv32_frequency_word_bank #(.WIDTH(DCACHE_RESPONSE_META_WIDTH)) response_metadata_owner (
        .clk_i(clk_i),.write_i(response_metadata_write),.data_i(response_metadata_next),.data_o(response_metadata_saved));
    assign {resp_lsq_reg,resp_addr_reg,resp_line_valid_reg,resp_error_reg}=response_metadata_saved;

    wire response_data_write;
    wire [159:0] response_data_next,response_data_saved;
    wire response_sram_capture=!reset_i && resp_from_sram && resp_valid_reg;
    rv32_frequency_event_select #(.WIDTH(160),.EVENTS(6)) response_data_selector (
        .events_i({response_demand_capture,response_failed_load,response_waiter_capture,response_forward_capture,
                   response_hit_capture && TAG_SRAM!=0,response_sram_capture}),
        .values_i({
            mem_resp_data_i,extract_value(mem_resp_data_i,mshr_addr[response_index],mshr_size[response_index],mshr_unsigned[response_index]),
            128'b0,32'b0,
            waiter_line[waiter_load_ready_index],extract_value(waiter_line[waiter_load_ready_index],waiter_addr[waiter_load_ready_index],waiter_size[waiter_load_ready_index],waiter_unsigned[waiter_load_ready_index]),
            mshr_wdata[matching_index],extract_value(mshr_wdata[matching_index],core_req_addr,core_req_size,core_req_unsigned),
            data_rdata,extract_value(data_rdata,core_req_addr,core_req_size,core_req_unsigned),
            data_rdata,extract_value(data_rdata,resp_addr_reg,resp_size_reg,resp_unsigned_reg)}),
        .write_o(response_data_write),.value_o(response_data_next));
    rv32_frequency_word_bank #(.WIDTH(160)) response_data_owner (
        .clk_i(clk_i),.write_i(response_data_write),.data_i(response_data_next),.data_o(response_data_saved));
    assign {resp_line_reg,resp_word_reg}=response_data_saved;
    // This metadata is read only while the deferred synchronous hit is live;
    // the accepting hit initializes it before resp_from_sram exposes it.
    wire [2:0] response_size_saved;
    rv32_frequency_word_bank #(.WIDTH(3)) response_size_owner (
        .clk_i(clk_i),.write_i(response_hit_capture),.data_i({core_req_size,core_req_unsigned}),.data_o(response_size_saved));
    assign {resp_size_reg,resp_unsigned_reg}=response_size_saved;

    wire ack_payload_write;
    wire [TAG_WIDTH:0] ack_payload_next,ack_payload_saved;
    rv32_frequency_event_select #(.WIDTH(TAG_WIDTH+1),.EVENTS(3)) acknowledgement_selector (
        .events_i({response_failed_store,!reset_i && waiter_store_consume,!reset_i && request_fire && request_is_store}),
        .values_i({mshr_lsq[response_index],1'b1,
                   waiter_lsq[waiter_store_ready_index],waiter_error[waiter_store_ready_index],core_req_lsq_tag,1'b0}),
        .write_o(ack_payload_write),.value_o(ack_payload_next));
    rv32_frequency_word_bank #(.WIDTH(TAG_WIDTH+1)) acknowledgement_owner (
        .clk_i(clk_i),.write_i(ack_payload_write),.data_i(ack_payload_next),.data_o(ack_payload_saved));
    assign {ack_lsq_reg,ack_error_reg}=ack_payload_saved;
'''


def owners(t):
    fields=['resp_lsq_reg','resp_addr_reg','resp_line_reg','resp_word_reg','resp_line_valid_reg','resp_error_reg',
            'resp_size_reg','resp_unsigned_reg','ack_lsq_reg','ack_error_reg']
    for field in fields:
        pattern=r'^    reg (\[[^\n]*?\] )?'+field+';'
        t,n=re.subn(pattern,lambda m:'    wire '+(m[1] or '')+field+';',t,flags=re.M)
        if n!=1: raise ValueError('Expected response declaration '+field)
    start=t.index('    always @(posedge clk_i) begin\n        if (reset_i) begin\n            resp_valid_reg')
    stop=t.index('\n    initial begin',start)
    commands=t[start:stop]
    for field in fields:
        commands,n=re.subn(r'^ +'+field+r'\s*<=\s*[^;]*;\n','',commands,flags=re.M)
        if n<1 or re.search(r'\b'+field+r'\s*<=',commands):
            raise ValueError('Review response NBA '+field)
    for empty in ['            if (resp_from_sram && resp_valid_reg) begin\n            end\n',
                  '                    if (TAG_SRAM != 0) begin\n                    end\n']:
        commands=change(commands,empty,'')
    return t[:start]+OWNERS+'\n'+commands+t[stop:]


if __name__=='__main__':
    prepare('BC_dcache_response_payload_owners',ROOT/'BB_dcache_mshr_local_lifecycle',
            {'rtl/cache/rv32_dcache_nonblocking.v':owners},
            'BB plus Dcache response metadata/line/word/deferred-hit-size and ACK payload local event owners, retain SRAM-copy<hit<forward<waiter<writeback-failure/demand-response ordering and existing bypass/valid/backpressure; sixteen-bit select/write leaves, no added FF/cycles and no EDA')
