"""Route resolved-branch feedback with bounded one-hot payloads; no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


ROUTE = r'''
    localparam integer FEEDBACK_LANE_WIDTH=(BE_WIDTH<=1)?1:$clog2(BE_WIDTH);
    localparam integer FEEDBACK_PACKET_WIDTH=100+ROB_SLOT_WIDTH;
    wire [BE_WIDTH-1:0] feedback_candidates,feedback_grants;
    wire [FEEDBACK_LANE_WIDTH-1:0] feedback_lane;
    wire [BE_WIDTH*FEEDBACK_PACKET_WIDTH-1:0] feedback_values;
    wire [FEEDBACK_PACKET_WIDTH-1:0] feedback_packet;
    rv32_frequency_first_two #(.ENTRIES(BE_WIDTH),.INDEX_WIDTH(FEEDBACK_LANE_WIDTH)) feedback_selector (
        .candidates_i(feedback_candidates),.first_valid_o(branch_feedback_valid_r),.first_index_o(feedback_lane),
        .second_valid_o(),.second_index_o());
    rv32_frequency_event_select #(.WIDTH(FEEDBACK_PACKET_WIDTH),.EVENTS(BE_WIDTH)) feedback_payload_selector (
        .events_i(feedback_grants),.values_i(feedback_values),.write_o(),.value_o(feedback_packet));
    assign {branch_feedback_slot,branch_feedback_pc_r,branch_feedback_kind_r,branch_feedback_taken_r,
        branch_feedback_target_r,branch_feedback_pred_taken_r,branch_feedback_pred_target_r}=feedback_packet;
    genvar feedback_source,feedback_row;
    generate
        for(feedback_source=0;feedback_source<BE_WIDTH;feedback_source=feedback_source+1) begin:g_feedback_source
            wire [ROB_SLOT_WIDTH-1:0] slot=alu_exec_tag[feedback_source*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
            wire [31:0] pc,pred_target;
            wire [1:0] kind;
            wire pred_taken;
            assign feedback_candidates[feedback_source]=alu_exec_valid[feedback_source] && alu_exec_ready[feedback_source] &&
                (PREDICTOR_META==0 || branch_training_live[feedback_source]) && alu_exec_is_branch[feedback_source];
            assign feedback_grants[feedback_source]=branch_feedback_valid_r && feedback_lane==feedback_source;
            if(RS_ISSUE_METADATA!=0) begin:g_inline
                assign pc=alu_exec_source_pc[feedback_source*32 +: 32];
                assign kind=alu_exec_pred_kind[feedback_source*2 +: 2];
                assign pred_taken=alu_exec_pred_taken[feedback_source];
                assign pred_target=alu_exec_pred_target[feedback_source*32 +: 32];
            end else begin:g_legacy
                wire [ROB_ENTRIES*67-1:0] metadata_rows;
                for(feedback_row=0;feedback_row<ROB_ENTRIES;feedback_row=feedback_row+1) begin:g_row
                    assign metadata_rows[feedback_row*67 +: 67]={rob_pc_mem[feedback_row],
                        rob_pred_kind_mem[feedback_row],rob_pred_taken_mem[feedback_row],rob_pred_target_mem[feedback_row]};
                end
                rv32_frequency_array_read #(.WIDTH(67),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(ROB_SLOT_WIDTH)) metadata_read (
                    .rows_i(metadata_rows),.index_i(slot),.value_o({pc,kind,pred_taken,pred_target}));
            end
            assign feedback_values[feedback_source*FEEDBACK_PACKET_WIDTH +: FEEDBACK_PACKET_WIDTH]={
                slot,pc,kind,alu_exec_branch_taken[feedback_source],
                alu_exec_branch_target[feedback_source*32 +: 32],pred_taken,pred_target};
        end
        if(PREDICTOR_META!=0) begin:g_feedback_history
            wire [ROB_ENTRIES*16-1:0] history_rows;
            wire [15:0] history;
            for(feedback_row=0;feedback_row<ROB_ENTRIES;feedback_row=feedback_row+1) begin:g_row
                assign history_rows[feedback_row*16 +: 16]=rob_pred_metadata_mem[feedback_row];
            end
            rv32_frequency_array_read #(.WIDTH(16),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(ROB_SLOT_WIDTH)) history_read (
                .rows_i(history_rows),.index_i(branch_feedback_slot),.value_o(history));
            rv32_frequency_event_select #(.WIDTH(16),.EVENTS(1)) valid_selector (
                .events_i(branch_feedback_valid_r),.values_i(history),.write_o(),.value_o(branch_feedback_metadata_o));
        end else begin:g_no_feedback_history
            assign branch_feedback_metadata_o=0;
        end
    endgenerate
'''


def routing(t):
    for old in ['    reg branch_feedback_valid_r;','    reg [31:0] branch_feedback_pc_r;',
                '    reg [1:0] branch_feedback_kind_r;','    reg branch_feedback_taken_r;',
                '    reg [31:0] branch_feedback_target_r;','    reg branch_feedback_pred_taken_r;',
                '    reg [31:0] branch_feedback_pred_target_r;']:
        t=change(t,old,old.replace('reg ','wire ',1))
    for old in ['    integer branch_feedback_lane;\n','    integer branch_feedback_found;\n']:
        t=change(t,old,'')
    t=change(t,'    integer branch_feedback_slot;',
             '    wire [ROB_SLOT_WIDTH-1:0] branch_feedback_slot;')
    t=change(t,'''    assign branch_feedback_metadata_o = (PREDICTOR_META != 0 && branch_feedback_valid_r) ?
        rob_pred_metadata_mem[branch_feedback_slot] : 16'b0;
''','')
    a=t.index('    always @* begin\n        branch_feedback_valid_r =')
    b=t.index('    // One shared MDU',a)
    return t[:a]+ROUTE+'\n'+t[b:]


if __name__=='__main__':
    prepare('BQ_bounded_branch_feedback',ROOT/'BP_store_probe_match_reuse',
            {'rtl/backend/rv32_backend_joint.v':routing},
            'BP plus resolved-branch feedback lowest accepted lane parallel arbitration and sixteen-bit one-hot payload selection, parameter-gated bounded legacy ROB metadata/history reads; preserve accepted lane, generation-training policy and all valid payloads, zero invalid feedback fields; no added FF/cycles, no EDA')
