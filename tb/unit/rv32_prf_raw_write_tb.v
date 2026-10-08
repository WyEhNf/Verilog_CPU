`timescale 1ns/1ps
module rv32_prf_raw_write_tb;
    reg clk=0,reset=1;always #5 clk=~clk;
    reg [23:0] queries=0;
    reg [11:0] allocations=0,writes=0;
    reg [1:0] av=0,wv=0;
    reg [63:0] values=0;
    reg [23:0] offsets=0;
    wire [127:0] data[0:1];wire [3:0] ready[0:1],saved_ready[0:1],pending[0:1];
    wire [63:0] address[0:1];wire [5:0] flags[0:1],saved_flags[0:1];
    genvar p;generate for(p=0;p<2;p=p+1) begin:g_policy
        rv32_physical_register_file #(.BE_WIDTH(2),.PHYS_REGS(36),.PHYS_ADDR_WIDTH(6),
            .LOCAL_VALUE_ROWS(1),.VALUE_SRAM(1),.SRAM_PORT_FORWARD(p),.SRAM_RAW_WRITE(p),.READ_MUX_IMPL(1),
            .STORE_ADDRESS_READ(1),.STORE_ADDRESS_FLAGS(1),.STORE_SAVED_QUERY(1),.STORE_CLASS_COMPARE(1)) dut (
            .clk_i(clk),.reset_i(reset),.read_phys_i(queries),.read_data_o(data[p]),.read_ready_o(ready[p]),
            .alloc_phys_i(allocations),.alloc_valid_i(av),.write_phys_i(writes),.write_data_i(values),.write_valid_i(wv),
            .store_offset_i(offsets),.store_address_o(address[p]),.store_address_flags_o(flags[p]),
            .read_stored_ready_o(saved_ready[p]),.read_bypass_pending_o(pending[p]),.store_saved_flags_o(saved_flags[p]));
    end endgenerate
    integer port;
    task compare;begin
        #1;
        if(ready[0]!==ready[1] || saved_ready[0]!==saved_ready[1] || pending[0]!==pending[1])
            $fatal(1,"PRF ready/forward ownership policies differ");
        for(port=0;port<4;port=port+1) begin
            if(ready[0][port] && data[0][port*32 +: 32]!==data[1][port*32 +: 32])
                $fatal(1,"PRF ready data differs port %0d",port);
            if(port%2==0 && ready[0][port] &&
                (address[0][(port/2)*32 +: 32]!==address[1][(port/2)*32 +: 32] ||
                 flags[0][(port/2)*3 +: 3]!==flags[1][(port/2)*3 +: 3]))
                $fatal(1,"PRF address/current flags differ port %0d",port);
            if(port%2==0 && saved_ready[0][port] &&
                saved_flags[0][(port/2)*3 +: 3]!==saved_flags[1][(port/2)*3 +: 3])
                $fatal(1,"PRF saved address flags differ port %0d",port);
        end
    end endtask
    task tick;begin @(posedge clk);#1;compare;end endtask
    initial begin
        tick;tick;reset=0;queries={6'd63,6'd0,6'd2,6'd1};offsets={12'hfff,12'd4};compare;
        if(ready[1]!==4'b0100 || data[1][127:64]!==64'b0) $fatal(1,"P0/illegal read behavior changed");
        av=3;allocations={6'd2,6'd1};tick;av=0;
        wv=3;writes={6'd2,6'd1};values={32'h7ffffffe,32'h80000000};compare;tick;
        wv=0;compare;
        if(data[1][63:0]!==64'h7ffffffe80000000 || address[1][31:0]!==32'h80000004)
            $fatal(1,"previous SRAM write not forwarded to data/address");
        queries={6'd35,6'd2,6'd1,6'd1};wv=3;writes={6'd1,6'd1};values={32'hffffffff,32'h12345678};compare;
        if(data[1][31:0]!==32'hffffffff || address[1][31:0]!==32'd3)
            $fatal(1,"highest duplicate write priority changed");
        tick;wv=1;writes={6'd0,6'd1};values={32'b0,32'h00000100};compare;
        if(address[1][31:0]!==32'h104 || saved_flags[1][2:0]!==3'b001)
            $fatal(1,"saved/current address classification conflated");
        av=1;allocations=12'd1;tick;av=0;wv=0;compare;
        if(!ready[1][0] || data[1][31:0]!==32'h100) $fatal(1,"write did not dominate allocation");
        tick;queries={6'd35,6'd35,6'd2,6'd1};wv=1;writes=12'd35;values=64'hfffffff0;compare;tick;wv=0;compare;
        if(data[1][127:64]!==64'hfffffff0fffffff0) $fatal(1,"distant SRAM owner forwarding lost");
        tick;av=1;allocations=12'd35;tick;av=0;compare;
        if(ready[1][3:2]!=0) $fatal(1,"allocated owner stayed ready");
        wv=3;writes={6'd63,6'd0};values=64'hdeadbeefabcdef01;queries={6'd63,6'd0,6'd2,6'd1};compare;tick;wv=0;compare;
        if(data[1][127:64]!=0 || ready[1][3:2]!==2'b01) $fatal(1,"invalid write changed P0/illegal");
        reset=1;tick;reset=0;compare;
        if(ready[1]!==4'b0100) $fatal(1,"reset ready semantics changed");
        $display("PASS: limited PRF raw-write sample");$finish;
    end
    initial begin #2000;$fatal(1,"PRF port-forward sample timeout");end
endmodule
