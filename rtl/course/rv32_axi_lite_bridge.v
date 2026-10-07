`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Convert the core's tagged 16-byte lines to the course's ONE 32-bit AXI-Lite
// interface. AR and AW/W can overlap, but I/D reads share the same AR/R queues.
// AXI-Lite has no IDs; FIFO metadata restores each line/word's core-side ID.
module rv32_axi_lite_bridge #(
    parameter integer READ_LINES = 16,
    parameter integer WRITE_LINES = 8,
    parameter integer WORD_QUEUE = 64,
    parameter integer READ_PAYLOAD_SRAM = 0,
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
    wire read_data_side [0:READ_LINES-1];
    wire [31:0] read_addr [0:READ_LINES-1];
    wire [7:0] read_id [0:READ_LINES-1];
    wire [127:0] read_data [0:READ_LINES-1];
    reg [2:0] read_sent [0:READ_LINES-1], read_received [0:READ_LINES-1];
    reg read_error [0:READ_LINES-1];
    reg [WRITE_LINES-1:0] write_valid;
    wire [31:0] write_addr [0:WRITE_LINES-1];
    wire [7:0] write_id [0:WRITE_LINES-1];
    wire [127:0] write_data [0:WRITE_LINES-1];
    wire [15:0] write_mask [0:WRITE_LINES-1];
    reg [2:0] write_sent [0:WRITE_LINES-1], write_received [0:WRITE_LINES-1];
    reg [2:0] write_expected [0:WRITE_LINES-1];
    reg write_error [0:WRITE_LINES-1];

    wire [RPW-1:0] rq_slot [0:WORD_QUEUE-1];
    wire [1:0] rq_word [0:WORD_QUEUE-1];
    wire [WPW-1:0] wq_slot [0:WORD_QUEUE-1];
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
    wire unused_legacy_i_resp_valid_bits = &{1'b0, legacy_i_resp_valid};

    wire unused_legacy_d_resp_valid_bits = &{1'b0, legacy_d_resp_valid};

    wire [RESPONSE_WIDTH-1:0] legacy_i_resp_packet, legacy_d_resp_packet;
    wire unused_legacy_i_resp_packet_bits = &{1'b0, legacy_i_resp_packet};

    wire unused_legacy_d_resp_packet_bits = &{1'b0, legacy_d_resp_packet};

    wire fifo_i_ready, fifo_d_ready;
    // Depth zero preserves the original same-cycle response replacement.
    // A real FIFO admits a line from REGISTERED capacity alone: core READY
    // cannot propagate through reply selection into hundreds of payload FFs.
    wire i_slot_free = (RESPONSE_FIFO_DEPTH == 0) ?
        (!i_resp_valid || i_resp_ready) : fifo_i_ready;
    wire d_slot_free = (RESPONSE_FIFO_DEPTH == 0) ?
        (!d_resp_valid || d_resp_ready) : fifo_d_ready;
    wire [RPW-1:0] read_free,read_send,read_reply;
    wire [WPW-1:0] write_free,write_send,write_reply;
    wire read_free_found, write_free_found, read_send_found, write_send_found;
    wire read_reply_found, write_reply_found;
    wire [RPW-1:0] read_wrap;
    wire [WPW-1:0] write_wrap;
    wire read_wrap_found, write_wrap_found;

    wire [READ_LINES-1:0] read_free_candidates,read_send_candidates,read_upper_candidates,read_reply_candidates;
    wire [WRITE_LINES-1:0] write_free_candidates,write_send_candidates,write_upper_candidates,write_reply_candidates;
    wire read_upper_found,write_upper_found;
    wire [RPW-1:0] read_upper;
    wire [WPW-1:0] write_upper;
    genvar candidate_row;
    generate
        for(candidate_row=0;candidate_row<WRITE_LINES;candidate_row=candidate_row+1) begin:g_write_candidates
            assign write_free_candidates[candidate_row]=!write_valid[candidate_row];
            assign write_send_candidates[candidate_row]=write_valid[candidate_row] && write_sent[candidate_row]<4;
            if (candidate_row >= (1<<WPW)-1) begin : g_last_cursor
                assign write_upper_candidates[candidate_row]=write_send_candidates[candidate_row];
            end else begin : g_compare_cursor
                assign write_upper_candidates[candidate_row]=write_send_candidates[candidate_row] && candidate_row>=write_cursor;
            end
            assign write_reply_candidates[candidate_row]=write_valid[candidate_row] && write_sent[candidate_row]==4 &&
                write_received[candidate_row]==write_expected[candidate_row] && d_slot_free;
        end
        for(candidate_row=0;candidate_row<READ_LINES;candidate_row=candidate_row+1) begin:g_read_candidates
            assign read_free_candidates[candidate_row]=!read_valid[candidate_row];
            assign read_send_candidates[candidate_row]=read_valid[candidate_row] && read_sent[candidate_row]<4;
            if (candidate_row >= (1<<RPW)-1) begin : g_last_cursor
                assign read_upper_candidates[candidate_row]=read_send_candidates[candidate_row];
            end else begin : g_compare_cursor
                assign read_upper_candidates[candidate_row]=read_send_candidates[candidate_row] && candidate_row>=read_cursor;
            end
            assign read_reply_candidates[candidate_row]=read_valid[candidate_row] && read_received[candidate_row]==4 &&
                (read_data_side[candidate_row]?(d_slot_free && !(write_reply_found && prefer_write_reply)):i_slot_free);
        end
    endgenerate
        wire  unused_read_free_selector_second_valid_o;
    wire [(RPW)-1:0] unused_read_free_selector_second_index_o;
    rv32_frequency_first_two #(.ENTRIES(READ_LINES),.INDEX_WIDTH(RPW)) read_free_selector (
        .candidates_i(read_free_candidates),.first_valid_o(read_free_found),.first_index_o(read_free),
        .second_valid_o(unused_read_free_selector_second_valid_o),.second_index_o(unused_read_free_selector_second_index_o));
        wire  unused_write_free_selector_second_valid_o;
    wire [(WPW)-1:0] unused_write_free_selector_second_index_o;
    rv32_frequency_first_two #(.ENTRIES(WRITE_LINES),.INDEX_WIDTH(WPW)) write_free_selector (
        .candidates_i(write_free_candidates),.first_valid_o(write_free_found),.first_index_o(write_free),
        .second_valid_o(unused_write_free_selector_second_valid_o),.second_index_o(unused_write_free_selector_second_index_o));
        wire  unused_read_wrap_selector_second_valid_o;
    wire [(RPW)-1:0] unused_read_wrap_selector_second_index_o;
    rv32_frequency_first_two #(.ENTRIES(READ_LINES),.INDEX_WIDTH(RPW)) read_wrap_selector (
        .candidates_i(read_send_candidates),.first_valid_o(read_wrap_found),.first_index_o(read_wrap),
        .second_valid_o(unused_read_wrap_selector_second_valid_o),.second_index_o(unused_read_wrap_selector_second_index_o));
        wire  unused_read_upper_selector_second_valid_o;
    wire [(RPW)-1:0] unused_read_upper_selector_second_index_o;
    rv32_frequency_first_two #(.ENTRIES(READ_LINES),.INDEX_WIDTH(RPW)) read_upper_selector (
        .candidates_i(read_upper_candidates),.first_valid_o(read_upper_found),.first_index_o(read_upper),
        .second_valid_o(unused_read_upper_selector_second_valid_o),.second_index_o(unused_read_upper_selector_second_index_o));
        wire  unused_write_wrap_selector_second_valid_o;
    wire [(WPW)-1:0] unused_write_wrap_selector_second_index_o;
    rv32_frequency_first_two #(.ENTRIES(WRITE_LINES),.INDEX_WIDTH(WPW)) write_wrap_selector (
        .candidates_i(write_send_candidates),.first_valid_o(write_wrap_found),.first_index_o(write_wrap),
        .second_valid_o(unused_write_wrap_selector_second_valid_o),.second_index_o(unused_write_wrap_selector_second_index_o));
        wire  unused_write_upper_selector_second_valid_o;
    wire [(WPW)-1:0] unused_write_upper_selector_second_index_o;
    rv32_frequency_first_two #(.ENTRIES(WRITE_LINES),.INDEX_WIDTH(WPW)) write_upper_selector (
        .candidates_i(write_upper_candidates),.first_valid_o(write_upper_found),.first_index_o(write_upper),
        .second_valid_o(unused_write_upper_selector_second_valid_o),.second_index_o(unused_write_upper_selector_second_index_o));
        wire  unused_read_reply_selector_second_valid_o;
    wire [(RPW)-1:0] unused_read_reply_selector_second_index_o;
    rv32_frequency_first_two #(.ENTRIES(READ_LINES),.INDEX_WIDTH(RPW)) read_reply_selector (
        .candidates_i(read_reply_candidates),.first_valid_o(read_reply_found),.first_index_o(read_reply),
        .second_valid_o(unused_read_reply_selector_second_valid_o),.second_index_o(unused_read_reply_selector_second_index_o));
        wire  unused_write_reply_selector_second_valid_o;
    wire [(WPW)-1:0] unused_write_reply_selector_second_index_o;
    rv32_frequency_first_two #(.ENTRIES(WRITE_LINES),.INDEX_WIDTH(WPW)) write_reply_selector (
        .candidates_i(write_reply_candidates),.first_valid_o(write_reply_found),.first_index_o(write_reply),
        .second_valid_o(unused_write_reply_selector_second_valid_o),.second_index_o(unused_write_reply_selector_second_index_o));
    assign read_send_found=read_upper_found || read_wrap_found;
    assign read_send=read_upper_found?read_upper:read_wrap;
    assign write_send_found=write_upper_found || write_wrap_found;
    assign write_send=write_upper_found?write_upper:write_wrap;

    wire d_read_request = d_req_valid && !d_req_write;
    assign i_req_ready = !reset && read_free_found && (!d_read_request || !prefer_d_request);
    assign d_req_ready = !reset && (d_req_write ? write_free_found :
                         (read_free_found && (!i_req_valid || prefer_d_request)));
    wire take_i = i_req_valid && i_req_ready;
    wire take_d_read = d_read_request && d_req_ready;
    wire take_d_write = d_req_valid && d_req_write && d_req_ready;

    assign arvalid = !reset && read_active && 32'(rq_count) < WORD_QUEUE;
    assign rready = !reset && rq_count != 0;
    wire read_push = arvalid && arready;
    wire read_pop = rvalid && rready;
    wire write_word_present = write_active && current_mask != 0;
    assign awvalid = !reset && write_word_present && !aw_done && 32'(wq_count) < WORD_QUEUE;
    assign wvalid = !reset && write_word_present && !w_done && 32'(wq_count) < WORD_QUEUE;
    wire aw_fire = awvalid && awready;
    wire w_fire = wvalid && wready;
    // Pair channels only after BOTH handshakes, including different cycles.
    wire write_push = !reset && write_word_present && (aw_done || aw_fire) && (w_done || w_fire);
    assign bready = !reset && wq_count != 0;
    wire write_pop = bvalid && bready;
    wire fill_read = !reset && read_reply_found;
    wire fill_write = !reset && write_reply_found &&
                      !(read_reply_found && query_read_reply_side);

    generate if (RESPONSE_FIFO_DEPTH == 0) begin : g_legacy_responses
        assign i_resp_valid = legacy_i_resp_valid;
        assign d_resp_valid = legacy_d_resp_valid;
        assign {i_resp_addr, i_resp_data, i_resp_id, i_resp_error} = legacy_i_resp_packet;
        assign {d_resp_addr, d_resp_data, d_resp_id, d_resp_error} = legacy_d_resp_packet;
        assign fifo_i_ready = 1'b0;
        assign fifo_d_ready = 1'b0;
    end else begin : g_response_fifos
        wire [RESPONSE_WIDTH-1:0] read_packet =
            {query_read_reply_addr, query_read_reply_data, query_read_reply_id, query_read_reply_error};
        wire [RESPONSE_WIDTH-1:0] write_packet =
            {query_write_reply_addr, 128'b0, query_write_reply_id, query_write_reply_error};
        wire [RESPONSE_WIDTH-1:0] data_packet;
        wire  unused_response_data_selector_write_o;
        rv32_frequency_event_select #(.WIDTH(RESPONSE_WIDTH),.EVENTS(2)) response_data_selector (
            .events_i({fill_write,fill_read && query_read_reply_side}),
            .values_i({write_packet,read_packet}),.write_o(unused_response_data_selector_write_o),.value_o(data_packet));
        rv32_axi_response_fifo #(.WIDTH(RESPONSE_WIDTH), .DEPTH(RESPONSE_FIFO_DEPTH)) instruction (
            .clock(clock), .reset(reset),
            .in_valid(fill_read && !query_read_reply_side), .in_ready(fifo_i_ready),
            .in_packet(read_packet), .out_valid(i_resp_valid), .out_ready(i_resp_ready),
            .out_packet({i_resp_addr, i_resp_data, i_resp_id, i_resp_error}));
        rv32_axi_response_fifo #(.WIDTH(RESPONSE_WIDTH), .DEPTH(RESPONSE_FIFO_DEPTH)) data (
            .clock(clock), .reset(reset),
            .in_valid(fill_write || (fill_read && query_read_reply_side)), .in_ready(fifo_d_ready),
            .in_packet(data_packet),
            .out_valid(d_resp_valid), .out_ready(d_resp_ready),
            .out_packet({d_resp_addr, d_resp_data, d_resp_id, d_resp_error}));
    end endgenerate

    localparam integer READ_ISSUE_WIDTH=35;
    wire [READ_LINES*READ_ISSUE_WIDTH-1:0] read_issue_rows;
    genvar read_issue_row;
    generate for(read_issue_row=0;read_issue_row<READ_LINES;read_issue_row=read_issue_row+1) begin:g_read_issue_rows
        assign read_issue_rows[read_issue_row*READ_ISSUE_WIDTH +: READ_ISSUE_WIDTH]={read_addr[read_issue_row],read_sent[read_issue_row]};
    end endgenerate
    wire [31:0] query_read_issue_addr;
    wire [2:0] query_read_issue_sent;
    rv32_frequency_array_read #(.WIDTH(READ_ISSUE_WIDTH),.ENTRIES(READ_LINES),.INDEX_WIDTH(RPW)) read_issue_reader (
        .rows_i(read_issue_rows),.index_i(read_issue_slot),.value_o({query_read_issue_addr,query_read_issue_sent}));
    localparam integer READ_REPLY_WIDTH=170;
    wire [READ_LINES*READ_REPLY_WIDTH-1:0] read_reply_rows;
    genvar read_reply_row;
    generate for(read_reply_row=0;read_reply_row<READ_LINES;read_reply_row=read_reply_row+1) begin:g_read_reply_rows
        assign read_reply_rows[read_reply_row*READ_REPLY_WIDTH +: READ_REPLY_WIDTH]={read_addr[read_reply_row],read_data[read_reply_row],read_id[read_reply_row],read_error[read_reply_row],read_data_side[read_reply_row]};
    end endgenerate
    wire [31:0] query_read_reply_addr;
    wire [127:0] query_read_reply_data;
    wire [7:0] query_read_reply_id;
    wire query_read_reply_error;
    wire query_read_reply_side;
    rv32_frequency_array_read #(.WIDTH(READ_REPLY_WIDTH),.ENTRIES(READ_LINES),.INDEX_WIDTH(RPW)) read_reply_reader (
        .rows_i(read_reply_rows),.index_i(read_reply),.value_o({query_read_reply_addr,query_read_reply_data,query_read_reply_id,query_read_reply_error,query_read_reply_side}));
    localparam integer WRITE_ISSUE_WIDTH=35;
    wire [WRITE_LINES*WRITE_ISSUE_WIDTH-1:0] write_issue_rows;
    genvar write_issue_row;
    generate for(write_issue_row=0;write_issue_row<WRITE_LINES;write_issue_row=write_issue_row+1) begin:g_write_issue_rows
        assign write_issue_rows[write_issue_row*WRITE_ISSUE_WIDTH +: WRITE_ISSUE_WIDTH]={write_addr[write_issue_row],write_sent[write_issue_row]};
    end endgenerate
    wire [31:0] query_write_issue_addr;
    wire [2:0] query_write_issue_sent;
    rv32_frequency_array_read #(.WIDTH(WRITE_ISSUE_WIDTH),.ENTRIES(WRITE_LINES),.INDEX_WIDTH(WPW)) write_issue_reader (
        .rows_i(write_issue_rows),.index_i(write_issue_slot),.value_o({query_write_issue_addr,query_write_issue_sent}));
    localparam integer WRITE_REPLY_WIDTH=41;
    wire [WRITE_LINES*WRITE_REPLY_WIDTH-1:0] write_reply_rows;
    genvar write_reply_row;
    generate for(write_reply_row=0;write_reply_row<WRITE_LINES;write_reply_row=write_reply_row+1) begin:g_write_reply_rows
        assign write_reply_rows[write_reply_row*WRITE_REPLY_WIDTH +: WRITE_REPLY_WIDTH]={write_addr[write_reply_row],write_id[write_reply_row],write_error[write_reply_row]};
    end endgenerate
    wire [31:0] query_write_reply_addr;
    wire [7:0] query_write_reply_id;
    wire query_write_reply_error;
    rv32_frequency_array_read #(.WIDTH(WRITE_REPLY_WIDTH),.ENTRIES(WRITE_LINES),.INDEX_WIDTH(WPW)) write_reply_reader (
        .rows_i(write_reply_rows),.index_i(write_reply),.value_o({query_write_reply_addr,query_write_reply_id,query_write_reply_error}));
    localparam integer READ_RETURN_WIDTH=RPW+2;
    wire [WORD_QUEUE*READ_RETURN_WIDTH-1:0] read_return_rows;
    genvar read_return_row;
    generate for(read_return_row=0;read_return_row<WORD_QUEUE;read_return_row=read_return_row+1) begin:g_read_return_rows
        assign read_return_rows[read_return_row*READ_RETURN_WIDTH +: READ_RETURN_WIDTH]={rq_slot[read_return_row],rq_word[read_return_row]};
    end endgenerate
    wire [RPW-1:0] query_read_return_slot;
    wire [1:0] query_read_return_word;
    rv32_frequency_array_read #(.WIDTH(READ_RETURN_WIDTH),.ENTRIES(WORD_QUEUE),.INDEX_WIDTH(QPW)) read_return_reader (
        .rows_i(read_return_rows),.index_i(rq_head),.value_o({query_read_return_slot,query_read_return_word}));
    localparam integer WRITE_RETURN_WIDTH=WPW;
    wire [WORD_QUEUE*WRITE_RETURN_WIDTH-1:0] write_return_rows;
    genvar write_return_row;
    generate for(write_return_row=0;write_return_row<WORD_QUEUE;write_return_row=write_return_row+1) begin:g_write_return_rows
        assign write_return_rows[write_return_row*WRITE_RETURN_WIDTH +: WRITE_RETURN_WIDTH]={wq_slot[write_return_row]};
    end endgenerate
    wire [WPW-1:0] query_write_return_slot;
    rv32_frequency_array_read #(.WIDTH(WRITE_RETURN_WIDTH),.ENTRIES(WORD_QUEUE),.INDEX_WIDTH(QPW)) write_return_reader (
        .rows_i(write_return_rows),.index_i(wq_head),.value_o({query_write_return_slot}));

    localparam integer WRITE_WORDS=4*WRITE_LINES;
    wire [WRITE_WORDS*36-1:0] write_word_rows;
    wire [WPW+1:0] write_word_query={write_issue_slot,query_write_issue_sent[1:0]};
    wire [31:0] selected_write_word;
    wire [3:0] current_mask;
    genvar selected_word;
    generate for(selected_word=0;selected_word<WRITE_WORDS;selected_word=selected_word+1) begin:g_write_word_rows
        assign write_word_rows[selected_word*36 +: 36]={
            write_data[selected_word/4][(selected_word%4)*32 +: 32],write_mask[selected_word/4][(selected_word%4)*4 +: 4]};
    end endgenerate
    rv32_frequency_array_read #(.WIDTH(36),.ENTRIES(WRITE_WORDS),.INDEX_WIDTH(WPW+2)) write_word_reader (
        .rows_i(write_word_rows),.index_i(write_word_query),.value_o({selected_write_word,current_mask}));
    wire [1:0] read_address_views;
    wire [4:0] write_output_views;
    rv32_frequency_control_tree #(.LEAVES(2)) read_address_tree (
        .signal_i(read_active),.views_o(read_address_views));
    rv32_frequency_control_tree #(.LEAVES(5)) write_output_tree (
        .signal_i(write_active),.views_o(write_output_views));
    wire [31:0] selected_read_address=query_read_issue_addr+{28'b0,query_read_issue_sent[1:0],2'b0};
    wire [31:0] selected_write_address=query_write_issue_addr+{28'b0,query_write_issue_sent[1:0],2'b0};
    genvar output_word;
    generate for(output_word=0;output_word<2;output_word=output_word+1) begin:g_axi_output_words
        assign araddr[output_word*16 +: 16]={16{read_address_views[output_word]}} & selected_read_address[output_word*16 +: 16];
        assign awaddr[output_word*16 +: 16]={16{write_output_views[output_word]}} & selected_write_address[output_word*16 +: 16];
        assign wdata[output_word*16 +: 16]={16{write_output_views[output_word+2]}} & selected_write_word[output_word*16 +: 16];
    end endgenerate
    assign wstrb={4{write_output_views[4]}} & current_mask;

    function automatic [2:0] enabled_words;
        input [15:0] mask;
        begin
            enabled_words = {2'd0, |mask[3:0]} + {2'd0, |mask[7:4]} +
                            {2'd0, |mask[11:8]} + {2'd0, |mask[15:12]};
        end
    endfunction

    localparam integer READ_DOMAINS=(READ_LINES+3)/4;
    wire [READ_DOMAINS*(RPW+3)-1:0] read_return_views;
    wire [READ_DOMAINS*32-1:0] read_return_data;
    rv32_frequency_control_tree #(.WIDTH(RPW+3),.LEAVES(READ_DOMAINS)) read_return_tree (
        .signal_i({!reset && read_pop,query_read_return_slot,query_read_return_word}),.views_o(read_return_views));
    rv32_frequency_control_tree #(.WIDTH(32),.LEAVES(READ_DOMAINS)) read_return_data_tree (
        .signal_i(rdata),.views_o(read_return_data));
    wire read_allocate;
    wire [40:0] read_allocate_metadata;
    rv32_frequency_event_select #(.WIDTH(41),.EVENTS(2)) read_allocate_selector (
        .events_i({take_d_read,take_i}),.values_i({1'b1,d_req_addr,d_req_id,1'b0,i_req_addr,i_req_id}),
        .write_o(read_allocate),.value_o(read_allocate_metadata));
    genvar payload_row,payload_word;
    generate
        for(payload_row=0;payload_row<READ_LINES;payload_row=payload_row+1) begin:g_read_payload_owner
            wire [40:0] metadata;
            rv32_frequency_word_bank #(.WIDTH(41)) metadata_owner (
                .clk_i(clock),.write_i(read_allocate && read_free==payload_row),
                .data_i(read_allocate_metadata),.data_o(metadata));
            assign {read_data_side[payload_row],read_addr[payload_row],read_id[payload_row]}=metadata;
            wire return_valid;
            wire [RPW-1:0] return_slot;
            wire [1:0] return_word;
            assign {return_valid,return_slot,return_word}=read_return_views[(payload_row/4)*(RPW+3) +: RPW+3];
            if(READ_PAYLOAD_SRAM!=0) begin:g_sram_words
                wire row_return=return_valid && return_slot==payload_row;
                wire write_prefix=row_return && return_word!=2'd3;
                wire [31:0] word_data=read_return_data[(payload_row/4)*32 +: 32];
                // AXI-Lite returns the issued words in FIFO order 0,1,2,3.
                // On the final-word edge this prefix bank reads, while word3
                // is captured independently. All 128 bits are ready when the
                // unchanged received==4 condition publishes the line.
                // Reread on idle edges: FakeRAM Q does not retain idle data.
                sram_fakeram #(.DEPTH(1),.WIDTH(96),.WRITE_GRANULARITY(32)) prefix (
                    .clk(clock),.en(!reset),.we(write_prefix),
                    .wmask(3'b001 << return_word),.addr(1'b0),
                    .wdata({3{word_data}}),.rdata(read_data[payload_row][95:0]));
                rv32_frequency_word_bank #(.WIDTH(32)) final_word (
                    .clk_i(clock),.write_i(row_return && return_word==2'd3),
                    .data_i(word_data),.data_o(read_data[payload_row][127:96]));
            end else begin:g_register_words
                for(payload_word=0;payload_word<4;payload_word=payload_word+1) begin:g_word
                    rv32_frequency_word_bank #(.WIDTH(32)) word_owner (
                        .clk_i(clock),.write_i(return_valid && return_slot==payload_row && return_word==payload_word),
                        .data_i(read_return_data[(payload_row/4)*32 +: 32]),.data_o(read_data[payload_row][payload_word*32 +: 32]));
                end
            end
        end
        for(payload_row=0;payload_row<WRITE_LINES;payload_row=payload_row+1) begin:g_write_payload_owner
            wire [183:0] packet;
            rv32_frequency_word_bank #(.WIDTH(184)) owner (
                .clk_i(clock),.write_i(take_d_write && write_free==payload_row),
                .data_i({d_req_addr,d_req_id,d_req_data,d_req_mask}),.data_o(packet));
            assign {write_addr[payload_row],write_id[payload_row],write_data[payload_row],write_mask[payload_row]}=packet;
        end
        if(RESPONSE_FIFO_DEPTH==0) begin:g_legacy_payload_owner
            wire read_instruction=fill_read && !query_read_reply_side;
            wire read_data_response=fill_read && query_read_reply_side;
            wire data_write;
            wire [RESPONSE_WIDTH-1:0] data_next;
            rv32_frequency_word_bank #(.WIDTH(RESPONSE_WIDTH)) instruction_owner (
                .clk_i(clock),.write_i(read_instruction),
                .data_i({query_read_reply_addr,query_read_reply_data,query_read_reply_id,query_read_reply_error}),
                .data_o(legacy_i_resp_packet));
            rv32_frequency_event_select #(.WIDTH(RESPONSE_WIDTH),.EVENTS(2)) data_selector (
                .events_i({fill_write,read_data_response}),
                .values_i({query_write_reply_addr,128'b0,query_write_reply_id,query_write_reply_error,
                    query_read_reply_addr,query_read_reply_data,query_read_reply_id,query_read_reply_error}),
                .write_o(data_write),.value_o(data_next));
            rv32_frequency_word_bank #(.WIDTH(RESPONSE_WIDTH)) data_owner (
                .clk_i(clock),.write_i(data_write),.data_i(data_next),.data_o(legacy_d_resp_packet));
        end else begin:g_unused_legacy_payload
            assign legacy_i_resp_packet=0;
            assign legacy_d_resp_packet=0;
        end
    endgenerate

    localparam integer WRITE_DOMAINS=(WRITE_LINES+3)/4;
    localparam integer READ_LIFECYCLE_WIDTH=6+4*RPW;
    localparam integer WRITE_LIFECYCLE_WIDTH=9+4*WPW;
    wire [READ_DOMAINS*READ_LIFECYCLE_WIDTH-1:0] read_lifecycle_views;
    wire [WRITE_DOMAINS*WRITE_LIFECYCLE_WIDTH-1:0] write_lifecycle_views;
    wire write_progress=write_active && (current_mask==0 || write_push);
    rv32_frequency_control_tree #(.WIDTH(READ_LIFECYCLE_WIDTH),.LEAVES(READ_DOMAINS)) read_lifecycle_tree (
        .signal_i({reset,read_allocate,read_free[RPW-1:0],read_push,read_issue_slot,
            read_pop,query_read_return_slot,fill_read,read_reply[RPW-1:0],(rresp!=0)}),.views_o(read_lifecycle_views));
    rv32_frequency_control_tree #(.WIDTH(WRITE_LIFECYCLE_WIDTH),.LEAVES(WRITE_DOMAINS)) write_lifecycle_tree (
        .signal_i({reset,take_d_write,write_free[WPW-1:0],write_progress,write_issue_slot,
            write_pop,query_write_return_slot,fill_write,write_reply[WPW-1:0],(bresp!=0),enabled_words(d_req_mask)}),
        .views_o(write_lifecycle_views));
    genvar lifecycle_row,queue_row;
    generate
        for(lifecycle_row=0;lifecycle_row<READ_LINES;lifecycle_row=lifecycle_row+1) begin:g_read_lifecycle
            wire local_reset,allocate,push,pop,fill,error;
            wire [RPW-1:0] free_slot,issue_slot,return_slot,reply_slot;
            assign {local_reset,allocate,free_slot,push,issue_slot,pop,return_slot,fill,reply_slot,error}=
                read_lifecycle_views[(lifecycle_row/4)*READ_LIFECYCLE_WIDTH +: READ_LIFECYCLE_WIDTH];
            always @(posedge clock) begin
                if(local_reset) read_valid[lifecycle_row]<=1'b0;
                else begin
                    if(allocate && free_slot==lifecycle_row) begin
                        read_valid[lifecycle_row]<=1'b1;
                        read_sent[lifecycle_row]<=0;
                        read_received[lifecycle_row]<=0;
                        read_error[lifecycle_row]<=1'b0;
                    end
                    if(push && issue_slot==lifecycle_row) read_sent[lifecycle_row]<=read_sent[lifecycle_row]+1'b1;
                    if(pop && return_slot==lifecycle_row) begin
                        read_received[lifecycle_row]<=read_received[lifecycle_row]+1'b1;
                        read_error[lifecycle_row]<=read_error[lifecycle_row] || error;
                    end
                    if(fill && reply_slot==lifecycle_row) read_valid[lifecycle_row]<=1'b0;
                end
            end
        end
        for(lifecycle_row=0;lifecycle_row<WRITE_LINES;lifecycle_row=lifecycle_row+1) begin:g_write_lifecycle
            wire local_reset,allocate,progress,pop,fill,error;
            wire [WPW-1:0] free_slot,issue_slot,return_slot,reply_slot;
            wire [2:0] expected;
            assign {local_reset,allocate,free_slot,progress,issue_slot,pop,return_slot,fill,reply_slot,error,expected}=
                write_lifecycle_views[(lifecycle_row/4)*WRITE_LIFECYCLE_WIDTH +: WRITE_LIFECYCLE_WIDTH];
            always @(posedge clock) begin
                if(local_reset) write_valid[lifecycle_row]<=1'b0;
                else begin
                    if(allocate && free_slot==lifecycle_row) begin
                        write_valid[lifecycle_row]<=1'b1;
                        write_sent[lifecycle_row]<=(expected==0)?3'd4:3'd0;
                        write_received[lifecycle_row]<=0;
                        write_expected[lifecycle_row]<=expected;
                        write_error[lifecycle_row]<=1'b0;
                    end
                    if(progress && issue_slot==lifecycle_row) write_sent[lifecycle_row]<=write_sent[lifecycle_row]+1'b1;
                    if(pop && return_slot==lifecycle_row) begin
                        write_received[lifecycle_row]<=write_received[lifecycle_row]+1'b1;
                        write_error[lifecycle_row]<=write_error[lifecycle_row] || error;
                    end
                    if(fill && reply_slot==lifecycle_row) write_valid[lifecycle_row]<=1'b0;
                end
            end
        end
        for(queue_row=0;queue_row<WORD_QUEUE;queue_row=queue_row+1) begin:g_word_queue_metadata
            wire [RPW+1:0] read_metadata;
            rv32_frequency_word_bank #(.WIDTH(RPW+2)) read_owner (
                .clk_i(clock),.write_i(read_push && rq_tail==queue_row),
                .data_i({read_issue_slot,query_read_issue_sent[1:0]}),.data_o(read_metadata));
            assign {rq_slot[queue_row],rq_word[queue_row]}=read_metadata;
            rv32_frequency_word_bank #(.WIDTH(WPW)) write_owner (
                .clk_i(clock),.write_i(write_push && wq_tail==queue_row),
                .data_i(write_issue_slot),.data_o(wq_slot[queue_row]));
        end
    endgenerate

    always @(posedge clock) begin
        if (reset)
        begin
            rq_head <= 0;
            rq_tail <= 0;
            rq_count <= 0;
            wq_head <= 0;
            wq_tail <= 0;
            wq_count <= 0;
            read_active <= 0;
            write_active <= 0;
            aw_done <= 0;
            w_done <= 0;
            read_issue_slot <= 0;
            write_issue_slot <= 0;
            read_cursor <= 0;
            write_cursor <= 0;
            legacy_i_resp_valid <= 0;
            legacy_d_resp_valid <= 0;
            prefer_d_request <= 0;
            prefer_write_reply <= 0;
        end
        else
        begin
            if (take_i || take_d_read)
            begin
                prefer_d_request <= take_i;
            end
            if (!read_active && read_send_found)
            begin
                read_active <= 1;
                read_issue_slot <= read_send[RPW-1:0];
            end
            if (read_push)
            begin
                rq_tail <= rq_tail + 1'b1;
                if (query_read_issue_sent == 3)
                begin
                    read_active <= 0;
                    read_cursor <= read_issue_slot + 1'b1;
                end
            end
            if (read_pop)
            begin
                rq_head <= rq_head + 1'b1;
            end
            case ({read_push, read_pop})
            2'b10: rq_count <= rq_count + 1'b1;
            2'b01: rq_count <= rq_count - 1'b1;
            default: ; // Both/neither operations leave the count unchanged.
            endcase
            if (!write_active && write_send_found)
            begin
                write_active <= 1;
                write_issue_slot <= write_send[WPW-1:0];
                aw_done <= 0;
                w_done <= 0;
            end
            if (aw_fire)
                aw_done <= 1;
            if (w_fire)
                w_done <= 1;
            if (write_active && (current_mask == 0 || write_push))
            begin
                aw_done <= 0;
                w_done <= 0;
                if (query_write_issue_sent == 3)
                begin
                    write_active <= 0;
                    write_cursor <= write_issue_slot + 1'b1;
                end
            end
            if (write_push)
            begin
                wq_tail <= wq_tail + 1'b1;
            end
            if (write_pop)
            begin
                wq_head <= wq_head + 1'b1;
            end
            case ({write_push, write_pop})
            2'b10: wq_count <= wq_count + 1'b1;
            2'b01: wq_count <= wq_count - 1'b1;
            default: ; // Both/neither operations leave the count unchanged.
            endcase
            if (i_resp_valid && i_resp_ready)
                legacy_i_resp_valid <= 0;
            if (d_resp_valid && d_resp_ready)
                legacy_d_resp_valid <= 0;
            if (fill_read)
            begin
                if (query_read_reply_side)
                begin
                    legacy_d_resp_valid <= 1;
                    prefer_write_reply <= 1;
                end
                else
                begin
                    legacy_i_resp_valid <= 1;
                end
            end
            if (fill_write)
            begin
                legacy_d_resp_valid <= 1;
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
