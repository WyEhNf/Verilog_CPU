"""Prepare row-owned PRF writes and local query domains; no hardware tools."""
import re
from prepare_staged_frequency_candidate import change,prepare,ROOT


def local_prf(t):
    t=change(t,'    parameter integer READ_MUX_IMPL = 0,',
             '    parameter integer READ_MUX_IMPL = 0,\n    parameter integer LOCAL_VALUE_ROWS = 0,')
    t=change(t,'    reg [31:0] value [0:PHYS_REGS-1];',
             '    wire [31:0] value [0:PHYS_REGS-1];\n    reg [31:0] value_legacy [0:PHYS_REGS-1];')
    t=change(t,'    reg [PHYS_REGS-1:0] ready;',
             '    wire [PHYS_REGS-1:0] ready;\n    reg [PHYS_REGS-1:0] ready_legacy;')
    start=t.index('    always @(posedge clk_i) begin')
    end=t.index('endmodule',start)
    block=t[start:end]
    block=re.sub(r'\bvalue\b','value_legacy',block)
    block=re.sub(r'\bready\b','ready_legacy',block)
    t=t[:start]+'''    generate if(LOCAL_VALUE_ROWS==0) begin:g_legacy_storage
'''+block+'''    end endgenerate
'''+t[end:]
    # Scope signal renaming to parent reads; module port declarations keep
    # their original identifiers and the added tree takes the external bus.
    start=t.index('    // Decode each read word once')
    end=t.index('    generate if(LOCAL_VALUE_ROWS==0)')
    t=t[:start]+re.sub(r'\bread_phys_i\b','read_phys_local',t[start:end])+t[end:]
    insert='''    wire [2*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] read_phys_local;
    rv32_frequency_control_tree #(.WIDTH(2*BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(1)) read_query_tree (
        .signal_i(read_phys_i),.views_o(read_phys_local));
    genvar owner_row,owner_lane;
    generate if(LOCAL_VALUE_ROWS!=0) begin:g_local_storage
        wire [4*BE_WIDTH*32-1:0] write_values;
        wire [4*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] write_addresses,alloc_addresses;
        wire [4*BE_WIDTH-1:0] write_valids,alloc_valids;
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*32),.LEAVES(4)) value_tree (
            .signal_i(write_data_i),.views_o(write_values));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(4)) write_address_tree (
            .signal_i(write_phys_i),.views_o(write_addresses));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(4)) alloc_address_tree (
            .signal_i(alloc_phys_i),.views_o(alloc_addresses));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(4)) write_valid_tree (
            .signal_i(write_valid_i),.views_o(write_valids));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(4)) alloc_valid_tree (
            .signal_i(alloc_valid_i),.views_o(alloc_valids));
        for(owner_row=0;owner_row<PHYS_REGS;owner_row=owner_row+1) begin:g_row
            if(owner_row==0) begin:g_zero
                assign value[owner_row]=0;assign ready[owner_row]=1;
            end else begin:g_register
                localparam integer DOMAIN=(owner_row*4)/PHYS_REGS;
                wire [BE_WIDTH-1:0] writes,allocations;
                for(owner_lane=0;owner_lane<BE_WIDTH;owner_lane=owner_lane+1) begin:g_match
                    assign writes[owner_lane]=write_valids[DOMAIN*BE_WIDTH+owner_lane] &&
                        write_addresses[(DOMAIN*BE_WIDTH+owner_lane)*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==owner_row;
                    assign allocations[owner_lane]=alloc_valids[DOMAIN*BE_WIDTH+owner_lane] &&
                        alloc_addresses[(DOMAIN*BE_WIDTH+owner_lane)*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==owner_row;
                end
                rv32_prf_value_row #(.LANES(BE_WIDTH)) contents (
                    .clk_i(clk_i),.reset_i(reset_i),.alloc_i(|allocations),.write_matches_i(writes),
                    .write_values_i(write_values[DOMAIN*BE_WIDTH*32 +: BE_WIDTH*32]),
                    .value_o(value[owner_row]),.ready_o(ready[owner_row]));
            end
        end
    end else begin:g_legacy_alias
        for(owner_row=0;owner_row<PHYS_REGS;owner_row=owner_row+1) begin:g_row
            assign value[owner_row]=value_legacy[owner_row];
        end
        assign ready=ready_legacy;
    end endgenerate

'''
    t=change(t,'    // Decode each read word once',insert+'    // Decode each read word once')
    t+='''
// Highest valid lane wins. Value payload has no later reset mux; the final
// write enable already excludes reset before its priced local driver.
module rv32_prf_value_row #(parameter integer LANES=4) (
    input wire clk_i,reset_i,alloc_i,
    input wire [LANES-1:0] write_matches_i,
    input wire [LANES*32-1:0] write_values_i,
    output reg [31:0] value_o,
    output reg ready_o
);
    wire [LANES-1:0] grants,local_grants;
    wire write_local;
    genvar lane;
    generate for(lane=0;lane<LANES;lane=lane+1) begin:g_grant
        if(lane==LANES-1) assign grants[lane]=write_matches_i[lane];
        else assign grants[lane]=write_matches_i[lane] && !(|write_matches_i[LANES-1:lane+1]);
    end endgenerate
    rv32_frequency_control_tree #(.WIDTH(LANES),.LEAVES(1)) grant_tree (
        .signal_i(grants),.views_o(local_grants));
    rv32_frequency_control_tree #(.LEAVES(1)) write_tree (
        .signal_i(!reset_i && (|write_matches_i)),.views_o(write_local));
    reg [31:0] next_value;
    integer port;
    always @* begin
        next_value=0;
        for(port=0;port<LANES;port=port+1)
            next_value=next_value | ({32{local_grants[port]}} & write_values_i[port*32 +: 32]);
    end
    always @(posedge clk_i) if(write_local) value_o<=next_value;
    always @(posedge clk_i) begin
        if(reset_i) ready_o<=0;
        else if(|write_matches_i) ready_o<=1;
        else if(alloc_i) ready_o<=0;
    end
endmodule
'''
    return t


def enable_prf(t):
    return change(t,'.READ_MUX_IMPL(PRF_READ_MUX_IMPL)) prf (',
                  '.READ_MUX_IMPL(PRF_READ_MUX_IMPL), .LOCAL_VALUE_ROWS(1)) prf (')


if __name__=='__main__':
    prepare('P_local_prf_storage',ROOT/'O_local_free_pool_queries',
            {'rtl/rv32_physical_register_file.v':local_prf,'rtl/backend/rv32_backend_joint.v':enable_prf},
            'Separate untested alternative: O plus single-owner row-local PRF data and ready, balanced last-lane write selection and priced local read/write/allocation query and payload domains; no new stage')
