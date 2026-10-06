"""Prepare local execution ownership cancellation; source transformations only."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


PARAMS='''    parameter integer ROB_ENTRIES = `RV32IM_ROB_ENTRIES_DEFAULT,
    parameter integer SELECTIVE_RECOVERY = 0,
    parameter integer RECOVERY_WIDTH = 1+2*((ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES))+$clog2(ROB_ENTRIES+1)'''


def interface(source,last,occupied=False):
    source=change(source,last,last+',\n'+PARAMS)
    source=change(source,'    input  wire                         flush_i,',
        '''    input  wire                         flush_i,
    input  wire [RECOVERY_WIDTH-1:0]    recovery_packet_i,''')
    if occupied:
        source=change(source,'    output wire                         resp_valid_o,',
            '''    output wire                         occupied_o,
    output wire                         resp_valid_o,''')
    return source


def guard(name,active,tag,packet='recovery_packet_i',kill_branch=0):
    return f'''    wire {name};
    rv32_execution_recovery_cancel #(.TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES),
        .ENABLED(SELECTIVE_RECOVERY),.KILL_BRANCH({kill_branch})) {name}_guard (
        .packet_i({packet}),.active_i({active}),.tag_i({tag}),.cancel_o({name}));
'''


def common(source):
    if 'module rv32_execution_recovery_cancel' in source:
        raise ValueError('Preserve existing cancellation helper')
    return source+'''

// Execution ownership uses the registered recovery snapshot, not a late
// dynamic ROB read. Packet layout: {apply,occupancy,head,branch_relative_age}.
// Default-disabled instances retain old standalone interfaces and semantics.
module rv32_execution_recovery_cancel #(
    parameter integer TAG_WIDTH=17, ROB_ENTRIES=64, ENABLED=0, KILL_BRANCH=0,
    parameter integer SW=(ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES),
    parameter integer CW=$clog2(ROB_ENTRIES+1),
    parameter integer WIDTH=1+2*SW+CW
) (
    input wire [WIDTH-1:0] packet_i,
    input wire active_i,
    input wire [TAG_WIDTH-1:0] tag_i,
    output wire cancel_o
);
    generate if(ENABLED!=0) begin:g_enabled
        wire apply;
        wire [CW-1:0] occupancy;
        wire [SW-1:0] head,branch_age;
        wire [SW-1:0] age=tag_i[3 +: SW]-head;
        assign {apply,occupancy,head,branch_age}=packet_i;
        assign cancel_o=active_i && apply && (!tag_i[0] || age>=occupancy ||
            (KILL_BRANCH ? age>=branch_age : age>branch_age));
    end else begin:g_disabled
        assign cancel_o=1'b0;
    end endgenerate
endmodule
'''


def alu(source):
    source=interface(source,'    parameter integer FORWARD_METADATA = 0')
    anchor='    wire result_visible = result_valid_reg &&'
    source=change(source,anchor,
        guard('result_cancel','result_valid_reg || shift_busy','result_rob_tag_reg',kill_branch=1)+
        guard('issue_cancel','issue_valid_i','issue_rob_tag_i',kill_branch=1)+
        '    wire result_visible = result_valid_reg && !result_cancel &&')
    source=change(source,'    assign issue_ready_o = !flush_i && !shift_busy &&',
        '    assign issue_ready_o = !flush_i && !result_cancel && !issue_cancel && !shift_busy &&')
    source=change(source,'    wire payload_shift=!reset_i && !flush_i && shift_busy && !payload_stale;',
        '    wire payload_shift=!reset_i && !flush_i && !result_cancel && shift_busy && !payload_stale;')
    source=change(source,'        if (reset_i || flush_i) begin',
        '        if (reset_i || flush_i || result_cancel) begin')
    return source


def multiplier(source):
    source=interface(source,'    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT',True)
    anchor='    wire s1_discard=s1_valid && (!s1_live ||'
    guards='''    wire [3*RECOVERY_WIDTH-1:0] recovery_views;
    rv32_frequency_control_tree #(.WIDTH(RECOVERY_WIDTH),.LEAVES(3)) recovery_tree (
        .signal_i(recovery_packet_i),.views_o(recovery_views));
    assign occupied_o=s1_valid || s2_valid || out_valid;
'''
    for stage,index in [('s1',0),('s2',1),('out',2)]:
        guards+=guard(stage+'_cancel',stage+'_valid',stage+'_tag',f'recovery_views[{index}*RECOVERY_WIDTH +: RECOVERY_WIDTH]')
    guards+=guard('request_cancel','req_valid_i','req_rob_tag_i')
    source=change(source,anchor,guards+'    wire s1_discard=s1_valid && (s1_cancel || !s1_live ||')
    source=change(source,'    wire s2_discard=s2_valid && (!s2_live ||',
        '    wire s2_discard=s2_valid && (s2_cancel || !s2_live ||')
    source=change(source,'    wire out_discard=out_valid && (!out_live ||',
        '    wire out_discard=out_valid && (out_cancel || !out_live ||')
    source=change(source,'    assign req_ready_o=!flush_i && s1_ready;',
        '    assign req_ready_o=!flush_i && !request_cancel && s1_ready;')
    source=change(source,'    assign resp_valid_o=out_valid && out_live &&',
        '    assign resp_valid_o=out_valid && !out_cancel && out_live &&')
    return source


def divider(source):
    source=interface(source,'    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT',True)
    source=change(source,'    wire payload_clear=reset_i || flush_i;',
        guard('operation_cancel','busy_reg || result_valid_reg','result_tag_reg')+
        guard('request_cancel','req_valid_i','req_rob_tag_i')+
        '''    assign occupied_o=busy_reg || result_valid_reg;
    wire payload_clear=reset_i || flush_i;
    wire payload_active=!payload_clear && !operation_cancel;''')
    source=change(source,'    wire payload_accept=!payload_clear && !busy_reg && req_valid_i && req_ready_o;',
        '    wire payload_accept=payload_active && !busy_reg && req_valid_i && req_ready_o;')
    source=change(source,'    wire payload_prepare=!payload_clear && busy_reg && prepare_reg;',
        '    wire payload_prepare=payload_active && busy_reg && prepare_reg;')
    source=change(source,'    wire payload_finish=!payload_clear && busy_reg && !prepare_reg && finish_reg;',
        '    wire payload_finish=payload_active && busy_reg && !prepare_reg && finish_reg;')
    source=change(source,'    wire payload_iterate=!payload_clear && busy_reg && !prepare_reg && !finish_reg;',
        '    wire payload_iterate=payload_active && busy_reg && !prepare_reg && !finish_reg;')
    source=change(source,'    wire result_discard = result_valid_reg && (!result_live_reg ||',
        '    wire result_discard = result_valid_reg && (operation_cancel || !result_live_reg ||')
    source=change(source,'    assign req_ready_o = !flush_i && !busy_reg &&',
        '    assign req_ready_o = !flush_i && !operation_cancel && !request_cancel && !busy_reg &&')
    source=change(source,'    assign resp_valid_o = result_valid_reg && result_live_reg &&',
        '    assign resp_valid_o = result_valid_reg && !operation_cancel && result_live_reg &&')
    source=change(source,'''        end else begin
            if(result_valid_reg && (result_discard || resp_ready_i))''',
        '''        end else if(operation_cancel) begin
            // Payload/cache history is pure data; clear transaction ownership.
            // No canceled prepare/finish/iteration may publish a new result.
            busy_reg<=1'b0; prepare_reg<=1'b0; finish_reg<=1'b0;
            result_valid_reg<=1'b0; result_live_reg<=1'b0;
        end else begin
            if(result_valid_reg && (result_discard || resp_ready_i))''')
    return source


def iterative(source):
    source=interface(source,'    parameter integer PHYS_ADDR_WIDTH = `RV32IM_PHYS_REG_ADDR_WIDTH_DEFAULT',True)
    source=change(source,'    wire out_discard = out_valid && (!out_live ||',
        '''    wire [2*RECOVERY_WIDTH-1:0] recovery_views;
    rv32_frequency_control_tree #(.WIDTH(RECOVERY_WIDTH),.LEAVES(2)) recovery_tree (
        .signal_i(recovery_packet_i),.views_o(recovery_views));
    assign occupied_o=busy || out_valid;
'''+guard('operation_cancel','busy','operation_tag','recovery_views[0 +: RECOVERY_WIDTH]')+
        guard('out_cancel','out_valid','out_tag','recovery_views[RECOVERY_WIDTH +: RECOVERY_WIDTH]')+
        guard('request_cancel','req_valid_i','req_rob_tag_i')+
        '    wire out_discard = out_valid && (out_cancel || !out_live ||')
    source=change(source,'    assign req_ready_o = !flush_i && !busy && out_slot_ready;',
        '    assign req_ready_o = !flush_i && !operation_cancel && !request_cancel && !busy && out_slot_ready;')
    source=change(source,'    assign resp_valid_o = out_valid && out_live &&',
        '    assign resp_valid_o = out_valid && !out_cancel && out_live &&')
    source=change(source,'            if (busy) begin',
        '''            if(operation_cancel) busy<=1'b0;
            if (busy && !operation_cancel) begin''')
    return source


def unit_instance(source,unit,domain):
    start=source.index(unit+' #(')
    end=source.index(');',start)+2
    instance=source[start:end]
    instance=change(instance,'.PHYS_ADDR_WIDTH(PHYS_ADDR_WIDTH))',
        '.PHYS_ADDR_WIDTH(PHYS_ADDR_WIDTH), .ROB_ENTRIES(ROB_ENTRIES), .SELECTIVE_RECOVERY(SELECTIVE_RECOVERY))')
    occupied='div_occupied' if unit=='rv32m_divider' else 'mul_occupied'
    instance=change(instance,'.flush_i(flush_i),',
        f'.flush_i(flush_i), .recovery_packet_i(recovery_views[{domain}*RECOVERY_WIDTH +: RECOVERY_WIDTH]), .occupied_o({occupied}),')
    if unit=='rv32m_mdu_iterative':
        instance=change(instance,'.req_valid_i(pending_valid)',
            '.req_valid_i(pending_valid && !pending_cancel)')
    return source[:start]+instance+source[end:]


def mdu(source):
    source=interface(source,'    parameter integer MUL_IMPL = 0')
    source=change(source,'    reg [2:0] inflight_count;',
        '''    wire [2:0] inflight_count;
    wire mul_occupied,div_occupied;
    wire [3*RECOVERY_WIDTH-1:0] recovery_views;
    rv32_frequency_control_tree #(.WIDTH(RECOVERY_WIDTH),.LEAVES(3)) recovery_tree (
        .signal_i(recovery_packet_i),.views_o(recovery_views));
'''+guard('pending_cancel','pending_valid','pending_tag','recovery_views[0 +: RECOVERY_WIDTH]'))
    source=change(source,'    wire mul_req_valid = pending_valid && ((pending_op',
        '    wire mul_req_valid = pending_valid && !pending_cancel && ((pending_op')
    source=change(source,'    wire div_req_valid = pending_valid && ((pending_op',
        '    wire div_req_valid = pending_valid && !pending_cancel && ((pending_op')
    source=change(source,'    assign issue_ready_o = !flush_i &&',
        '''    assign issue_ready_o = !flush_i &&
                           (!SELECTIVE_RECOVERY || !recovery_packet_i[RECOVERY_WIDTH-1]) &&''')
    source=change(source,'    assign busy_o = pending_valid || (inflight_count != 0);',
        '''    // Selectively canceled requests do not produce fake completions.
    // Their physical stage occupancy is the authority for the busy counter.
    assign busy_o = pending_valid || (SELECTIVE_RECOVERY ?
        (mul_occupied || div_occupied) : (inflight_count != 0));''')
    for unit,domain in [('rv32m_multiplier',1),('rv32m_multiplier_radix4',1),
                        ('rv32m_mdu_iterative',1),('rv32m_divider',2)]:
        source=unit_instance(source,unit,domain)
    source=change(source,"            assign div_resp_rd_we = 1'b0;",
        "            assign div_resp_rd_we = 1'b0;\n            assign div_occupied = 1'b0;")
    source=change(source,'            inflight_count <= 0;','')
    source=change(source,'            if (pending_valid && ((mul_req_valid && mul_req_ready) || (div_req_valid && div_req_ready)))',
        '            if (pending_cancel || (pending_valid && ((mul_req_valid && mul_req_ready) || (div_req_valid && div_req_ready))))')
    source=change(source,'''            case ({unit_req_fire, completion_fire})
                2'b10: inflight_count <= inflight_count + 1'b1;
                2'b01: inflight_count <= inflight_count - 1'b1;
                default: inflight_count <= inflight_count;
            endcase''','')
    source=change(source,'endmodule',
        '''    generate if(SELECTIVE_RECOVERY==0) begin:g_legacy_busy_count
        reg [2:0] count;
        assign inflight_count=count;
        always @(posedge clk_i) begin
            if(reset_i || flush_i) count<=0;
            else case({unit_req_fire,completion_fire})
                2'b10: count<=count+1'b1;
                2'b01: count<=count-1'b1;
                default: count<=count;
            endcase
        end
    end else begin:g_owned_busy
        assign inflight_count=3'b0;
    end endgenerate
endmodule''')
    return source


def backend(source):
    source=change(source,'    wire [31:0] branch_pending_value;',
        '''    // Local ownership is used only with the recovery-aware issue FIFO.
    localparam integer LOCAL_EXEC_RECOVERY=(ISSUE_PIPELINE!=0);
    localparam integer EXEC_RECOVERY_WIDTH=1+2*ROB_SLOT_WIDTH+ROB_COUNT_WIDTH;
    wire [ROB_SLOT_WIDTH-1:0] execution_branch_age=
        branch_pending_tag[3 +: ROB_SLOT_WIDTH]-recovery_descriptor_head;
    wire [(BE_WIDTH+1)*EXEC_RECOVERY_WIDTH-1:0] execution_recovery_views;
    rv32_frequency_control_tree #(.WIDTH(EXEC_RECOVERY_WIDTH),.LEAVES(BE_WIDTH+1)) execution_recovery_tree (
        .signal_i({recovery_apply,recovery_descriptor_occupancy,recovery_descriptor_head,execution_branch_age}),
        .views_o(execution_recovery_views));
    wire [31:0] branch_pending_value;''')
    source=change(source,'.FORWARD_METADATA(RS_ISSUE_METADATA)) alu (',
        '.FORWARD_METADATA(RS_ISSUE_METADATA), .ROB_ENTRIES(ROB_ENTRIES), .SELECTIVE_RECOVERY(LOCAL_EXEC_RECOVERY)) alu (')
    source=change(source,'.clk_i(clk_i), .reset_i(reset_i), .flush_i(alu_flush_r[alu_lane]),',
        '''.clk_i(clk_i), .reset_i(reset_i), .flush_i(alu_flush_r[alu_lane]),
                .recovery_packet_i(execution_recovery_views[alu_lane*EXEC_RECOVERY_WIDTH +: EXEC_RECOVERY_WIDTH]),''')
    source=change(source,'.MUL_IMPL(MUL_IMPL)) mdu (',
        '.MUL_IMPL(MUL_IMPL), .ROB_ENTRIES(ROB_ENTRIES), .SELECTIVE_RECOVERY(LOCAL_EXEC_RECOVERY)) mdu (')
    source=change(source,'.flush_i(flush_i), .issue_valid_i(mdu_issue_valid)',
        '.flush_i(flush_i), .recovery_packet_i(execution_recovery_views[BE_WIDTH*EXEC_RECOVERY_WIDTH +: EXEC_RECOVERY_WIDTH]), .issue_valid_i(mdu_issue_valid)')
    source=change(source,'        if (recovery_domains[6]) begin\n            for (alu_recovery_lane',
        '        if (LOCAL_EXEC_RECOVERY==0 && recovery_domains[6]) begin\n            for (alu_recovery_lane')
    return source


if __name__=='__main__':
    prepare('CX_execution_local_cancel',ROOT/'CW_rs_decoded_low_rank',{
        'rtl/common/rv32_asap7_fanout.v':common,
        'rtl/rv32i_alu.v':alu,
        'rtl/rv32m_multiplier.v':multiplier,
        'rtl/rv32m_divider.v':divider,
        'rtl/rv32m_multiplier_radix4.v':iterative,
        'rtl/rv32m_mdu_iterative.v':iterative,
        'rtl/backend/rv32m_mdu_reservation_station.v':mdu,
        'rtl/backend/rv32_backend_joint.v':backend,
    },'Local recovery cancellation for all ALU/MDU resident stages; preserved older tasks and default-disabled interfaces; real stage occupancy for selective MDU busy; early wake still ROB generation guarded; no HDL/EDA tests')
