"""Move LSQ array fields into functional owners, without running hardware tools.

Per-field commands preserve the original last-NBA-wins priority. The held
request pipeline stays in its original process. All existing field resets,
generation counters, recovery rules and allocation initialization remain.
"""
from prepare_staged_frequency_candidate import change, prepare, ROOT
from prepare_control_islands import bank_arrays


def owned_lsq(t):
    anchor='    always @(posedge clk_i) begin'
    # The first process is the registered request selection added by J.
    # The second is the original array/pointer owner and is the sole target.
    assert t.count(anchor)==2
    hidden='    always @(posedge clk_i)begin'
    t=change(t,t[:t.index(anchor)+len(anchor)],
             t[:t.index(anchor)]+hidden)
    t, field_count=bank_arrays(t,'LSQ_ENTRIES','rv32_lsq_owned_field')
    assert field_count==25,field_count
    t=change(t,hidden,anchor)
    t=change(t,'''    output reg [WIDTH-1:0] data_o
);
    always @(posedge clk_i) if(write_i) data_o<=data_i;
endmodule''', '''    output wire [WIDTH-1:0] data_o
);
    rv32_frequency_word_bank #(.WIDTH(WIDTH)) payload_owner (
        .clk_i(clk_i),.write_i(write_i),.data_i(data_i),.data_o(data_o));
endmodule''')
    return t


if __name__=='__main__':
    prepare('U1_lsq_functional_field_owners', ROOT/'T_bounded_payload_consumers',
            {'rtl/backend/rv32_lsq.v':owned_lsq},
            'T plus 25 LSQ fields in independent ordinary RTL state owners with local word write distribution; exact original reset/recovery/commit/response/allocation assignment priority and unchanged request-selection pipeline; no EDA run')
