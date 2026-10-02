`timescale 1ns/1ps
// Convert the core's tagged 16-byte lines to the course's ONE 32-bit AXI-Lite
// interface. AR and AW/W can overlap, but I/D reads share the same AR/R queues.
// AXI-Lite has no IDs; FIFO metadata restores each line/word's core-side ID.
(* keep_hierarchy = 1 *)
module rv32_axi_lite_bridge #(
    parameter integer READ_LINES = 16,
    parameter integer WRITE_LINES = 8,
    parameter integer WORD_QUEUE = 64,
    parameter integer RESPONSE_FIFO_DEPTH = 0
) (
    input wire clock, reset,
    input wire i_req_valid, output wire i_req_ready,
    input wire [31:0] i_req_addr, input wire [7:0] i_req_id,
    output wire i_resp_valid, input wire i_resp_ready,
    output wire [31:0] i_resp_addr, output wire [127:0] i_resp_data,
    output wire [7:0] i_resp_id, output wire i_resp_error,
    input wire d_req_valid, output wire d_req_ready, input wire d_req_write,
    input wire [31:0] d_req_addr, input wire [127:0] d_req_data,
    input wire [15:0] d_req_mask, input wire [7:0] d_req_id,
    output wire d_resp_valid, input wire d_resp_ready,
    output wire [31:0] d_resp_addr, output wire [127:0] d_resp_data,
    output wire [7:0] d_resp_id, output wire d_resp_error,
    output wire [31:0] araddr, output wire arvalid, input wire arready,
    input wire [31:0] rdata, input wire [1:0] rresp,
    input wire rvalid, output wire rready,
    output wire [31:0] awaddr, output wire awvalid, input wire awready,
    output wire [31:0] wdata, output wire [3:0] wstrb,
    output wire wvalid, input wire wready,
    input wire [1:0] bresp, input wire bvalid, output wire bready
);
    localparam integer RPW = $clog2(READ_LINES);
    localparam integer WPW = $clog2(WRITE_LINES);
    localparam integer QPW = $clog2(WORD_QUEUE);
    reg [READ_LINES-1:0] read_valid;
    reg read_data_side [0:READ_LINES-1];
    reg [31:0] read_addr [0:READ_LINES-1];
    reg [7:0] read_id [0:READ_LINES-1];
    reg [127:0] read_data [0:READ_LINES-1];
    reg [2:0] read_sent [0:READ_LINES-1], read_received [0:READ_LINES-1];
    reg read_error [0:READ_LINES-1];
    reg [WRITE_LINES-1:0] write_valid;
    reg [31:0] write_addr [0:WRITE_LINES-1];
    reg [7:0] write_id [0:WRITE_LINES-1];
    reg [127:0] write_data [0:WRITE_LINES-1];
    reg [15:0] write_mask [0:WRITE_LINES-1];
    reg [2:0] write_sent [0:WRITE_LINES-1], write_received [0:WRITE_LINES-1];
    reg [2:0] write_expected [0:WRITE_LINES-1];
    reg write_error [0:WRITE_LINES-1];

    reg [RPW-1:0] rq_slot [0:WORD_QUEUE-1];
    reg [1:0] rq_word [0:WORD_QUEUE-1];
    reg [WPW-1:0] wq_slot [0:WORD_QUEUE-1];
    reg [QPW-1:0] rq_head, rq_tail, wq_head, wq_tail;
    reg [QPW:0] rq_count, wq_count;
    reg read_active, write_active, aw_done, w_done;
    reg [RPW-1:0] read_issue_slot;
    reg [WPW-1:0] write_issue_slot;
    reg [RPW-1:0] read_cursor;
    reg [WPW-1:0] write_cursor;
    reg prefer_d_request, prefer_write_reply;
    localparam integer RESPONSE_WIDTH = 32 + 128 + 8 + 1;
    reg legacy_i_resp_valid, legacy_d_resp_valid;
    reg [RESPONSE_WIDTH-1:0] legacy_i_resp_packet, legacy_d_resp_packet;
    wire fifo_i_ready, fifo_d_ready;
    // Depth zero preserves the original same-cycle response replacement.
    // A real FIFO admits a line from REGISTERED capacity alone: core READY
    // cannot propagate through reply selection into hundreds of payload FFs.
    wire i_slot_free = (RESPONSE_FIFO_DEPTH == 0) ?
        (!i_resp_valid || i_resp_ready) : fifo_i_ready;
    wire d_slot_free = (RESPONSE_FIFO_DEPTH == 0) ?
        (!d_resp_valid || d_resp_ready) : fifo_d_ready;
    integer scan;
    integer read_free, write_free, read_send, write_send, read_reply, write_reply;
    reg read_free_found, write_free_found, read_send_found, write_send_found;
    reg read_reply_found, write_reply_found;
    integer read_wrap, write_wrap;
    reg read_wrap_found, write_wrap_found;
    always @* begin
        read_free = 0; write_free = 0; read_send = 0; write_send = 0;
        read_reply = 0; write_reply = 0;
        read_free_found = 0; write_free_found = 0;
        read_send_found = 0; write_send_found = 0;
        read_reply_found = 0; write_reply_found = 0;
        read_wrap = 0; write_wrap = 0; read_wrap_found = 0; write_wrap_found = 0;
        for (scan = 0; scan < WRITE_LINES; scan = scan + 1) begin
            if (!write_free_found && !write_valid[scan]) begin
                write_free_found = 1; write_free = scan;
            end
            if (write_valid[scan] && write_sent[scan] < 4) begin
                if (!write_wrap_found) begin write_wrap_found = 1; write_wrap = scan; end
                if (!write_send_found && scan >= write_cursor) begin
                    write_send_found = 1; write_send = scan;
                end
            end
            if (!write_reply_found && write_valid[scan] && write_sent[scan] == 4 &&
                write_received[scan] == write_expected[scan] && d_slot_free) begin
                write_reply_found = 1; write_reply = scan;
            end
        end
        for (scan = 0; scan < READ_LINES; scan = scan + 1) begin
            if (!read_free_found && !read_valid[scan]) begin
                read_free_found = 1; read_free = scan;
            end
            if (read_valid[scan] && read_sent[scan] < 4) begin
                if (!read_wrap_found) begin read_wrap_found = 1; read_wrap = scan; end
                if (!read_send_found && scan >= read_cursor) begin
                    read_send_found = 1; read_send = scan;
                end
            end
            // A blocked instruction consumer cannot hold up data completions.
            // Dedicated response registers keep both outputs stable, while
            // just ONE 128-bit array read moves a completed line into them.
            if (!read_reply_found && read_valid[scan] && read_received[scan] == 4 &&
                (read_data_side[scan] ?
                 (d_slot_free && !(write_reply_found && prefer_write_reply)) : i_slot_free)) begin
                read_reply_found = 1; read_reply = scan;
            end
        end
        if (!read_send_found && read_wrap_found) begin read_send_found = 1; read_send = read_wrap; end
        if (!write_send_found && write_wrap_found) begin write_send_found = 1; write_send = write_wrap; end
    end
    wire d_read_request = d_req_valid && !d_req_write;
    assign i_req_ready = !reset && read_free_found && (!d_read_request || !prefer_d_request);
    assign d_req_ready = !reset && (d_req_write ? write_free_found :
                         (read_free_found && (!i_req_valid || prefer_d_request)));
    wire take_i = i_req_valid && i_req_ready;
    wire take_d_read = d_read_request && d_req_ready;
    wire take_d_write = d_req_valid && d_req_write && d_req_ready;

    assign arvalid = !reset && read_active && rq_count < WORD_QUEUE;
    assign araddr = read_active ? read_addr[read_issue_slot] + {28'd0, read_sent[read_issue_slot][1:0], 2'b00} : 0;
    assign rready = !reset && rq_count != 0;
    wire read_push = arvalid && arready;
    wire read_pop = rvalid && rready;
    wire [3:0] current_mask = write_mask[write_issue_slot] >> (write_sent[write_issue_slot][1:0] * 4);
    wire write_word_present = write_active && current_mask != 0;
    assign awvalid = !reset && write_word_present && !aw_done && wq_count < WORD_QUEUE;
    assign wvalid = !reset && write_word_present && !w_done && wq_count < WORD_QUEUE;
    assign awaddr = write_active ? write_addr[write_issue_slot] + {28'd0, write_sent[write_issue_slot][1:0], 2'b00} : 0;
    assign wdata = write_active ? write_data[write_issue_slot] >> (write_sent[write_issue_slot][1:0] * 32) : 0;
    assign wstrb = write_active ? current_mask : 0;
    wire aw_fire = awvalid && awready;
    wire w_fire = wvalid && wready;
    // Pair channels only after BOTH handshakes, including different cycles.
    wire write_push = !reset && write_word_present && (aw_done || aw_fire) && (w_done || w_fire);
    assign bready = !reset && wq_count != 0;
    wire write_pop = bvalid && bready;
    wire fill_read = !reset && read_reply_found;
    wire fill_write = !reset && write_reply_found &&
                      !(read_reply_found && read_data_side[read_reply]);

    generate if (RESPONSE_FIFO_DEPTH == 0) begin : g_legacy_responses
        assign i_resp_valid = legacy_i_resp_valid;
        assign d_resp_valid = legacy_d_resp_valid;
        assign {i_resp_addr, i_resp_data, i_resp_id, i_resp_error} = legacy_i_resp_packet;
        assign {d_resp_addr, d_resp_data, d_resp_id, d_resp_error} = legacy_d_resp_packet;
        assign fifo_i_ready = 1'b0;
        assign fifo_d_ready = 1'b0;
    end else begin : g_response_fifos
        wire [RESPONSE_WIDTH-1:0] read_packet =
            {read_addr[read_reply], read_data[read_reply], read_id[read_reply], read_error[read_reply]};
        wire [RESPONSE_WIDTH-1:0] write_packet =
            {write_addr[write_reply], 128'b0, write_id[write_reply], write_error[write_reply]};
        rv32_axi_response_fifo #(.WIDTH(RESPONSE_WIDTH), .DEPTH(RESPONSE_FIFO_DEPTH)) instruction (
            .clock(clock), .reset(reset),
            .in_valid(fill_read && !read_data_side[read_reply]), .in_ready(fifo_i_ready),
            .in_packet(read_packet), .out_valid(i_resp_valid), .out_ready(i_resp_ready),
            .out_packet({i_resp_addr, i_resp_data, i_resp_id, i_resp_error}));
        rv32_axi_response_fifo #(.WIDTH(RESPONSE_WIDTH), .DEPTH(RESPONSE_FIFO_DEPTH)) data (
            .clock(clock), .reset(reset),
            .in_valid(fill_write || (fill_read && read_data_side[read_reply])), .in_ready(fifo_d_ready),
            .in_packet(fill_write ? write_packet : read_packet),
            .out_valid(d_resp_valid), .out_ready(d_resp_ready),
            .out_packet({d_resp_addr, d_resp_data, d_resp_id, d_resp_error}));
    end endgenerate

    function [2:0] enabled_words;
        input [15:0] mask;
        begin
            enabled_words = {2'd0, |mask[3:0]} + {2'd0, |mask[7:4]} +
                            {2'd0, |mask[11:8]} + {2'd0, |mask[15:12]};
        end
    endfunction
    always @(posedge clock) begin
        if (reset) begin
            read_valid <= 0; write_valid <= 0;
            rq_head <= 0; rq_tail <= 0; rq_count <= 0;
            wq_head <= 0; wq_tail <= 0; wq_count <= 0;
            read_active <= 0; write_active <= 0; aw_done <= 0; w_done <= 0;
            read_issue_slot <= 0; write_issue_slot <= 0;
            read_cursor <= 0; write_cursor <= 0;
            legacy_i_resp_valid <= 0; legacy_d_resp_valid <= 0;
            prefer_d_request <= 0; prefer_write_reply <= 0;
        end else begin
            if (take_i || take_d_read) begin
                read_valid[read_free] <= 1;
                read_data_side[read_free] <= take_d_read;
                read_addr[read_free] <= take_d_read ? d_req_addr : i_req_addr;
                read_id[read_free] <= take_d_read ? d_req_id : i_req_id;
                read_sent[read_free] <= 0; read_received[read_free] <= 0;
                read_error[read_free] <= 0;
                prefer_d_request <= take_i;
            end
            if (take_d_write) begin
                write_valid[write_free] <= 1;
                write_addr[write_free] <= d_req_addr;
                write_id[write_free] <= d_req_id;
                write_data[write_free] <= d_req_data;
                write_mask[write_free] <= d_req_mask;
                write_sent[write_free] <= enabled_words(d_req_mask) == 0 ? 4 : 0;
                write_received[write_free] <= 0;
                write_expected[write_free] <= enabled_words(d_req_mask);
                write_error[write_free] <= 0;
            end
            if (!read_active && read_send_found) begin
                read_active <= 1; read_issue_slot <= read_send[RPW-1:0];
            end
            if (read_push) begin
                rq_slot[rq_tail] <= read_issue_slot;
                rq_word[rq_tail] <= read_sent[read_issue_slot][1:0];
                rq_tail <= rq_tail + 1'b1;
                read_sent[read_issue_slot] <= read_sent[read_issue_slot] + 1'b1;
                if (read_sent[read_issue_slot] == 3) begin
                    read_active <= 0; read_cursor <= read_issue_slot + 1'b1;
                end
            end
            if (read_pop) begin
                read_data[rq_slot[rq_head]][rq_word[rq_head]*32 +: 32] <= rdata;
                read_received[rq_slot[rq_head]] <= read_received[rq_slot[rq_head]] + 1'b1;
                read_error[rq_slot[rq_head]] <= read_error[rq_slot[rq_head]] || rresp != 0;
                rq_head <= rq_head + 1'b1;
            end
            case ({read_push, read_pop})
                2'b10: rq_count <= rq_count + 1'b1;
                2'b01: rq_count <= rq_count - 1'b1;
            endcase
            if (!write_active && write_send_found) begin
                write_active <= 1; write_issue_slot <= write_send[WPW-1:0];
                aw_done <= 0; w_done <= 0;
            end
            if (aw_fire) aw_done <= 1;
            if (w_fire) w_done <= 1;
            if (write_active && (current_mask == 0 || write_push)) begin
                write_sent[write_issue_slot] <= write_sent[write_issue_slot] + 1'b1;
                aw_done <= 0; w_done <= 0;
                if (write_sent[write_issue_slot] == 3) begin
                    write_active <= 0; write_cursor <= write_issue_slot + 1'b1;
                end
            end
            if (write_push) begin
                wq_slot[wq_tail] <= write_issue_slot;
                wq_tail <= wq_tail + 1'b1;
            end
            if (write_pop) begin
                write_received[wq_slot[wq_head]] <= write_received[wq_slot[wq_head]] + 1'b1;
                write_error[wq_slot[wq_head]] <= write_error[wq_slot[wq_head]] || bresp != 0;
                wq_head <= wq_head + 1'b1;
            end
            case ({write_push, write_pop})
                2'b10: wq_count <= wq_count + 1'b1;
                2'b01: wq_count <= wq_count - 1'b1;
            endcase
            if (i_resp_valid && i_resp_ready) legacy_i_resp_valid <= 0;
            if (d_resp_valid && d_resp_ready) legacy_d_resp_valid <= 0;
            if (fill_read) begin
                read_valid[read_reply] <= 0;
                if (read_data_side[read_reply]) begin
                    legacy_d_resp_valid <= 1;
                    legacy_d_resp_packet <= {read_addr[read_reply], read_data[read_reply],
                                             read_id[read_reply], read_error[read_reply]};
                    prefer_write_reply <= 1;
                end else begin
                    legacy_i_resp_valid <= 1;
                    legacy_i_resp_packet <= {read_addr[read_reply], read_data[read_reply],
                                             read_id[read_reply], read_error[read_reply]};
                end
            end
            if (fill_write) begin
                write_valid[write_reply] <= 0;
                legacy_d_resp_valid <= 1;
                legacy_d_resp_packet <= {write_addr[write_reply], 128'b0,
                                         write_id[write_reply], write_error[write_reply]};
                prefer_write_reply <= 0;
            end
        end
    end
    initial begin
        if (READ_LINES < 2 || WRITE_LINES < 2 || WORD_QUEUE < 4 ||
            (READ_LINES & (READ_LINES-1)) != 0 || (WRITE_LINES & (WRITE_LINES-1)) != 0 ||
            (WORD_QUEUE & (WORD_QUEUE-1)) != 0 ||
            (RESPONSE_FIFO_DEPTH != 0 && (RESPONSE_FIFO_DEPTH < 2 ||
             (RESPONSE_FIFO_DEPTH & (RESPONSE_FIFO_DEPTH-1)) != 0))) begin
            $display("ERROR: AXI bridge capacities must be powers of two"); $finish;
        end
    end
endmodule

// Registered-credit FIFO for completed line responses, not a cache or RAM
// replacement. A nonempty queue has no fall-through input-to-output path.
// Concurrent push/pop sustains one line/cycle when a slot is already free;
// a full queue releases credit on the following cycle, never through READY.
module rv32_axi_response_fifo #(
    parameter integer WIDTH = 169,
    parameter integer DEPTH = 2,
    parameter integer PTR_WIDTH = $clog2(DEPTH),
    parameter integer COUNT_WIDTH = $clog2(DEPTH + 1)
) (
    input wire clock, reset,
    input wire in_valid, output wire in_ready,
    input wire [WIDTH-1:0] in_packet,
    output wire out_valid, input wire out_ready,
    output wire [WIDTH-1:0] out_packet
);
    reg [WIDTH-1:0] packets [0:DEPTH-1];
    reg [PTR_WIDTH-1:0] head, tail;
    reg [COUNT_WIDTH-1:0] count;
    assign in_ready = !reset && count < DEPTH;
    assign out_valid = !reset && count != 0;
    assign out_packet = packets[head];
    wire push = in_valid && in_ready;
    wire pop = out_valid && out_ready;
    always @(posedge clock) begin
        if (reset) begin
            head <= 0; tail <= 0; count <= 0;
        end else begin
            if (push) begin
                packets[tail] <= in_packet;
                tail <= tail + 1'b1;
            end
            if (pop) head <= head + 1'b1;
            case ({push, pop})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
            endcase
        end
    end
    initial begin
        if (WIDTH < 1 || DEPTH < 2 || (DEPTH & (DEPTH-1)) != 0) begin
            $display("ERROR: response FIFO needs positive width and power-of-two depth >= 2");
            $finish;
        end
    end
endmodule
