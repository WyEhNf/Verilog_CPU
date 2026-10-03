"""Bound cache register-array reads and final request masks; source only."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


READER = r'''

// Four-row query domains, sixteen-bit selection leaves and a binary OR tree.
// Payload remains unqualified here: its transaction validity is checked by
// the consumer at the same point as the former dynamic array read.
module rv32_frequency_array_read #(
    parameter integer WIDTH=32,ENTRIES=8,
    parameter integer INDEX_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES),
    parameter integer DOMAINS=(ENTRIES+3)/4,
    parameter integer WORDS=(WIDTH+15)/16,
    parameter integer LEAVES=1<<$clog2(ENTRIES)
) (
    input wire [ENTRIES*WIDTH-1:0] rows_i,
    input wire [INDEX_WIDTH-1:0] index_i,
    output wire [WIDTH-1:0] value_o
);
    wire [DOMAINS*INDEX_WIDTH-1:0] query_views;
    wire [WIDTH-1:0] reads [1:2*LEAVES-1];
    rv32_frequency_control_tree #(.WIDTH(INDEX_WIDTH),.LEAVES(DOMAINS)) query_tree (
        .signal_i(index_i),.views_o(query_views));
    assign value_o=reads[1];
    genvar row,word,node;
    generate
        for(row=0;row<LEAVES;row=row+1) begin:g_row
            if(row<ENTRIES) begin:g_present
                wire [WORDS-1:0] selects;
                wire hit=query_views[(row/4)*INDEX_WIDTH +: INDEX_WIDTH]==row;
                rv32_frequency_control_tree #(.LEAVES(WORDS)) select_tree (
                    .signal_i(hit),.views_o(selects));
                for(word=0;word<WORDS;word=word+1) begin:g_word
                    localparam integer LOW=word*16;
                    localparam integer BITS=(WIDTH-LOW>=16)?16:WIDTH-LOW;
                    assign reads[LEAVES+row][LOW +: BITS]=
                        {BITS{selects[word]}} & rows_i[row*WIDTH+LOW +: BITS];
                end
            end else begin:g_padding
                assign reads[LEAVES+row]=0;
            end
        end
        for(node=1;node<LEAVES;node=node+1) begin:g_reduce
            assign reads[node]=reads[2*node] | reads[2*node+1];
        end
    endgenerate
endmodule
'''


MSHR_FIELDS=[('mshr_victim_data','127:0',128),('mshr_victim_entry','CACHE_ENTRY_WIDTH-1:0','CACHE_ENTRY_WIDTH'),
             ('mshr_victim_addr','31:0',32),('mshr_lsq','TAG_WIDTH-1:0','TAG_WIDTH'),
             ('mshr_wdata','127:0',128),('mshr_mask','15:0',16),('mshr_unsigned',None,1),
             ('mshr_size','1:0',2),('mshr_addr','31:0',32),('mshr_writeback',None,1),
             ('mshr_prefetch',None,1),('mshr_store',None,1)]
WAITER_FIELDS=[('waiter_line','127:0',128),('waiter_lsq','TAG_WIDTH-1:0','TAG_WIDTH'),
               ('waiter_unsigned',None,1),('waiter_size','1:0',2),('waiter_addr','31:0',32),
               ('waiter_mshr','2:0',3),('waiter_error',None,1)]


def read_family(t,family,fields,queries,entries,width):
    text=f'    localparam integer {family.upper()}_READ_WIDTH={width};\n'
    text+=f'    wire [{entries}*{family.upper()}_READ_WIDTH-1:0] {family}_read_rows;\n'
    text+=f'    genvar {family}_read_row;\n'
    text+=f'    generate for({family}_read_row=0;{family}_read_row<{entries};{family}_read_row={family}_read_row+1) begin:g_{family}_read_rows\n'
    values=','.join(name+f'[{family}_read_row]' for name,_,_ in fields)
    text+=f'        assign {family}_read_rows[{family}_read_row*{family.upper()}_READ_WIDTH +: {family.upper()}_READ_WIDTH]={{'+values+'};\n'
    text+='    end endgenerate\n'
    for port,index,index_width in queries:
        for name,bits,_ in fields:
            wire=f'query_{port}_{name}'
            text+='    wire '+('['+bits+'] ' if bits else '')+wire+';\n'
            # Only the old dynamic query is replaced, not the static row
            # drivers or scalar lifecycle assignments.
            t=re.sub(r'(?<!\w)'+re.escape(name+'['+index+']'),wire,t)
        bundle=','.join('query_'+port+'_'+name for name,_,_ in fields)
        text+=f'    rv32_frequency_array_read #(.WIDTH({family.upper()}_READ_WIDTH),.ENTRIES({entries}),.INDEX_WIDTH({index_width})) {port}_read (\n'
        text+=f'        .rows_i({family}_read_rows),.index_i({index}),.value_o({{'+bundle+'}));\n'
    return t,text


def cache(t):
    t,mshr=read_family(t,'mshr',MSHR_FIELDS,
        [('send','send_index',3),('matching','matching_index',3),('local','local_fill_index',3),('response','response_index',32)],
        'MSHR_ENTRIES','TAG_WIDTH+CACHE_ENTRY_WIDTH+342')
    # response_index stays a 32-bit procedural integer. Only its lower eight
    # bits come from the response ID; no out-of-range ID becomes an alias.
    t,waiter=read_family(t,'waiter',WAITER_FIELDS,
        [('waiter_load','waiter_load_ready_index','WAITER_SLOT_WIDTH'),
         ('waiter_store','waiter_store_ready_index','WAITER_SLOT_WIDTH')],
        'WAITER_ENTRIES','TAG_WIDTH+167')
    t=change(t,'    integer reset_index;',mshr+waiter+'\n    integer reset_index;')
    old='''    assign mem_req_wdata_o = send_found && query_send_mshr_writeback ?
                             ((victim_from_sram && victim_mshr_reg == send_index) ?
                              data_rdata : query_send_mshr_victim_data) : 128'd0;'''
    new=r'''    wire [7:0] memory_write_data_enable,memory_victim_bypass;
    wire [1:0] memory_line_enable,memory_line_victim;
    wire memory_write=send_found && query_send_mshr_writeback;
    rv32_frequency_control_tree #(.LEAVES(8)) memory_write_tree (
        .signal_i(memory_write),.views_o(memory_write_data_enable));
    rv32_frequency_control_tree #(.LEAVES(8)) memory_victim_bypass_tree (
        .signal_i(victim_from_sram && victim_mshr_reg==send_index),.views_o(memory_victim_bypass));
    rv32_frequency_control_tree #(.LEAVES(2)) memory_line_enable_tree (
        .signal_i(send_found),.views_o(memory_line_enable));
    rv32_frequency_control_tree #(.LEAVES(2)) memory_line_victim_tree (
        .signal_i(query_send_mshr_writeback),.views_o(memory_line_victim));
    genvar memory_word;
    generate
        for(memory_word=0;memory_word<8;memory_word=memory_word+1) begin:g_memory_write_word
            wire [15:0] selected_data=memory_victim_bypass[memory_word]?
                data_rdata[memory_word*16 +: 16]:query_send_mshr_victim_data[memory_word*16 +: 16];
            assign mem_req_wdata_o[memory_word*16 +: 16]={16{memory_write_data_enable[memory_word]}} & selected_data;
        end
        for(memory_word=0;memory_word<2;memory_word=memory_word+1) begin:g_memory_address_word
            wire [31:0] demand_line={query_send_mshr_addr[31:4],4'b0};
            wire [15:0] selected_address=memory_line_victim[memory_word]?
                query_send_mshr_victim_addr[memory_word*16 +: 16]:demand_line[memory_word*16 +: 16];
            assign mem_req_line_addr_o[memory_word*16 +: 16]={16{memory_line_enable[memory_word]}} & selected_address;
        end
    endgenerate'''
    t=change(t,old,new)
    t=change(t,'''    assign mem_req_line_addr_o = send_found ?
                                  (query_send_mshr_writeback ?
                                   query_send_mshr_victim_addr :
                                   {query_send_mshr_addr[31:4], 4'b0}) : 32'd0;
''','')
    return t


if __name__=='__main__':
    prepare('BF1_bounded_cache_payload_queries',ROOT/'BE_balanced_cache_priority',{
        'rtl/cache/rv32_dcache_nonblocking.v':cache,
        'rtl/common/rv32_asap7_fanout.v':lambda t:t+READER,
    },'BE plus Dcache send/matching/local/response and waiter payload query domains and sixteen-bit one-hot binary routing; final 128-bit memory write data valid/bypass and 32-bit line address masks split into sixteen-bit leaves, unchanged locked transaction/backpressure and valid qualification; no new FF/cycles and no EDA')
