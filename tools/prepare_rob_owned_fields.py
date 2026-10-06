"""Prepare ROB field ownership and bounded LSQ recovery arithmetic; no tests."""
from prepare_staged_frequency_candidate import change, prepare, ROOT
from prepare_control_islands import bank_arrays


def owned_rob(t):
    anchor='    always @(posedge clk_i) begin'
    assert t.count(anchor)==2
    hidden='    always @(posedge clk_i)begin'
    first=t.index(anchor)
    t=t[:first]+t[first:].replace(anchor,hidden,1)
    t,field_count=bank_arrays(t,'ROB_ENTRIES','rv32_rob_owned_field')
    assert field_count==22,field_count
    t=change(t,hidden,anchor)
    t=change(t,'''    output reg [WIDTH-1:0] data_o
);
    always @(posedge clk_i) if(write_i) data_o<=data_i;
endmodule''', '''    output wire [WIDTH-1:0] data_o
);
    rv32_frequency_word_bank #(.WIDTH(WIDTH)) payload_owner (
        .clk_i(clk_i),.write_i(write_i),.data_i(data_i),.data_o(data_o));
endmodule''')
    # CHECKPOINT_IMPL=1 uses the existing separate checkpoint mechanism.
    # Never preserve a 64-row unused full checkpoint register bank merely
    # because local distribution cells have keep attributes.
    start=t.index('        rv32_rob_owned_field #(.WIDTH(CHECKPOINT_WIDTH-1+1)) checkpoint_mem_owner (')
    stop=t.index(');',start)+2
    owner=t[start:stop]
    return t[:start]+'''        if(CHECKPOINT_IMPL==0) begin:g_array_checkpoint
'''+owner+'''
        end else begin:g_unused_array_checkpoint
            assign checkpoint_mem[storage_row]={CHECKPOINT_WIDTH{1'b0}};
        end'''+t[stop:]


def narrow_lsq(t):
    t=change(t,'    integer entry_rob_slot;', '''    localparam integer RECOVERY_ARITH_WIDTH=
        ((ROB_ENTRIES & (ROB_ENTRIES-1))==0) ? ROB_SLOT_WIDTH : 32;
    reg [RECOVERY_ARITH_WIDTH-1:0] entry_rob_slot;''')
    for prefix in ('','bank_'):
        names=['recovery_branch_slot','recovery_branch_age','recovery_entry_age']
        if prefix: names+=['entry_rob_slot']
        for name in names:
            t=change(t,f'integer {prefix}{name};',f'reg [RECOVERY_ARITH_WIDTH-1:0] {prefix}{name};')
        # Power-of-two ROB ages wrap directly at SLOT_WIDTH. For other ROB
        # sizes retain the original 32-bit subtraction and negative-wrap
        # correction, detecting the sign bit explicitly before comparison.
        for name in ('recovery_branch_age','recovery_entry_age'):
            old=f'if ({prefix}{name} < 0)'
            new=f'if (((ROB_ENTRIES & (ROB_ENTRIES-1))!=0) && {prefix}{name}[RECOVERY_ARITH_WIDTH-1])'
            assert old in t
            t=t.replace(old,new)
    return t


if __name__=='__main__':
    prepare('W1_rob_ownership_and_recovery_arithmetic', ROOT/'V_local_producer_tag_table',
            {'rtl/backend/rv32_rob.v':owned_rob,'rtl/backend/rv32_lsq.v':narrow_lsq},
            'V plus 22 ROB functional field owners (unused array checkpoints explicitly excluded for CHECKPOINT_IMPL=1), local word write drivers and SLOT_WIDTH unsigned LSQ recovery arithmetic with non-power-of-two fallback; assignment priority and pipeline boundaries unchanged; no EDA run')
