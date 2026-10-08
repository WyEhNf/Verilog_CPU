`timescale 1ns/1ps
`include "rv32im_defs.vh"

// A small direct-mapped L0 over the immutable instruction-line interface.
// It has one registered response, at most one primary miss in flight, and
// accepts a replacement request on the same edge as a consumed response.
// There is no combinational path from a new request to response validity.
module rv32_instruction_line_filter #(
    parameter integer LINES=16,EPOCH_WIDTH=4,DATA_SRAM=0,
    parameter integer OWNER_PAYLOAD_SELECT=0,
    parameter integer INDEX_WIDTH=$clog2(LINES),
    parameter integer TAG_BITS=28-INDEX_WIDTH
) (
    input wire clk_i,reset_i,
    input wire [EPOCH_WIDTH-1:0] current_epoch_i,
    input wire if_req_valid_i,
    output wire if_req_ready_o,
    input wire [31:0] if_req_pc_i,
    input wire [EPOCH_WIDTH-1:0] if_req_epoch_i,
    output wire if_resp_valid_o,
    input wire if_resp_ready_i,
    output wire [31:0] if_resp_pc_o,if_resp_line_addr_o,
    output wire [127:0] if_resp_line_data_o,
    output wire [EPOCH_WIDTH-1:0] if_resp_epoch_o,
    output wire if_resp_error_o,
    output wire primary_req_valid_o,
    input wire primary_req_ready_i,
    output wire [31:0] primary_req_pc_o,
    output wire [EPOCH_WIDTH-1:0] primary_req_epoch_o,
    input wire primary_resp_valid_i,
    output wire primary_resp_ready_o,
    input wire [31:0] primary_resp_pc_i,primary_resp_line_addr_i,
    input wire [127:0] primary_resp_line_data_i,
    input wire [EPOCH_WIDTH-1:0] primary_resp_epoch_i,
    input wire primary_resp_error_i
);
    reg [LINES-1:0] valid;
    wire [TAG_BITS-1:0] row_tags [0:LINES-1];
    wire [LINES*128-1:0] row_lines;
    wire unused_row_lines_bits = &{1'b0, row_lines};

    wire [LINES-1:0] hits;
    wire [LINES*28-1:0] request_line_views;
    rv32_frequency_control_tree #(.WIDTH(28),.LEAVES(LINES)) request_views (
        .signal_i(if_req_pc_i[31:4]),.views_o(request_line_views));
    wire [127:0] hit_line;
    wire unused_hit_line_bits = &{1'b0, hit_line};

    generate if(DATA_SRAM==0) begin:g_register_line_read
wire  unused_line_select_write_o;
rv32_frequency_event_select #(.WIDTH(128),.EVENTS(LINES),.PRIORITY(0)) line_select (
            .events_i(hits),.values_i(row_lines),.write_o(unused_line_select_write_o),.value_o(hit_line));
    end else begin:g_no_register_line_read
        assign hit_line=128'b0;
    end endgenerate
    wire hit=|hits;

    reg fast_valid,miss_pending;
    wire [31:0] fast_pc,pending_pc;
    wire [EPOCH_WIDTH-1:0] fast_epoch,pending_epoch;
    wire [127:0] fast_line;
    wire fast_live=fast_valid && fast_epoch==current_epoch_i;
    wire miss_live=miss_pending && pending_epoch==current_epoch_i;
    wire primary_live=miss_live && primary_resp_valid_i &&
        primary_resp_epoch_i==pending_epoch && primary_resp_pc_i==pending_pc;
    wire release_miss=primary_live && if_resp_ready_i;
    wire fill=!reset_i && primary_live && if_resp_ready_i && !primary_resp_error_i &&
        primary_resp_line_addr_i=={primary_resp_pc_i[31:4],4'b0};
    // Independent low-index banks allow a fill and next hit together. Only
    // a hit in the actual write bank waits, retaining the original old-line
    // semantics when that row is being replaced.
    localparam integer SRAM_BANKS=(LINES<4)?LINES:4;
    localparam integer SRAM_BANK_WIDTH=$clog2(SRAM_BANKS);
    localparam integer SRAM_DEPTH=LINES/SRAM_BANKS;
    localparam integer SRAM_ADDR_WIDTH=(SRAM_DEPTH<=1)?1:$clog2(SRAM_DEPTH);
    wire hit_fill_conflict=(DATA_SRAM!=0) && fill && hit &&
        (if_req_pc_i[4 +: SRAM_BANK_WIDTH]==primary_resp_line_addr_i[4 +: SRAM_BANK_WIDTH]);
    wire fast_slot_free=!fast_valid || !fast_live || if_resp_ready_i;
    wire can_start=!reset_i && (!miss_live || release_miss) && fast_slot_free && !hit_fill_conflict;
    assign if_req_ready_o=can_start && (hit || primary_req_ready_i);
    wire request_fire=if_req_valid_i && if_req_ready_o;
    wire accept_hit=request_fire && hit && if_req_epoch_i==current_epoch_i;
    wire accept_miss=request_fire && !hit;
    assign primary_req_valid_o=if_req_valid_i && can_start && !hit;
    assign primary_req_pc_o=if_req_pc_i;
    assign primary_req_epoch_o=if_req_epoch_i;
    // Unexpected or epoch-stale primary outputs drain without publishing.
    // A live primary response obeys the original frontend backpressure.
    assign primary_resp_ready_o=!reset_i && (!primary_live || if_resp_ready_i);
    assign if_resp_valid_o=!reset_i && (fast_live || primary_live);
    localparam integer RESPONSE_WIDTH=65+128+EPOCH_WIDTH;
wire  unused_response_select_write_o;
rv32_frequency_event_select #(.WIDTH(RESPONSE_WIDTH),.EVENTS(2),.PRIORITY(0)) response_select (
        // fast_valid and miss_pending are mutually exclusive registered owners.
        // Epoch qualification still controls response VALID and all handshakes.
        // Unqualified payloads are observable only when the original live gate
        // allows publication, when this selects precisely the same owner.
        .events_i((OWNER_PAYLOAD_SELECT!=0)?{fast_valid,!fast_valid}:{fast_live,primary_live}),
        .values_i({fast_pc,{fast_pc[31:4],4'b0},fast_line,fast_epoch,1'b0,
            primary_resp_pc_i,primary_resp_line_addr_i,primary_resp_line_data_i,
            primary_resp_epoch_i,primary_resp_error_i}),.write_o(unused_response_select_write_o),
        .value_o({if_resp_pc_o,if_resp_line_addr_o,if_resp_line_data_o,if_resp_epoch_o,if_resp_error_o}));
    generate if(DATA_SRAM!=0) begin:g_sram_lines
        wire [SRAM_BANKS*128-1:0] bank_data;
        wire [SRAM_BANKS-1:0] response_banks;
        rv32_frequency_word_bank #(.WIDTH(32+EPOCH_WIDTH)) fast_identity (
            .clk_i(clk_i),.write_i(accept_hit),.data_i({if_req_pc_i,if_req_epoch_i}),
            .data_o({fast_pc,fast_epoch}));
        for(genvar bank=0;bank<SRAM_BANKS;bank=bank+1) begin:g_bank
            localparam [SRAM_BANK_WIDTH-1:0] BANK=bank;
            wire bank_fill=fill && primary_resp_line_addr_i[4 +: SRAM_BANK_WIDTH]==BANK;
            wire bank_hit=accept_hit && if_req_pc_i[4 +: SRAM_BANK_WIDTH]==BANK;
            wire unused_bank_hit_bits = &{1'b0, bank_hit};

            // FakeRAM invalidates rdata on idle/write edges. Reread a held
            // response on every stalled edge instead of assuming Q holds.
            // A live primary fill requires ready, so cannot overwrite a
            // backpressured fast response.
            wire bank_hold=fast_live && !fast_slot_free && fast_pc[4 +: SRAM_BANK_WIDTH]==BANK;
            // Hold chooses the saved PC; otherwise an offered request PC is
            // safe before its tag/hit acceptance. Extra speculative reads do
            // not publish a response: fast_identity/valid still use accept_hit.
            wire hold_read=fast_live && !fast_slot_free;
            wire offered_read=if_req_valid_i && fast_slot_free &&
                if_req_pc_i[4 +: SRAM_BANK_WIDTH]==BANK;
            wire [INDEX_WIDTH-1:0] read_index=hold_read?
                fast_pc[4 +: INDEX_WIDTH]:if_req_pc_i[4 +: INDEX_WIDTH];
            wire [SRAM_ADDR_WIDTH-1:0] address=bank_fill?
                SRAM_ADDR_WIDTH'(primary_resp_line_addr_i[4 +: INDEX_WIDTH] >> SRAM_BANK_WIDTH):
                SRAM_ADDR_WIDTH'(read_index >> SRAM_BANK_WIDTH);
            localparam integer COMMAND_WIDTH=SRAM_ADDR_WIDTH+2;
            wire [8*COMMAND_WIDTH-1:0] commands;
            rv32_frequency_control_tree #(.WIDTH(COMMAND_WIDTH),.LEAVES(8)) command_tree (
                .signal_i({!reset_i && (bank_fill || offered_read || bank_hold),bank_fill,address}),
                .views_o(commands));
            // Same eight physical4x16 macros per bank as the former128-bit
            // wrapper expansion; each priced command leaf drives one macro.
            for(genvar data_lane=0;data_lane<8;data_lane=data_lane+1) begin:g_data_lane
                wire enable,write;
                wire [SRAM_ADDR_WIDTH-1:0] lane_address;
                assign {enable,write,lane_address}=commands[data_lane*COMMAND_WIDTH +: COMMAND_WIDTH];
                sram_fakeram #(.DEPTH(SRAM_DEPTH),.WIDTH(16),.WRITE_GRANULARITY(16)) data (
                    .clk(clk_i),.en(enable),.we(write),.wmask(1'b1),.addr(lane_address),
                    .wdata(primary_resp_line_data_i[data_lane*16 +: 16]),
                    .rdata(bank_data[bank*128+data_lane*16 +: 16]));
            end
            assign response_banks[bank]=fast_live && fast_pc[4 +: SRAM_BANK_WIDTH]==BANK;
        end
wire  unused_response_read_write_o;
rv32_frequency_event_select #(.WIDTH(128),.EVENTS(SRAM_BANKS),.PRIORITY(0)) response_read (
            .events_i(response_banks),.values_i(bank_data),.write_o(unused_response_read_write_o),.value_o(fast_line));
    end else begin:g_register_lines
        rv32_frequency_word_bank #(.WIDTH(32+EPOCH_WIDTH+128)) fast_response (
            .clk_i(clk_i),.write_i(accept_hit),.data_i({if_req_pc_i,if_req_epoch_i,hit_line}),
            .data_o({fast_pc,fast_epoch,fast_line}));
    end endgenerate
    rv32_frequency_word_bank #(.WIDTH(32+EPOCH_WIDTH)) miss_identity (
        .clk_i(clk_i),.write_i(accept_miss),.data_i({if_req_pc_i,if_req_epoch_i}),
        .data_o({pending_pc,pending_epoch}));

    genvar row;
    generate for(row=0;row<LINES;row=row+1) begin:g_row
        localparam [INDEX_WIDTH-1:0] ROW=row;
        wire [27:0] request_line=request_line_views[row*28 +: 28];
        wire [TAG_BITS-1:0] row_tag=row_tags[row];
        assign hits[row]=valid[row] && request_line[INDEX_WIDTH-1:0]==ROW &&
            request_line[27:INDEX_WIDTH]==row_tag;

        wire row_write=fill && primary_resp_line_addr_i[4 +: INDEX_WIDTH]==ROW;
        if(DATA_SRAM!=0) begin:g_sram_tag
            rv32_frequency_word_bank #(.WIDTH(TAG_BITS)) tag (
                .clk_i(clk_i),.write_i(row_write),
                .data_i(primary_resp_line_addr_i[31:4+INDEX_WIDTH]),.data_o(row_tags[row]));
            assign row_lines[row*128 +: 128]=128'b0;
        end else begin:g_register_payload
            wire [TAG_BITS+128-1:0] payload_word;
            rv32_frequency_word_bank #(.WIDTH(TAG_BITS+128)) payload (
                .clk_i(clk_i),.write_i(row_write),
                .data_i({primary_resp_line_addr_i[31:4+INDEX_WIDTH],primary_resp_line_data_i}),
                .data_o(payload_word));
            assign row_tags[row]=payload_word[128 +: TAG_BITS];
            assign row_lines[row*128 +: 128]=payload_word[127:0];
        end
        always @(posedge clk_i) begin
            if(reset_i)
                valid[row]<=1'b0;
            else
                if(row_write)
                    valid[row]<=1'b1;
        end
    end endgenerate
    always @(posedge clk_i) begin
        if(reset_i)
        begin
            fast_valid<=1'b0;
            miss_pending<=1'b0;
        end
        else
        begin
            if(fast_slot_free)
                fast_valid<=1'b0;
            if(accept_hit)
                fast_valid<=1'b1;
            if(!miss_live || release_miss)
                miss_pending<=1'b0;
            if(accept_miss)
                miss_pending<=1'b1;
        end
    end
    always @(posedge clk_i) begin
        if(OWNER_PAYLOAD_SELECT!=0 && !reset_i && fast_valid && miss_pending)
            $fatal(1,"Instruction response owners overlap");
    end
    initial begin
        if(LINES<2 || LINES>32 || (LINES & (LINES-1))!=0)
            $fatal(1,"Instruction line filter needs a power-of-two line count in 2..32");
    end
endmodule
