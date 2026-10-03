"""Let ALU validity own invalidation, with bounded payload writes; no EDA."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


FIELDS=[
    ('result_phys_rd_reg','PHYS_ADDR_WIDTH','issue_phys_rd_i'),
    ('result_rob_tag_reg','TAG_WIDTH','issue_rob_tag_i'),
    ('result_epoch_reg','EPOCH_WIDTH','issue_epoch_i'),
    ('result_rd_we_reg','1','calc_rd_we'),
    ('result_is_branch_reg','1','calc_is_branch'),
    ('result_branch_taken_reg','1','calc_branch_taken'),
    ('result_branch_target_reg','32','calc_branch_target'),
    ('result_redirect_valid_reg','1','calc_redirect_valid'),
    ('result_redirect_pc_reg','32','calc_redirect_pc'),
    ('result_is_memory_reg','1','calc_is_memory'),
    ('result_is_load_reg','1','calc_is_load'),
    ('result_is_store_reg','1','calc_is_store'),
    ('result_mem_addr_reg','32','calc_mem_addr'),
    ('result_mem_size_reg','2','calc_mem_size'),
    ('result_mem_unsigned_reg','1','calc_mem_unsigned'),
    ('result_store_data_reg','32','calc_store_data')]


CONTROLS=r'''
    // Invalid execution data is not architectural state. Reset/flush only
    // clear result validity and shift control; every newly valid result has
    // a complete payload write on its original acceptance edge.
    wire payload_stale=live_tag_valid_i && result_rob_tag_reg!=live_tag_i;
    wire payload_cancel=result_valid_reg && payload_stale && !exec_ready_i;
    wire payload_accept=!reset_i && !flush_i && !shift_busy && !payload_cancel &&
        issue_ready_o && issue_valid_i;
    wire payload_shift=!reset_i && !flush_i && shift_busy && !payload_stale;
    wire [31:0] shifted_payload=shift_right ?
        {(shift_arithmetic && result_value_reg[31]),result_value_reg[31:1]} :
        {result_value_reg[30:0],1'b0};
    wire [31:0] value_payload;
    wire value_write;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(2)) value_selector (
        .events_i({payload_accept,payload_shift}),.values_i({calc_value,shifted_payload}),
        .write_o(value_write),.value_o(value_payload));
    rv32_frequency_word_bank #(.WIDTH(32)) value_owner (
        .clk_i(clk_i),.write_i(value_write),.data_i(value_payload),.data_o(result_value_reg));
'''


def lifecycle(t):
    for name in ['result_value_reg']+[n for n,_,_ in FIELDS]:
        pattern=re.compile(r'\breg(\s+(?:\[[^\n]+?\]\s+)?)'+name+r'\s*;')
        t,n=pattern.subn(r'wire\1'+name+';',t)
        if n!=1:
            raise ValueError('Ambiguous ALU field declaration: '+name)
    marker='    // Capture on the original result acceptance edge, with the original stall,'
    t=change(t,marker,CONTROLS+'\n'+marker)
    start=t.index('        always @(posedge clk_i) begin\n            if (reset_i || flush_i) begin\n                source_pc_reg')
    stop=t.index('    end else begin : g_no_forward_metadata',start)
    t=t[:start]+'''        rv32_frequency_word_bank #(.WIDTH(67)) prediction_owner (
            .clk_i(clk_i),.write_i(payload_accept),
            .data_i({issue_pc_i,issue_pred_target_i,issue_pred_taken_i,issue_pred_kind_i}),
            .data_o({source_pc_reg,pred_target_reg,pred_taken_reg,pred_kind_reg}));
'''+t[stop:]
    for old,new in [('reg [31:0] source_pc_reg, pred_target_reg;','wire [31:0] source_pc_reg, pred_target_reg;'),
                    ('reg pred_taken_reg;','wire pred_taken_reg;'),('reg [1:0] pred_kind_reg;','wire [1:0] pred_kind_reg;')]:
        t=change(t,old,new)
    start=t.index('    always @(posedge clk_i) begin\n        if (reset_i || flush_i) begin\n            result_valid_reg')
    prefix,scalar=t[:start],t[start:]
    for name in ['result_value_reg']+[n for n,_,_ in FIELDS]:
        scalar,n=re.subn(r'\b'+name+r'\s*<=\s*[^;]*;',';',scalar)
        if n<2:
            raise ValueError('Missing original ALU field writes: '+name)
    width='+'.join(w for _,w,_ in FIELDS)
    outputs=','.join(n for n,_,_ in FIELDS)
    inputs=','.join(v for _,_,v in FIELDS)
    metadata=f'''    localparam integer RESULT_METADATA_WIDTH={width};
    rv32_frequency_word_bank #(.WIDTH(RESULT_METADATA_WIDTH)) result_metadata_owner (
        .clk_i(clk_i),.write_i(payload_accept),
        .data_i({{{inputs}}}),.data_o({{{outputs}}}));

'''
    return prefix+metadata+scalar


if __name__=='__main__':
    prepare('AL_alu_validity_owned_payload',ROOT/'AK_registered_decode_space',
            {'rtl/rv32i_alu.v':lifecycle},
            'AK plus ALU result/prediction payload only written at original accepted-issue or iterative-shift edge, validity/shift controls retain reset/flush/cancel priority; bounded word owners, no new registers/cycles; invalid payload no longer guaranteed zero; no EDA run')
