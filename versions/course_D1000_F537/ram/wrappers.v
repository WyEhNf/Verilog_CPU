// Generated SRAM wrappers; do not edit.
module sram_fakeram_1x32_m32 (
    input clk, en, we,
    input [0:0] wmask,
    input [0:0] addr,
    input [31:0] wdata,
    output [31:0] rdata);
    fakeram_asap7_1x32 lane_0 (
        .clk(clk), .ce_in(en & (~we | wmask[0])), .we_in(we),
        .addr_in(addr), .wd_in(wdata[31:0]), .rd_out(rdata[31:0]));
endmodule

module sram_fakeram_4x16_m16 (
    input clk, en, we,
    input [0:0] wmask,
    input [1:0] addr,
    input [15:0] wdata,
    output [15:0] rdata);
    fakeram_asap7_4x16 lane_0 (
        .clk(clk), .ce_in(en & (~we | wmask[0])), .we_in(we),
        .addr_in(addr), .wd_in(wdata[15:0]), .rd_out(rdata[15:0]));
endmodule

module sram_fakeram_128x16_m16 (
    input clk, en, we,
    input [0:0] wmask,
    input [6:0] addr,
    input [15:0] wdata,
    output [15:0] rdata);
    fakeram_asap7_128x16 lane_0 (
        .clk(clk), .ce_in(en & (~we | wmask[0])), .we_in(we),
        .addr_in(addr), .wd_in(wdata[15:0]), .rd_out(rdata[15:0]));
endmodule

module sram_fakeram_512x8_m8 (
    input clk, en, we,
    input [0:0] wmask,
    input [8:0] addr,
    input [7:0] wdata,
    output [7:0] rdata);
    fakeram_asap7_512x8 lane_0 (
        .clk(clk), .ce_in(en & (~we | wmask[0])), .we_in(we),
        .addr_in(addr), .wd_in(wdata[7:0]), .rd_out(rdata[7:0]));
endmodule

module sram_fakeram_512x19_m19 (
    input clk, en, we,
    input [0:0] wmask,
    input [8:0] addr,
    input [18:0] wdata,
    output [18:0] rdata);
    fakeram_asap7_512x19 lane_0 (
        .clk(clk), .ce_in(en & (~we | wmask[0])), .we_in(we),
        .addr_in(addr), .wd_in(wdata[18:0]), .rd_out(rdata[18:0]));
endmodule
