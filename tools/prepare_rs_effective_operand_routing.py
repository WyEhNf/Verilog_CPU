"""Bound final RS stored-vs-same-cycle-wake operand muxes; no EDA."""
from prepare_staged_frequency_candidate import ROOT, prepare, change


EFFECTIVE = r'''
    genvar effective_row,effective_word;
    generate for(effective_row=0;effective_row<ENTRIES;effective_row=effective_row+1) begin:g_effective_operand
        if(WAKE_MUX_IMPL!=0) begin:g_parallel
            wire wake1=(|wake1_match[effective_row]);
            wire wake2=(|wake2_match[effective_row]);
            wire [1:0] select1,select2;
            rv32_frequency_control_tree #(.LEAVES(2)) select1_tree (
                .signal_i(!src1_ready_mem[effective_row] && wake1),.views_o(select1));
            rv32_frequency_control_tree #(.LEAVES(2)) select2_tree (
                .signal_i(!src2_ready_mem[effective_row] && wake2),.views_o(select2));
            assign src1_ready_effective[effective_row]=src1_ready_mem[effective_row] || wake1;
            assign src2_ready_effective[effective_row]=src2_ready_mem[effective_row] || wake2;
            for(effective_word=0;effective_word<2;effective_word=effective_word+1) begin:g_word
                assign src1_value_effective[effective_row][effective_word*16 +: 16]=select1[effective_word]?
                    wake1_first[effective_row][effective_word*16 +: 16]:src1_value_mem[effective_row][effective_word*16 +: 16];
                assign src2_value_effective[effective_row][effective_word*16 +: 16]=select2[effective_word]?
                    wake2_first[effective_row][effective_word*16 +: 16]:src2_value_mem[effective_row][effective_word*16 +: 16];
            end
        end else begin:g_legacy
            reg ready1,ready2;
            reg [31:0] value1,value2;
            integer source;
            always @* begin
                ready1=src1_ready_mem[effective_row];value1=src1_value_mem[effective_row];
                ready2=src2_ready_mem[effective_row];value2=src2_value_mem[effective_row];
                for(source=0;source<WAKE_WIDTH;source=source+1) begin
                    if(!ready1 && wake_valid_i[source] && wake_tag_i[source*TAG_WIDTH] &&
                        src1_tag_mem[effective_row][0] &&
                        wake_tag_i[source*TAG_WIDTH +: TAG_WIDTH]==src1_tag_mem[effective_row]) begin
                        ready1=1'b1;value1=wake_value_i[source*32 +: 32];
                    end
                    if(!ready2 && wake_valid_i[source] && wake_tag_i[source*TAG_WIDTH] &&
                        src2_tag_mem[effective_row][0] &&
                        wake_tag_i[source*TAG_WIDTH +: TAG_WIDTH]==src2_tag_mem[effective_row]) begin
                        ready2=1'b1;value2=wake_value_i[source*32 +: 32];
                    end
                end
            end
            assign src1_ready_effective[effective_row]=ready1;
            assign src2_ready_effective[effective_row]=ready2;
            assign src1_value_effective[effective_row]=value1;
            assign src2_value_effective[effective_row]=value2;
        end
    end endgenerate
'''


def operands(t):
    for old in ['    reg src1_ready_effective [0:ENTRIES-1];',
                '    reg [31:0] src1_value_effective [0:ENTRIES-1];',
                '    reg src2_ready_effective [0:ENTRIES-1];',
                '    reg [31:0] src2_value_effective [0:ENTRIES-1];']:
        t=change(t,old,old.replace('reg ','wire ',1))
    a=t.index('    always @* begin\n        for (slot = 0; slot < ENTRIES; slot = slot + 1) begin\n            src1_ready_effective[slot]')
    b=t.index("        alloc_fire_o = {BE_WIDTH{1'b0}};",a)
    t=t[:a]+EFFECTIVE+'\n    always @* begin\n'+t[b:]
    return t


if __name__=='__main__':
    prepare('BU_bounded_rs_effective_operands',ROOT/'BT_bounded_alu_result_control',
            {'rtl/backend/rv32_reservation_station.v':operands},
            'BT plus sixteen-bit final stored-vs-first-same-cycle-wake RS operand selection, ready OR independently qualified as before; preserve first duplicate wake priority on bypass, clocked last duplicate wake unchanged, legacy wake parameter path retained; no new FF/cycles, no EDA')
