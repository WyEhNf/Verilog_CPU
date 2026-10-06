"""Bound AXI transaction/queue queries and word/address output masks; no EDA."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


def reader(t,name,width,fields,entries,index,index_width):
    flat=f'{name}_rows'
    text=f'    localparam integer {name.upper()}_WIDTH={width};\n'
    text+=f'    wire [{entries}*{name.upper()}_WIDTH-1:0] {flat};\n'
    text+=f'    genvar {name}_row;\n'
    text+=f'    generate for({name}_row=0;{name}_row<{entries};{name}_row={name}_row+1) begin:g_{name}_rows\n'
    text+=f'        assign {flat}[{name}_row*{name.upper()}_WIDTH +: {name.upper()}_WIDTH]={{'
    text+=','.join(field+'['+name+'_row]' for field,_,_ in fields)+'};\n    end endgenerate\n'
    values=[]
    for field,bits,label in fields:
        alias='query_'+name+'_'+label
        text+='    wire '+('['+bits+'] ' if bits else '')+alias+';\n'
        t=re.sub(r'(?<!\w)'+re.escape(field+'['+index+']'),alias,t)
        values.append(alias)
    text+=f'    rv32_frequency_array_read #(.WIDTH({name.upper()}_WIDTH),.ENTRIES({entries}),.INDEX_WIDTH({index_width})) {name}_reader (\n'
    text+=f'        .rows_i({flat}),.index_i({index}),.value_o({{'+','.join(values)+'}));\n'
    return t,text


WORDS = r'''
    localparam integer WRITE_WORDS=4*WRITE_LINES;
    wire [WRITE_WORDS*36-1:0] write_word_rows;
    wire [WPW+1:0] write_word_query={write_issue_slot,query_write_issue_sent[1:0]};
    wire [31:0] selected_write_word;
    wire [3:0] current_mask;
    genvar selected_word;
    generate for(selected_word=0;selected_word<WRITE_WORDS;selected_word=selected_word+1) begin:g_write_word_rows
        assign write_word_rows[selected_word*36 +: 36]={
            write_data[selected_word/4][(selected_word%4)*32 +: 32],write_mask[selected_word/4][(selected_word%4)*4 +: 4]};
    end endgenerate
    rv32_frequency_array_read #(.WIDTH(36),.ENTRIES(WRITE_WORDS),.INDEX_WIDTH(WPW+2)) write_word_reader (
        .rows_i(write_word_rows),.index_i(write_word_query),.value_o({selected_write_word,current_mask}));
    wire [1:0] read_address_views;
    wire [4:0] write_output_views;
    rv32_frequency_control_tree #(.LEAVES(2)) read_address_tree (
        .signal_i(read_active),.views_o(read_address_views));
    rv32_frequency_control_tree #(.LEAVES(5)) write_output_tree (
        .signal_i(write_active),.views_o(write_output_views));
    wire [31:0] selected_read_address=query_read_issue_addr+{28'b0,query_read_issue_sent[1:0],2'b0};
    wire [31:0] selected_write_address=query_write_issue_addr+{28'b0,query_write_issue_sent[1:0],2'b0};
    genvar output_word;
    generate for(output_word=0;output_word<2;output_word=output_word+1) begin:g_axi_output_words
        assign araddr[output_word*16 +: 16]={16{read_address_views[output_word]}} & selected_read_address[output_word*16 +: 16];
        assign awaddr[output_word*16 +: 16]={16{write_output_views[output_word]}} & selected_write_address[output_word*16 +: 16];
        assign wdata[output_word*16 +: 16]={16{write_output_views[output_word+2]}} & selected_write_word[output_word*16 +: 16];
    end endgenerate
    assign wstrb={4{write_output_views[4]}} & current_mask;
'''


def queries(t):
    insert=''
    for name,width,fields,entries,index,index_width in [
        ('read_issue','35',[('read_addr','31:0','addr'),('read_sent','2:0','sent')],
            'READ_LINES','read_issue_slot','RPW'),
        ('read_reply','170',[('read_addr','31:0','addr'),('read_data','127:0','data'),
            ('read_id','7:0','id'),('read_error',None,'error'),('read_data_side',None,'side')],
            'READ_LINES','read_reply','RPW'),
        ('write_issue','35',[('write_addr','31:0','addr'),('write_sent','2:0','sent')],
            'WRITE_LINES','write_issue_slot','WPW'),
        ('write_reply','41',[('write_addr','31:0','addr'),('write_id','7:0','id'),('write_error',None,'error')],
            'WRITE_LINES','write_reply','WPW'),
        ('read_return','RPW+2',[('rq_slot','RPW-1:0','slot'),('rq_word','1:0','word')],
            'WORD_QUEUE','rq_head','QPW'),
        ('write_return','WPW',[('wq_slot','WPW-1:0','slot')],
            'WORD_QUEUE','wq_head','QPW'),
    ]:
        t,block=reader(t,name,width,fields,entries,index,index_width)
        insert+=block
    t=change(t,'    function [2:0] enabled_words;',insert+WORDS+'\n    function [2:0] enabled_words;')
    for old in [
        "    assign araddr = read_active ? query_read_issue_addr + {28'd0, query_read_issue_sent[1:0], 2'b00} : 0;\n",
        '    wire [3:0] current_mask = write_mask[write_issue_slot] >> (query_write_issue_sent[1:0] * 4);\n',
        "    assign awaddr = write_active ? query_write_issue_addr + {28'd0, query_write_issue_sent[1:0], 2'b00} : 0;\n",
        '    assign wdata = write_active ? write_data[write_issue_slot] >> (query_write_issue_sent[1:0] * 32) : 0;\n',
        '    assign wstrb = write_active ? current_mask : 0;\n',
    ]:
        t=change(t,old,'')
    return t


if __name__=='__main__':
    prepare('BM_axi_bounded_transaction_queries',ROOT/'BL_axi_balanced_cursor_arbitration',
            {'rtl/course/rv32_axi_lite_bridge.v':queries},
            'BL plus field-specific AXI issue/reply and request-word queue binary reads with four-row query domains and sixteen-bit select leaves; flatten word/mask selection into one 36-bit write-word query and bound AR/AW/W output masks, keep exact address addition and original handshakes; no new FF/cycles and no EDA')
