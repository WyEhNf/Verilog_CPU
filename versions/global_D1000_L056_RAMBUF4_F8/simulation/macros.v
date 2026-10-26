module fakeram_asap7_1x32(input clk,ce_in,we_in,input [0:0] addr_in,
    input [31:0] wd_in,output [31:0] rd_out);
    sram_fakeram #(.DEPTH(1),.WIDTH(32),.WRITE_GRANULARITY(32)) storage(
        .clk(clk),.en(ce_in),.we(we_in),.wmask(1'b1),.addr(addr_in),.wdata(wd_in),.rdata(rd_out));
endmodule

module fakeram_asap7_4x16(input clk,ce_in,we_in,input [1:0] addr_in,
    input [15:0] wd_in,output [15:0] rd_out);
    sram_fakeram #(.DEPTH(4),.WIDTH(16),.WRITE_GRANULARITY(16)) storage(
        .clk(clk),.en(ce_in),.we(we_in),.wmask(1'b1),.addr(addr_in),.wdata(wd_in),.rdata(rd_out));
endmodule

module fakeram_asap7_128x128(input clk,ce_in,we_in,input [6:0] addr_in,
    input [127:0] wd_in,output [127:0] rd_out);
    sram_fakeram #(.DEPTH(128),.WIDTH(128),.WRITE_GRANULARITY(128)) storage(
        .clk(clk),.en(ce_in),.we(we_in),.wmask(1'b1),.addr(addr_in),.wdata(wd_in),.rdata(rd_out));
endmodule

module fakeram_asap7_512x8(input clk,ce_in,we_in,input [8:0] addr_in,
    input [7:0] wd_in,output [7:0] rd_out);
    sram_fakeram #(.DEPTH(512),.WIDTH(8),.WRITE_GRANULARITY(8)) storage(
        .clk(clk),.en(ce_in),.we(we_in),.wmask(1'b1),.addr(addr_in),.wdata(wd_in),.rdata(rd_out));
endmodule

module fakeram_asap7_512x19(input clk,ce_in,we_in,input [8:0] addr_in,
    input [18:0] wd_in,output [18:0] rd_out);
    sram_fakeram #(.DEPTH(512),.WIDTH(19),.WRITE_GRANULARITY(19)) storage(
        .clk(clk),.en(ce_in),.we(we_in),.wmask(1'b1),.addr(addr_in),.wdata(wd_in),.rdata(rd_out));
endmodule
