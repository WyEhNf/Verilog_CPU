"""Bound barrel-shift amount and sign-fill controls at unchanged latency."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


BARREL = r'''

// Five binary shift stages. Each amount-bit leaf selects <=16 mux bits;
// right-shift logical/arithmetic behavior differs only in the fill bit.
// Immediate and register amounts keep separate networks, so this change
// does not add an opcode-selected amount mux ahead of the barrel stages.
module rv32_frequency_barrel32 (
    input wire [31:0] value_i,
    input wire [4:0] amount_i,
    input wire fill_i,
    output wire [31:0] left_o,
    output wire [31:0] right_o
);
    wire [19:0] amount_views;
    wire [4:0] fill_views;
    wire [31:0] left_stage [0:5];
    wire [31:0] right_stage [0:5];
    rv32_frequency_control_tree #(.WIDTH(5),.LEAVES(4)) amount_tree (
        .signal_i(amount_i),.views_o(amount_views));
    rv32_frequency_control_tree #(.LEAVES(5)) fill_tree (
        .signal_i(fill_i),.views_o(fill_views));
    assign left_stage[0]=value_i;
    assign right_stage[0]=value_i;
    assign left_o=left_stage[5];
    assign right_o=right_stage[5];
    genvar stage,bit_id;
    generate for(stage=0;stage<5;stage=stage+1) begin:g_stage
        localparam integer DISTANCE=1<<stage;
        for(bit_id=0;bit_id<32;bit_id=bit_id+1) begin:g_bit
            if(bit_id>=DISTANCE) begin:g_left_data
                assign left_stage[stage+1][bit_id]=amount_views[(bit_id/16)*5+stage]?
                    left_stage[stage][bit_id-DISTANCE]:left_stage[stage][bit_id];
            end else begin:g_left_zero
                assign left_stage[stage+1][bit_id]=!amount_views[(bit_id/16)*5+stage] && left_stage[stage][bit_id];
            end
            if(bit_id+DISTANCE<32) begin:g_right_data
                assign right_stage[stage+1][bit_id]=amount_views[(2+bit_id/16)*5+stage]?
                    right_stage[stage][bit_id+DISTANCE]:right_stage[stage][bit_id];
            end else begin:g_right_fill
                assign right_stage[stage+1][bit_id]=amount_views[(2+bit_id/16)*5+stage]?
                    fill_views[stage]:right_stage[stage][bit_id];
            end
        end
    end endgenerate
endmodule
'''


SHIFT = r'''
    wire [31:0] immediate_shift_left,immediate_shift_right;
    wire [31:0] register_shift_left,register_shift_right;
    wire shift_sign_fill=issue_src1_value_i[31] &&
        (issue_op_i==`RV32IM_OP_SRAI || issue_op_i==`RV32IM_OP_SRA);
    generate if(SHIFT_IMPL==0) begin:g_parallel_barrel
        rv32_frequency_barrel32 immediate_barrel (
            .value_i(issue_src1_value_i),.amount_i(issue_imm_i[4:0]),.fill_i(shift_sign_fill),
            .left_o(immediate_shift_left),.right_o(immediate_shift_right));
        rv32_frequency_barrel32 register_barrel (
            .value_i(issue_src1_value_i),.amount_i(issue_src2_value_i[4:0]),.fill_i(shift_sign_fill),
            .left_o(register_shift_left),.right_o(register_shift_right));
    end else begin:g_iterative_shift_values
        assign immediate_shift_left=issue_src1_value_i;
        assign immediate_shift_right=issue_src1_value_i;
        assign register_shift_left=issue_src1_value_i;
        assign register_shift_right=issue_src1_value_i;
    end endgenerate
'''


def alu(t):
    t=change(t,'    // Compare four-bit chunks in parallel, then combine high chunks before',
             SHIFT+'\n    // Compare four-bit chunks in parallel, then combine high chunks before')
    for amount,prefix in [('issue_imm_i[4:0]','immediate'),('issue_src2_value_i[4:0]','register')]:
        t=change(t,f'(SHIFT_IMPL == 0) ? (issue_src1_value_i << {amount}) : issue_src1_value_i',
                 prefix+'_shift_left')
        t=change(t,f'(SHIFT_IMPL == 0) ? (issue_src1_value_i >> {amount}) : issue_src1_value_i',
                 prefix+'_shift_right')
        t=change(t,f'''                if (SHIFT_IMPL == 0)
                    calc_value = $signed(issue_src1_value_i) >>> {amount};
                else
                    calc_value = issue_src1_value_i;''',
                 '                calc_value = '+prefix+'_shift_right;')
    return t


if __name__=='__main__':
    prepare('BS_bounded_barrel_shifters',ROOT/'BR_rs_chronological_order',{
        'rtl/common/rv32_asap7_fanout.v':lambda t:t+BARREL,
        'rtl/rv32i_alu.v':alu,
    },'BR plus five-stage combinational barrel shifts with each amount leaf selecting at most sixteen bits and stage-local arithmetic fill; logical/arithmetic right shift share the same network, immediate/register amounts retain separate networks to avoid an earlier opcode mux; SHIFT_IMPL=1 iterative behavior unchanged; no new FF/cycles, no EDA')
