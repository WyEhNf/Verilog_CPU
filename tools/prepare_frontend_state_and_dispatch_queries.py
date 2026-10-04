"""Bound frontend state writes and reserved-dispatch recovery status reads."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


STATE = r'''
    wire [31:0] pc_update;
    wire pc_write;
    // Original edge precedence is reset > redirect > accepted response.
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(3)) pc_update_selector (
        .events_i({reset_i,redirect_valid_i,resp_fire}),
        .values_i({32'b0,redirect_pc_i,next_pc_comb}),.write_o(pc_write),.value_o(pc_update));
    rv32_frequency_word_bank #(.WIDTH(32)) pc_owner (
        .clk_i(clk_i),.write_i(pc_write),.data_i(pc_update),.data_o(pc_reg));
    wire [EPOCH_WIDTH-1:0] epoch_update;
    wire epoch_write;
    rv32_frequency_event_select #(.WIDTH(EPOCH_WIDTH),.EVENTS(2)) epoch_update_selector (
        .events_i({reset_i,redirect_valid_i}),
        .values_i({{EPOCH_WIDTH{1'b0}},redirect_epoch_i}),.write_o(epoch_write),.value_o(epoch_update));
    rv32_frequency_word_bank #(.WIDTH(EPOCH_WIDTH)) epoch_owner (
        .clk_i(clk_i),.write_i(epoch_write),.data_i(epoch_update),.data_o(epoch_reg));
    wire [1:0] chain_views;
    rv32_frequency_control_tree #(.LEAVES(2)) chain_tree (
        .signal_i(response_can_chain),.views_o(chain_views));
    genvar request_half;
    generate for(request_half=0;request_half<2;request_half=request_half+1) begin:g_request_pc
        assign if_req_pc_o[request_half*16 +: 16]=chain_views[request_half]?
            next_pc_comb[request_half*16 +: 16]:pc_reg[request_half*16 +: 16];
    end endgenerate
'''


def frontend(t):
    t=change(t,'    reg [31:0] pc_reg;','    wire [31:0] pc_reg;')
    t=change(t,'    reg [EPOCH_WIDTH-1:0] epoch_reg;','    wire [EPOCH_WIDTH-1:0] epoch_reg;')
    t=change(t,'''    integer bundle_count;
    integer enq_count;
    integer deq_count;''',
             '''    // Every count is constructed from <=FE_WIDTH accepted lanes.
    localparam integer BUNDLE_COUNT_WIDTH=(FE_WIDTH<=1)?1:$clog2(FE_WIDTH+1);
    reg [BUNDLE_COUNT_WIDTH-1:0] bundle_count,enq_count,deq_count;''')
    t=change(t,'    assign if_req_pc_o = response_can_chain ? next_pc_comb : pc_reg;',STATE)
    for old in ["            pc_reg <= 32'd0;\n",
                "            epoch_reg <= {EPOCH_WIDTH{1'b0}};\n",
                '                pc_reg <= redirect_pc_i;\n',
                '                epoch_reg <= redirect_epoch_i;\n',
                '                    pc_reg <= next_pc_comb;\n']:
        t=change(t,old,'')
    return t


def dispatch(t):
    a=t.index('module rv32_reserved_dispatch_packet #(')
    before,part=t[:a],t[a:]
    part=change(part,'    reg [TAG_WIDTH-1:0] tag_q [0:LANES-1];',
                '''    wire [TAG_WIDTH-1:0] tag_q [0:LANES-1];
    wire [ROB_ENTRIES*(GW+1)-1:0] live_rows;
    genvar live_row;
    generate for(live_row=0;live_row<ROB_ENTRIES;live_row=live_row+1) begin:g_live_row
        assign live_rows[live_row*(GW+1) +: GW+1]={rob_valid_i[live_row],rob_generation_i[live_row*GW +: GW]};
    end endgenerate''')
    part=change(part,'''        wire generation_live=rob_valid_i[slot] &&
            tag_q[lane][3+SW +: GW]==rob_generation_i[slot*GW +: GW];''',
                '''        wire [GW:0] live;
        rv32_frequency_array_read #(.WIDTH(GW+1),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SW)) live_reader (
            .rows_i(live_rows),.index_i(slot),.value_o(live));
        wire generation_live=live[GW] && tag_q[lane][3+SW +: GW]==live[0 +: GW];''')
    part=change(part,'''        wire write_local;
        rv32_frequency_control_tree #(.LEAVES(1)) tag_write_tree (
            .signal_i(normal && valid_i[lane]),.views_o(write_local));
        always @(posedge clk_i) if(write_local) tag_q[lane]<=tag_i[lane*TAG_WIDTH +: TAG_WIDTH];''',
                '''        rv32_frequency_word_bank #(.WIDTH(TAG_WIDTH)) tag_owner (
            .clk_i(clk_i),.write_i(normal && valid_i[lane]),
            .data_i(tag_i[lane*TAG_WIDTH +: TAG_WIDTH]),.data_o(tag_q[lane]));''')
    return before+part


if __name__=='__main__':
    prepare('BW_frontend_state_and_dispatch_queries',ROOT/'BV_bounded_frontend_combination',{
        'rtl/frontend/rv32_fetch_frontend.v':frontend,
        'rtl/backend/rv32_backend_joint.v':dispatch,
    },'BV plus original-edge frontend PC/epoch event ownership and sixteen-bit response-chain request-PC mux; bundle/enqueue/dequeue combinational counts sized to legal FE_WIDTH range; reserved dispatch tag word ownership and four-row ROB generation-live queries preserve recovery conditions/hold and reservations; no added FF/cycles, no EDA')
