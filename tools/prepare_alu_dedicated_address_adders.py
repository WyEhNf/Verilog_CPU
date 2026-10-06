"""Separate target/AGU/integer arithmetic before opcode selection; no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


def adders(t):
    declarations='''    reg [31:0] adder_lhs;
    reg [31:0] adder_rhs;
    reg adder_subtract;
    reg [31:0] shared_sum;
'''
    dedicated='''    // Target and AGU adders have fixed operands, so opcode selection is
    // after arithmetic instead of being in front of all thirty-two bits.
    // They trade combinational area for a shorter operation-to-result path.
    wire [2:0] integer_subtract_views;
    wire [31:0] integer_adjusted_rhs;
    rv32_frequency_control_tree #(.LEAVES(3)) integer_subtract_tree (
        .signal_i(issue_op_i==`RV32IM_OP_SUB),.views_o(integer_subtract_views));
    assign integer_adjusted_rhs[15:0]=issue_src2_value_i[15:0] ^ {16{integer_subtract_views[0]}};
    assign integer_adjusted_rhs[31:16]=issue_src2_value_i[31:16] ^ {16{integer_subtract_views[1]}};
    wire [31:0] integer_sum=fast_add_carry(issue_src1_value_i,integer_adjusted_rhs,integer_subtract_views[2]);
    wire [31:0] address_sum=fast_add_carry(issue_src1_value_i,issue_imm_i,1'b0);
    wire [31:0] pc_relative_sum=fast_add_carry(issue_pc_i,issue_imm_i,1'b0);
'''
    t=change(t,declarations,dedicated)
    t=change(t,'function [31:0] fast_add_sub;','function [31:0] fast_add_carry;')
    t=change(t,'''        input [31:0] rhs;
        input subtract;
        reg [31:0] adjusted_rhs;''','''        input [31:0] adjusted_rhs;
        input carry_in;''')
    t=change(t,'            adjusted_rhs = rhs ^ {32{subtract}};\n','')
    t=change(t,'            carry[0] = subtract;','            carry[0] = carry_in;')
    t=change(t,'carry[chunk+1] = g3[chunk] | (p3[chunk] & subtract);',
               'carry[chunk+1] = g3[chunk] | (p3[chunk] & carry_in);')
    t=change(t,'fast_add_sub[chunk*4 +: 4]','fast_add_carry[chunk*4 +: 4]')
    a=t.index('        // Only one operation is accepted per cycle.')
    b=t.index('        pc_plus_four = issue_pc_i + 32\'d4;',a)
    t=t[:a]+t[b:]
    t=change(t,'''            `RV32IM_OP_AUIPC: begin
                calc_value = shared_sum;''','''            `RV32IM_OP_AUIPC: begin
                calc_value = pc_relative_sum;''')
    t=change(t,'                actual_next_pc = shared_sum;','                actual_next_pc = pc_relative_sum;')
    t=change(t,'                actual_next_pc = shared_sum & 32\'hfffffffe;',
               '                actual_next_pc = address_sum & 32\'hfffffffe;')
    if t.count('                calc_mem_addr = shared_sum;')!=2: raise ValueError('Expected load and store AGU uses')
    t=t.replace('                calc_mem_addr = shared_sum;','                calc_mem_addr = address_sum;')
    t=change(t,'''            `RV32IM_OP_ADDI,
            `RV32IM_OP_ADD: begin calc_value = shared_sum; calc_rd_we = 1'b1; end''','''            `RV32IM_OP_ADDI: begin calc_value = address_sum; calc_rd_we = 1'b1; end
            `RV32IM_OP_ADD: begin calc_value = integer_sum; calc_rd_we = 1'b1; end''')
    t=change(t,'`RV32IM_OP_SUB: begin calc_value = shared_sum;','`RV32IM_OP_SUB: begin calc_value = integer_sum;')
    t=change(t,'            calc_branch_target = shared_sum;','            calc_branch_target = pc_relative_sum;')
    t=change(t,'            actual_next_pc = calc_branch_taken ? shared_sum : pc_plus_four;',
               '            actual_next_pc = calc_branch_taken ? pc_relative_sum : pc_plus_four;')
    if 'shared_sum' in t or 'fast_add_sub' in t: raise ValueError('Review old shared arithmetic reference')
    return t


if __name__=='__main__':
    prepare('BD_dedicated_target_and_address_adders',ROOT/'BC_dcache_response_payload_owners',
            {'rtl/rv32i_alu.v':adders},
            'BC plus independent PC-relative target/AUIPC, rs1-immediate AGU/JALR/ADDI and integer add/sub prefix adders with bounded subtract polarity fanout; remove shared opcode-controlled operand mux before arithmetic, unchanged RV32 wrapping/JALR clearing/compare/prediction/result edge; combinational area tradeoff, no new FF/cycles and no EDA')
