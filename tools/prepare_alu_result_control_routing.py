"""Decode ALU classes once and bound result/branch/AGU control; no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


VALUES = [
    (['LUI'],'issue_imm_i'),(['AUIPC'],'pc_relative_sum'),(['JAL','JALR'],'pc_plus_four'),
    (['ADDI'],'address_sum'),(['ADD','SUB'],'integer_sum'),
    (['XORI'],'issue_src1_value_i ^ issue_imm_i'),(['ORI'],'issue_src1_value_i | issue_imm_i'),
    (['ANDI'],'issue_src1_value_i & issue_imm_i'),
    (['SLLI'],'immediate_shift_left'),(['SRLI','SRAI'],'immediate_shift_right'),
    (['XOR'],'issue_src1_value_i ^ issue_src2_value_i'),(['OR'],'issue_src1_value_i | issue_src2_value_i'),
    (['AND'],'issue_src1_value_i & issue_src2_value_i'),
    (['SLL'],'register_shift_left'),(['SRL','SRA'],'register_shift_right'),
    (['SLTI','SLTIU','SLT','SLTU'],"{31'd0,comparison_value}"),
]


def op(ops):
    return '('+' || '.join('issue_op_i==`RV32IM_OP_'+name for name in ops)+')'


def result_router():
    t=r'''
    // Exclusive opcode classes select fixed arithmetic/logic results after
    // their networks. Each decoded class reaches <=16 data bits per leaf.
    wire [15:0] value_classes;
    wire [16*32-1:0] value_class_data;
    wire comparison_value=
        (issue_op_i==`RV32IM_OP_SLTI && $signed(issue_src1_value_i)<$signed(issue_imm_i)) ||
        (issue_op_i==`RV32IM_OP_SLTIU && issue_src1_value_i<issue_imm_i) ||
        (issue_op_i==`RV32IM_OP_SLT && cmp_signed_lt) ||
        (issue_op_i==`RV32IM_OP_SLTU && cmp_unsigned_lt);
    wire [31:0] pc_plus_four=issue_pc_i+32'd4;
'''
    for i,(ops,value) in enumerate(VALUES):
        t+=f'    assign value_classes[{i}]={op(ops)};\n'
        t+=f'    assign value_class_data[{i}*32 +: 32]={value};\n'
    t+=r'''
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(16),.PRIORITY(0)) value_class_selector (
        .events_i(value_classes),.values_i(value_class_data),.write_o(),.value_o(calc_value));
'''
    t+='    wire conditional_branch='+op(['BEQ','BNE','BLT','BGE','BLTU','BGEU'])+';\n'
    t+='    wire jal='+op(['JAL'])+';\n    wire jalr='+op(['JALR'])+';\n'
    t+='    assign calc_is_load='+op(['LB','LH','LW','LBU','LHU'])+';\n'
    t+='    assign calc_is_store='+op(['SB','SH','SW'])+';\n'
    t+=r'''
    assign calc_rd_we=(|value_classes) || calc_is_load;
    assign calc_is_branch=conditional_branch || jal || jalr;
    assign calc_is_memory=calc_is_load || calc_is_store;
    assign calc_mem_size=issue_mem_size_i;
    assign calc_mem_unsigned=issue_mem_unsigned_i;
    assign calc_branch_taken=jal || jalr ||
        (issue_op_i==`RV32IM_OP_BEQ && cmp_equal) ||
        (issue_op_i==`RV32IM_OP_BNE && !cmp_equal) ||
        (issue_op_i==`RV32IM_OP_BLT && cmp_signed_lt) ||
        (issue_op_i==`RV32IM_OP_BGE && !cmp_signed_lt) ||
        (issue_op_i==`RV32IM_OP_BLTU && cmp_unsigned_lt) ||
        (issue_op_i==`RV32IM_OP_BGEU && !cmp_unsigned_lt);
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(2),.PRIORITY(0)) branch_target_selector (
        .events_i({jalr,(conditional_branch || jal)}),
        .values_i({(address_sum & 32'hfffffffe),pc_relative_sum}),.write_o(),.value_o(calc_branch_target));
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(3),.PRIORITY(0)) branch_next_pc_selector (
        .events_i({jalr,(jal || (conditional_branch && calc_branch_taken)),
                   (conditional_branch && !calc_branch_taken)}),
        .values_i({(address_sum & 32'hfffffffe),pc_relative_sum,pc_plus_four}),
        .write_o(),.value_o(calc_redirect_pc));
    assign calc_redirect_valid=calc_is_branch &&
        ((issue_pred_taken_i!=calc_branch_taken) ||
         (calc_branch_taken && issue_pred_target_i!=calc_branch_target));
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(1)) memory_address_selector (
        .events_i(calc_is_memory),.values_i(address_sum),.write_o(),.value_o(calc_mem_addr));
    wire [1:0] store_fallback_views;
    rv32_frequency_control_tree #(.LEAVES(2)) store_fallback_tree (
        .signal_i(calc_is_store && issue_store_data_i==32'b0),.views_o(store_fallback_views));
    genvar store_word;
    generate for(store_word=0;store_word<2;store_word=store_word+1) begin:g_store_operand
        assign calc_store_data[store_word*16 +: 16]=store_fallback_views[store_word]?
            issue_src2_value_i[store_word*16 +: 16]:issue_store_data_i[store_word*16 +: 16];
    end endgenerate
'''
    return t


def common(t):
    t=change(t,'    parameter integer WORDS=(WIDTH+15)/16\n',
             '''    parameter integer WORDS=(WIDTH+15)/16,
    // 0 requires mutually exclusive events; 1 preserves last-event priority.
    parameter integer PRIORITY=1
''')
    return change(t,'if(event_id==EVENTS-1) begin:g_last',
                  'if(PRIORITY==0 || event_id==EVENTS-1) begin:g_last')


def alu(t):
    for old in ['    reg [31:0] calc_value;','    reg calc_rd_we;','    reg calc_is_branch;',
                '    reg calc_branch_taken;','    reg [31:0] calc_branch_target;','    reg calc_redirect_valid;',
                '    reg [31:0] calc_redirect_pc;','    reg calc_is_memory;','    reg calc_is_load;',
                '    reg calc_is_store;','    reg [31:0] calc_mem_addr;','    reg [1:0] calc_mem_size;',
                '    reg calc_mem_unsigned;','    reg [31:0] calc_store_data;']:
        t=change(t,old,old.replace('reg ','wire ',1))
    for old in ['    reg actual_control;\n','    reg [31:0] actual_next_pc;\n','    reg [31:0] pc_plus_four;\n']:
        t=change(t,old,'')
    a=t.index('    // All operation semantics are combinational from the accepted IssuePacket.')
    b=t.index('    localparam integer RESULT_METADATA_WIDTH=',a)
    old=t[a:b]
    # Preserve the source inventory as an anchor guard, not an RTL check.
    if old.count('calc_value =')!=24 or old.count('case (issue_op_i)')!=1:
        raise ValueError('Preserve changed ALU semantics block')
    return t[:a]+result_router()+'\n'+t[b:]


if __name__=='__main__':
    prepare('BT_bounded_alu_result_control',ROOT/'BS_bounded_barrel_shifters',{
        'rtl/common/rv32_asap7_fanout.v':common,
        'rtl/rv32i_alu.v':alu,
    },'BS plus mutually exclusive ALU result classes with sixteen-bit payload selects, bounded branch target/next-PC and AGU masks, bounded zero-predecoded-store fallback; narrow result flags preserve supported RV32I semantics and both shift modes; no priority prefix on proven exclusive opcode classes, all pre-existing event owners retain default last-event priority; no added FF/cycles, no EDA')
