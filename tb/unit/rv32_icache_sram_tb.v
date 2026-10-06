`timescale 1ns/1ps
// Four-state SRAM timing, backpressure, refill arbitration and stale epochs.
module rv32_icache_sram_tb;
    parameter integer LINES = 16, WAYS = 2;
    reg clk = 0, reset = 1;
    always #5 clk = ~clk;
    reg [1:0] epoch = 0, req_epoch = 0;
    reg req_valid = 0, resp_ready = 0;
    reg [31:0] req_pc = 0;
    wire req_ready, resp_valid, resp_error, mem_valid, mem_ready;
    wire [31:0] resp_pc, resp_addr, mem_addr;
    wire [127:0] resp_data;
    wire [1:0] resp_epoch;
    wire [7:0] mem_id;
    reg reply_valid = 0, reply_error = 0;
    reg [31:0] reply_addr = 0;
    reg [127:0] reply_data = 0;
    reg [7:0] reply_id = 0;
    reg [31:0] pending_addr [0:127];
    reg [7:0] pending_id [0:127];
    reg pending_used [0:127];
    integer issued = 0, accepted = 0, step = 0, n, slot;
    reg [7:0] stale_id;
    reg [127:0] a = 128'h0102031304050613070809130a0b0c13;
    reg [127:0] b = 128'h1112131314151613171819131a1b1c13;
    reg [127:0] c = 128'h2122231324252613272829132a2b2c13;
    rv32_icache_nonblocking #(.EPOCH_WIDTH(2), .MSHR_ENTRIES(4),
        .CACHE_LINES(LINES), .CACHE_WAYS(WAYS), .PREFETCH_DISTANCE(1)) dut (
        .clk_i(clk), .reset_i(reset), .current_epoch_i(epoch),
        .if_req_valid_i(req_valid), .if_req_ready_o(req_ready),
        .if_req_pc_i(req_pc), .if_req_epoch_i(req_epoch),
        .if_resp_valid_o(resp_valid), .if_resp_ready_i(resp_ready),
        .if_resp_pc_o(resp_pc), .if_resp_line_addr_o(resp_addr),
        .if_resp_line_data_o(resp_data), .if_resp_epoch_o(resp_epoch),
        .if_resp_error_o(resp_error), .mem_req_valid_o(mem_valid),
        .mem_req_ready_i(1'b1), .mem_req_line_addr_o(mem_addr),
        .mem_req_id_o(mem_id), .mem_resp_valid_i(reply_valid),
        .mem_resp_ready_o(mem_ready), .mem_resp_line_addr_i(reply_addr),
        .mem_resp_data_i(reply_data), .mem_resp_id_i(reply_id),
        .mem_resp_error_i(reply_error)
    );
    always @(posedge clk) begin
        if (!reset && mem_valid) begin
            if (issued >= 128) $fatal(1, "too many test requests");
            pending_addr[issued] = mem_addr;
            pending_id[issued] = mem_id;
            pending_used[issued] = 0;
            issued = issued + 1;
        end
        if (!reset && req_valid && req_ready) accepted = accepted + 1;
    end
    initial begin #100000; $fatal(1, "icache SRAM timeout step=%0d", step); end
    task submit;
        input [31:0] pc;
        begin
            @(negedge clk); req_pc = pc; req_epoch = epoch; req_valid = 1;
            #1; while (!req_ready) begin @(negedge clk); #1; end
            @(negedge clk); req_valid = 0;
        end
    endtask
    task expect_response;
        input [31:0] pc;
        input [127:0] data;
        input error;
        begin
            #1;
            if (resp_valid !== 1 || resp_pc !== pc || resp_addr !== {pc[31:4],4'b0} ||
                resp_data !== data || resp_epoch !== epoch || resp_error !== error)
                $fatal(1, "response mismatch step=%0d pc=%h actual=%h valid=%b data=%h", step, pc, resp_pc, resp_valid, resp_data);
        end
    endtask
    task consume;
        begin @(negedge clk); resp_ready = 1; @(negedge clk); resp_ready = 0; end
    endtask
    task find_pending;
        input [31:0] address;
        begin
            slot = -1;
            for (n = 0; n < issued; n = n + 1)
                if (!pending_used[n] && pending_addr[n] == address) slot = n;
            while (slot < 0) begin
                @(negedge clk);
                for (n = 0; n < issued; n = n + 1)
                    if (!pending_used[n] && pending_addr[n] == address) slot = n;
            end
        end
    endtask
    task return_line;
        input [31:0] address;
        input [127:0] data;
        input error;
        begin
            find_pending(address);
            @(negedge clk);
            reply_addr = address; reply_id = pending_id[slot]; pending_used[slot] = 1;
            reply_data = data; reply_error = error; reply_valid = 1;
            #1; while (!mem_ready) begin @(negedge clk); #1; end
            @(negedge clk); reply_valid = 0; reply_error = 0;
        end
    endtask
    initial begin
        repeat (3) @(negedge clk); reset = 0;
        step = 1; submit(0); return_line(0, a, 0); expect_response(0, a, 0); consume;
        // A synchronous hit must still produce the full line in one cycle.
        step = 2; submit(4); expect_response(4, a, 0);
        repeat (3) begin @(negedge clk); expect_response(4, a, 0); end
        // A refill writes the same 1RW macro while the old hit is held.
        step = 3; return_line(16, b, 0); expect_response(4, a, 0);
        repeat (3) begin @(negedge clk); expect_response(4, a, 0); end
        consume;
        // Continuous hits must not insert a read pipeline bubble.
        step = 4; @(negedge clk); req_pc = 0; req_epoch = epoch; req_valid = 1; resp_ready = 1;
        #1; if (req_ready !== 1) $fatal(1, "first streaming hit not ready");
        @(negedge clk); expect_response(0, a, 0); req_pc = 16;
        #1; if (req_ready !== 1) $fatal(1, "second streaming hit not ready");
        @(negedge clk); expect_response(16, b, 0); req_valid = 0;
        @(negedge clk); resp_ready = 0;
        // Demand 16 seeds a clean prefetch 32. A returning prefetch must block
        // a new data-array hit for exactly its write edge, not steal its data.
        step = 5; find_pending(32); @(negedge clk);
        reply_addr = 32; reply_data = c; reply_id = pending_id[slot]; pending_used[slot] = 1;
        reply_valid = 1; req_pc = 0; req_epoch = epoch; req_valid = 1;
        #1;
        if (mem_ready !== 1 || req_ready !== 0) $fatal(1, "refill did not own single data port");
        @(negedge clk); reply_valid = 0;
        #1; if (req_ready !== 1) $fatal(1, "hit not resumed after refill");
        @(negedge clk); req_valid = 0; expect_response(0, a, 0); consume;
        step = 6; submit(32); expect_response(32, c, 0); consume;
        // A reset masks stale SRAM contents without clearing the macro.
        step = 7; @(negedge clk); reset = 1; @(negedge clk); reset = 0;
        #1; if (resp_valid !== 0) $fatal(1, "warm reset exposed stale output");
        submit(0); #1; if (resp_valid !== 0) $fatal(1, "warm-reset tag remained valid");
        return_line(0, b, 0); expect_response(0, b, 0); consume;
        // Old epoch prefetch may return after redirect; consume/drop it, and
        // never surface its payload as an instruction response.
        step = 8; find_pending(16); stale_id = pending_id[slot]; pending_used[slot] = 1;
        @(negedge clk); epoch = 1; req_epoch = 1;
        reply_valid = 1; reply_addr = 16; reply_data = a; reply_id = stale_id;
        #1; if (mem_ready !== 1) $fatal(1, "stale reply blocked memory");
        @(negedge clk); reply_valid = 0;
        #1; if (resp_valid !== 0) $fatal(1, "stale reply became demand output");
        step = 9; submit(16); return_line(16, c, 1); expect_response(16, c, 1); consume;
        // Failed refills do not install valid tags/data.
        step = 10; submit(16); #1; if (resp_valid !== 0) $fatal(1, "error refill was cached");
        return_line(16, a, 0); expect_response(16, a, 0); consume;
        $display("PASS: icache SRAM lines=%0d ways=%0d hit/hold/refill/epoch/reset/error", LINES, WAYS);
        $finish;
    end
endmodule
