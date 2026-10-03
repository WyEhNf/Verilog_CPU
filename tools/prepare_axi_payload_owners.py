"""Own AXI bridge/FIFO payload at existing allocation/response edges; no EDA."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


OWNERS = r'''
    localparam integer READ_DOMAINS=(READ_LINES+3)/4;
    wire [READ_DOMAINS*(RPW+3)-1:0] read_return_views;
    wire [READ_DOMAINS*32-1:0] read_return_data;
    rv32_frequency_control_tree #(.WIDTH(RPW+3),.LEAVES(READ_DOMAINS)) read_return_tree (
        .signal_i({!reset && read_pop,rq_slot[rq_head],rq_word[rq_head]}),.views_o(read_return_views));
    rv32_frequency_control_tree #(.WIDTH(32),.LEAVES(READ_DOMAINS)) read_return_data_tree (
        .signal_i(rdata),.views_o(read_return_data));
    wire read_allocate;
    wire [40:0] read_allocate_metadata;
    rv32_frequency_event_select #(.WIDTH(41),.EVENTS(2)) read_allocate_selector (
        .events_i({take_d_read,take_i}),.values_i({1'b1,d_req_addr,d_req_id,1'b0,i_req_addr,i_req_id}),
        .write_o(read_allocate),.value_o(read_allocate_metadata));
    genvar payload_row,payload_word;
    generate
        for(payload_row=0;payload_row<READ_LINES;payload_row=payload_row+1) begin:g_read_payload_owner
            wire [40:0] metadata;
            rv32_frequency_word_bank #(.WIDTH(41)) metadata_owner (
                .clk_i(clock),.write_i(read_allocate && read_free==payload_row),
                .data_i(read_allocate_metadata),.data_o(metadata));
            assign {read_data_side[payload_row],read_addr[payload_row],read_id[payload_row]}=metadata;
            wire return_valid;
            wire [RPW-1:0] return_slot;
            wire [1:0] return_word;
            assign {return_valid,return_slot,return_word}=read_return_views[(payload_row/4)*(RPW+3) +: RPW+3];
            for(payload_word=0;payload_word<4;payload_word=payload_word+1) begin:g_word
                rv32_frequency_word_bank #(.WIDTH(32)) word_owner (
                    .clk_i(clock),.write_i(return_valid && return_slot==payload_row && return_word==payload_word),
                    .data_i(read_return_data[(payload_row/4)*32 +: 32]),.data_o(read_data[payload_row][payload_word*32 +: 32]));
            end
        end
        for(payload_row=0;payload_row<WRITE_LINES;payload_row=payload_row+1) begin:g_write_payload_owner
            wire [183:0] packet;
            rv32_frequency_word_bank #(.WIDTH(184)) owner (
                .clk_i(clock),.write_i(take_d_write && write_free==payload_row),
                .data_i({d_req_addr,d_req_id,d_req_data,d_req_mask}),.data_o(packet));
            assign {write_addr[payload_row],write_id[payload_row],write_data[payload_row],write_mask[payload_row]}=packet;
        end
        if(RESPONSE_FIFO_DEPTH==0) begin:g_legacy_payload_owner
            wire read_instruction=fill_read && !read_data_side[read_reply];
            wire read_data_response=fill_read && read_data_side[read_reply];
            wire data_write;
            wire [RESPONSE_WIDTH-1:0] data_next;
            rv32_frequency_word_bank #(.WIDTH(RESPONSE_WIDTH)) instruction_owner (
                .clk_i(clock),.write_i(read_instruction),
                .data_i({read_addr[read_reply],read_data[read_reply],read_id[read_reply],read_error[read_reply]}),
                .data_o(legacy_i_resp_packet));
            rv32_frequency_event_select #(.WIDTH(RESPONSE_WIDTH),.EVENTS(2)) data_selector (
                .events_i({fill_write,read_data_response}),
                .values_i({write_addr[write_reply],128'b0,write_id[write_reply],write_error[write_reply],
                    read_addr[read_reply],read_data[read_reply],read_id[read_reply],read_error[read_reply]}),
                .write_o(data_write),.value_o(data_next));
            rv32_frequency_word_bank #(.WIDTH(RESPONSE_WIDTH)) data_owner (
                .clk_i(clock),.write_i(data_write),.data_i(data_next),.data_o(legacy_d_resp_packet));
        end else begin:g_unused_legacy_payload
            assign legacy_i_resp_packet=0;
            assign legacy_d_resp_packet=0;
        end
    endgenerate
'''


def payload(t):
    declarations=['read_data_side [0:READ_LINES-1]','[31:0] read_addr [0:READ_LINES-1]',
                  '[7:0] read_id [0:READ_LINES-1]','[127:0] read_data [0:READ_LINES-1]',
                  '[31:0] write_addr [0:WRITE_LINES-1]','[7:0] write_id [0:WRITE_LINES-1]',
                  '[127:0] write_data [0:WRITE_LINES-1]','[15:0] write_mask [0:WRITE_LINES-1]',
                  '[RESPONSE_WIDTH-1:0] legacy_i_resp_packet, legacy_d_resp_packet']
    for d in declarations:
        t=change(t,'    reg '+d+';','    wire '+d+';')
    a=t.index('    always @(posedge clock) begin\n        if (reset) begin\n            read_valid')
    b=t.index('    initial begin',a)
    commands=t[a:b]
    for field in ['read_data_side','read_addr','read_id','read_data','write_addr','write_id','write_data','write_mask']:
        commands,n=re.subn(r'^ +'+field+r'\[[^\n]*?\](?:\[[^\n]*?\])?\s*<=\s*[^;]*;\n','',commands,flags=re.M)
        if n!=1: raise ValueError('Expected one AXI payload write '+field)
    for field,count in [('legacy_i_resp_packet',1),('legacy_d_resp_packet',2)]:
        commands,n=re.subn(r'^ +'+field+r'\s*<=\s*[^;]*;\n','',commands,flags=re.M)
        if n!=count: raise ValueError('Expected legacy packet write '+field)
    t=t[:a]+OWNERS+'\n'+commands+t[b:]
    # FIFO input choice matters only on an accepted valid packet. It is a
    # local bounded selector, with the same write-response priority.
    a=t.index('        rv32_axi_response_fifo #(.WIDTH(RESPONSE_WIDTH), .DEPTH(RESPONSE_FIFO_DEPTH)) instruction')
    t=t[:a]+'''        wire [RESPONSE_WIDTH-1:0] data_packet;
        rv32_frequency_event_select #(.WIDTH(RESPONSE_WIDTH),.EVENTS(2)) response_data_selector (
            .events_i({fill_write,fill_read && read_data_side[read_reply]}),
            .values_i({write_packet,read_packet}),.write_o(),.value_o(data_packet));
'''+t[a:]
    t=change(t,'.in_packet(fill_write ? write_packet : read_packet),','.in_packet(data_packet),')
    # Existing FIFO pointers/count stay in their original owner and cycles.
    a=t.index('module rv32_axi_response_fifo #(')
    before,part=t[:a],t[a:]
    part=change(part,'    reg [WIDTH-1:0] packets [0:DEPTH-1];','    wire [DEPTH*WIDTH-1:0] packets;')
    part=change(part,'    assign out_packet = packets[head];',r'''    rv32_frequency_array_read #(.WIDTH(WIDTH),.ENTRIES(DEPTH),.INDEX_WIDTH(PTR_WIDTH)) output_reader (
        .rows_i(packets),.index_i(head),.value_o(out_packet));
    genvar packet_row;
    generate for(packet_row=0;packet_row<DEPTH;packet_row=packet_row+1) begin:g_packet_owner
        rv32_frequency_word_bank #(.WIDTH(WIDTH)) owner (
            .clk_i(clock),.write_i(push && tail==packet_row),.data_i(in_packet),
            .data_o(packets[packet_row*WIDTH +: WIDTH]));
    end endgenerate''')
    part=change(part,'                packets[tail] <= in_packet;\n','')
    return before+part


if __name__=='__main__':
    prepare('BJ_axi_payload_owners',ROOT/'BI_dcache_query_and_hold_owners',
            {'rtl/course/rv32_axi_lite_bridge.v':payload},
            'BI plus AXI read/write transaction payload row/word owners, partial read-return word qualification, sixteen-bit legacy/FIFO response ownership and FIFO routing at existing edges; unchanged AW/W pairing, queues, arbitration, valid/credit/response order; no new FF/cycles and no EDA')
