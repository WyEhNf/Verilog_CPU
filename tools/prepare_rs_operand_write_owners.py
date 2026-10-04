"""Give each retained RS operand two bounded mux/hold domains, no latency."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


OWNERS = r'''
    wire [7:0] alloc_views;
    wire src1_write=allocation || wake1_write;
    wire src2_write=allocation || wake2_write;
    wire [31:0] src1_write_data,src2_write_data;
    rv32_frequency_control_tree #(.LEAVES(8)) allocation_tree (
        .signal_i(allocation),.views_o(alloc_views));
    genvar operand_word;
    generate for(operand_word=0;operand_word<2;operand_word=operand_word+1) begin:g_operand_word
        // Allocation wins even if the row also observes a wake this edge.
        // Each select controls only its own 16 data bits.
        assign src1_write_data[operand_word*16 +: 16]=alloc_views[3+operand_word] ?
            new_value1[operand_word*16 +: 16] : wake1_value_i[operand_word*16 +: 16];
        assign src2_write_data[operand_word*16 +: 16]=alloc_views[5+operand_word] ?
            new_value2[operand_word*16 +: 16] : wake2_value_i[operand_word*16 +: 16];
    end endgenerate
    rv32_frequency_word_bank #(.WIDTH(32)) src1_value_owner (
        .clk_i(clk_i),.write_i(src1_write),.data_i(src1_write_data),.data_o(src1_value_o));
    rv32_frequency_word_bank #(.WIDTH(32)) src2_value_owner (
        .clk_i(clk_i),.write_i(src2_write),.data_i(src2_write_data),.data_o(src2_value_o));
'''


def station(t):
    t=change(t,'    output reg [31:0] src1_value_o,src2_value_o,',
             '    output wire [31:0] src1_value_o,src2_value_o,')
    start=t.index('    wire [5:0] alloc_views;')
    end=t.index('    localparam integer META_BITS=',start)
    t=t[:start]+OWNERS+t[end:]
    t=change(t,'        if(src1_write) src1_value_o<=alloc_views[3]?new_value1:wake1_value_i;\n','')
    t=change(t,'        if(src2_write) src2_value_o<=alloc_views[4]?new_value2:wake2_value_i;\n','')
    return change(t,'            if(alloc_views[5]) begin','            if(alloc_views[7]) begin')


if __name__=='__main__':
    prepare('BZ_bounded_rs_operand_writes',ROOT/'BY1_physical_register_wakeup',{
        'rtl/backend/rv32_reservation_station.v':station,
    },'BY1 plus two 16-bit allocation/wake selects and word-bank retained operand owners per RS row; no 32-bit final select/hold drivers, allocation-over-wake same-edge priority and no reset on invalid payload preserved, same storage/cycles; SOURCE_TAG_WIDTH identity unchanged; no EDA')
