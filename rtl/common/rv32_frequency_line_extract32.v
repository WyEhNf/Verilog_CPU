`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Full 128-bit logical shift semantics, retaining zero fill even for an
// unaligned byte window near the end of a line. Only bits needed by the
// eventual 32-bit result are routed through the four byte-offset stages.
// Each amount leaf owns at most sixteen actual mux bits; no state/cycle.
module rv32_frequency_line_extract32 (
    input wire [127:0] line_i,
    input wire [3:0] offset_i,
    input wire [1:0] size_i,
    input wire unsigned_i,
    output wire [31:0] value_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    wire [127:0] shifted_line = line_i >> {offset_i,3'b0};
    wire unused_shifted_line_bits = &{1'b0, shifted_line};

    wire [31:0] shifted = shifted_line[31:0];
    assign value_o = (size_i==2'd0) ? {{24{!unsigned_i && shifted[7]}},shifted[7:0]} :
        ((size_i==2'd1) ? {{16{!unsigned_i && shifted[15]}},shifted[15:0]} : shifted);
`else
    wire [87:0] shift64;
    wire [55:0] shift32;
    wire [39:0] shift16;
    wire [31:0] shifted;
    wire [5:0] amount64;
    wire [3:0] amount32;
    wire [2:0] amount16;
    wire [1:0] amount8;
    rv32_frequency_control_tree #(.LEAVES(6)) amount64_tree (
        .signal_i(offset_i[3]),.views_o(amount64));
    rv32_frequency_control_tree #(.LEAVES(4)) amount32_tree (
        .signal_i(offset_i[2]),.views_o(amount32));
    rv32_frequency_control_tree #(.LEAVES(3)) amount16_tree (
        .signal_i(offset_i[1]),.views_o(amount16));
    rv32_frequency_control_tree #(.LEAVES(2)) amount8_tree (
        .signal_i(offset_i[0]),.views_o(amount8));
    genvar bit_id;
    generate
        for(bit_id=0;bit_id<88;bit_id=bit_id+1) begin:g_shift64
            if(bit_id+64<128) begin:g_data
                assign shift64[bit_id]=amount64[bit_id/16]?line_i[bit_id+64]:line_i[bit_id];
            end else begin:g_zero
                assign shift64[bit_id]=!amount64[bit_id/16] && line_i[bit_id];
            end
        end
        for(bit_id=0;bit_id<56;bit_id=bit_id+1) begin:g_shift32
            assign shift32[bit_id]=amount32[bit_id/16]?shift64[bit_id+32]:shift64[bit_id];
        end
        for(bit_id=0;bit_id<40;bit_id=bit_id+1) begin:g_shift16
            assign shift16[bit_id]=amount16[bit_id/16]?shift32[bit_id+16]:shift32[bit_id];
        end
        for(bit_id=0;bit_id<32;bit_id=bit_id+1) begin:g_shift8
            assign shifted[bit_id]=amount8[bit_id/16]?shift16[bit_id+8]:shift16[bit_id];
        end
    endgenerate
    // RV32IM_MEM_BYTE=0, RV32IM_MEM_HALF=1; both remaining codes
    // retain the former function's default full-word behavior.
    wire [7:0] format_views;
    rv32_frequency_control_tree #(.WIDTH(4),.LEAVES(2)) format_tree (
        .signal_i({size_i==2'd0,size_i==2'd1,
                   !unsigned_i && shifted[7],!unsigned_i && shifted[15]}),
        .views_o(format_views));
    generate for(bit_id=0;bit_id<32;bit_id=bit_id+1) begin:g_format
        wire byte_load,half_load,byte_sign,half_sign;
        assign {byte_load,half_load,byte_sign,half_sign}=format_views[(bit_id/16)*4 +: 4];
        if(bit_id<8) begin:g_low
            assign value_o[bit_id]=shifted[bit_id];
        end else if(bit_id<16) begin:g_byte_extend
            assign value_o[bit_id]=byte_load?byte_sign:shifted[bit_id];
        end else begin:g_half_extend
            assign value_o[bit_id]=byte_load?byte_sign:(half_load?half_sign:shifted[bit_id]);
        end
    end endgenerate
`endif
endmodule
