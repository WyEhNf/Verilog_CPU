"""Bound cache-facing LSQ request data muxes; source-only, no tests."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


INSERT='''

// Insert an access-relative word at any byte offset, preserving the original
// 128-bit left shift and overflow truncation. Increasing intermediate widths
// retain all reachable bits; each amount leaf owns <=16 actual mux bits.
module rv32_frequency_line_insert32 (
    input wire [31:0] value_i,
    input wire [3:0] offset_i,
    output wire [127:0] line_o
);
    wire [39:0] shift8;
    wire [55:0] shift16;
    wire [87:0] shift32;
    wire [127:0] original [0:3];
    wire [127:0] shifted [0:3];
    wire [2:0] amount8;
    wire [3:0] amount16;
    wire [5:0] amount32;
    wire [7:0] amount64;
    assign original[0]={96'b0,value_i};
    assign shifted[0]={88'b0,value_i,8'b0};
    assign original[1]={88'b0,shift8};
    assign shifted[1]={72'b0,shift8,16'b0};
    assign original[2]={72'b0,shift16};
    assign shifted[2]={40'b0,shift16,32'b0};
    assign original[3]={40'b0,shift32};
    assign shifted[3]={shift32[63:0],64'b0};
    rv32_frequency_control_tree #(.LEAVES(3)) amount8_tree (
        .signal_i(offset_i[0]),.views_o(amount8));
    rv32_frequency_control_tree #(.LEAVES(4)) amount16_tree (
        .signal_i(offset_i[1]),.views_o(amount16));
    rv32_frequency_control_tree #(.LEAVES(6)) amount32_tree (
        .signal_i(offset_i[2]),.views_o(amount32));
    rv32_frequency_control_tree #(.LEAVES(8)) amount64_tree (
        .signal_i(offset_i[3]),.views_o(amount64));
    genvar bit_id;
    generate
        for(bit_id=0;bit_id<40;bit_id=bit_id+1) begin:g_shift8
            assign shift8[bit_id]=amount8[bit_id/16]?shifted[0][bit_id]:original[0][bit_id];
        end
        for(bit_id=0;bit_id<56;bit_id=bit_id+1) begin:g_shift16
            assign shift16[bit_id]=amount16[bit_id/16]?shifted[1][bit_id]:original[1][bit_id];
        end
        for(bit_id=0;bit_id<88;bit_id=bit_id+1) begin:g_shift32
            assign shift32[bit_id]=amount32[bit_id/16]?shifted[2][bit_id]:original[2][bit_id];
        end
        for(bit_id=0;bit_id<128;bit_id=bit_id+1) begin:g_shift64
            assign line_o[bit_id]=amount64[bit_id/16]?shifted[3][bit_id]:original[3][bit_id];
        end
    endgenerate
endmodule
'''


def common(source):
    if 'module rv32_frequency_line_insert32' in source:
        raise ValueError('Already has insertion routing')
    return source+INSERT


def lsq(source):
    source=change(source,'    output reg  [127:0]                 dcache_req_wdata_o,',
                        '    output wire [127:0]                 dcache_req_wdata_o,')
    source=change(source,"        dcache_req_wdata_o = 128'b0;",'        // Wide request data is routed by the bounded combinational unit below.')
    source=change(source,'                    dcache_req_wdata_o = line_data_from_relative(fwd_data, selected_addr);','                    // Forwarded request bytes use the shared insertion unit.')
    source=change(source,'                dcache_req_wdata_o = line_data_from_relative(selected_store_data, selected_addr);','                // Store request bytes use the shared insertion unit.')
    source=change(source,'    // Load reporting follows queue age; store admission preserves the former','''    // The old request-admission gate fed ~151 mapped pins and also happened
    // to be named as AXI enabled_words bit0 after flattening. Keep admission
    // itself unchanged. Select one relative32-bit source, then insert it;
    // qualify AFTER insertion so late request-valid never traverses shifts.
    wire [1:0] request_source_views;
    wire [7:0] request_data_views;
    wire [31:0] request_relative_data;
    wire [127:0] request_inserted_data;
    rv32_frequency_control_tree #(.LEAVES(2)) request_source_tree (
        .signal_i(selected_load),.views_o(request_source_views));
    rv32_frequency_control_tree #(.LEAVES(8)) request_data_tree (
        .signal_i(dcache_req_valid_o),.views_o(request_data_views));
    generate for(genvar request_source_word=0;request_source_word<2;request_source_word=request_source_word+1) begin:g_request_source_word
        assign request_relative_data[request_source_word*16 +: 16]=request_source_views[request_source_word]?
            fwd_data[request_source_word*16 +: 16]:selected_store_data[request_source_word*16 +: 16];
    end endgenerate
    rv32_frequency_line_insert32 request_insertion (
        .value_i(request_relative_data),.offset_i(selected_addr[3:0]),.line_o(request_inserted_data));
    generate for(genvar request_line_word=0;request_line_word<8;request_line_word=request_line_word+1) begin:g_request_line_word
        assign dcache_req_wdata_o[request_line_word*16 +: 16]=
            {16{request_data_views[request_line_word]}} & request_inserted_data[request_line_word*16 +: 16];
    end endgenerate

    // Load reporting follows queue age; store admission preserves the former''')
    return source


if __name__=='__main__':
    prepare('CN_lsq_request_data_distribution',ROOT/'CM_dcache_refill_data_distribution',{
        'rtl/common/rv32_asap7_fanout.v':common,
        'rtl/backend/rv32_lsq.v':lsq,
    },'CM plus one shared32-to128-byte insertion unit for forwarded/store request data, bounded amount bits and16-bit final request-valid qualification. Late admission remains after the shifts; original zero-invalid, mask/scalar handshake, all offsets/overflow and cycles preserved. No FF/SRAM/protocol change or hardware tests; source-only candidate.')
