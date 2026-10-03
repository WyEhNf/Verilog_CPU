"""Local LSQ wide-field event muxes preserve the original write order, no EDA."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


EVENT_SELECT = r'''

// Last event wins, matching ordered nonblocking writes. Qualification takes
// place before distribution; each select leaf drives at most 32 payload bits.
module rv32_frequency_event_select #(
    parameter integer WIDTH=32,EVENTS=4,
    parameter integer LEAVES=1<<$clog2(EVENTS),
    parameter integer WORDS=(WIDTH+31)/32
) (
    input wire [EVENTS-1:0] events_i,
    input wire [EVENTS*WIDTH-1:0] values_i,
    output wire write_o,
    output wire [WIDTH-1:0] value_o
);
    wire [EVENTS-1:0] grants;
    wire [WIDTH-1:0] mux_tree [1:2*LEAVES-1];
    assign write_o=|events_i;
    assign value_o=mux_tree[1];
    genvar event_id,word_id,node_id;
    generate
        for(event_id=0;event_id<LEAVES;event_id=event_id+1) begin:g_event
            if(event_id<EVENTS) begin:g_present
                wire [WORDS-1:0] selections;
                if(event_id==EVENTS-1) begin:g_last
                    assign grants[event_id]=events_i[event_id];
                end else begin:g_priority
                    assign grants[event_id]=events_i[event_id] && !(|events_i[EVENTS-1:event_id+1]);
                end
                rv32_frequency_control_tree #(.LEAVES(WORDS)) selection_tree (
                    .signal_i(grants[event_id]),.views_o(selections));
                for(word_id=0;word_id<WORDS;word_id=word_id+1) begin:g_word
                    localparam integer LOW=word_id*32;
                    localparam integer BITS=WIDTH-LOW>=32 ? 32 : WIDTH-LOW;
                    assign mux_tree[LEAVES+event_id][LOW +: BITS]=
                        {BITS{selections[word_id]}} & values_i[event_id*WIDTH+LOW +: BITS];
                end
            end else begin:g_padding
                assign mux_tree[LEAVES+event_id]=0;
            end
        end
        for(node_id=1;node_id<LEAVES;node_id=node_id+1) begin:g_or
            assign mux_tree[node_id]=mux_tree[2*node_id] | mux_tree[2*node_id+1];
        end
    endgenerate
endmodule
'''


OWNERS = r'''
    // Wide payload fields have no reset state. Their old write sequence is
    // expressed as independent local events; scalar metadata remains separate.
    localparam integer ADDRESS_EVENTS=1+2*BE_WIDTH;
    localparam integer DATA_EVENTS=3*BE_WIDTH;
    localparam integer RESULT_EVENTS=2+BE_WIDTH;
    localparam integer FORWARD_EVENTS=1+BE_WIDTH;
    wire [3*LSQ_ENTRIES-1:0] payload_modes;
    wire [SLOT_WIDTH-1:0] payload_alloc_slot [0:BE_WIDTH-1];
    wire [31:0] payload_response_word=dcache_resp_line_valid_i ?
        relative_data_from_line(dcache_resp_line_data_i,addr_mem[response_slot]) : dcache_resp_word_data_i;
    wire [31:0] payload_response_merge=
        (forward_data_mem[response_slot] & expand_word_bytes(forward_mask_mem[response_slot])) |
        (payload_response_word & ~expand_word_bytes(forward_mask_mem[response_slot]));
    wire [31:0] payload_response_value=format_relative_value(
        payload_response_merge,size_mem[response_slot],unsigned_mem[response_slot]);
    wire [31:0] payload_forward_value=format_relative_value(fwd_data,selected_size,selected_unsigned);
    function [RECOVERY_ARITH_WIDTH-1:0] payload_recovery_age;
        input [ROB_TAG_WIDTH-1:0] tag;
        reg [RECOVERY_ARITH_WIDTH-1:0] difference;
        begin
            difference=tag[3 +: ROB_SLOT_WIDTH]-recovery_head_i;
            if(((ROB_ENTRIES & (ROB_ENTRIES-1))!=0) && difference[RECOVERY_ARITH_WIDTH-1])
                difference=difference+ROB_ENTRIES;
            payload_recovery_age=difference;
        end
    endfunction
    wire [RECOVERY_ARITH_WIDTH-1:0] payload_branch_age=payload_recovery_age(recovery_tag_i);
    rv32_frequency_control_tree #(.WIDTH(3),.LEAVES(LSQ_ENTRIES)) payload_mode_tree (
        .signal_i({recovery_valid_i,flush_i,reset_i}),.views_o(payload_modes));
    genvar payload_row,payload_lane;
    generate
        for(payload_lane=0;payload_lane<BE_WIDTH;payload_lane=payload_lane+1) begin:g_payload_allocation
            wire [31:0] offset=tail_reg+alloc_count_before_lane(payload_lane,alloc_fire_o);
            assign payload_alloc_slot[payload_lane]=(offset>=LSQ_ENTRIES)?offset-LSQ_ENTRIES:offset;
        end
        for(payload_row=0;payload_row<LSQ_ENTRIES;payload_row=payload_row+1) begin:g_payload_row
            wire enabled=!payload_modes[payload_row*3] && !payload_modes[payload_row*3+1];
            wire recovery=payload_modes[payload_row*3+2];
            wire normal=enabled && !recovery;
            wire [BE_WIDTH-1:0] allocations;
            wire [ADDRESS_EVENTS-1:0] address_events;
            wire [ADDRESS_EVENTS*32-1:0] address_values;
            wire [DATA_EVENTS-1:0] data_events;
            wire [DATA_EVENTS*32-1:0] data_values;
            wire [RESULT_EVENTS-1:0] result_events;
            wire [RESULT_EVENTS*32-1:0] result_values;
            wire [FORWARD_EVENTS-1:0] forward_events;
            wire [FORWARD_EVENTS*32-1:0] forward_values;
            wire [BE_WIDTH*ROB_TAG_WIDTH-1:0] rob_tag_values;
            wire [31:0] address_value,data_value,result_value,forward_value;
            wire [ROB_TAG_WIDTH-1:0] rob_tag_value;
            wire address_write,data_write,result_write,forward_write,rob_tag_write;
            wire early_event=normal && (STORE_ADDRESS_PROBE!=0) && early_addr_valid_i &&
                tag_matches_slot(early_addr_tag_i,payload_row) && store_mem[payload_row] &&
                !addr_ready_mem[payload_row] && !request_sent_mem[payload_row] && !complete_mem[payload_row];
            assign address_events[0]=early_event;
            assign address_values[0 +: 32]=early_addr_i;
            assign result_events[0]=normal && candidate_found && candidate==payload_row &&
                load_mem[payload_row] && !request_sent_mem[payload_row] && !complete_mem[payload_row] &&
                ((fwd_mask & target_mask)==target_mask);
            assign result_values[0 +: 32]=payload_forward_value;
            wire [RECOVERY_ARITH_WIDTH-1:0] row_age=payload_recovery_age(rob_tag_mem[payload_row]);
            assign result_events[1]=enabled && response_fire && response_slot==payload_row &&
                (!recovery || !(row_age>payload_branch_age && row_age<recovery_occupancy_i));
            assign result_values[32 +: 32]=payload_response_value;
            assign forward_events[0]=normal && request_fire && candidate==payload_row && load_mem[payload_row];
            assign forward_values[0 +: 32]=fwd_data;
            for(payload_lane=0;payload_lane<BE_WIDTH;payload_lane=payload_lane+1) begin:g_lane
                assign allocations[payload_lane]=normal && alloc_fire_o[payload_lane] &&
                    payload_alloc_slot[payload_lane]==payload_row;
                assign address_events[1+payload_lane]=enabled && addr_update_valid_i[payload_lane] &&
                    tag_matches_slot(addr_update_tag_i[payload_lane*TAG_WIDTH +: TAG_WIDTH],payload_row);
                assign address_values[(1+payload_lane)*32 +: 32]=addr_update_i[payload_lane*32 +: 32];
                assign address_events[1+BE_WIDTH+payload_lane]=allocations[payload_lane];
                assign address_values[(1+BE_WIDTH+payload_lane)*32 +: 32]=alloc_addr_i[payload_lane*32 +: 32];
                assign data_events[2*payload_lane]=enabled && data_update_valid_i[payload_lane] &&
                    tag_matches_slot(data_update_tag_i[payload_lane*TAG_WIDTH +: TAG_WIDTH],payload_row);
                assign data_values[(2*payload_lane)*32 +: 32]=data_update_i[payload_lane*32 +: 32];
                assign data_events[2*payload_lane+1]=enabled && wakeup_valid_i[payload_lane] &&
                    tag_matches_slot(wakeup_tag_i[payload_lane*TAG_WIDTH +: TAG_WIDTH],payload_row);
                assign data_values[(2*payload_lane+1)*32 +: 32]=wakeup_value_i[payload_lane*32 +: 32];
                assign data_events[2*BE_WIDTH+payload_lane]=allocations[payload_lane];
                assign data_values[(2*BE_WIDTH+payload_lane)*32 +: 32]=alloc_store_data_i[payload_lane*32 +: 32];
                assign result_events[2+payload_lane]=allocations[payload_lane];
                assign result_values[(2+payload_lane)*32 +: 32]=0;
                assign forward_events[1+payload_lane]=allocations[payload_lane];
                assign forward_values[(1+payload_lane)*32 +: 32]=0;
                assign rob_tag_values[payload_lane*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]=alloc_rob_tag_i[payload_lane*ROB_TAG_WIDTH +: ROB_TAG_WIDTH];
            end
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(ADDRESS_EVENTS)) address_selector (
                .events_i(address_events),.values_i(address_values),.write_o(address_write),.value_o(address_value));
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(DATA_EVENTS)) data_selector (
                .events_i(data_events),.values_i(data_values),.write_o(data_write),.value_o(data_value));
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(RESULT_EVENTS)) result_selector (
                .events_i(result_events),.values_i(result_values),.write_o(result_write),.value_o(result_value));
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(FORWARD_EVENTS)) forward_selector (
                .events_i(forward_events),.values_i(forward_values),.write_o(forward_write),.value_o(forward_value));
            rv32_frequency_event_select #(.WIDTH(ROB_TAG_WIDTH),.EVENTS(BE_WIDTH)) tag_selector (
                .events_i(allocations),.values_i(rob_tag_values),.write_o(rob_tag_write),.value_o(rob_tag_value));
            always @* begin
                addr_mem_write_data[payload_row]=address_value;
                addr_mem_write_enable[payload_row]=address_write;
                data_mem_write_data[payload_row]=data_value;
                data_mem_write_enable[payload_row]=data_write;
                complete_value_mem_write_data[payload_row]=result_value;
                complete_value_mem_write_enable[payload_row]=result_write;
                forward_data_mem_write_data[payload_row]=forward_value;
                forward_data_mem_write_enable[payload_row]=forward_write;
                rob_tag_mem_write_data[payload_row]=rob_tag_value;
                rob_tag_mem_write_enable[payload_row]=rob_tag_write;
            end
        end
    endgenerate
'''


def split(t):
    start=t.index('    always @* begin : g_state_commands')
    stop=t.index('\n    always @(posedge clk_i) begin',start)
    commands=t[start:stop]
    fields=['addr_mem','data_mem','complete_value_mem','forward_data_mem','rob_tag_mem']
    for name in fields:
        commands=change(commands,f'            {name}_write_data[bank_default_row]=0; {name}_write_enable[bank_default_row]=0;\n','')
        pattern=re.compile(r'begin '+name+r'_write_data(\[[^\]\n]*\]) = [^;]*; '+name+r"_write_enable\1 = 1'b1; end",re.S)
        commands,count=pattern.subn(';',commands)
        if count<1:
            raise ValueError('Missing original field assignments: '+name)
    # The original comma-declared loop temporaries must not be shared by
    # the remaining combinational commands and the scalar clock process.
    commands=change(commands,'        integer bank_default_row;',
                    '        integer bank_retirement_slot,bank_retirement_lane;\n        integer bank_default_row;')
    commands=re.sub(r'\bretirement_slot\b','bank_retirement_slot',commands)
    commands=re.sub(r'\bretirement_lane\b','bank_retirement_lane',commands)
    return t[:start]+OWNERS+commands+t[stop:]


if __name__=='__main__':
    prepare('AH_lsq_local_wide_events',ROOT/'AG_bounded_rob_allocation',
            {'rtl/backend/rv32_lsq.v':split,'rtl/common/rv32_asap7_fanout.v':lambda t:t+EVENT_SELECT},
            'AG plus row-local LSQ address/store-data/ROB-tag/result/forward-data event selection with bounded selects and balanced OR; preserve recovery updates and response filtering, normal early-store priority, wake-after-data lane order and allocation-last; private retirement temporaries; no added registers or cycles, no EDA run')
