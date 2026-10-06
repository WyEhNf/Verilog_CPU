"""Prepare radix-4 Booth rows and balanced three/three CSA stages; no tests."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def reduce_rows(input_name,count,output_name):
    triples=count//3
    remaining=count%3
    output_count=2*triples+remaining
    lines=[f'    wire [63:0] {output_name} [0:{output_count-1}];']
    for index in range(triples):
        arguments=','.join(f'{input_name}[{3*index+offset}]' for offset in range(3))
        lines += [f'    assign {output_name}[{2*index}]=csa_sum3({arguments});',
                  f'    assign {output_name}[{2*index+1}]=csa_carry3({arguments});']
    for offset in range(remaining):
        lines.append(f'    assign {output_name}[{2*triples+offset}]={input_name}[{3*triples+offset}];')
    return '\n'.join(lines)+'\n',output_count


def multiplier(source):
    start=source.index('    // Signed high halves are corrected in carry-save form, modulo 2^64:')
    end=source.index('    reg s1_valid;',start)
    first='''    // A and B are signed only where the requested high half requires it.
    // The 33rd sign bit also represents every unsigned 32-bit operand.
    // Seventeen radix-4 digits cover B. Negative rows use bitwise complement
    // plus one shared correction vector, avoiding per-row negate adders.
    wire signed_a=(req_op_i==`RV32IM_OP_MULH || req_op_i==`RV32IM_OP_MULHSU);
    wire signed_b=(req_op_i==`RV32IM_OP_MULH);
    wire [32:0] extended_a={signed_a && req_src1_i[31],req_src1_i};
    wire [34:0] booth_bits={{2{signed_b && req_src2_i[31]}},req_src2_i,1'b0};
    wire [5*33-1:0] multiplicand_views;
    rv32_frequency_control_tree #(.WIDTH(33),.LEAVES(5)) multiplicand_tree (
        .signal_i(extended_a),.views_o(multiplicand_views));
    wire [63:0] pp [0:17];
    wire [16:0] negative_corrections;
    genvar row;
    generate for(row=0;row<17;row=row+1) begin:g_booth_row
        wire [2:0] code=booth_bits[2*row +: 3];
        wire one=code[0] ^ code[1];
        wire two=(code[0]==code[1]) && (code[2]!=code[1]);
        wire negative=code[2] && (one || two);
        wire [2:0] one_views,two_views;
        wire [3:0] negative_views;
        wire [32:0] local_a=multiplicand_views[(row/4)*33 +: 33];
        wire [33:0] once={local_a[32],local_a};
        wire [33:0] twice={local_a,1'b0};
        wire [33:0] relative_row;
        localparam integer EXTENDED_BITS=(30-2*row>0)?30-2*row:0;
        localparam integer SIGN_DOMAINS=(EXTENDED_BITS+7)/8;
        rv32_frequency_control_tree #(.LEAVES(3)) one_tree (
            .signal_i(one),.views_o(one_views));
        rv32_frequency_control_tree #(.LEAVES(3)) two_tree (
            .signal_i(two),.views_o(two_views));
        rv32_frequency_control_tree #(.LEAVES(4)) negative_tree (
            .signal_i(negative),.views_o(negative_views));
        assign negative_corrections[row]=negative_views[3];
        for(genvar relative_bit=0;relative_bit<34;relative_bit=relative_bit+1) begin:g_relative_bit
            assign relative_row[relative_bit]=
                ((one_views[relative_bit/16] && once[relative_bit]) |
                 (two_views[relative_bit/16] && twice[relative_bit])) ^ negative_views[relative_bit/16];
        end
        if(SIGN_DOMAINS>0) begin:g_sign_extension
            wire [SIGN_DOMAINS-1:0] sign_views;
            // Each repeated sign feeds <=8 row bits, each used in CSA logic.
            rv32_frequency_control_tree #(.LEAVES(SIGN_DOMAINS)) sign_tree (
                .signal_i(relative_row[33]),.views_o(sign_views));
            for(genvar product_bit=0;product_bit<64;product_bit=product_bit+1) begin:g_bit
                if(product_bit<2*row) assign pp[row][product_bit]=1'b0;
                else if(product_bit<2*row+34)
                    assign pp[row][product_bit]=relative_row[product_bit-2*row];
                else assign pp[row][product_bit]=sign_views[(product_bit-2*row-34)/8];
            end
        end else begin:g_no_sign_extension
            for(genvar product_bit=0;product_bit<64;product_bit=product_bit+1) begin:g_bit
                if(product_bit<2*row) assign pp[row][product_bit]=1'b0;
                else assign pp[row][product_bit]=relative_row[product_bit-2*row];
            end
        end
    end endgenerate
    generate for(genvar correction_bit=0;correction_bit<64;correction_bit=correction_bit+1) begin:g_correction_bit
        if(correction_bit<=32 && correction_bit%2==0)
            assign pp[17][correction_bit]=negative_corrections[correction_bit/2];
        else assign pp[17][correction_bit]=1'b0;
    end endgenerate
'''
    count=18
    name='pp'
    for output in ('first_reduce1','first_reduce2','first_rows'):
        text,count=reduce_rows(name,count,output)
        first+=text
        name=output
    if count!=6:
        raise ValueError('Expected six registered first-stage rows')
    source=source[:start]+first+source[end:]
    source=change(source,'    reg [63:0] s1_rows [0:7];','    reg [63:0] s1_rows [0:5];')
    source=change(source,'    wire [32:0] s1_write_domains;','    wire [24:0] s1_write_domains;')
    source=change(source,'    // A single ready/valid gate must not directly drive 512 payload hold muxes.',
        '    // A single ready/valid gate must not directly drive 384 payload hold muxes.')
    source=change(source,'    rv32_frequency_control_tree #(.LEAVES(33)) s1_write_tree (',
        '    rv32_frequency_control_tree #(.LEAVES(25)) s1_write_tree (')
    start=source.index('    wire [63:0] l5 [0:5];')
    end=source.index('    // The final CPA starts from two registered rows, never from the same',start)
    second=''
    count=6
    name='s1_rows'
    for output in ('second_reduce1','second_reduce2','second_rows'):
        text,count=reduce_rows(name,count,output)
        second+=text
        name=output
    if count!=2:
        raise ValueError('Expected two registered second-stage rows')
    source=source[:start]+second+source[end:]
    source=change(source,"    // cycle's four CSA layers. Both rows retain the exact modulo-2^64 sum.",
        "    // cycle's three CSA layers. Both rows retain the exact modulo-2^64 sum.")
    if source.count('l8[row]')!=4 or source.count('l4[row]')!=4:
        raise ValueError('Preserve unexpected CSA payload writes')
    source=source.replace('l8[row]','second_rows[row]').replace('l4[row]','first_rows[row]')
    source=change(source,'    generate for(row=0;row<8;row=row+1) begin:g_s1_storage',
        '    generate for(row=0;row<6;row=row+1) begin:g_s1_storage')
    source=change(source,'s1_ready && s1_write_domains[32]','s1_ready && s1_write_domains[24]')
    return source


if __name__=='__main__':
    prepare('DA_radix4_booth_pipeline',ROOT/'CZ_carry_select_tails',
            {'rtl/rv32m_multiplier.v':multiplier},
            '33-bit signed/unsigned radix4 Booth: 17 rows plus one correction vector; CSA 18/12/8/6 then 6/4/3/2, three/three layers; S1 payload 512->384 bits; metadata/latency/local cancellation unchanged; no HDL/EDA tests')
