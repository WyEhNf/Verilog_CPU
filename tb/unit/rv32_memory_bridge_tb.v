`timescale 1ns/1ps

module rv32_memory_bridge_tb;
    reg clk, reset;
    reg i_req_valid, i_resp_ready;
    wire i_req_ready, i_resp_valid;
    reg [31:0] i_req_addr;
    reg [7:0] i_req_id;
    wire [31:0] i_resp_addr;
    wire [127:0] i_resp_data;
    wire [7:0] i_resp_id;
    wire i_resp_error;

    reg d_req_valid, d_req_write, d_resp_ready;
    wire d_req_ready, d_resp_valid;
    reg [31:0] d_req_addr;
    reg [127:0] d_req_wdata;
    reg [15:0] d_req_wmask;
    reg [7:0] d_req_id;
    wire [31:0] d_resp_addr;
    wire [127:0] d_resp_data;
    wire [7:0] d_resp_id;
    wire d_resp_error;

    wire mem_i_req_valid, mem_i_req_ready;
    wire [31:0] mem_i_req_addr;
    wire [7:0] mem_i_req_id;
    wire mem_i_resp_valid, mem_i_resp_ready;
    wire [31:0] mem_i_resp_addr;
    wire [127:0] mem_i_resp_data;
    wire [7:0] mem_i_resp_id;
    wire mem_i_resp_error;
    wire mem_d_req_valid, mem_d_req_ready, mem_d_req_write;
    wire [31:0] mem_d_req_addr;
    wire [127:0] mem_d_req_wdata;
    wire [15:0] mem_d_req_wmask;
    wire [7:0] mem_d_req_id;
    wire mem_d_resp_valid, mem_d_resp_ready;
    wire [31:0] mem_d_resp_addr;
    wire [127:0] mem_d_resp_data;
    wire [7:0] mem_d_resp_id;
    wire mem_d_resp_error;
    wire event_i_mem_request, event_d_mem_read, event_d_mem_write;

    integer cycle;
    integer i_mem_accept_cycle, d_mem_accept_cycle;
    integer i_first_resp_cycle, d_first_resp_cycle;
    integer i_mem_requests, d_mem_reads, d_mem_writes;
    integer bad;
    reg [31:0] held_addr;
    reg [127:0] held_data;
    reg [7:0] held_id;
    reg held_error;

    rv32_memory_bridge dut (
        .clk_i(clk), .reset_i(reset),
        .cache_i_req_valid_i(i_req_valid), .cache_i_req_ready_o(i_req_ready),
        .cache_i_req_line_addr_i(i_req_addr), .cache_i_req_id_i(i_req_id),
        .cache_i_resp_valid_o(i_resp_valid), .cache_i_resp_ready_i(i_resp_ready),
        .cache_i_resp_line_addr_o(i_resp_addr), .cache_i_resp_data_o(i_resp_data),
        .cache_i_resp_id_o(i_resp_id), .cache_i_resp_error_o(i_resp_error),
        .cache_d_req_valid_i(d_req_valid), .cache_d_req_ready_o(d_req_ready),
        .cache_d_req_write_i(d_req_write), .cache_d_req_line_addr_i(d_req_addr),
        .cache_d_req_wdata_i(d_req_wdata), .cache_d_req_wmask_i(d_req_wmask),
        .cache_d_req_id_i(d_req_id), .cache_d_resp_valid_o(d_resp_valid),
        .cache_d_resp_ready_i(d_resp_ready), .cache_d_resp_line_addr_o(d_resp_addr),
        .cache_d_resp_data_o(d_resp_data), .cache_d_resp_id_o(d_resp_id),
        .cache_d_resp_error_o(d_resp_error), .mem_i_req_valid_o(mem_i_req_valid),
        .mem_i_req_ready_i(mem_i_req_ready), .mem_i_req_line_addr_o(mem_i_req_addr),
        .mem_i_req_id_o(mem_i_req_id), .mem_i_resp_valid_i(mem_i_resp_valid),
        .mem_i_resp_ready_o(mem_i_resp_ready), .mem_i_resp_line_addr_i(mem_i_resp_addr),
        .mem_i_resp_data_i(mem_i_resp_data), .mem_i_resp_id_i(mem_i_resp_id),
        .mem_i_resp_error_i(mem_i_resp_error), .mem_d_req_valid_o(mem_d_req_valid),
        .mem_d_req_ready_i(mem_d_req_ready), .mem_d_req_write_o(mem_d_req_write),
        .mem_d_req_line_addr_o(mem_d_req_addr), .mem_d_req_wdata_o(mem_d_req_wdata),
        .mem_d_req_wmask_o(mem_d_req_wmask), .mem_d_req_id_o(mem_d_req_id),
        .mem_d_resp_valid_i(mem_d_resp_valid), .mem_d_resp_ready_o(mem_d_resp_ready),
        .mem_d_resp_line_addr_i(mem_d_resp_addr), .mem_d_resp_data_i(mem_d_resp_data),
        .mem_d_resp_id_i(mem_d_resp_id), .mem_d_resp_error_i(mem_d_resp_error),
        .event_i_mem_request_o(event_i_mem_request),
        .event_d_mem_read_o(event_d_mem_read), .event_d_mem_write_o(event_d_mem_write)
    );

    rv32im_memory_model mem (
        .clk_i(clk), .reset_i(reset),
        .i_req_valid_i(mem_i_req_valid), .i_req_ready_o(mem_i_req_ready),
        .i_req_line_addr_i(mem_i_req_addr), .i_req_id_i(mem_i_req_id),
        .i_resp_valid_o(mem_i_resp_valid), .i_resp_ready_i(mem_i_resp_ready),
        .i_resp_line_addr_o(mem_i_resp_addr), .i_resp_data_o(mem_i_resp_data),
        .i_resp_id_o(mem_i_resp_id), .i_resp_error_o(mem_i_resp_error),
        .d_req_valid_i(mem_d_req_valid), .d_req_ready_o(mem_d_req_ready),
        .d_req_write_i(mem_d_req_write), .d_req_line_addr_i(mem_d_req_addr),
        .d_req_wdata_i(mem_d_req_wdata), .d_req_wmask_i(mem_d_req_wmask),
        .d_req_id_i(mem_d_req_id), .d_resp_valid_o(mem_d_resp_valid),
        .d_resp_ready_i(mem_d_resp_ready), .d_resp_line_addr_o(mem_d_resp_addr),
        .d_resp_data_o(mem_d_resp_data), .d_resp_id_o(mem_d_resp_id),
        .d_resp_error_o(mem_d_resp_error)
    );

    initial begin clk = 1'b0; forever #5 clk = ~clk; end
    always @(posedge clk) begin
        cycle = cycle + 1;
        if (event_i_mem_request) begin
            i_mem_requests = i_mem_requests + 1;
            i_mem_accept_cycle = cycle;
        end
        if (event_d_mem_read) begin
            d_mem_reads = d_mem_reads + 1;
            d_mem_accept_cycle = cycle;
        end
        if (event_d_mem_write) begin
            d_mem_writes = d_mem_writes + 1;
            d_mem_accept_cycle = cycle;
        end
    end

    task issue_i;
        input [31:0] address;
        input [7:0] id;
        begin
            @(negedge clk);
            i_req_valid = 1'b1; i_req_addr = address; i_req_id = id;
            while (!i_req_ready) @(negedge clk);
            @(posedge clk); @(negedge clk);
            i_req_valid = 1'b0; i_req_addr = 32'hdeadbeef; i_req_id = 8'hee;
        end
    endtask

    task issue_d;
        input write_request;
        input [31:0] address;
        input [127:0] data;
        input [15:0] mask;
        input [7:0] id;
        begin
            @(negedge clk);
            d_req_valid = 1'b1; d_req_write = write_request; d_req_addr = address;
            d_req_wdata = data; d_req_wmask = mask; d_req_id = id;
            while (!d_req_ready) @(negedge clk);
            @(posedge clk); @(negedge clk);
            d_req_valid = 1'b0; d_req_write = 1'b0; d_req_addr = 32'hcafef00d;
            d_req_wdata = 128'hx; d_req_wmask = 16'hx; d_req_id = 8'hef;
        end
    endtask

    initial begin
        cycle = 0; i_mem_accept_cycle = -1; d_mem_accept_cycle = -1;
        i_first_resp_cycle = -1; d_first_resp_cycle = -1;
        i_mem_requests = 0; d_mem_reads = 0; d_mem_writes = 0; bad = 0;
        reset = 1'b1; i_req_valid = 1'b0; i_resp_ready = 1'b0;
        i_req_addr = 0; i_req_id = 0; d_req_valid = 1'b0; d_req_write = 1'b0;
        d_resp_ready = 1'b0; d_req_addr = 0; d_req_wdata = 0; d_req_wmask = 0; d_req_id = 0;
        #1;
        mem.memory[0] = 8'h13; mem.memory[1] = 8'h00; mem.memory[2] = 8'h00; mem.memory[3] = 8'h00;
        mem.memory[16'h0100] = 8'h11; mem.memory[16'h0101] = 8'h22;
        repeat (3) @(posedge clk);
        if (i_req_ready !== 1'b0 || d_req_ready !== 1'b0 || i_resp_valid !== 1'b0 ||
            d_resp_valid !== 1'b0 || event_i_mem_request !== 1'b0 ||
            event_d_mem_read !== 1'b0 || event_d_mem_write !== 1'b0) begin
            $display("FAIL: A-06 bridge reset outputs are not deterministic"); $finish(1);
        end
        @(negedge clk); reset = 1'b0;

        // Both channels must accept and complete independently through the real memory model.
        fork
            issue_i(32'h00000000, 8'h11);
            issue_d(1'b0, 32'h00000100, 128'd0, 16'd0, 8'h22);
        join
        fork
            begin
                while (!i_resp_valid) @(negedge clk);
                i_first_resp_cycle = cycle;
            end
            begin
                while (!d_resp_valid) @(negedge clk);
                d_first_resp_cycle = cycle;
            end
        join
        if (i_resp_addr != 0 || i_resp_id != 8'h11 || i_resp_data[31:0] != 32'h00000013 || i_resp_error) begin
            $display("FAIL: A-06 I response payload addr=%08x id=%02x data=%08x error=%b",
                     i_resp_addr, i_resp_id, i_resp_data[31:0], i_resp_error); bad = bad + 1;
        end
        if (d_resp_addr != 32'h100 || d_resp_id != 8'h22 || d_resp_data[15:0] != 16'h2211 || d_resp_error) begin
            $display("FAIL: A-06 D response payload addr=%08x id=%02x data=%04x error=%b",
                     d_resp_addr, d_resp_id, d_resp_data[15:0], d_resp_error); bad = bad + 1;
        end
        // The transparent bridge exposes the memory response during the
        // negedge observation window 49 completed clock intervals after the
        // accepting posedge; the memory model's posedge accounting remains
        // the architected 50-cycle latency checked by H-03.
        if ((i_first_resp_cycle - i_mem_accept_cycle) != 49 ||
            (d_first_resp_cycle - d_mem_accept_cycle) != 49) begin
            $display("FAIL: A-06 bridge changed memory latency i=%0d d=%0d",
                     i_first_resp_cycle-i_mem_accept_cycle,
                     d_first_resp_cycle-d_mem_accept_cycle); bad = bad + 1;
        end

        // Complete response payloads must remain stable while either cache is stalled.
        held_addr = i_resp_addr; held_data = i_resp_data; held_id = i_resp_id; held_error = i_resp_error;
        repeat (3) begin
            @(negedge clk);
            if (!i_resp_valid || i_resp_addr != held_addr || i_resp_data != held_data ||
                i_resp_id != held_id || i_resp_error != held_error) begin
                $display("FAIL: A-06 I response changed under backpressure"); bad = bad + 1;
            end
            if (!d_resp_valid || d_resp_addr != 32'h100 || d_resp_data[15:0] != 16'h2211 ||
                d_resp_id != 8'h22 || d_resp_error) begin
                $display("FAIL: A-06 D response changed under backpressure"); bad = bad + 1;
            end
        end
        i_resp_ready = 1'b1; d_resp_ready = 1'b1;
        @(posedge clk); @(negedge clk);

        // D writes retain the accepted byte mask/data even after the request wires change.
        issue_d(1'b1, 32'h00000020, 128'h000000000000000000000000aabbccdd, 16'h0005, 8'h33);
        while (!d_resp_valid) @(negedge clk);
        if (d_resp_addr != 32'h20 || d_resp_id != 8'h33 || d_resp_error) begin
            $display("FAIL: A-06 D write completion"); bad = bad + 1;
        end
        @(posedge clk); @(negedge clk);
        issue_d(1'b0, 32'h00000020, 128'd0, 16'd0, 8'h34);
        while (!d_resp_valid) @(negedge clk);
        if (d_resp_id != 8'h34 || d_resp_data[31:0] != 32'h00bb00dd || d_resp_error) begin
            $display("FAIL: A-06 D write mask/endianness data=%08x id=%02x error=%b",
                     d_resp_data[31:0], d_resp_id, d_resp_error); bad = bad + 1;
        end
        @(posedge clk); @(negedge clk);

        // Invalid lines complete locally with the original ID and no memory handshake.
        fork
            issue_i(32'h00000003, 8'h55);
            issue_d(1'b0, 32'h00100000, 128'd0, 16'd0, 8'h66);
        join
        while (!i_resp_valid || !d_resp_valid) @(negedge clk);
        if (!i_resp_error || i_resp_addr != 32'h3 || i_resp_id != 8'h55 || i_resp_data != 0) begin
            $display("FAIL: A-06 local I error response"); bad = bad + 1;
        end
        if (!d_resp_error || d_resp_addr != 32'h00100000 || d_resp_id != 8'h66 || d_resp_data != 0) begin
            $display("FAIL: A-06 local D error response"); bad = bad + 1;
        end
        if (i_mem_requests != 1 || d_mem_reads != 2 || d_mem_writes != 1) begin
            $display("FAIL: A-06 bridge handshake events I=%0d Dr=%0d Dw=%0d",
                     i_mem_requests, d_mem_reads, d_mem_writes); bad = bad + 1;
        end

        if (bad != 0) begin $display("FAIL: A-06 memory bridge checks=%0d", bad); $finish(1); end
        $display("PASS: A-06 memory bridge concurrency, payload hold, masks, IDs, and errors");
        $finish(0);
    end

    initial begin
        #20000;
        $display("FAIL: A-06 memory bridge timeout cycle=%0d", cycle);
        $finish(1);
    end
endmodule
