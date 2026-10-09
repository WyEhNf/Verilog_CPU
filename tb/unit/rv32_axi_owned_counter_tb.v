`timescale 1ns/1ps
module rv32_axi_owned_counter_tb #(
    parameter integer RESPONSE_FIFO_DEPTH = 2,
    parameter integer READ_LINES = 8,
    parameter integer WRITE_LINES = 4,
    parameter integer WORD_QUEUE = 16
);
    reg clock = 0, reset = 1;
    always #5 clock = ~clock;
    reg iv = 0, dv = 0, dw = 0;
    reg [31:0] ia = 0, da = 0;
    reg [7:0] iid = 0, did = 0;
    reg [127:0] dd = 0;
    reg [15:0] dm = 0;
    wire ir, dr, ov, oe, dsv, dse;
    wire [31:0] oa, dsa, araddr, awaddr, wdata;
    wire [127:0] od, dsd;
    wire [7:0] oid, dsid;
    wire [3:0] wstrb;
    wire arvalid, arready, rvalid, rready, awvalid, awready, wvalid, wready, bvalid, bready;
    wire [31:0] rdata;
    wire [1:0] rresp, bresp;
    integer cycle = 0, i_received = 0, d_reads_received = 0, d_writes_received = 0;
    wire ore = d_reads_received >= 2 && cycle % 7 != 0;
    wire dsr = cycle % 6 != 0;
    rv32_axi_lite_bridge #(.READ_LINES(READ_LINES), .WRITE_LINES(WRITE_LINES),
        .WORD_QUEUE(WORD_QUEUE), .READ_PAYLOAD_SRAM(1), .READ_COUNTERS_OWNED(0), .RESPONSE_FIFO_DEPTH(RESPONSE_FIFO_DEPTH)) dut (
        .clock(clock), .reset(reset), .i_req_valid(iv), .i_req_ready(ir), .i_req_addr(ia), .i_req_id(iid),
        .i_resp_valid(ov), .i_resp_ready(ore), .i_resp_addr(oa), .i_resp_data(od), .i_resp_id(oid), .i_resp_error(oe),
        .d_req_valid(dv), .d_req_ready(dr), .d_req_write(dw), .d_req_addr(da), .d_req_data(dd),
        .d_req_mask(dm), .d_req_id(did), .d_resp_valid(dsv), .d_resp_ready(dsr),
        .d_resp_addr(dsa), .d_resp_data(dsd), .d_resp_id(dsid), .d_resp_error(dse),
        .araddr(araddr), .arvalid(arvalid), .arready(arready), .rdata(rdata), .rresp(rresp),
        .rvalid(rvalid), .rready(rready), .awaddr(awaddr), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wvalid(wvalid), .wready(wready),
        .bresp(bresp), .bvalid(bvalid), .bready(bready)
    );
    wire ir_owned,dr_owned,ov_owned,oe_owned,dsv_owned,dse_owned;
    wire [31:0] oa_owned,dsa_owned,araddr_owned,awaddr_owned,wdata_owned;
    wire [127:0] od_owned,dsd_owned;
    wire [7:0] oid_owned,dsid_owned;
    wire [3:0] wstrb_owned;
    wire arvalid_owned,rready_owned,awvalid_owned,wvalid_owned,bready_owned;
    reg [READ_LINES-1:0] ever_allocated=0;
    integer reuse_events=0;
    always @(posedge clock) if(!reset && dut.read_allocate) begin
        if(ever_allocated[dut.read_free]) reuse_events<=reuse_events+1;
        ever_allocated[dut.read_free]<=1;
    end
    always @(negedge clock) if(!reset) begin
        assert({ir,dr,ov,dsv,arvalid,rready,awvalid,wvalid,bready}==
            {ir_owned,dr_owned,ov_owned,dsv_owned,arvalid_owned,rready_owned,awvalid_owned,wvalid_owned,bready_owned})
            else $fatal(1,"Owned AXI counters changed a public handshake/cycle");
        if(ov) assert({oa,od,oid,oe}=={oa_owned,od_owned,oid_owned,oe_owned});
        if(dsv) assert({dsa,dsd,dsid,dse}=={dsa_owned,dsd_owned,dsid_owned,dse_owned});
        if(arvalid) assert(araddr==araddr_owned);
        if(awvalid) assert(awaddr==awaddr_owned);
        if(wvalid) assert({wdata,wstrb}=={wdata_owned,wstrb_owned});
        assert(dut.read_valid==owned_dut.read_valid)
            else $fatal(1,"Owned AXI counters changed row lifecycle");
        for(integer row=0;row<READ_LINES;row=row+1) if(dut.read_valid[row])
            assert({dut.read_sent[row],dut.read_received[row],dut.read_error[row]}==
                {owned_dut.read_sent[row],owned_dut.read_received[row],owned_dut.read_error[row]})
                else $fatal(1,"Owned AXI counters changed valid-row complete state");
    end
    rv32_axi_lite_bridge #(.READ_LINES(READ_LINES), .WRITE_LINES(WRITE_LINES),
        .WORD_QUEUE(WORD_QUEUE), .READ_PAYLOAD_SRAM(1), .READ_COUNTERS_OWNED(1), .RESPONSE_FIFO_DEPTH(RESPONSE_FIFO_DEPTH)) owned_dut (
        .clock(clock), .reset(reset), .i_req_valid(iv), .i_req_ready(ir_owned), .i_req_addr(ia), .i_req_id(iid),
        .i_resp_valid(ov_owned), .i_resp_ready(ore), .i_resp_addr(oa_owned), .i_resp_data(od_owned), .i_resp_id(oid_owned), .i_resp_error(oe_owned),
        .d_req_valid(dv), .d_req_ready(dr_owned), .d_req_write(dw), .d_req_addr(da), .d_req_data(dd),
        .d_req_mask(dm), .d_req_id(did), .d_resp_valid(dsv_owned), .d_resp_ready(dsr),
        .d_resp_addr(dsa_owned), .d_resp_data(dsd_owned), .d_resp_id(dsid_owned), .d_resp_error(dse_owned),
        .araddr(araddr_owned), .arvalid(arvalid_owned), .arready(arready), .rdata(rdata), .rresp(rresp),
        .rvalid(rvalid), .rready(rready_owned), .awaddr(awaddr_owned), .awvalid(awvalid_owned), .awready(awready),
        .wdata(wdata_owned), .wstrb(wstrb_owned), .wvalid(wvalid_owned), .wready(wready),
        .bresp(bresp), .bvalid(bvalid), .bready(bready_owned)
    );
    // The slave follows the course queue/service discipline: a newly accepted
    // address cannot be serviced on that edge; words return 20 cycles later.
    // Deliberately stagger READY to exercise AW-first and W-first handshakes.
    reg [31:0] aq [0:255], awq [0:255], wdq [0:255], rdq [0:255];
    reg [3:0] wsq [0:255];
    reg [1:0] rsq [0:255], bsq [0:255];
    integer due_r [0:255], due_b [0:255];
    integer ah=0, at=0, ac=0, wh=0, wt=0, wc=0, dh=0, dt=0, dc=0;
    integer rh=0, rt=0, rc=0, bh=0, bt=0, bc=0;
    integer read_words=0, write_words=0, exit_words=0, aw_first=0, w_first=0;
    wire service_read = ac != 0 && rc < 16;
    wire service_write = wc != 0 && dc != 0 && bc < 16;
    assign arready = !reset && ac < 16 && cycle % 5 != 0;
    assign awready = !reset && wc < 16 && cycle % 3 != 0;
    assign wready = !reset && dc < 16 && cycle % 4 != 0;
    assign rvalid = !reset && rc != 0 && due_r[rh] <= cycle;
    assign rdata = rc != 0 ? rdq[rh] : 0;
    assign rresp = rc != 0 ? rsq[rh] : 0;
    assign bvalid = !reset && bc != 0 && due_b[bh] <= cycle;
    assign bresp = bc != 0 ? bsq[bh] : 0;
    function [127:0] expected_line;
        input [31:0] address;
        begin
            expected_line = {((address+32'd12)^32'h10203040), ((address+32'd8)^32'h10203040),
                             ((address+32'd4)^32'h10203040), (address^32'h10203040)};
        end
    endfunction
    always @(posedge clock) begin
        if (!reset) begin
            cycle <= cycle + 1;
            if (arvalid && arready) begin
                if (araddr[1:0] != 0) $fatal(1, "unaligned AR");
                aq[at] <= araddr; at <= at+1;
            end
            if (service_read) begin
                rdq[rt] <= aq[ah] ^ 32'h10203040;
                rsq[rt] <= aq[ah][9:8] == 2 ? 2 : 0;
                due_r[rt] <= cycle + 20;
                ah <= ah+1; rt <= rt+1; read_words <= read_words+1;
            end
            if (rvalid && rready) rh <= rh+1;
            case ({arvalid && arready, service_read}) 2'b10: ac<=ac+1; 2'b01: ac<=ac-1; endcase
            case ({service_read, rvalid && rready}) 2'b10: rc<=rc+1; 2'b01: rc<=rc-1; endcase
            if (awvalid && awready) begin awq[wt] <= awaddr; wt <= wt+1; end
            if (wvalid && wready) begin wdq[dt] <= wdata; wsq[dt] <= wstrb; dt <= dt+1; end
            if (awvalid && awready && !(wvalid && wready)) aw_first <= aw_first+1;
            if (wvalid && wready && !(awvalid && awready)) w_first <= w_first+1;
            if (service_write) begin
                if (awq[wh][1:0] != 0) $fatal(1, "unaligned AW");
                if (awq[wh] == 32'h80000000) begin
                    if (wsq[dh] !== 4'hf || wdq[dh] !== 32'h1234cdef) $fatal(1, "MMIO full word corrupted");
                    exit_words <= exit_words+1;
                end else begin
                    if (wdq[dh] !== 32'hcafebabe) $fatal(1, "AW/W pairing or data corruption");
                    if (awq[wh][31:4] == 28'h34) begin
                        case (awq[wh][3:2])
                            0: if (wsq[dh] !== 1) $fatal(1, "word0 byte mask");
                            1: $fatal(1, "zero-mask word issued on AXI");
                            2: if (wsq[dh] !== 12) $fatal(1, "word2 byte mask");
                            3: if (wsq[dh] !== 8) $fatal(1, "word3 byte mask");
                        endcase
                    end else if (wsq[dh] !== 4'hf) $fatal(1, "writeback byte mask corrupted");
                end
                bsq[bt] <= awq[wh][31:8] == 3 ? 2 : 0;
                due_b[bt] <= cycle + 20;
                wh <= wh+1; dh <= dh+1; bt <= bt+1; write_words <= write_words+1;
            end
            if (bvalid && bready) bh <= bh+1;
            case ({awvalid && awready, service_write}) 2'b10: wc<=wc+1; 2'b01: wc<=wc-1; endcase
            case ({wvalid && wready, service_write}) 2'b10: dc<=dc+1; 2'b01: dc<=dc-1; endcase
            case ({service_write, bvalid && bready}) 2'b10: bc<=bc+1; 2'b01: bc<=bc-1; endcase
        end
    end
    reg [255:0] pending = 0, was_store = 0;
    reg [31:0] expected_addr [0:255];
    reg [31:0] held_ar, held_aw, held_wd;
    reg [3:0] held_ws;
    reg ar_stall=0, aw_stall=0, w_stall=0, i_stall=0, d_stall=0;
    reg [168:0] held_i, held_d;
    always @(posedge clock) begin
        if (!reset) begin
            if (iv && ir) begin pending[iid] <= 1; was_store[iid] <= 0; expected_addr[iid] <= ia; end
            if (dv && dr) begin pending[did] <= 1; was_store[did] <= dw; expected_addr[did] <= da; end
            if (ar_stall && (!arvalid || araddr !== held_ar)) $fatal(1, "AR payload/valid changed under stall");
            if (aw_stall && (!awvalid || awaddr !== held_aw)) $fatal(1, "AW payload/valid changed under stall");
            if (w_stall && (!wvalid || wdata !== held_wd || wstrb !== held_ws)) $fatal(1, "W payload/valid changed under stall");
            if (i_stall && (!ov || {oa,oid,oe,od} !== held_i)) $fatal(1, "I response changed under stall");
            if (d_stall && (!dsv || {dsa,dsid,dse,dsd} !== held_d)) $fatal(1, "D response changed under stall");
            ar_stall <= arvalid && !arready; held_ar <= araddr;
            aw_stall <= awvalid && !awready; held_aw <= awaddr;
            w_stall <= wvalid && !wready; held_wd <= wdata; held_ws <= wstrb;
            i_stall <= ov && !ore; held_i <= {oa,oid,oe,od};
            d_stall <= dsv && !dsr; held_d <= {dsa,dsid,dse,dsd};
            if (ov && ore) begin
                if (!pending[oid] || was_store[oid] || oa !== expected_addr[oid] || oe || od !== expected_line(oa))
                    $fatal(1, "I line assembly/id mismatch");
                pending[oid] <= 0; i_received <= i_received+1;
            end
            if (dsv && dsr) begin
                if (!pending[dsid] || dsa !== expected_addr[dsid]) $fatal(1, "D response address/id mismatch");
                if (was_store[dsid]) begin
                    if (dse !== (dsa[31:8] == 3)) $fatal(1, "B errors not aggregated");
                    d_writes_received <= d_writes_received+1;
                end else begin
                    if (dsd !== expected_line(dsa) || dse !== (dsa[9:8] == 2)) $fatal(1, "R data/errors not assembled");
                    d_reads_received <= d_reads_received+1;
                end
                pending[dsid] <= 0;
            end
            if (dut.rq_count > WORD_QUEUE || dut.wq_count > WORD_QUEUE) $fatal(1, "word FIFO overflow");
        end
    end
    task send_i;
        input [31:0] address; input [7:0] id;
        begin
            @(negedge clock); ia=address; iid=id; iv=1; #1;
            while (!ir) begin @(negedge clock); #1; end
            @(negedge clock); iv=0;
        end
    endtask
    task send_d;
        input [31:0] address; input [7:0] id; input store; input [15:0] mask;
        begin
            @(negedge clock); da=address; did=id; dv=1; dw=store; dm=mask;
            dd = address == 32'h80000000 ? 128'h1234cdef : {4{32'hcafebabe}};
            #1; while (!dr) begin @(negedge clock); #1; end
            @(negedge clock); dv=0;
        end
    endtask
    integer n;
    initial begin
        #200000; $fatal(1, "AXI timeout I=%0d Dread=%0d Dwrite=%0d", i_received, d_reads_received, d_writes_received);
    end
    initial begin
        repeat (3) @(negedge clock); reset=0;
        fork
            begin for (n=0; n<8; n=n+1) send_i(n*16, n+1); end
            begin
                send_d(32'h100, 8'h40, 0, 0); send_d(32'h110, 8'h41, 0, 0);
                send_d(32'h200, 8'h42, 0, 0); send_d(32'h210, 8'h43, 0, 0);
                send_d(32'h280, 8'h80, 1, 16'hffff); send_d(32'h290, 8'h81, 1, 16'hffff);
                send_d(32'h300, 8'h82, 1, 16'hffff); send_d(32'h310, 8'h83, 1, 16'hffff);
                send_d(32'h340, 8'h84, 1, 16'h8c01); send_d(32'h80000000, 8'hfe, 1, 16'h000f);
            end
        join
        while (i_received != 8 || d_reads_received != 4 || d_writes_received != 6) @(negedge clock);
        repeat (5) @(negedge clock);
        if (pending != 0 || read_words != 48 || write_words != 20 || exit_words != 1 || aw_first == 0 || w_first == 0)
            $fatal(1, "AXI accounting pending=%h read=%0d write=%0d exit=%0d", pending, read_words, write_words, exit_words);
        if(reuse_events==0) $fatal(1,"AXI owned-counter row reuse absent");
        $display("PASS: limited paired AXI owned-counter sample reuse=%0d",reuse_events);
        $finish;
    end
endmodule
