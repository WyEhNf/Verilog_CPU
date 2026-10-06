"""Bound prediction result controls and retain RAS payload in local rows."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


TARGET = r'''
    wire [3:0] target_classes;
    wire [127:0] target_values;
    wire [31:0] default_next_pc=query_pc_i+32'd4;
    wire [31:0] direct_branch_pc=query_pc_i+branch_imm;
    wire [31:0] direct_jal_pc=query_pc_i+jal_imm;
    assign target_classes[0]=!pred_taken_o;
    assign target_classes[1]=pred_taken_o && pred_kind_o==`RV32IM_PRED_BRANCH &&
        ((DIRECT_BRANCH_TARGET!=0) || !pred_btb_hit_o);
    assign target_classes[2]=pred_taken_o && pred_kind_o==`RV32IM_PRED_JAL;
    assign target_classes[3]=pred_taken_o &&
        (pred_kind_o==`RV32IM_PRED_JALR ||
         (pred_kind_o==`RV32IM_PRED_BRANCH && DIRECT_BRANCH_TARGET==0 && pred_btb_hit_o));
    assign target_values={query_btb_word[33:2],direct_jal_pc,direct_branch_pc,default_next_pc};
    // The four legal target classes are exhaustive and mutually exclusive.
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(4),.PRIORITY(0)) target_selector (
        .events_i(target_classes),.values_i(target_values),.write_o(),.value_o(pred_target_o));
'''


def predictor(t):
    t=change(t,'    output reg  [31:0] pred_target_o,','    output wire [31:0] pred_target_o,')
    assignments={
        "        pred_target_o = query_pc_i + 32'd4;\n":1,
        '                            pred_target_o = query_pc_i + branch_imm;\n':1,
        '                        pred_target_o = query_pc_i + branch_imm;\n':1,
        '                        pred_target_o = query_btb_word[33:2];\n':1,
        '                    pred_target_o = query_pc_i + jal_imm;\n':1,
        '                            pred_target_o = query_btb_word[33:2];\n':1,
    }
    # Exact complete lines keep the two differently indented branch/BTB
    # assignments distinguishable while removing the old wide case mux.
    lines=t.splitlines(keepends=True)
    for assignment,count in assignments.items():
        if lines.count(assignment)!=count: raise ValueError('Target assignment inventory: '+assignment)
    t=''.join(line for line in lines if line not in assignments)
    return change(t,'    wire prediction_write=reset_i || feedback_valid_i;',
                  TARGET+'\n    wire prediction_write=reset_i || feedback_valid_i;')


RAS_OWNERS=r'''
    genvar ras_row;
    generate for(ras_row=0;ras_row<4;ras_row=ras_row+1) begin:g_ras_row
        // count=0 suppresses all observable RAS predictions after reset.
        // Only valid return addresses need storage; same-edge pushes win.
        wire write_event=!reset && ras_push && ras_sp==ras_row;
        rv32_frequency_word_bank #(.WIDTH(32)) payload_owner (
            .clk_i(clk),.write_i(write_event),.data_i(ras_push_address),.data_o(ras_stack[ras_row]));
        assign ras_rows[ras_row*32 +: 32]=ras_stack[ras_row];
    end endgenerate
    always @(posedge clk) begin
        if(reset) begin ras_sp<=2'd0;ras_count<=3'd0;end
        else if(ras_push) begin
            ras_sp<=ras_sp+1'b1;
            if(ras_count<4) ras_count<=ras_count+1'b1;
        end else if(ras_pop) begin
            ras_sp<=ras_sp-1'b1;
            ras_count<=ras_count-1'b1;
        end
    end
'''


def core(t):
    t=change(t,'    reg [31:0] ras_stack [0:3];','    wire [31:0] ras_stack [0:3];')
    t=change(t,'    wire [31:0] ras_target = ras_stack[ras_top_index];',
             '''    wire [127:0] ras_rows;
    wire [31:0] ras_target;
    wire [FE_WIDTH*32-1:0] ras_query_words;
    rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(4),.INDEX_WIDTH(2)) ras_query (
        .rows_i(ras_rows),.index_i(ras_top_index),.value_o(ras_target));''')
    t=change(t,'''            wire [31:0] query_inst =
                if_resp_line_data >> (query_word_index * 32);''',
             '''            wire [31:0] query_inst;
            rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(4),.INDEX_WIDTH(3)) instruction_query (
                .rows_i(if_resp_line_data),.index_i(query_word_index),.value_o(query_inst));
            assign ras_query_words[predictor_lane*32 +: 32]=query_inst;''')
    t=change(t,'                    ras_inst = if_resp_line_data >> (ras_word_index * 32);',
             '                    ras_inst = ras_query_words[ras_lane*32 +: 32];')
    start=t.index('            assign pred_taken_bus[predictor_lane] = ras_return_hit ?')
    end=t.index('\n        end\n    endgenerate',start)
    t=t[:start]+'''            wire [2:0] ras_hit_views;
            rv32_frequency_control_tree #(.LEAVES(3)) ras_hit_tree (
                .signal_i(ras_return_hit),.views_o(ras_hit_views));
            assign pred_taken_bus[predictor_lane]=ras_hit_views[2] ? 1'b1 : pred_taken_raw_bus[predictor_lane];
            assign pred_target_bus[predictor_lane*32 +: 32]={
                ras_hit_views[1] ? ras_target[31:16] : pred_target_raw_bus[predictor_lane*32+16 +: 16],
                ras_hit_views[0] ? ras_target[15:0] : pred_target_raw_bus[predictor_lane*32 +: 16]};
            assign pred_kind_bus[predictor_lane*2 +: 2]=ras_hit_views[2] ?
                `RV32IM_PRED_JALR : pred_kind_raw_bus[predictor_lane*2 +: 2];
            assign pred_btb_hit_bus[predictor_lane]=ras_hit_views[2] ? 1'b1 : pred_btb_hit_raw_bus[predictor_lane];'''+t[end:]
    start=t.index('    integer ras_reset_index;')
    end=t.index('\n    rv32_fetch_frontend',start)
    return t[:start]+RAS_OWNERS+t[end:]


if __name__=='__main__':
    prepare('CC_prediction_targets_and_ras_owners',ROOT/'CB_predictor_row_owners',{
        'rtl/predictor/rv32_branch_predictor.v':predictor,
        'rtl/cpu_core.v':core,
    },'CB plus parallel prediction target classes with 16-bit output masks, core RAS retained row owners/no invalid-payload reset, bounded RAS return override and four-word instruction queries shared with RAS event decoding; original first accepted call/return/taken event, stack pointer/count/full overwrite behavior and prediction semantics retained; no extra FF/cycles, no EDA')
