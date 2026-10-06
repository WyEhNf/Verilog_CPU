// Small toolchain fixture only. This is NOT the CPU or a performance candidate.
module student_top (
    input wire clk_i, reset_i,
    input wire en_i, we_i,
    input wire [3:0] addr_i, mask_i,
    input wire [31:0] data_i,
    output reg [31:0] data_o
);
    reg en_reg, we_reg;
    reg [3:0] addr_reg, mask_reg;
    reg [31:0] data_reg;
    wire [31:0] sram_data;
    always @(posedge clk_i) begin
        en_reg <= !reset_i && en_i;
        we_reg <= we_i;
        addr_reg <= addr_i;
        mask_reg <= mask_i;
        data_reg <= data_i;
        if (!reset_i) data_o <= sram_data;
    end
    sram_fakeram #(.DEPTH(16), .WIDTH(32), .WRITE_GRANULARITY(8)) storage (
        .clk(clk_i), .en(en_reg), .we(we_reg), .wmask(mask_reg),
        .addr(addr_reg), .wdata(data_reg), .rdata(sram_data)
    );
endmodule
