`timescale 1ns/1ps
module rv32_mmio_write_capacity_tb;
    reg clock=0,reset=1;
    always #5 clock=~clock;
    reg dvalid=0,dwrite=1,ivalid=0;
    reg [31:0] address=32'h80000000;
    reg [127:0] data=128'h12345678;
    reg [15:0] mask=16'h000f;
    reg [7:0] id=8'hfe;
    reg awready=0,wready=0,bvalid=0;
    wire ready,capacity,iready,awvalid,wvalid,bready,arvalid;
    wire [31:0] awaddr,wdata,araddr;
    wire [3:0] wstrb;
    integer accepted=0,limit;
    rv32_axi_lite_bridge #(.READ_LINES(2),.WRITE_LINES(2),.WORD_QUEUE(4)) dut (
        .clock(clock),.reset(reset),
        .i_req_valid(ivalid),.i_req_ready(iready),.i_req_addr(32'h100),.i_req_id(8'h10),
        .i_resp_ready(1'b1),.d_req_valid(dvalid),.d_req_ready(ready),.d_write_capacity_ready(capacity),
        .d_req_write(dwrite),.d_req_addr(address),.d_req_data(data),.d_req_mask(mask),.d_req_id(id),
        .d_resp_ready(1'b1),.araddr(araddr),.arvalid(arvalid),.arready(1'b0),
        .rdata(32'b0),.rresp(2'b0),.rvalid(1'b0),
        .awaddr(awaddr),.awvalid(awvalid),.awready(awready),
        .wdata(wdata),.wstrb(wstrb),.wvalid(wvalid),.wready(wready),
        .bresp(2'b0),.bvalid(bvalid),.bready(bready)
    );
    always @(posedge clock) if(!reset) begin
        if(dvalid && ready && dwrite) accepted=accepted+1;
        if(dvalid && dwrite && ready!=capacity) $fatal(1,"actual write and independent capacity disagree");
        if(awvalid && (awaddr!=32'h80000000 || !wvalid || wdata!=32'h12345678 || wstrb!=4'hf))
            $fatal(1,"held MMIO bus payload changed");
    end
    task tick;begin @(posedge clock);#1;end endtask
    initial begin
        tick;tick;#1;if(ready || capacity) $fatal(1,"reset admits a request");
        @(negedge clock);reset=0;#1;if(!ready || !capacity) $fatal(1,"empty write queue rejected MMIO");
        dvalid=1;tick;@(negedge clock);#1;if(!capacity) $fatal(1,"first write consumed two slots");
        tick;@(negedge clock);#1;
        if(capacity || ready || accepted!=2) $fatal(1,"full write queue admitted a third MMIO");
        tick;@(negedge clock);dvalid=0;#1;if(accepted!=2) $fatal(1,"held MMIO duplicated");
        // Invalid incoming exit classification may remain true while a normal
        // cache RFO owns the bus. Independent write capacity cannot block that
        // read transaction or alter bus ready/routing.
        dwrite=0;address=32'h200;id=8'h20;#1;
        if(!ready || capacity) $fatal(1,"full write queue blocked independent cache read");
        dvalid=1;tick;@(negedge clock);dvalid=0;dwrite=1;address=32'h80000000;id=8'hfe;#1;
        if(ready || capacity) $fatal(1,"normal read incorrectly reclaimed write capacity");
        // Drain the first one-word write through the original AW/W/B protocol.
        awready=1;wready=1;
        for(limit=0;limit<12 && !bready;limit=limit+1) begin tick;@(negedge clock);end
        if(!bready) $fatal(1,"AXI write did not reach response ownership");
        bvalid=1;tick;@(negedge clock);bvalid=0;
        for(limit=0;limit<12 && !capacity;limit=limit+1) begin tick;@(negedge clock);end
        if(!capacity || !ready || accepted!=2) $fatal(1,"write ACK did not return saved capacity");
        dvalid=1;tick;@(negedge clock);dvalid=0;
        if(accepted!=3) $fatal(1,"returned capacity did not admit held MMIO exactly once");
        $display("PASS: limited MMIO independent write-capacity sample");$finish;
    end
    initial begin #1000;$fatal(1,"MMIO capacity sample timeout");end
endmodule
