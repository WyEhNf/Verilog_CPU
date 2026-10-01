`timescale 1ns/1ps
module rv32_asap7_fanout_fixture #(
    parameter integer ENABLED = 0,
    parameter integer LEAVES = 16,
    parameter integer SINKS = 1024
) (
    input wire clock,
    input wire reset,
    input wire control_i,
    input wire [SINKS-1:0] data_i,
    output reg [SINKS-1:0] data_o
);
    reg control_q;
    always @(posedge clock)
        if (reset) control_q <= 1'b0;
        else control_q <= control_i;
    wire [LEAVES-1:0] control_replicas;
    rv32_asap7_fanout #(.WIDTH(1), .LEAVES(LEAVES), .ENABLED(ENABLED)) tree(
        .signal_i(control_q), .replicas_o(control_replicas));
    genvar bit_id;
    generate
        for (bit_id = 0; bit_id < SINKS; bit_id = bit_id + 1) begin : g_sink
            always @(posedge clock)
                if (reset) data_o[bit_id] <= 1'b0;
                else if (control_replicas[(bit_id*LEAVES)/SINKS])
                    data_o[bit_id] <= data_i[bit_id];
        end
    endgenerate
endmodule

`ifndef SYNTHESIS
module rv32_asap7_fanout_tb;
    reg clock = 0;
    always #5 clock = ~clock;
    reg reset = 1;
    reg control = 0;
    reg [1023:0] data = 0;
    wire [1023:0] normal, buffered;
    rv32_asap7_fanout_fixture #(.ENABLED(0)) reference(
        .clock(clock), .reset(reset), .control_i(control), .data_i(data), .data_o(normal));
    rv32_asap7_fanout_fixture #(.ENABLED(1)) candidate(
        .clock(clock), .reset(reset), .control_i(control), .data_i(data), .data_o(buffered));
    integer cycle, word;
    initial begin
        repeat (2) @(negedge clock);
        for (cycle = 0; cycle < 1000; cycle = cycle + 1) begin
            reset = (cycle == 237 || cycle == 599);
            control = $random;
            for (word = 0; word < 32; word = word + 1)
                data[word*32 +: 32] = $random;
            @(negedge clock);
            if (normal !== buffered)
                $fatal(1, "fanout tree changed a synchronous result at cycle %0d", cycle);
        end
        $display("PASS: physical fanout-tree functional identity, 1000 cycles");
        $finish;
    end
    initial begin
        #20000;
        $fatal(1, "fanout fixture timeout");
    end
endmodule
`endif
