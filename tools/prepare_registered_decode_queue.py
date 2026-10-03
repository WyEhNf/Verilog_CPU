"""Break decode reverse-ready propagation with a two-bundle queue; no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


READ = r'''
    localparam integer READ_LEAVES=1<<$clog2(CAPACITY);
    wire [CAPACITY*LANES*WORDS-1:0] read_selections;
    genvar read_row,read_word,read_node;
    for(read_row=0;read_row<CAPACITY;read_row=read_row+1) begin:g_head_selection
        wire selected=head==read_row;
        rv32_frequency_control_tree #(.LEAVES(LANES*WORDS)) selection_tree (
            .signal_i(selected),.views_o(read_selections[read_row*LANES*WORDS +: LANES*WORDS]));
    end
    for(read_lane=0;read_lane<LANES;read_lane=read_lane+1) begin:g_read
        wire [PAYLOAD_WIDTH-1:0] payload_tree [1:2*READ_LEAVES-1];
        for(read_row=0;read_row<READ_LEAVES;read_row=read_row+1) begin:g_row
            if(read_row<CAPACITY) begin:g_present
                localparam integer HEAD_ROW=(read_row+CAPACITY-read_lane)%CAPACITY;
                for(read_word=0;read_word<WORDS;read_word=read_word+1) begin:g_word
                    localparam integer LOW=read_word*32;
                    localparam integer BITS=PAYLOAD_WIDTH-LOW>=32 ? 32 : PAYLOAD_WIDTH-LOW;
                    assign payload_tree[READ_LEAVES+read_row][LOW +: BITS]=
                        {BITS{read_selections[(HEAD_ROW*LANES+read_lane)*WORDS+read_word]}} &
                        rows[read_row*PAYLOAD_WIDTH+LOW +: BITS];
                end
            end else begin:g_padding
                assign payload_tree[READ_LEAVES+read_row]=0;
            end
        end
        for(read_node=1;read_node<READ_LEAVES;read_node=read_node+1) begin:g_or
            assign payload_tree[read_node]=payload_tree[2*read_node] | payload_tree[2*read_node+1];
        end
        assign data_o[read_lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]=payload_tree[1];
    end
    endgenerate
    initial begin
        if(CAPACITY<LANES || (CAPACITY & (CAPACITY-1))!=0)
            $fatal(1,"Decode queue capacity must be a power of two >= LANES");
    end
'''


def queue(t):
    start=t.index('module rv32_decode_bundle_register #(')
    prefix,t=t[:start],t[start:]
    t=change(t,'parameter integer LANES=4, PAYLOAD_WIDTH=194,',
               'parameter integer LANES=4, PAYLOAD_WIDTH=194, CAPACITY=2*LANES,')
    t=change(t,'parameter integer CW=(LANES<2)?1:$clog2(LANES+1),',
               'parameter integer CW=(CAPACITY<2)?1:$clog2(CAPACITY+1),')
    t=change(t,'parameter integer PW=(LANES<2)?1:$clog2(LANES)\n',
               'parameter integer PW=(CAPACITY<2)?1:$clog2(CAPACITY)\n')
    t=change(t,'wire [LANES*PAYLOAD_WIDTH-1:0] rows;',
               'wire [CAPACITY*PAYLOAD_WIDTH-1:0] rows;')
    t=change(t,'capacity=LANES-count+storage_consumed;',
               '// Upstream space is determined solely by registered occupancy.\n'
               '        capacity=CAPACITY-count;')
    t=change(t,'head<=(head+consumed)%LANES;','head<=(head+consumed)%CAPACITY;')
    t=change(t,'tail<=(tail+accepted)%LANES;','tail<=(tail+accepted)%CAPACITY;')
    t=change(t,'generate for(slot=0;slot<LANES;slot=slot+1)',
               'generate for(slot=0;slot<CAPACITY;slot=slot+1)')
    t=change(t,'.WIDTH(W),.ROW(slot),.PW(PW)) bank (',
               '.WIDTH(W),.ROW(slot),.PW(PW),.CAPACITY(CAPACITY)) bank (')
    read_start=t.index('    for(read_lane=0;read_lane<LANES;read_lane=read_lane+1) begin:g_read')
    read_stop=t.index('\nendmodule',read_start)
    t=t[:read_start]+READ+t[read_stop:]
    t=change(t,'parameter integer LANES=4,WIDTH=32,ROW=0,PW=(LANES<2)?1:$clog2(LANES)',
               'parameter integer LANES=4,WIDTH=32,ROW=0,CAPACITY=LANES,PW=(CAPACITY<2)?1:$clog2(CAPACITY)')
    t=change(t,'(((tail_i+writer)%LANES)==ROW)',
               '(((tail_i+writer)%CAPACITY)==ROW)')
    return prefix+t


if __name__=='__main__':
    prepare('AK_registered_decode_space',ROOT/'AJ_bounded_frontend_payload',
            {'rtl/cpu_core.v':queue},
            'AJ plus two-bundle decode queue with upstream free space from registered occupancy only; no same-edge downstream ready in refill capacity, bounded one-hot head read words and balanced OR; current four-lane configuration adds 776 payload bits plus 3 pointer/count bits, no ordinary pipeline level added, no EDA run')
