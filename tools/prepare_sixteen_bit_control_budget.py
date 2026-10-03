"""Tighten main payload control leaves to sixteen sinks, source only/no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


def replaces(t, pairs):
    for old,new in pairs: t=change(t,old,new)
    return t


def common(t):
    t=replaces(t,[
        ('localparam integer WORDS=(WIDTH+31)/32;','localparam integer WORDS=(WIDTH+15)/16;'),
        ('parameter integer WORDS=(WIDTH+31)/32','parameter integer WORDS=(WIDTH+15)/16'),
    ])
    for old,new in [('LOW=word_id*32','LOW=word_id*16'),('WIDTH-LOW>=32 ? 32 : WIDTH-LOW','WIDTH-LOW>=16 ? 16 : WIDTH-LOW')]:
        if t.count(old)!=2: raise ValueError('Expected two common control word anchors '+old)
        t=t.replace(old,new)
    return t.replace('at most 32 existing payload','at most 16 existing payload').replace('at most 32 payload bits','at most 16 payload bits')


def rs(t):
    return replaces(t,[
        ('WORDS=(ALLOC_PAYLOAD_WIDTH+31)/32','WORDS=(ALLOC_PAYLOAD_WIDTH+15)/16'),
        ('LOW=alloc_word*32','LOW=alloc_word*16'),
        ('ALLOC_PAYLOAD_WIDTH-LOW>=32 ? 32 : ALLOC_PAYLOAD_WIDTH-LOW','ALLOC_PAYLOAD_WIDTH-LOW>=16 ? 16 : ALLOC_PAYLOAD_WIDTH-LOW'),
        ('ISSUE_DATA_WORDS=(ISSUE_DATA_WIDTH+31)/32','ISSUE_DATA_WORDS=(ISSUE_DATA_WIDTH+15)/16'),
        ('LOW=issue_word*32','LOW=issue_word*16'),
        ('ISSUE_DATA_WIDTH-LOW>=32 ? 32 : ISSUE_DATA_WIDTH-LOW','ISSUE_DATA_WIDTH-LOW>=16 ? 16 : ISSUE_DATA_WIDTH-LOW'),
    ])


def frontend(t):
    return replaces(t,[
        ('READ_WORDS=(READ_DATA_WIDTH+31)/32','READ_WORDS=(READ_DATA_WIDTH+15)/16'),
        ('LOW=read_word*32','LOW=read_word*16'),
        ('READ_DATA_WIDTH-LOW>=32 ? 32 : READ_DATA_WIDTH-LOW','READ_DATA_WIDTH-LOW>=16 ? 16 : READ_DATA_WIDTH-LOW'),
    ])


def decode(t):
    return replaces(t,[
        ('WORDS=(PAYLOAD_WIDTH+31)/32','WORDS=(PAYLOAD_WIDTH+15)/16'),
        ('W=((PAYLOAD_WIDTH-word_id*32)<32)?(PAYLOAD_WIDTH-word_id*32):32','W=((PAYLOAD_WIDTH-word_id*16)<16)?(PAYLOAD_WIDTH-word_id*16):16'),
        ('data_i[writer*PAYLOAD_WIDTH+word_id*32 +: W]','data_i[writer*PAYLOAD_WIDTH+word_id*16 +: W]'),
        ('rows[slot*PAYLOAD_WIDTH+word_id*32 +: W]','rows[slot*PAYLOAD_WIDTH+word_id*16 +: W]'),
        ('LOW=read_word*32','LOW=read_word*16'),
        ('PAYLOAD_WIDTH-LOW>=32 ? 32 : PAYLOAD_WIDTH-LOW','PAYLOAD_WIDTH-LOW>=16 ? 16 : PAYLOAD_WIDTH-LOW'),
    ])


def rename(t):
    return replaces(t,[
        ('FREE_WORDS=(PHYS_REGS+31)/32','FREE_WORDS=(PHYS_REGS+15)/16'),
        ('LOW=free_word*32','LOW=free_word*16'),
        ('PHYS_REGS-LOW>=32 ? 32 : PHYS_REGS-LOW','PHYS_REGS-LOW>=16 ? 16 : PHYS_REGS-LOW'),
    ])


def backend(t):
    t=change(t,'CHUNKS=(PAYLOAD_WIDTH+31)/32','CHUNKS=(PAYLOAD_WIDTH+15)/16')
    for old,new in [('LOW=chunk*32','LOW=chunk*16'),('(PAYLOAD_WIDTH-LOW>=32)?32:PAYLOAD_WIDTH-LOW','(PAYLOAD_WIDTH-LOW>=16)?16:PAYLOAD_WIDTH-LOW')]:
        if t.count(old)!=2: raise ValueError('Expected issue queue read/write anchors '+old)
        t=t.replace(old,new)
    return t


def lsq(t):
    return replaces(t,[
        ('REPORT_WORDS=(REPORT_WIDTH+31)/32','REPORT_WORDS=(REPORT_WIDTH+15)/16'),
        ('ACK_WORDS=(ACK_WIDTH+31)/32','ACK_WORDS=(ACK_WIDTH+15)/16'),
        ('BITS=REPORT_WIDTH-LOW>=32?32:REPORT_WIDTH-LOW','BITS=REPORT_WIDTH-LOW>=16?16:REPORT_WIDTH-LOW'),
        ('BITS=ACK_WIDTH-LOW>=32?32:ACK_WIDTH-LOW','BITS=ACK_WIDTH-LOW>=16?16:ACK_WIDTH-LOW'),
    ]).replace('LOW=report_word*32','LOW=report_word*16')


def icache(t):
    return replaces(t,[
        ('wire [3:0] response_data_write,response_data_memory;','wire [7:0] response_data_write,response_data_memory;'),
        ('#(.LEAVES(4)) response_write_tree','#(.LEAVES(8)) response_write_tree'),
        ('#(.LEAVES(4)) response_select_tree','#(.LEAVES(8)) response_select_tree'),
        ('for(response_word=0;response_word<4;','for(response_word=0;response_word<8;'),
        ('resp_data_reg[response_word*32 +: 32]','resp_data_reg[response_word*16 +: 16]'),
        ('mem_resp_data_i[response_word*32 +: 32]','mem_resp_data_i[response_word*16 +: 16]'),
        ('data_rdata[response_word*32 +: 32]','data_rdata[response_word*16 +: 16]'),
    ])


def rob(t):
    t=replaces(t,[
        ('ALLOC_DATA_WORDS=(ALLOC_DATA_WIDTH+31)/32','ALLOC_DATA_WORDS=(ALLOC_DATA_WIDTH+15)/16'),
        ('LOW=alloc_word*32','LOW=alloc_word*16'),
        ('ALLOC_DATA_WIDTH-LOW>=32 ? 32 : ALLOC_DATA_WIDTH-LOW','ALLOC_DATA_WIDTH-LOW>=16 ? 16 : ALLOC_DATA_WIDTH-LOW'),
        ('wire [3:0] c_select;','wire [(LOCAL_COMPLETION_DATA_WIDTH+15)/16-1:0] c_select;'),
    ])
    start=t.index('                    rv32_frequency_control_tree #(.LEAVES(4)) select_tree')
    stop=t.index('                    wire [31:0] commit_offset',start)
    selection=r'''                    rv32_frequency_control_tree #(.LEAVES((LOCAL_COMPLETION_DATA_WIDTH+15)/16)) select_tree (
                        .signal_i(completion_grant[command_lane]),.views_o(c_select));
                    for(genvar completion_word=0;completion_word<(LOCAL_COMPLETION_DATA_WIDTH+15)/16;
                        completion_word=completion_word+1) begin:g_word
                        localparam integer LOW=completion_word*16;
                        localparam integer BITS=LOCAL_COMPLETION_DATA_WIDTH-LOW>=16?16:LOCAL_COMPLETION_DATA_WIDTH-LOW;
                        assign completion_mux[LOCAL_COMPLETION_LEAVES+command_lane][LOW +: BITS]=
                            {BITS{c_select[completion_word]}} & c_data[LOW +: BITS];
                    end
'''
    return t[:start]+selection+t[stop:]


def prf(t):
    t=replaces(t,[
        ('wire bypass_write,bypass_select;','wire bypass_write;\n            wire [1:0] bypass_select;'),
        ('wire [1:0] select_views;','wire [2:0] select_views;'),
        ('#(.LEAVES(2)) selection_tree','#(.LEAVES(3)) selection_tree'),
        ('assign stored_tree[READ_ROWS+row]={32{select_views[0]}} & value[row];',
         'assign stored_tree[READ_ROWS+row]={{16{select_views[1]}} & value[row][31:16],{16{select_views[0]}} & value[row][15:0]};'),
        ('assign ready_tree[READ_ROWS+row]=select_views[1] && ready[row];','assign ready_tree[READ_ROWS+row]=select_views[2] && ready[row];'),
        ('#(.LEAVES(1)) bypass_choice_tree','#(.LEAVES(2)) bypass_choice_tree'),
        ('read_data_o[rp*32 +: 32]=bypass_select?bypass_value:stored_tree[1];',
         'read_data_o[rp*32 +: 32]={bypass_select[1]?bypass_value[31:16]:stored_tree[1][31:16],bypass_select[0]?bypass_value[15:0]:stored_tree[1][15:0]};'),
    ])
    start=t.index('    wire [LANES-1:0] grants,local_grants;',t.index('module rv32_prf_value_row'))
    stop=t.index('    always @(posedge clk_i) begin\n        if(reset_i) ready_o<=0;',start)
    writer=r'''    wire [1:0] write_views;
    wire write_event;
    wire [31:0] next_value;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(LANES)) value_selector (
        .events_i(write_matches_i),.values_i(write_values_i),.write_o(write_event),.value_o(next_value));
    rv32_frequency_control_tree #(.LEAVES(2)) write_tree (
        .signal_i(!reset_i && write_event),.views_o(write_views));
    always @(posedge clk_i) if(write_views[0]) value_o[15:0]<=next_value[15:0];
    always @(posedge clk_i) if(write_views[1]) value_o[31:16]<=next_value[31:16];
'''
    return t[:start]+writer+t[stop:]


def completion(t):
    t=change(t,'genvar payload_lane,payload_source,payload_node;','genvar payload_lane,payload_source,payload_node,payload_word;')
    start=t.index('                wire [4:0] selected_views;')
    stop=t.index('            end else begin:g_zero',start)
    payload=r'''                localparam integer DATA_WIDTH=DIRECT_META_WIDTH+128;
                localparam integer WORDS=(DATA_WIDTH+15)/16;
                wire [WORDS-1:0] selected_views;
                wire [DATA_WIDTH-1:0] data={
                    producer_tag_i[payload_source*TAG_WIDTH +: TAG_WIDTH],
                    producer_phys_rd_i[payload_source*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH],
                    producer_rd_we_i[payload_source] && !producer_is_store_i[payload_source],
                    producer_is_store_i[payload_source],producer_is_branch_i[payload_source],
                    producer_branch_taken_i[payload_source],producer_redirect_valid_i[payload_source],
                    producer_is_memory_i[payload_source],producer_is_load_i[payload_source],
                    producer_value_i[payload_source*32 +: 32],producer_addr_i[payload_source*32 +: 32],
                    producer_store_data_i[payload_source*32 +: 32],producer_branch_target_i[payload_source*32 +: 32]};
                wire [DATA_WIDTH-1:0] selected_data;
                rv32_frequency_control_tree #(.LEAVES(WORDS)) select_tree (
                    .signal_i(selected_mask[payload_lane][payload_source] && !reset_i && !flush_i),
                    .views_o(selected_views));
                for(payload_word=0;payload_word<WORDS;payload_word=payload_word+1) begin:g_word
                    localparam integer LOW=payload_word*16;
                    localparam integer BITS=DATA_WIDTH-LOW>=16?16:DATA_WIDTH-LOW;
                    assign selected_data[LOW +: BITS]={BITS{selected_views[payload_word]}} & data[LOW +: BITS];
                end
                assign meta_tree[RANK_LEAVES+payload_source]=selected_data[128 +: DIRECT_META_WIDTH];
                assign value_tree[RANK_LEAVES+payload_source]=selected_data[96 +: 32];
                assign memory_tree[RANK_LEAVES+payload_source]=selected_data[32 +: 64];
                assign target_tree[RANK_LEAVES+payload_source]=selected_data[0 +: 32];
'''
    return t[:start]+payload+t[stop:]


if __name__=='__main__':
    prepare('AT1_sixteen_bit_payload_control_budget',ROOT/'AS_lsq_balanced_report_and_admission',{
        'rtl/common/rv32_asap7_fanout.v':common,
        'rtl/backend/rv32_reservation_station.v':rs,
        'rtl/backend/rv32_rob.v':rob,
        'rtl/backend/rv32_lsq.v':lsq,
        'rtl/backend/rv32_completion_network.v':completion,
        'rtl/backend/rv32_backend_joint.v':backend,
        'rtl/rv32_physical_register_file.v':prf,
        'rtl/rv32_rename_unit.v':rename,
        'rtl/frontend/rv32_fetch_frontend.v':frontend,
        'rtl/cpu_core.v':decode,
        'rtl/cache/rv32_icache_nonblocking.v':icache,
    },'AS plus sixteen-bit groups for shared word/event owners, RS allocation/issue, ROB allocation/completion, LSQ report/ACK, completion payloads, PRF read/write/bypass, frontend/decode read/write, issue queues, raw free bitmap and Icache response payload; based on fixed-library NAND2x1 input load vs weak INV max cap; no FF/cycle/ISA-width change and no EDA; actual cap/slew and hierarchy mapping still unverified')
