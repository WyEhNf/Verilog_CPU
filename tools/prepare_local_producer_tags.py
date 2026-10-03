"""Local producer-tag storage and parallel reads; source work only."""
from prepare_staged_frequency_candidate import change, prepare, ROOT


OWNER = r'''

module rv32_producer_tag_row #(parameter integer LANES=4,TAG_WIDTH=17) (
    input wire clk_i,reset_i,
    input wire [LANES-1:0] match_i,
    input wire [LANES*TAG_WIDTH-1:0] tag_i,
    output wire [TAG_WIDTH-1:0] tag_o
);
    reg stored_valid;
    reg [TAG_WIDTH-1:0] stored_tag;
    wire [LANES-1:0] grants,local_grants;
    wire write_local;
    genvar lane;
    generate for(lane=0;lane<LANES;lane=lane+1) begin:g_grant
        if(lane==LANES-1) assign grants[lane]=match_i[lane];
        else assign grants[lane]=match_i[lane] && !(|match_i[LANES-1:lane+1]);
    end endgenerate
    rv32_frequency_control_tree #(.WIDTH(LANES),.LEAVES(1)) grant_tree (
        .signal_i(grants),.views_o(local_grants));
    rv32_frequency_control_tree #(.LEAVES(1)) write_tree (
        .signal_i(!reset_i && (|match_i)),.views_o(write_local));
    reg [TAG_WIDTH-1:0] next_tag;
    integer writer;
    always @* begin
        next_tag=0;
        for(writer=0;writer<LANES;writer=writer+1)
            next_tag=next_tag | ({TAG_WIDTH{local_grants[writer]}} &
                               tag_i[writer*TAG_WIDTH +: TAG_WIDTH]);
    end
    always @(posedge clk_i) if(write_local) stored_tag<=next_tag;
    always @(posedge clk_i) begin
        if(reset_i) stored_valid<=0;
        else if(|match_i) stored_valid<=1;
    end
    // Before the first write after reset, the visible tag is exactly zero,
    // matching the former full-word reset. A write replaces all tag bits.
    assign tag_o={TAG_WIDTH{stored_valid}} & stored_tag;
endmodule
'''


def local_tags(t):
    t=change(t,'    reg [TAG_WIDTH-1:0] phys_tag_mem [0:PHYS_REGS-1];',
               '    wire [TAG_WIDTH-1:0] phys_tag_mem [0:PHYS_REGS-1];\n'+r'''
    localparam integer TAG_READ_PORTS=2*BE_WIDTH;
    localparam integer TAG_ROWS=(PHYS_REGS<=1)?1:(1<<$clog2(PHYS_REGS));
    wire [TAG_READ_PORTS*PAW-1:0] tag_read_queries;
    wire [TAG_READ_PORTS*TAG_WIDTH-1:0] tag_read_values;
    wire [4*TAG_READ_PORTS*PAW-1:0] tag_query_views;
    wire [4*BE_WIDTH*PAW-1:0] tag_write_address_views;
    wire [4*BE_WIDTH*TAG_WIDTH-1:0] tag_write_value_views;
    wire [4*BE_WIDTH-1:0] tag_write_valid_views;
    wire [PHYS_REGS-1:0] tag_reset_views;
    genvar tag_lane,tag_row,tag_port,tag_node;
    generate
        for(tag_lane=0;tag_lane<BE_WIDTH;tag_lane=tag_lane+1) begin:g_tag_query
            assign tag_read_queries[(2*tag_lane)*PAW +: PAW]=rename_rs1_phys[tag_lane*PAW +: PAW];
            assign tag_read_queries[(2*tag_lane+1)*PAW +: PAW]=rename_rs2_phys[tag_lane*PAW +: PAW];
        end
        if(PHYS_TAG_IMPL==0) begin:g_owned_producer_tags
            rv32_frequency_control_tree #(.WIDTH(TAG_READ_PORTS*PAW),.LEAVES(4)) query_tree (
                .signal_i(tag_read_queries),.views_o(tag_query_views));
            rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PAW),.LEAVES(4)) address_tree (
                .signal_i(rename_new_phys),.views_o(tag_write_address_views));
            rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*TAG_WIDTH),.LEAVES(4)) value_tree (
                .signal_i(rob_alloc_tag),.views_o(tag_write_value_views));
            rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(4)) valid_tree (
                .signal_i(dispatch_valid & rob_alloc_fire & rename_rd_we),.views_o(tag_write_valid_views));
            rv32_frequency_control_tree #(.LEAVES(PHYS_REGS)) reset_tree (
                .signal_i(reset_i),.views_o(tag_reset_views));
            for(tag_row=0;tag_row<PHYS_REGS;tag_row=tag_row+1) begin:g_row
                localparam integer DOMAIN=(tag_row*4)/PHYS_REGS;
                wire [BE_WIDTH-1:0] matches;
                for(tag_lane=0;tag_lane<BE_WIDTH;tag_lane=tag_lane+1) begin:g_match
                    assign matches[tag_lane]=tag_write_valid_views[DOMAIN*BE_WIDTH+tag_lane] &&
                        tag_write_address_views[(DOMAIN*BE_WIDTH+tag_lane)*PAW +: PAW]==tag_row;
                end
                rv32_producer_tag_row #(.LANES(BE_WIDTH),.TAG_WIDTH(TAG_WIDTH)) owner (
                    .clk_i(clk_i),.reset_i(tag_reset_views[tag_row]),.match_i(matches),
                    .tag_i(tag_write_value_views[DOMAIN*BE_WIDTH*TAG_WIDTH +: BE_WIDTH*TAG_WIDTH]),
                    .tag_o(phys_tag_mem[tag_row]));
            end
            for(tag_port=0;tag_port<TAG_READ_PORTS;tag_port=tag_port+1) begin:g_read
                wire [TAG_WIDTH-1:0] tree [1:2*TAG_ROWS-1];
                for(tag_row=0;tag_row<TAG_ROWS;tag_row=tag_row+1) begin:g_select
                    if(tag_row<PHYS_REGS) begin:g_present
                        localparam integer DOMAIN=(tag_row*4)/PHYS_REGS;
                        wire selected=tag_query_views[(DOMAIN*TAG_READ_PORTS+tag_port)*PAW +: PAW]==tag_row;
                        wire local_selected;
                        rv32_frequency_control_tree #(.LEAVES(1)) select_tree (
                            .signal_i(selected),.views_o(local_selected));
                        assign tree[TAG_ROWS+tag_row]={TAG_WIDTH{local_selected}} & phys_tag_mem[tag_row];
                    end else begin:g_padding
                        assign tree[TAG_ROWS+tag_row]=0;
                    end
                end
                for(tag_node=1;tag_node<TAG_ROWS;tag_node=tag_node+1) begin:g_or
                    assign tree[tag_node]=tree[2*tag_node] | tree[2*tag_node+1];
                end
                assign tag_read_values[tag_port*TAG_WIDTH +: TAG_WIDTH]=tree[1];
            end
        end else begin:g_rob_search_producer_tags
            assign tag_read_values=0;
            for(tag_row=0;tag_row<PHYS_REGS;tag_row=tag_row+1) begin:g_unused
                assign phys_tag_mem[tag_row]=0;
            end
        end
    endgenerate
''')
    for operand in (1,2):
        t=change(t,f'phys_tag_mem[rename_rs{operand}_phys[source_lane*PAW +: PAW]];',
                   f'tag_read_values[(2*source_lane+{operand-1})*TAG_WIDTH +: TAG_WIDTH];')
    t=change(t,'''            if (PHYS_TAG_IMPL == 0)
                for (map_phys_slot = 0; map_phys_slot < PHYS_REGS; map_phys_slot = map_phys_slot + 1)
                    phys_tag_mem[map_phys_slot] <= 0;
''','')
    t=change(t,'''                    if ((PHYS_TAG_IMPL == 0) && rename_rd_we[map_lane] &&
                        (rename_new_phys[map_lane*PAW +: PAW] < PHYS_REGS))
                        phys_tag_mem[rename_new_phys[map_lane*PAW +: PAW]] <=
                            rob_alloc_tag[map_lane*TAG_WIDTH +: TAG_WIDTH];
''','')
    return t+OWNER


if __name__=='__main__':
    prepare('V_local_producer_tag_table', ROOT/'U1_lsq_functional_field_owners',
            {'rtl/backend/rv32_backend_joint.v':local_tags},
            'U1 plus row-owned producer tags, grouped read/write queries and balanced one-hot tag reads; visible reset-to-zero and highest-lane write priority retained, no pipeline cycle added; up to PHYS_REGS valid bits added, no EDA run')
