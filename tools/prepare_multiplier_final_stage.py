"""Separate final carry-save reduction from the 64-bit CPA; source only."""
from prepare_staged_frequency_candidate import change, prepare, ROOT


def final_stage(t):
    t=change(t,'    reg out_valid;', '''    reg s2_valid;
    reg [63:0] s2_rows [0:1];
    reg [OP_WIDTH-1:0] s2_op;
    reg [TAG_WIDTH-1:0] s2_tag;
    reg [PHYS_ADDR_WIDTH-1:0] s2_phys;
    reg s2_live;
    reg out_valid;''')
    t=change(t,'    wire s1_ready=!s1_valid || out_ready || s1_discard;', '''    wire s2_discard=s2_valid && (!s2_live ||
        (live_tag_valid_i && s2_tag!=live_tag_i));
    wire s2_ready=!s2_valid || out_ready || s2_discard;
    wire s1_ready=!s1_valid || s2_ready || s1_discard;
    wire [4:0] s2_write_domains;
    rv32_frequency_control_tree #(.LEAVES(5)) s2_write_tree (
        .signal_i(s2_ready && s1_valid && !s1_discard),.views_o(s2_write_domains));''')
    t=change(t,'.signal_i(out_ready && s1_valid && !s1_discard),.views_o(out_write_domains));',
               '.signal_i(out_ready && s2_valid && !s2_discard),.views_o(out_write_domains));')
    t=change(t,'    wire [63:0] product=l8[0]+l8[1];', '''    // The final CPA starts from two registered rows, never from the same
    // cycle's four CSA layers. Both rows retain the exact modulo-2^64 sum.
    wire [63:0] product=s2_rows[0]+s2_rows[1];
    generate for(row=0;row<2;row=row+1) begin:g_s2_storage
        always @(posedge clk_i) begin
            if(s2_write_domains[2*row]) s2_rows[row][31:0]<=l8[row][31:0];
            if(s2_write_domains[2*row+1]) s2_rows[row][63:32]<=l8[row][63:32];
        end
    end endgenerate''')
    t=change(t,"            s1_valid<=1'b0;\n", "            s1_valid<=1'b0;\n            s2_valid<=1'b0;\n")
    t=change(t,'''            if(out_ready) begin
                out_valid<=s1_valid && !s1_discard;
            end''', '''            if(s2_ready) s2_valid<=s1_valid && !s1_discard;
            if(s2_write_domains[4]) begin
                s2_op<=s1_op;s2_tag<=s1_tag;s2_phys<=s1_phys;s2_live<=s1_live;
            end
            if(out_ready) begin
                out_valid<=s2_valid && !s2_discard;
            end''')
    t=change(t,'                    case(s1_op)','                    case(s2_op)')
    for field in ('tag','phys','live'):
        t=change(t,f'                    out_{field}<=s1_{field};',f'                    out_{field}<=s2_{field};')
    return t


if __name__=='__main__':
    prepare('AB_registered_final_multiplier_cpa', ROOT/'AA_parallel_radix4_divider',
            {'rtl/rv32m_multiplier.v':final_stage},
            'AA plus registered two-row carry-save result before final 64-bit CPA, complete live-tag/valid/ready backpressure per stage; multiplier latency increases one cycle, intrinsic initiation interval remains one, ordinary integer pipeline unchanged; 159 bits at current widths, no EDA run')
