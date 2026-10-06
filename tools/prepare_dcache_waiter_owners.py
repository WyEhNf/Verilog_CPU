"""Dcache waiter row ownership, unchanged event ordering; source only/no EDA."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


OWNERS = r'''
    localparam integer WAITER_SLOT_WIDTH=(WAITER_ENTRIES<=1)?1:$clog2(WAITER_ENTRIES);
    localparam integer WAITER_DOMAINS=(WAITER_ENTRIES+3)/4;
    localparam integer WAITER_META_WIDTH=TAG_WIDTH+38;
    localparam integer WAITER_EVENT_WIDTH=13+3*WAITER_SLOT_WIDTH;
    wire waiter_allocate_event=static_request_action==4'd5;
    wire waiter_load_consume=resp_slot_free && waiter_load_ready_found && !demand_response_fire;
    wire waiter_store_consume=ack_slot_free && waiter_store_ready_found && !store_response_fire;
    wire [WAITER_EVENT_WIDTH*WAITER_DOMAINS-1:0] waiter_event_views;
    rv32_frequency_control_tree #(.WIDTH(WAITER_EVENT_WIDTH),.LEAVES(WAITER_DOMAINS)) waiter_event_tree (
        .signal_i({reset_i,waiter_allocate_event,local_array_write,store_response_fire,demand_response_fire,
            waiter_load_consume,waiter_store_consume,waiter_free_index[WAITER_SLOT_WIDTH-1:0],
            waiter_load_ready_index[WAITER_SLOT_WIDTH-1:0],waiter_store_ready_index[WAITER_SLOT_WIDTH-1:0],
            local_fill_index[2:0],response_index[2:0]}),.views_o(waiter_event_views));
    wire [127:0] waiter_store_fill=merge_store(mem_resp_data_i,mshr_wdata[response_index],mshr_mask[response_index]);
    genvar waiter_row;
    generate for(waiter_row=0;waiter_row<WAITER_ENTRIES;waiter_row=waiter_row+1) begin:g_waiter_owner
        wire local_reset,allocate_event,local_event,store_event,demand_event,load_consume,store_consume;
        wire [WAITER_SLOT_WIDTH-1:0] free_slot,load_slot,store_slot;
        wire [2:0] local_mshr,response_mshr;
        assign {local_reset,allocate_event,local_event,store_event,demand_event,load_consume,store_consume,
                free_slot,load_slot,store_slot,local_mshr,response_mshr}=
            waiter_event_views[(waiter_row/4)*WAITER_EVENT_WIDTH +: WAITER_EVENT_WIDTH];
        wire allocate=!local_reset && allocate_event && free_slot==waiter_row;
        wire local_fill=!local_reset && local_event && waiter_valid[waiter_row] &&
            !waiter_ready[waiter_row] && waiter_mshr[waiter_row]==local_mshr;
        wire response_fill=!local_reset && waiter_valid[waiter_row] && !waiter_ready[waiter_row] &&
            waiter_mshr[waiter_row]==response_mshr &&
            (store_event || (demand_event && !waiter_store[waiter_row]));
        // This source has only load waiter allocations. There is no producer
        // of a store waiter; its former reset/allocation FF was always zero.
        assign waiter_store[waiter_row]=1'b0;
        wire [WAITER_META_WIDTH-1:0] saved_metadata;
        rv32_frequency_word_bank #(.WIDTH(WAITER_META_WIDTH)) metadata_owner (
            .clk_i(clk_i),.write_i(allocate),
            .data_i({core_req_lsq_tag,core_req_unsigned,core_req_size,core_req_addr,matching_index[2:0]}),
            .data_o(saved_metadata));
        assign {waiter_lsq[waiter_row],waiter_unsigned[waiter_row],waiter_size[waiter_row],
                waiter_addr[waiter_row],waiter_mshr[waiter_row]}=saved_metadata;
        wire line_write;
        wire [127:0] line_next;
        rv32_frequency_event_select #(.WIDTH(128),.EVENTS(2)) line_selector (
            .events_i({response_fill && !waiter_store[waiter_row],local_fill && !waiter_store[waiter_row]}),
            .values_i({(store_event?waiter_store_fill:mem_resp_data_i),mshr_wdata[local_fill_index]}),
            .write_o(line_write),.value_o(line_next));
        rv32_frequency_word_bank #(.WIDTH(128)) line_owner (
            .clk_i(clk_i),.write_i(line_write),.data_i(line_next),.data_o(waiter_line[waiter_row]));
        wire error_write,error_next;
        rv32_frequency_event_select #(.WIDTH(1),.EVENTS(3)) error_selector (
            .events_i({response_fill,local_fill,allocate}),
            .values_i({(mem_resp_error_i || !response_matches),1'b0,1'b0}),
            .write_o(error_write),.value_o(error_next));
        rv32_frequency_word_bank #(.WIDTH(1)) error_owner (
            .clk_i(clk_i),.write_i(error_write),.data_i(error_next),.data_o(waiter_error[waiter_row]));
        always @(posedge clk_i) begin
            if(local_reset) begin
                waiter_valid[waiter_row]<=1'b0;
                waiter_ready[waiter_row]<=1'b0;
            end else begin
                if(allocate) begin waiter_valid[waiter_row]<=1'b1;waiter_ready[waiter_row]<=1'b0;end
                if(local_fill) waiter_ready[waiter_row]<=1'b1;
                if(load_consume && load_slot==waiter_row) begin
                    waiter_valid[waiter_row]<=1'b0;waiter_ready[waiter_row]<=1'b0;
                end
                if(store_consume && store_slot==waiter_row) begin
                    waiter_valid[waiter_row]<=1'b0;waiter_ready[waiter_row]<=1'b0;
                end
                // Memory response is the last original NBA writer.
                if(response_fill) waiter_ready[waiter_row]<=1'b1;
            end
        end
    end endgenerate
'''


def owners(t):
    payload=['waiter_store','waiter_mshr','waiter_addr','waiter_size','waiter_unsigned','waiter_lsq','waiter_line','waiter_error']
    for field in payload:
        pattern=r'^    reg (\[[^\n]*?\] )?'+field+r' \[0:WAITER_ENTRIES-1\];'
        t,n=re.subn(pattern,lambda m:'    wire '+(m[1] or '')+field+' [0:WAITER_ENTRIES-1];',t,flags=re.M)
        if n!=1: raise ValueError('Expected waiter declaration '+field)
    start=t.index('    always @(posedge clk_i) begin\n        if (reset_i) begin\n            resp_valid_reg')
    stop=t.index('\n    initial begin',start)
    commands=t[start:stop]
    # Entire old waiter fill loops now belong to row owners; remove their if
    # guards with the loops, avoiding orphaned single-statement conditions.
    loops=list(re.finditer(r'^ +for \(waiter_index = 0;',commands,flags=re.M))
    if len(loops)!=3: raise ValueError('Expected local/store/demand fill loops')
    for m in reversed(loops):
        a=m.start()
        tail=commands[a:]
        b=re.search(r'^'+re.escape(m.group(0).split('for')[0])+r'end\n',tail,flags=re.M)
        if not b: raise ValueError('Missing same-indent loop end')
        commands=commands[:a]+commands[a+b.end():]
    # The reset waiter loop contains no other state.
    commands,n=re.subn(r'^            for \(reset_index = 0; reset_index < WAITER_ENTRIES;[^\n]*\n.*?^            end\n','',commands,flags=re.M|re.S)
    if n!=1: raise ValueError('Expected reset waiter loop')
    for field in payload+['waiter_valid','waiter_ready']:
        pattern=r'^ +'+field+r'\[[^\n]*?\]\s*<=\s*[^;]*;\n'
        commands,n=re.subn(pattern,'',commands,flags=re.M)
        if re.search(r'^ +'+field+r'\[[^\]\n]*\]\s*<=',commands,flags=re.M):
            raise ValueError('Residual waiter NBA '+field)
    return t[:start]+OWNERS+'\n'+commands+t[stop:]


if __name__=='__main__':
    prepare('BA_dcache_waiter_row_owners',ROOT/'AZ1_dcache_mshr_payload_owners',
            {'rtl/cache/rv32_dcache_nonblocking.v':owners},
            'AZ1 plus Dcache waiter metadata/128-bit line/error validity-owned row payload and distributed allocate/fill/consume lifecycle; local fill<consume<memory response priority, complete initialization before valid/ready exposure, preserve load/store refill merge and consumer cycles; no new FF/cycles and no EDA')
