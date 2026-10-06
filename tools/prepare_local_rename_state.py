"""Local RAT rows and free-bitmap words, preserving rename priority; no EDA."""
from prepare_staged_frequency_candidate import change, prepare, ROOT


OWNER=r'''

module rv32_rename_map_row #(parameter integer LANES=4,PAW=6) (
    input wire clk_i,reset_i,restore_i,
    input wire [PAW-1:0] restore_value_i,
    input wire [LANES-1:0] match_i,
    input wire [LANES*PAW-1:0] values_i,
    output reg [PAW-1:0] value_o
);
    reg [PAW-1:0] selected;
    integer lane;
    always @* begin
        selected=0;
        for(lane=0;lane<LANES;lane=lane+1)
            if(match_i[lane]) selected=values_i[lane*PAW +: PAW];
    end
    always @(posedge clk_i) begin
        if(reset_i) value_o<=0;
        else if(restore_i) value_o<=restore_value_i;
        else if(|match_i) value_o<=selected;
    end
endmodule
'''


def local_rename(t):
    t=change(t,'    reg [PHYS_ADDR_WIDTH-1:0] rat [0:31];',
               '    wire [PHYS_ADDR_WIDTH-1:0] rat [0:31];')
    t=change(t,'    reg [PHYS_REGS-1:0] free_bitmap;',
               '    wire [PHYS_REGS-1:0] free_bitmap;')
    insert=r'''
    localparam integer FREE_WORDS=(PHYS_REGS+31)/32;
    wire [32+FREE_WORDS-1:0] rename_reset_views,rename_restore_views;
    wire [4*BE_WIDTH*5-1:0] map_address_views;
    wire [4*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] map_value_views;
    wire [4*BE_WIDTH-1:0] map_valid_views;
    rv32_frequency_control_tree #(.LEAVES(32+FREE_WORDS)) reset_tree (
        .signal_i(reset_i),.views_o(rename_reset_views));
    rv32_frequency_control_tree #(.LEAVES(32+FREE_WORDS)) restore_tree (
        .signal_i(restore_valid_i),.views_o(rename_restore_views));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*5),.LEAVES(4)) map_address_tree (
        .signal_i(rename_rd_o),.views_o(map_address_views));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(4)) map_value_tree (
        .signal_i(rename_new_phys_o),.views_o(map_value_views));
    rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(4)) map_valid_tree (
        .signal_i(rename_valid_o & rename_rd_we_o),.views_o(map_valid_views));
    genvar map_row,map_lane,free_word;
    generate
        for(map_row=0;map_row<32;map_row=map_row+1) begin:g_map_row
            if(map_row==0) begin:g_zero
                assign rat[map_row]=0;
            end else begin:g_stored
                localparam integer DOMAIN=map_row/8;
                wire [BE_WIDTH-1:0] matches;
                for(map_lane=0;map_lane<BE_WIDTH;map_lane=map_lane+1) begin:g_match
                    assign matches[map_lane]=map_valid_views[DOMAIN*BE_WIDTH+map_lane] &&
                        map_address_views[(DOMAIN*BE_WIDTH+map_lane)*5 +: 5]==map_row;
                end
                rv32_rename_map_row #(.LANES(BE_WIDTH),.PAW(PHYS_ADDR_WIDTH)) owner (
                    .clk_i(clk_i),.reset_i(rename_reset_views[map_row]),
                    .restore_i(rename_restore_views[map_row]),
                    .restore_value_i(restore_rat_i[map_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]),
                    .match_i(matches),
                    .values_i(map_value_views[DOMAIN*BE_WIDTH*PHYS_ADDR_WIDTH +: BE_WIDTH*PHYS_ADDR_WIDTH]),
                    .value_o(rat[map_row]));
            end
        end
        for(free_word=0;free_word<FREE_WORDS;free_word=free_word+1) begin:g_free_word
            localparam integer LOW=free_word*32;
            localparam integer BITS=PHYS_REGS-LOW>=32 ? 32 : PHYS_REGS-LOW;
            reg [BITS-1:0] bits_q,bits_next;
            integer writer,phys_index;
            always @* begin
                bits_next=bits_q;
                phys_index=0;
                if(rename_reset_views[32+free_word]) bits_next={BITS{1'b1}};
                else if(rename_restore_views[32+free_word])
                    bits_next=restore_free_bitmap_i[LOW +: BITS];
                else begin
                    if(REGISTERED_FREE_POOL!=0)
                        bits_next=bits_q & ~pool_reserve_mask[LOW +: BITS];
                    for(writer=0;writer<BE_WIDTH;writer=writer+1) begin
                        phys_index=rename_new_phys_o[writer*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
                        if(REGISTERED_FREE_POOL==0 && rename_valid_o[writer] && rename_rd_we_o[writer] &&
                           phys_index>=LOW && phys_index<LOW+BITS)
                            bits_next[phys_index-LOW]=0;
                    end
                    // Commit returns win over same-edge reservation/allocation,
                    // exactly as the original low-to-high NBA sequence.
                    for(writer=0;writer<BE_WIDTH;writer=writer+1) begin
                        phys_index=commit_old_phys_i[writer*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
                        if(commit_valid_i && commit_rd_we_i[writer] && commit_rd_i[writer*5 +: 5]!=0 &&
                           phys_index!=0 && phys_index>=LOW && phys_index<LOW+BITS)
                            bits_next[phys_index-LOW]=1;
                    end
                end
                if(LOW==0) bits_next[0]=0;
            end
            always @(posedge clk_i) bits_q<=bits_next;
            assign free_bitmap[LOW +: BITS]=bits_q;
        end
    endgenerate
'''
    t=change(t,'    integer lane;\n',insert+'\n    integer lane;\n')
    start=t.rindex('    always @(posedge clk_i) begin')
    earlier,state=t[:start],t[start:]
    state=change(state,'        if (reset_i) begin','        if (rename_reset_views[0]) begin')
    state=change(state,'        end else if (restore_valid_i) begin','        end else if (rename_restore_views[0]) begin')
    state=change(state,'''            for (reset_index = 0; reset_index < 32; reset_index = reset_index + 1) begin
                rat[reset_index] <= 0;
            end
''','')
    state=change(state,'''            for (restore_index = 0; restore_index < 32; restore_index = restore_index + 1)
                rat[restore_index] <= restore_rat_i[(restore_index*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH];
''','')
    state=change(state,'                    rat[rename_rd_o[(lane*5) +: 5]] <= rename_new_phys_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH];\n','')
    state=change(state,"            free_bitmap <= {PHYS_REGS{1'b1}};\n",'')
    state=change(state,'            free_bitmap <= restore_free_bitmap_i;\n','')
    state=change(state,'            if(REGISTERED_FREE_POOL!=0) free_bitmap<=free_bitmap & ~pool_reserve_mask;\n','')
    state=change(state,'''                    if(REGISTERED_FREE_POOL==0)
                        free_bitmap[rename_new_phys_o[(lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]] <= 1'b0;
''','')
    state=change(state,"                        free_bitmap[commit_old_phys_i[(commit_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]] <= 1'b1;\n",'')
    assert state.count("            free_bitmap[0] <= 1'b0;\n")==3
    state=state.replace("            free_bitmap[0] <= 1'b0;\n",'')
    assert state.count('            rat[0] <= 0;\n')==2
    state=state.replace('            rat[0] <= 0;\n','')
    return earlier+state+OWNER


if __name__=='__main__':
    prepare('X_local_rename_state', ROOT/'W1_rob_ownership_and_recovery_arithmetic',
            {'rtl/rv32_rename_unit.v':local_rename},
            'W1 plus row-owned RAT and word-owned raw free bitmap, grouped qualified rename writes and local reset/restore; identical register bits and clock edges, reset > restore > normal and commit-return priority retained; no EDA run')
