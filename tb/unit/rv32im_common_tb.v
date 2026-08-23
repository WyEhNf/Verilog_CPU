`timescale 1ns/1ps

module rv32im_common_tb #(
    parameter integer LANES = 1
);
    localparam integer COUNT_WIDTH = (LANES <= 1) ? 1 : $clog2(LANES + 1);
    localparam integer DEPTH = 8;
    reg clk;
    reg reset;
    reg flush;
    reg [LANES-1:0] push_valid;
    reg [COUNT_WIDTH-1:0] push_count;
    reg [(LANES*8)-1:0] push_payload;
    wire push_ready;
    reg pop_ready;
    wire pop_valid;
    wire [COUNT_WIDTH-1:0] pop_count;
    wire [(LANES*8)-1:0] pop_payload;
    reg [($clog2(DEPTH + 1))-1:0] flush_count;
    wire [($clog2(DEPTH + 1))-1:0] occupancy;
    wire [($clog2(DEPTH + 1))-1:0] free_count;
    reg [LANES-1:0] prefix_grant;
    reg [COUNT_WIDTH-1:0] prefix_count;
    reg [LANES-1:0] prefix_valid;
    reg [COUNT_WIDTH-1:0] prefix_capacity;
    wire [LANES-1:0] alloc_grant;
    wire [COUNT_WIDTH-1:0] alloc_count;
    wire select_valid;
    wire [((LANES <= 2) ? 1 : $clog2(LANES))-1:0] select_index;
    wire [LANES-1:0] select_onehot;
    reg skid_in_valid;
    wire skid_in_ready;
    reg [7:0] skid_in_payload;
    wire skid_out_valid;
    reg skid_out_ready;
    wire [7:0] skid_out_payload;
    integer expected;

    rv32im_fifo #(.WIDTH(8), .DEPTH(DEPTH), .LANES(LANES)) fifo (
        .clk_i(clk), .reset_i(reset), .flush_i(flush),
        .push_valid_i(push_valid), .push_count_i(push_count), .push_payload_i(push_payload), .push_ready_o(push_ready),
        .pop_ready_i(pop_ready), .pop_valid_o(pop_valid), .pop_count_o(pop_count), .pop_payload_o(pop_payload),
        .flush_count_i(flush_count), .occupancy_o(occupancy), .free_count_o(free_count)
    );
    rv32im_prefix_alloc #(.LANES(LANES)) alloc (
        .valid_i(prefix_valid), .capacity_i(prefix_capacity), .grant_o(alloc_grant), .count_o(alloc_count)
    );
    rv32im_priority_select #(.WIDTH(LANES)) select (
        .valid_i(prefix_valid), .grant_valid_o(select_valid), .grant_index_o(select_index), .grant_onehot_o(select_onehot)
    );
    rv32im_skid_buffer #(.WIDTH(8)) skid (
        .clk_i(clk), .reset_i(reset), .flush_i(flush), .in_valid_i(skid_in_valid), .in_ready_o(skid_in_ready),
        .in_payload_i(skid_in_payload), .out_valid_o(skid_out_valid), .out_ready_i(skid_out_ready), .out_payload_o(skid_out_payload)
    );

    initial begin clk = 1'b0; forever #5 clk = ~clk; end

    task push_one;
        input integer base;
        integer j;
        begin
            @(negedge clk);
            push_valid = {LANES{1'b1}};
            push_count = LANES;
            for (j = 0; j < LANES; j = j + 1)
                push_payload[(j*8) +: 8] = base + j;
            while (!push_ready) @(negedge clk);
            @(negedge clk);
            push_valid = {LANES{1'b0}};
            push_count = {COUNT_WIDTH{1'b0}};
        end
    endtask

    initial begin
        reset = 1'b1;
        flush = 1'b0;
        push_valid = {LANES{1'b0}};
        push_count = {COUNT_WIDTH{1'b0}};
        push_payload = {(LANES*8){1'b0}};
        pop_ready = 1'b0;
        flush_count = 0;
        prefix_valid = {LANES{1'b0}};
        prefix_capacity = LANES;
        skid_in_valid = 1'b0;
        skid_in_payload = 0;
        skid_out_ready = 1'b0;
        expected = 0;
        #12;
        reset = 1'b0;

        prefix_valid = {LANES{1'b1}};
        prefix_capacity = (LANES < 2) ? LANES : 2;
        #1;
        if (alloc_count != prefix_capacity || alloc_grant != ((1 << prefix_capacity) - 1)) begin
            $display("FAIL: contiguous prefix allocator"); $finish(1);
        end
        if (LANES == 1)
            prefix_valid = 1'b1;
        else if (LANES == 2)
            prefix_valid = 2'b01;
        else
            prefix_valid = 4'b1101;
        #1;
        if ((LANES > 1) && (alloc_count != 1 || alloc_grant != {{(LANES-1){1'b0}}, 1'b1})) begin
            $display("FAIL: prefix allocator stopped at first hole"); $finish(1);
        end
        if (select_valid && select_index != 0) begin
            $display("FAIL: priority selector did not choose oldest lane"); $finish(1);
        end

        skid_in_valid = 1'b1;
        skid_in_payload = 8'h5a;
        #10;
        if (!skid_out_valid || skid_out_payload != 8'h5a) begin
            $display("FAIL: skid capture"); $finish(1);
        end
        skid_in_payload = 8'ha5;
        #10;
        if (skid_out_payload != 8'h5a) begin
            $display("FAIL: skid payload changed under backpressure"); $finish(1);
        end
        skid_out_ready = 1'b1;
        #10;
        skid_in_valid = 1'b0;
        skid_out_ready = 1'b0;

        push_one(8'h10);
        if (occupancy != LANES) begin $display("FAIL: FIFO push occupancy"); $finish(1); end
        pop_ready = 1'b1;
        #1;
        if (!pop_valid || pop_count == 0 || pop_payload[7:0] != 8'h10) begin $display("FAIL: FIFO first pop"); $finish(1); end
        @(posedge clk);
        @(negedge clk);
        pop_ready = 1'b0;
        push_one(8'h20);
        push_one(8'h30);
        if (occupancy < LANES) begin $display("FAIL: FIFO wrap occupancy"); $finish(1); end
        flush = 1'b1;
        flush_count = 1;
        @(posedge clk);
        #1;
        flush = 1'b0;
        flush_count = 0;
        pop_ready = 1'b1;
        repeat (4) @(posedge clk);
        $display("PASS: H-02 FIFO/skid/prefix/priority primitives LANES=%0d", LANES);
        $finish(0);
    end
endmodule
