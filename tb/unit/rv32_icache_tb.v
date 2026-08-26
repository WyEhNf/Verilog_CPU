`timescale 1ns/1ps

module rv32_icache_tb;
    reg clk, reset;
    reg [3:0] current_epoch;
    reg req_valid;
    wire req_ready;
    reg [31:0] req_pc;
    reg [3:0] req_epoch;
    wire resp_valid;
    reg resp_ready;
    wire [31:0] resp_pc, resp_line_addr;
    wire [127:0] resp_line_data;
    wire [3:0] resp_epoch;
    wire resp_error;
    wire mem_req_valid, mem_req_ready;
    wire [31:0] mem_req_addr;
    wire [7:0] mem_req_id;
    wire mem_resp_valid, mem_resp_ready;
    wire [31:0] mem_resp_addr;
    wire [127:0] mem_resp_data;
    wire [7:0] mem_resp_id;
    wire mem_resp_error;
    wire event_request, event_hit, event_miss, event_refill, event_stall;
    integer cycle;
    integer accept_cycle [0:11];
    integer response_count;
    integer request_event_count;
    integer hit_event_count;
    integer miss_event_count;
    integer refill_event_count;
    integer stall_event_count;
    integer last_response_cycle;
    integer stream_slot;
    reg [31:0] held_pc;
    reg [31:0] held_line_addr;
    reg [127:0] held_data;
    reg [3:0] held_epoch;
    reg held_error;

    rv32_icache dut (
        .clk_i(clk), .reset_i(reset), .current_epoch_i(current_epoch),
        .if_req_valid_i(req_valid), .if_req_ready_o(req_ready),
        .if_req_pc_i(req_pc), .if_req_epoch_i(req_epoch),
        .if_resp_valid_o(resp_valid), .if_resp_ready_i(resp_ready),
        .if_resp_pc_o(resp_pc), .if_resp_line_addr_o(resp_line_addr),
        .if_resp_line_data_o(resp_line_data), .if_resp_epoch_o(resp_epoch),
        .if_resp_error_o(resp_error), .mem_req_valid_o(mem_req_valid),
        .mem_req_ready_i(mem_req_ready), .mem_req_line_addr_o(mem_req_addr),
        .mem_req_id_o(mem_req_id), .mem_resp_valid_i(mem_resp_valid),
        .mem_resp_ready_o(mem_resp_ready), .mem_resp_line_addr_i(mem_resp_addr),
        .mem_resp_data_i(mem_resp_data), .mem_resp_id_i(mem_resp_id),
        .mem_resp_error_i(mem_resp_error), .event_request_o(event_request),
        .event_hit_o(event_hit), .event_miss_o(event_miss),
        .event_refill_o(event_refill), .event_stall_o(event_stall)
    );

    rv32im_memory_model mem (
        .clk_i(clk), .reset_i(reset),
        .i_req_valid_i(mem_req_valid), .i_req_ready_o(mem_req_ready),
        .i_req_line_addr_i(mem_req_addr), .i_req_id_i(mem_req_id),
        .i_resp_valid_o(mem_resp_valid), .i_resp_ready_i(mem_resp_ready),
        .i_resp_line_addr_o(mem_resp_addr), .i_resp_data_o(mem_resp_data),
        .i_resp_id_o(mem_resp_id), .i_resp_error_o(mem_resp_error),
        .d_req_valid_i(1'b0), .d_req_ready_o(), .d_req_write_i(1'b0),
        .d_req_line_addr_i(32'd0), .d_req_wdata_i(128'd0),
        .d_req_wmask_i(16'd0), .d_req_id_i(8'd0), .d_resp_valid_o(),
        .d_resp_ready_i(1'b1), .d_resp_line_addr_o(), .d_resp_data_o(),
        .d_resp_id_o(), .d_resp_error_o()
    );

    initial begin clk = 1'b0; forever #5 clk = ~clk; end
    always @(posedge clk) begin
        cycle = cycle + 1;
        if (resp_valid && resp_ready)
            response_count = response_count + 1;
        if (event_request) request_event_count = request_event_count + 1;
        if (event_hit) hit_event_count = hit_event_count + 1;
        if (event_miss) miss_event_count = miss_event_count + 1;
        if (event_refill) refill_event_count = refill_event_count + 1;
        if (event_stall) stall_event_count = stall_event_count + 1;
    end

    task send_request;
        input [31:0] pc;
        input [3:0] epoch;
        input integer slot;
        begin
            @(negedge clk);
            req_valid = 1'b1;
            req_pc = pc;
            req_epoch = epoch;
            while (!req_ready) @(negedge clk);
            @(posedge clk);
            @(negedge clk);
            accept_cycle[slot] = cycle;
            req_valid = 1'b0;
        end
    endtask

    task wait_error_response;
        input [31:0] expected_pc;
        begin
            while (!resp_valid) @(negedge clk);
            if (resp_pc != expected_pc || !resp_error || resp_epoch != current_epoch) begin
                $display("FAIL: I-cache error response pc=%08x/%08x epoch=%0d/%0d error=%b cycle=%0d",
                         resp_pc, expected_pc, resp_epoch, current_epoch, resp_error, cycle);
                $finish(1);
            end
            @(negedge clk);
        end
    endtask

    task send_hit_stream;
        begin
            @(negedge clk);
            req_valid = 1'b1;
            req_pc = 32'h00000000;
            req_epoch = 4'd1;
            for (stream_slot = 1; stream_slot <= 3; stream_slot = stream_slot + 1) begin
                while (!req_ready) @(negedge clk);
                @(posedge clk);
                @(negedge clk);
                accept_cycle[stream_slot] = cycle;
                if (stream_slot != 3)
                    req_pc = req_pc + 32'd4;
                else
                    req_valid = 1'b0;
            end
        end
    endtask

    task wait_response;
        input [31:0] expected_pc;
        begin
            while (!resp_valid) @(negedge clk);
            if (resp_pc != expected_pc || resp_error || resp_epoch != current_epoch) begin
                $display("FAIL: I-cache response pc=%08x/%08x epoch=%0d/%0d error=%b cycle=%0d",
                         resp_pc, expected_pc, resp_epoch, current_epoch, resp_error, cycle);
                $finish(1);
            end
            last_response_cycle = cycle;
            @(negedge clk);
        end
    endtask

    initial begin
        cycle = 0;
        response_count = 0;
        request_event_count = 0;
        hit_event_count = 0;
        miss_event_count = 0;
        refill_event_count = 0;
        stall_event_count = 0;
        last_response_cycle = 0;
        reset = 1'b1;
        current_epoch = 4'd1;
        req_valid = 1'b0;
        req_pc = 32'd0;
        req_epoch = 4'd1;
        resp_ready = 1'b1;
        #1;
        mem.memory[0] = 8'h13; mem.memory[1] = 8'h00; mem.memory[2] = 8'h00; mem.memory[3] = 8'h00;
        mem.memory[4] = 8'h93; mem.memory[5] = 8'h00; mem.memory[6] = 8'h10; mem.memory[7] = 8'h00;
        mem.memory[8] = 8'h13; mem.memory[9] = 8'h01; mem.memory[10] = 8'h20; mem.memory[11] = 8'h00;
        mem.memory[12] = 8'h6f; mem.memory[13] = 8'h00; mem.memory[14] = 8'h00; mem.memory[15] = 8'h00;
        mem.memory[16'h0400] = 8'haa; mem.memory[16'h0401] = 8'hbb;
        repeat (3) @(posedge clk);
        if (req_ready !== 1'b0 || resp_valid !== 1'b0 || mem_req_valid !== 1'b0 ||
            event_request !== 1'b0 || event_hit !== 1'b0 || event_miss !== 1'b0 ||
            event_refill !== 1'b0 || event_stall !== 1'b0) begin
            $display("FAIL: I-cache reset outputs are not deterministic"); $finish(1);
        end
        @(negedge clk); reset = 1'b0;

        // Cold miss exercises the real 50-cycle memory model and line refill.
        send_request(32'h00000000, 4'd1, 0);
        @(negedge clk);
        req_valid = 1'b1;
        req_pc = 32'h00000004;
        req_epoch = 4'd1;
        repeat (3) begin
            @(negedge clk);
            if (req_ready) begin
                $display("FAIL: I-cache accepted a request while a miss was outstanding"); $finish(1);
            end
        end
        req_valid = 1'b0;
        wait_response(32'h00000000);
        if (resp_line_addr != 0 || resp_line_data[63:0] != 64'h0010009300000013) begin
            $display("FAIL: I-cache refill data/endianness %032x", resp_line_data); $finish(1);
        end

        // Warm requests must accept and respond on consecutive cycles at N+3.
        fork
            begin
                send_hit_stream();
            end
            begin
                wait_response(32'h00000000);
                if ((last_response_cycle - accept_cycle[1]) != 3) begin $display("FAIL: hit latency 0 was %0d", last_response_cycle-accept_cycle[1]); $finish(1); end
                wait_response(32'h00000004);
                if ((last_response_cycle - accept_cycle[2]) != 3) begin $display("FAIL: hit latency 1 was %0d", last_response_cycle-accept_cycle[2]); $finish(1); end
                wait_response(32'h00000008);
                if ((last_response_cycle - accept_cycle[3]) != 3) begin $display("FAIL: hit latency 2 was %0d", last_response_cycle-accept_cycle[3]); $finish(1); end
            end
        join

        // Response payload must remain stable under downstream backpressure.
        resp_ready = 1'b0;
        send_request(32'h0000000c, 4'd1, 4);
        while (!resp_valid) @(negedge clk);
        held_pc = resp_pc;
        held_line_addr = resp_line_addr;
        held_data = resp_line_data;
        held_epoch = resp_epoch;
        held_error = resp_error;
        repeat (4) begin
            @(negedge clk);
            if (!resp_valid || resp_pc != held_pc || resp_line_addr != held_line_addr ||
                resp_line_data != held_data || resp_epoch != held_epoch ||
                resp_error != held_error) begin
                $display("FAIL: I-cache response changed under backpressure"); $finish(1);
            end
        end
        resp_ready = 1'b1;
        @(negedge clk);

        // Redirect kills an old-epoch hit before it can become visible.
        send_request(32'h00000000, 4'd1, 5);
        @(negedge clk); current_epoch = 4'd2;
        repeat (5) begin
            @(negedge clk);
            if (resp_valid && resp_epoch == 4'd1) begin $display("FAIL: stale epoch hit escaped"); $finish(1); end
        end

        // A stale miss still refills the cache but must not produce a response.
        current_epoch = 4'd3;
        send_request(32'h00000400, 4'd3, 6);
        repeat (5) @(negedge clk);
        current_epoch = 4'd4;
        wait (mem_resp_valid);
        repeat (3) @(negedge clk);
        if (resp_valid && resp_epoch == 4'd3) begin $display("FAIL: stale miss response escaped"); $finish(1); end
        send_request(32'h00000400, 4'd4, 7);
        wait_response(32'h00000400);
        if ((last_response_cycle - accept_cycle[7]) != 3 || resp_line_data[15:0] != 16'hbbaa) begin
            $display("FAIL: stale refill was not retained as a warm line"); $finish(1);
        end

        // Address 0x400 aliases set zero, so fetching address zero again must miss and replace it.
        send_request(32'h00000000, 4'd4, 8);
        wait_response(32'h00000000);
        if (resp_line_addr != 0 || resp_line_data[31:0] != 32'h00000013) begin
            $display("FAIL: I-cache same-set conflict replacement"); $finish(1);
        end

        // An out-of-range memory response must be delivered as an error and never counted as a refill.
        send_request(32'h00100000, 4'd4, 9);
        wait_error_response(32'h00100000);

        if (response_count != 8) begin $display("FAIL: response balance %0d", response_count); $finish(1); end
        if (request_event_count != 10 || hit_event_count != 6 || miss_event_count != 4 ||
            refill_event_count != 3 || stall_event_count == 0) begin
            $display("FAIL: I-cache events request=%0d hit=%0d miss=%0d refill=%0d stall=%0d",
                     request_event_count, hit_event_count, miss_event_count,
                     refill_event_count, stall_event_count);
            $finish(1);
        end
        $display("PASS: A-03 I-cache latency, conflicts, errors, backpressure, and epoch filtering");
        $finish(0);
    end

    initial begin
        #10000;
        $display("FAIL: A-03 I-cache timeout cycle=%0d", cycle);
        $finish(1);
    end
endmodule
