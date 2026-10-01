`timescale 1ns/1ps
module rv32_axi_response_fifo_tb #(
    parameter integer DEPTH = 2,
    parameter integer SEED = 17
);
    localparam integer WIDTH = 169;
    reg clock = 0, reset = 1;
    always #5 clock = ~clock;
    reg in_valid = 0, out_ready = 0;
    reg [WIDTH-1:0] in_packet = 0;
    wire in_ready, out_valid;
    wire [WIDTH-1:0] out_packet;
    rv32_axi_response_fifo #(.WIDTH(WIDTH), .DEPTH(DEPTH)) dut (
        .clock(clock), .reset(reset), .in_valid(in_valid), .in_ready(in_ready),
        .in_packet(in_packet), .out_valid(out_valid), .out_ready(out_ready), .out_packet(out_packet));
    reg [WIDTH-1:0] expected [0:8191];
    integer head = 0, tail = 0, count = 0;
    integer pushes = 0, pops = 0, concurrent = 0, full_cycles = 0, stalls = 0, reset_pending = 0;
    reg held_valid = 0;
    reg [WIDTH-1:0] held_packet;
    always @(posedge clock) begin
        if (reset) begin
            if (count != 0) reset_pending = reset_pending + 1;
            head = 0; tail = 0; count = 0; held_valid = 0;
        end else begin
            if (in_ready !== (count < DEPTH) || out_valid !== (count != 0))
                $fatal(1, "FIFO occupancy/credit mismatch count=%0d", count);
            if (held_valid && (!out_valid || out_packet !== held_packet))
                $fatal(1, "FIFO changed a blocked output");
            if (count == DEPTH) full_cycles = full_cycles + 1;
            if (out_valid && !out_ready) stalls = stalls + 1;
            held_valid = out_valid && !out_ready;
            held_packet = out_packet;
            if (in_valid && in_ready && out_valid && out_ready) concurrent = concurrent + 1;
            // Observe the OLD head before recording a simultaneous enqueue.
            if (out_valid && out_ready) begin
                if (out_packet !== expected[head]) $fatal(1, "FIFO order/data mismatch");
                head = (head + 1) % 8192; count = count - 1; pops = pops + 1;
            end
            if (in_valid && in_ready) begin
                expected[tail] = in_packet;
                tail = (tail + 1) % 8192; count = count + 1; pushes = pushes + 1;
            end
            if (count < 0 || count > DEPTH) $fatal(1, "FIFO overflow/underflow");
        end
    end
    integer step, bit_index, random_state = SEED;
    reg prior_ready;
    task drive_packet;
        begin
            for (bit_index = 0; bit_index < WIDTH; bit_index = bit_index + 1)
                in_packet[bit_index] = $random(random_state) & 1;
        end
    endtask
    initial begin
        repeat (3) @(negedge clock); reset = 0;
        for (step = 0; step < 3000; step = step + 1) begin
            // Long blocked intervals fill the queue; long streaming intervals
            // exercise every head/tail wrap with simultaneous push and pop.
            out_ready = (step % 101 >= 23) && ((step % 3 == 0) || (step % 97 >= 41));
            in_valid = (step % 101 < 79) || (step % 97 >= 41);
            drive_packet;
            #1; prior_ready = in_ready;
            out_ready = !out_ready;
            #1; if (in_ready !== prior_ready) $fatal(1, "READY propagates into FIFO credit");
            out_ready = !out_ready;
            @(negedge clock);
            if (step == 1010 || step == 2020) begin
                // Fill, then discard pending responses by a genuine reset.
                in_valid = 1; out_ready = 0;
                repeat (DEPTH + 2) begin drive_packet; @(negedge clock); end
                reset = 1; in_valid = 0;
                repeat (2) @(negedge clock); reset = 0;
            end
        end
        in_valid = 0; out_ready = 1;
        repeat (DEPTH + 3) @(negedge clock);
        if (count != 0 || concurrent < 100 || full_cycles < 100 || stalls < 100 || reset_pending != 2)
            $fatal(1, "FIFO coverage incomplete count=%0d concurrent=%0d full=%0d stall=%0d resets=%0d",
                   count, concurrent, full_cycles, stalls, reset_pending);
        $display("PASS: response FIFO depth=%0d width=169 push=%0d pop=%0d concurrent=%0d full=%0d stall=%0d pending_resets=%0d",
                 DEPTH, pushes, pops, concurrent, full_cycles, stalls, reset_pending);
        $finish;
    end
    initial begin #1000000; $fatal(1, "response FIFO test timeout"); end
endmodule
