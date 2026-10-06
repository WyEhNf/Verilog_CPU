"""Own AXI transaction lifecycle and queue metadata per row; no EDA."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


OWNERS = r'''
    localparam integer WRITE_DOMAINS=(WRITE_LINES+3)/4;
    localparam integer READ_LIFECYCLE_WIDTH=6+4*RPW;
    localparam integer WRITE_LIFECYCLE_WIDTH=9+4*WPW;
    wire [READ_DOMAINS*READ_LIFECYCLE_WIDTH-1:0] read_lifecycle_views;
    wire [WRITE_DOMAINS*WRITE_LIFECYCLE_WIDTH-1:0] write_lifecycle_views;
    wire write_progress=write_active && (current_mask==0 || write_push);
    rv32_frequency_control_tree #(.WIDTH(READ_LIFECYCLE_WIDTH),.LEAVES(READ_DOMAINS)) read_lifecycle_tree (
        .signal_i({reset,read_allocate,read_free[RPW-1:0],read_push,read_issue_slot,
            read_pop,rq_slot[rq_head],fill_read,read_reply[RPW-1:0],(rresp!=0)}),.views_o(read_lifecycle_views));
    rv32_frequency_control_tree #(.WIDTH(WRITE_LIFECYCLE_WIDTH),.LEAVES(WRITE_DOMAINS)) write_lifecycle_tree (
        .signal_i({reset,take_d_write,write_free[WPW-1:0],write_progress,write_issue_slot,
            write_pop,wq_slot[wq_head],fill_write,write_reply[WPW-1:0],(bresp!=0),enabled_words(d_req_mask)}),
        .views_o(write_lifecycle_views));
    genvar lifecycle_row,queue_row;
    generate
        for(lifecycle_row=0;lifecycle_row<READ_LINES;lifecycle_row=lifecycle_row+1) begin:g_read_lifecycle
            wire local_reset,allocate,push,pop,fill,error;
            wire [RPW-1:0] free_slot,issue_slot,return_slot,reply_slot;
            assign {local_reset,allocate,free_slot,push,issue_slot,pop,return_slot,fill,reply_slot,error}=
                read_lifecycle_views[(lifecycle_row/4)*READ_LIFECYCLE_WIDTH +: READ_LIFECYCLE_WIDTH];
            always @(posedge clock) begin
                if(local_reset) read_valid[lifecycle_row]<=1'b0;
                else begin
                    if(allocate && free_slot==lifecycle_row) begin
                        read_valid[lifecycle_row]<=1'b1;
                        read_sent[lifecycle_row]<=0;
                        read_received[lifecycle_row]<=0;
                        read_error[lifecycle_row]<=1'b0;
                    end
                    if(push && issue_slot==lifecycle_row) read_sent[lifecycle_row]<=read_sent[lifecycle_row]+1'b1;
                    if(pop && return_slot==lifecycle_row) begin
                        read_received[lifecycle_row]<=read_received[lifecycle_row]+1'b1;
                        read_error[lifecycle_row]<=read_error[lifecycle_row] || error;
                    end
                    if(fill && reply_slot==lifecycle_row) read_valid[lifecycle_row]<=1'b0;
                end
            end
        end
        for(lifecycle_row=0;lifecycle_row<WRITE_LINES;lifecycle_row=lifecycle_row+1) begin:g_write_lifecycle
            wire local_reset,allocate,progress,pop,fill,error;
            wire [WPW-1:0] free_slot,issue_slot,return_slot,reply_slot;
            wire [2:0] expected;
            assign {local_reset,allocate,free_slot,progress,issue_slot,pop,return_slot,fill,reply_slot,error,expected}=
                write_lifecycle_views[(lifecycle_row/4)*WRITE_LIFECYCLE_WIDTH +: WRITE_LIFECYCLE_WIDTH];
            always @(posedge clock) begin
                if(local_reset) write_valid[lifecycle_row]<=1'b0;
                else begin
                    if(allocate && free_slot==lifecycle_row) begin
                        write_valid[lifecycle_row]<=1'b1;
                        write_sent[lifecycle_row]<=(expected==0)?3'd4:3'd0;
                        write_received[lifecycle_row]<=0;
                        write_expected[lifecycle_row]<=expected;
                        write_error[lifecycle_row]<=1'b0;
                    end
                    if(progress && issue_slot==lifecycle_row) write_sent[lifecycle_row]<=write_sent[lifecycle_row]+1'b1;
                    if(pop && return_slot==lifecycle_row) begin
                        write_received[lifecycle_row]<=write_received[lifecycle_row]+1'b1;
                        write_error[lifecycle_row]<=write_error[lifecycle_row] || error;
                    end
                    if(fill && reply_slot==lifecycle_row) write_valid[lifecycle_row]<=1'b0;
                end
            end
        end
        for(queue_row=0;queue_row<WORD_QUEUE;queue_row=queue_row+1) begin:g_word_queue_metadata
            wire [RPW+1:0] read_metadata;
            rv32_frequency_word_bank #(.WIDTH(RPW+2)) read_owner (
                .clk_i(clock),.write_i(read_push && rq_tail==queue_row),
                .data_i({read_issue_slot,read_sent[read_issue_slot][1:0]}),.data_o(read_metadata));
            assign {rq_slot[queue_row],rq_word[queue_row]}=read_metadata;
            rv32_frequency_word_bank #(.WIDTH(WPW)) write_owner (
                .clk_i(clock),.write_i(write_push && wq_tail==queue_row),
                .data_i(write_issue_slot),.data_o(wq_slot[queue_row]));
        end
    endgenerate
'''


def lifecycle(t):
    for d in ['[RPW-1:0] rq_slot [0:WORD_QUEUE-1]','[1:0] rq_word [0:WORD_QUEUE-1]',
              '[WPW-1:0] wq_slot [0:WORD_QUEUE-1]']:
        t=change(t,'    reg '+d+';','    wire '+d+';')
    a=t.index('    always @(posedge clock) begin\n        if (reset) begin\n            read_valid')
    b=t.index('    initial begin',a)
    commands=t[a:b]
    commands=change(commands,'            read_valid <= 0; write_valid <= 0;\n','')
    expected={'read_valid':2,'read_sent':2,'read_received':2,'read_error':2,
              'write_valid':2,'write_sent':2,'write_received':2,'write_expected':1,'write_error':2,
              'rq_slot':1,'rq_word':1,'wq_slot':1}
    for field,count in expected.items():
        # Complete scalar/constant-width indexed assignment only. This does
        # not consume a relational expression or a neighbouring NBA.
        commands,n=re.subn(r'(?<!\w)'+field+r'\[[^\n]*?\]\s*<=\s*[^;]*;','',commands)
        if n!=count: raise ValueError('Expected lifecycle/queue writes '+field+': '+str(n))
    return t[:a]+OWNERS+'\n'+commands+t[b:]


if __name__=='__main__':
    prepare('BK1_axi_row_lifecycle',ROOT/'BJ_axi_payload_owners',
            {'rtl/course/rv32_axi_lite_bridge.v':lifecycle},
            'BJ plus distributed AXI row-owned valid/sent/received/error/expected lifecycle and request-word queue metadata; preserve allocation<send<return<reply NBA order, no reset of invalid status/payload, counts/pointers/AW-W pairing remain at original edges; no added FF/cycles and no EDA')
