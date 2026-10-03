"""Own branch recovery capture at the existing edge; source preparation only."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


CAPTURE = r'''
    // Only accepted live redirects can acquire this packet. Select the first
    // lane exactly as the old ordered loop, then distribute the qualified
    // grants and write enable into at most sixteen payload bits per leaf.
    localparam integer BRANCH_CAPTURE_WIDTH=TAG_WIDTH+PAW+65;
    wire [BE_WIDTH-1:0] branch_capture_match,branch_capture_grant;
    wire [BE_WIDTH*BRANCH_CAPTURE_WIDTH-1:0] branch_capture_values;
    wire branch_capture_write;
    wire [BRANCH_CAPTURE_WIDTH-1:0] branch_capture_next,branch_capture_saved;
    genvar capture_lane;
    generate for(capture_lane=0;capture_lane<BE_WIDTH;capture_lane=capture_lane+1) begin:g_branch_capture
        assign branch_capture_match[capture_lane]=!reset_i && !flush_i && !branch_pending &&
            alu_exec_valid[capture_lane] && alu_exec_ready[capture_lane] &&
            branch_training_live[capture_lane] && alu_exec_redirect_valid[capture_lane];
        if(capture_lane==0) begin:g_first
            assign branch_capture_grant[capture_lane]=branch_capture_match[capture_lane];
        end else begin:g_priority
            assign branch_capture_grant[capture_lane]=branch_capture_match[capture_lane] &&
                !(|branch_capture_match[capture_lane-1:0]);
        end
        assign branch_capture_values[capture_lane*BRANCH_CAPTURE_WIDTH +: BRANCH_CAPTURE_WIDTH]={
            alu_exec_tag[capture_lane*TAG_WIDTH +: TAG_WIDTH],
            alu_exec_phys[capture_lane*PAW +: PAW],alu_exec_rd_we[capture_lane],
            alu_exec_value[capture_lane*32 +: 32],alu_exec_redirect_pc[capture_lane*32 +: 32]};
    end endgenerate
    rv32_frequency_event_select #(.WIDTH(BRANCH_CAPTURE_WIDTH),.EVENTS(BE_WIDTH)) branch_capture_selector (
        .events_i(branch_capture_grant),.values_i(branch_capture_values),
        .write_o(branch_capture_write),.value_o(branch_capture_next));
    rv32_frequency_word_bank #(.WIDTH(BRANCH_CAPTURE_WIDTH)) branch_capture_owner (
        .clk_i(clk_i),.write_i(branch_capture_write),.data_i(branch_capture_next),.data_o(branch_capture_saved));
    assign {branch_pending_tag,branch_pending_phys,branch_pending_rd_we,
            branch_pending_value,branch_pending_pc}=branch_capture_saved;
    generate if(PREDICTOR_META!=0) begin:g_branch_history_capture
        wire [BE_WIDTH*8-1:0] histories;
        wire history_write;
        wire [7:0] history_next;
        for(capture_lane=0;capture_lane<BE_WIDTH;capture_lane=capture_lane+1) begin:g_lane
            wire [ROB_SLOT_WIDTH-1:0] slot=alu_exec_tag[capture_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
            wire [1:0] kind=(RS_ISSUE_METADATA!=0)?
                alu_exec_pred_kind[capture_lane*2 +: 2]:rob_pred_kind_mem[slot];
            assign histories[capture_lane*8 +: 8]=(kind==`RV32IM_PRED_BRANCH)?
                {rob_pred_metadata_mem[slot][14:8],alu_exec_branch_taken[capture_lane]}:
                rob_pred_metadata_mem[slot][15:8];
        end
        rv32_frequency_event_select #(.WIDTH(8),.EVENTS(BE_WIDTH)) history_selector (
            .events_i(branch_capture_grant),.values_i(histories),.write_o(history_write),.value_o(history_next));
        rv32_frequency_word_bank #(.WIDTH(8)) history_owner (
            .clk_i(clk_i),.write_i(history_write),.data_i(history_next),.data_o(branch_recovery_history_o));
    end else begin:g_no_branch_history
        assign branch_recovery_history_o=8'b0;
    end endgenerate

    always @(posedge clk_i) begin
        if(reset_i) branch_pending<=1'b0;
        else if(flush_i || (branch_pending && !recovery_descriptor_valid && !rob_recovery_preview))
            branch_pending<=1'b0;
        else if(recovery_domains[7] && branch_pending) branch_pending<=1'b0;
        else if(branch_capture_write) branch_pending<=1'b1;
        else if(branch_pending && commit_ready_i && rob_commit_valid[0] &&
                rob_commit_tag[TAG_WIDTH-1:0]==recovery_tag_views[0 +: TAG_WIDTH])
            branch_pending<=1'b0;
    end
'''


def capture(t):
    t=change(t,'    output reg  [7:0]                   branch_recovery_history_o,',
               '    output wire [7:0]                   branch_recovery_history_o,')
    for declaration in ['[TAG_WIDTH-1:0] branch_pending_tag','[31:0] branch_pending_value',
                        '[PAW-1:0] branch_pending_phys','branch_pending_rd_we','[31:0] branch_pending_pc']:
        t=change(t,'    reg '+declaration+';','    wire '+declaration+';')
    # These fields have no consumers; their old registers were already
    # synthesis-dead. Do not count their removal as physical savings.
    for declaration in ['[31:0] branch_pending_source_pc','[1:0] branch_pending_kind',
                        'branch_pending_taken','[31:0] branch_pending_target',
                        'branch_pending_pred_taken','[31:0] branch_pending_pred_target']:
        t=change(t,'    reg '+declaration+';\n','')
    t=change(t,'    integer branch_lane;\n    integer branch_capture_found;\n','')
    start=t.index('    always @(posedge clk_i) begin\n        if (reset_i) begin\n            branch_pending <=')
    stop=t.index('\nendmodule',start)
    return t[:start]+CAPTURE+t[stop:]


if __name__=='__main__':
    prepare('AX_branch_capture_payload_owner',ROOT/'AW1_icache_response_and_stream_owners',
            {'rtl/backend/rv32_backend_joint.v':capture},
            'AW1 plus first accepted live redirect one-hot selection and sixteen-bit local payload capture at the existing branch_pending edge; validity-owned tag/link/redirect packet and conditional predictor history, remove synthesis-dead captured fields; no new FF/cycles, no EDA')
