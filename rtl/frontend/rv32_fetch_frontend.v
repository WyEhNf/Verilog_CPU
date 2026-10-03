`timescale 1ns/1ps
`include "rv32im_defs.vh"

/* verilator lint_off WIDTHEXPAND */
/* verilator lint_off WIDTHTRUNC */
/* verilator lint_off BLKSEQ */

// Frontend controller between the instruction cache and decode/rename.
// Predictor metadata is carried with each returned instruction so this block
// can be verified independently from predictor table state.
module rv32_fetch_frontend #(
    parameter integer FE_WIDTH = `RV32IM_FE_WIDTH_DEFAULT,
    parameter integer FQ_DEPTH = 16,
    parameter integer EPOCH_WIDTH = `RV32IM_EPOCH_WIDTH,
    parameter integer NARROW_OCCUPANCY = 0, LEGACY_SENTINEL_HALT = 0,
    parameter integer QUEUE_PAYLOAD_BANKS = 0,
    parameter integer PREDICTOR_META = 0
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         redirect_valid_i,
    input  wire [31:0]                  redirect_pc_i,
    input  wire [EPOCH_WIDTH-1:0]       redirect_epoch_i,
    input  wire                         stop_i,
    input  wire                         error_i,

    output wire                         if_req_valid_o,
    input  wire                         if_req_ready_i,
    output wire [31:0]                  if_req_pc_o,
    output wire [EPOCH_WIDTH-1:0]       if_req_epoch_o,

    input  wire                         if_resp_valid_i,
    output wire                         if_resp_ready_o,
    input  wire [31:0]                  if_resp_pc_i,
    input  wire [31:0]                  if_resp_line_addr_i,
    input  wire [127:0]                 if_resp_line_data_i,
    input  wire [EPOCH_WIDTH-1:0]       if_resp_epoch_i,
    input  wire                         if_resp_error_i,
    input  wire [FE_WIDTH-1:0]          if_resp_pred_taken_i,
    input  wire [FE_WIDTH*32-1:0]       if_resp_pred_target_i,
    input  wire [FE_WIDTH*2-1:0]        if_resp_pred_kind_i,
    input  wire [FE_WIDTH-1:0]          if_resp_pred_btb_hit_i,
    input  wire [FE_WIDTH*16-1:0]       if_resp_pred_metadata_i,
    output reg  [FE_WIDTH*16-1:0]       fetch_pred_metadata_o,

    output reg  [FE_WIDTH-1:0]          fetch_valid_o,
    input  wire [FE_WIDTH-1:0]           fetch_ready_i,
    output reg  [FE_WIDTH*`RV32IM_FETCH_PACKET_WIDTH-1:0] fetch_packet_o,
    output wire [EPOCH_WIDTH-1:0]       current_epoch_o,
    output wire                         frozen_o,
    output reg                          event_fetch_o,
    output reg                          event_redirect_o,
    output reg                          event_stall_o
);
    localparam integer PACKET_WIDTH = `RV32IM_FETCH_PACKET_WIDTH;
    localparam integer PTR_WIDTH = (FQ_DEPTH <= 2) ? 1 : $clog2(FQ_DEPTH);

    reg [31:0] pc_reg;
    reg [EPOCH_WIDTH-1:0] epoch_reg;
    reg req_pending_reg;
    reg frozen_reg;
    reg [PTR_WIDTH-1:0] head_reg, tail_reg;
    localparam integer COUNT_WIDTH = (NARROW_OCCUPANCY != 0) ?
        ((FQ_DEPTH <= 1) ? 1 : $clog2(FQ_DEPTH + 1)) : 32;
    reg [COUNT_WIDTH-1:0] count_storage_reg;
    wire signed [31:0] count_reg = {{(32-COUNT_WIDTH){1'b0}}, count_storage_reg};

    wire [31:0] fq_pc [0:FQ_DEPTH-1];
    reg [31:0] legacy_fq_pc [0:FQ_DEPTH-1];
    wire [31:0] fq_inst [0:FQ_DEPTH-1];
    reg [31:0] legacy_fq_inst [0:FQ_DEPTH-1];
    wire fq_pred_taken [0:FQ_DEPTH-1];
    reg legacy_fq_pred_taken [0:FQ_DEPTH-1];
    wire [31:0] fq_pred_target [0:FQ_DEPTH-1];
    reg [31:0] legacy_fq_pred_target [0:FQ_DEPTH-1];
    wire [1:0] fq_pred_kind [0:FQ_DEPTH-1];
    reg [1:0] legacy_fq_pred_kind [0:FQ_DEPTH-1];
    wire fq_pred_btb_hit [0:FQ_DEPTH-1];
    reg legacy_fq_pred_btb_hit [0:FQ_DEPTH-1];
    wire [EPOCH_WIDTH-1:0] fq_epoch [0:FQ_DEPTH-1];
    reg [EPOCH_WIDTH-1:0] legacy_fq_epoch [0:FQ_DEPTH-1];
    wire [15:0] fq_pred_metadata [0:FQ_DEPTH-1];
    reg [15:0] legacy_fq_pred_metadata [0:FQ_DEPTH-1];

    reg [FE_WIDTH-1:0] bundle_pred_taken;
    reg [FE_WIDTH-1:0] bundle_pred_btb_hit;
    reg [FE_WIDTH*32-1:0] bundle_pred_target;
    reg [FE_WIDTH*2-1:0] bundle_pred_kind;
    reg [FE_WIDTH*32-1:0] bundle_inst;
    reg [FE_WIDTH*32-1:0] bundle_pc;
    reg [EPOCH_WIDTH-1:0] bundle_epoch;
    integer bundle_count;
    integer enq_count;
    integer deq_count;
    integer i;
    integer b;
    integer j;
    integer k;
    integer write_index;
    integer word_index;
    reg [31:0] next_pc_comb;
    reg bundle_freeze;
    reg freeze_after_response;
    reg req_fire;
    reg resp_fire;

    // Payload may be written on an invalidating edge: occupancy discards
    // those rows. Architectural response acceptance remains redirect-qualified.
    wire payload_response_write = if_resp_valid_i && response_live && queue_space;
    wire queue_space = (count_reg + bundle_count <= FQ_DEPTH);
    wire response_live = (if_resp_epoch_i == epoch_reg) &&
                         (if_resp_line_addr_i == {if_resp_pc_i[31:4], 4'b0000});

    // Decode the queue head once, before selecting any packet bits. Four
    // dynamic array reads otherwise map to binary mux trees whose head bits
    // directly drive thousands of gates. Rotating the one-hot row selection
    // implements exactly head+lane modulo FQ_DEPTH, without another cycle.
    wire [FQ_DEPTH-1:0] head_row_select;
    wire [FE_WIDTH*PACKET_WIDTH-1:0] queue_read_packets;
    wire [FE_WIDTH*16-1:0] queue_read_metadata;
    genvar read_row, read_lane;
    generate
        for (read_row = 0; read_row < FQ_DEPTH; read_row = read_row + 1) begin : g_head_decode
            localparam [PTR_WIDTH-1:0] ROW = read_row;
            assign head_row_select[read_row] = (head_reg == ROW);
        end
        for (read_lane = 0; read_lane < FE_WIDTH; read_lane = read_lane + 1) begin : g_packet_read
            reg [PACKET_WIDTH-1:0] packet;
            reg [15:0] metadata;
            integer row;
            always @* begin
                packet = {PACKET_WIDTH{1'b0}};
                metadata = 16'b0;
                for (row = 0; row < FQ_DEPTH; row = row + 1) begin
                    packet = packet |
                        ({PACKET_WIDTH{head_row_select[(row+FQ_DEPTH-read_lane)%FQ_DEPTH]}} &
                         `RV32IM_FETCH_PACKET_PACK(fq_pc[row], fq_inst[row],
                            fq_pred_taken[row], fq_pred_target[row], fq_pred_kind[row],
                            fq_pred_btb_hit[row], fq_epoch[row]));
                    if (PREDICTOR_META != 0)
                        metadata = metadata | ({16{head_row_select[(row+FQ_DEPTH-read_lane)%FQ_DEPTH]}} &
                            fq_pred_metadata[row]);
                end
            end
            assign queue_read_packets[read_lane*PACKET_WIDTH +: PACKET_WIDTH] = packet;
            assign queue_read_metadata[read_lane*16 +: 16] = metadata;
        end
    endgenerate

    localparam integer PAYLOAD_WIDTH = 116 + EPOCH_WIDTH;
    wire [FE_WIDTH*PAYLOAD_WIDTH-1:0] payload_write_packets;
    wire [FE_WIDTH-1:0] payload_write_valid;
    wire [FE_WIDTH*PTR_WIDTH-1:0] payload_write_slots;
    genvar payload_lane, payload_row;
    generate
        for(payload_lane=0;payload_lane<FE_WIDTH;payload_lane=payload_lane+1) begin:g_payload_lane
            assign payload_write_packets[payload_lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH] = {
                bundle_pc[payload_lane*32 +: 32], bundle_inst[payload_lane*32 +: 32],
                bundle_pred_taken[payload_lane], bundle_pred_target[payload_lane*32 +: 32],
                bundle_pred_kind[payload_lane*2 +: 2], bundle_pred_btb_hit[payload_lane], bundle_epoch,
                ((PREDICTOR_META != 0) ? if_resp_pred_metadata_i[payload_lane*16 +: 16] : 16'b0)};
            assign payload_write_valid[payload_lane]=payload_response_write && (payload_lane<bundle_count);
            assign payload_write_slots[payload_lane*PTR_WIDTH +: PTR_WIDTH]=tail_reg+payload_lane;
        end
        for(payload_row=0;payload_row<FQ_DEPTH;payload_row=payload_row+1) begin:g_payload_row
            if(QUEUE_PAYLOAD_BANKS != 0) begin:g_banks
                rv32_frontend_queue_payload_bank #(.WIDTH(PAYLOAD_WIDTH), .FE_WIDTH(FE_WIDTH),
                    .PTR_WIDTH(PTR_WIDTH), .ROW_ID(payload_row)) packet_bank (
                    .clk_i(clk_i), .reset_i(1'b0), .redirect_i(1'b0),
                    .write_valid_i(payload_write_valid), .write_slots_i(payload_write_slots),
                    .write_data_i(payload_write_packets),
                    .data_o({fq_pc[payload_row], fq_inst[payload_row], fq_pred_taken[payload_row],
                        fq_pred_target[payload_row], fq_pred_kind[payload_row], fq_pred_btb_hit[payload_row],
                        fq_epoch[payload_row], fq_pred_metadata[payload_row]}));
            end else begin:g_legacy
                assign fq_pc[payload_row]=legacy_fq_pc[payload_row];
                assign fq_inst[payload_row]=legacy_fq_inst[payload_row];
                assign fq_pred_taken[payload_row]=legacy_fq_pred_taken[payload_row];
                assign fq_pred_target[payload_row]=legacy_fq_pred_target[payload_row];
                assign fq_pred_kind[payload_row]=legacy_fq_pred_kind[payload_row];
                assign fq_pred_btb_hit[payload_row]=legacy_fq_pred_btb_hit[payload_row];
                assign fq_epoch[payload_row]=legacy_fq_epoch[payload_row];
                assign fq_pred_metadata[payload_row]=legacy_fq_pred_metadata[payload_row];
            end
        end
    endgenerate

    assign current_epoch_o = epoch_reg;
    assign frozen_o = frozen_reg;
    // A consumed response determines the next predicted PC combinationally.
    // Reuse that same edge to launch the next cache lookup, eliminating the
    // otherwise mandatory idle cycle between warm line requests.
    wire response_can_chain = if_resp_valid_i && if_resp_ready_o &&
                              !freeze_after_response && !stop_i && !error_i;
    assign if_req_valid_o = !reset_i && !frozen_reg && !stop_i && !error_i &&
                            (!req_pending_reg || response_can_chain);
    assign if_req_pc_o = response_can_chain ? next_pc_comb : pc_reg;
    assign if_req_epoch_o = epoch_reg;
    assign if_resp_ready_o = !reset_i && !redirect_valid_i && response_live && queue_space;

    always @* begin
        // Form the largest contiguous bundle available in this returned line.
        bundle_pred_taken = {FE_WIDTH{1'b0}};
        bundle_pred_btb_hit = {FE_WIDTH{1'b0}};
        bundle_pred_target = {FE_WIDTH*32{1'b0}};
        bundle_pred_kind = {FE_WIDTH*2{1'b0}};
        bundle_inst = {FE_WIDTH*32{1'b0}};
        bundle_pc = {FE_WIDTH*32{1'b0}};
        bundle_epoch = if_resp_epoch_i;
        bundle_count = 0;
        next_pc_comb = if_resp_pc_i + 32'd4;
        bundle_freeze = if_resp_error_i;
        freeze_after_response = if_resp_error_i;
        word_index = if_resp_pc_i[3:2];
        for (b = 0; b < FE_WIDTH; b = b + 1) begin
            if ((word_index + b) < 4 && !bundle_freeze) begin
                bundle_inst[b*32 +: 32] = if_resp_line_data_i >> ((word_index+b)*32);
                bundle_pc[b*32 +: 32] = if_resp_pc_i + (b*32'd4);
                bundle_pred_taken[b] = if_resp_pred_taken_i[b];
                bundle_pred_btb_hit[b] = if_resp_pred_btb_hit_i[b];
                bundle_pred_target[b*32 +: 32] = if_resp_pred_target_i[b*32 +: 32];
                bundle_pred_kind[b*2 +: 2] = if_resp_pred_kind_i[b*2 +: 2];
                bundle_count = bundle_count + 1;
                next_pc_comb = if_resp_pc_i + ((b+1)*32'd4);
                if (if_resp_pred_taken_i[b]) begin
                    next_pc_comb = if_resp_pred_target_i[b*32 +: 32];
                    bundle_freeze = 1'b1;
                end
                if ((LEGACY_SENTINEL_HALT != 0) &&
                    ((if_resp_line_data_i >> ((word_index+b)*32)) == 32'h0ff00513)) begin
                    bundle_freeze = 1'b1;
                    freeze_after_response = 1'b1;
                end
            end
        end
        if (if_resp_error_i)
            bundle_count = 0;
        enq_count = (if_resp_valid_i && if_resp_ready_o) ? bundle_count : 0;
    end

    always @* begin
        fetch_valid_o = {FE_WIDTH{1'b0}};
        fetch_packet_o = {(FE_WIDTH*PACKET_WIDTH){1'b0}};
        fetch_pred_metadata_o = {FE_WIDTH*16{1'b0}};
        deq_count = 0;
        for (j = 0; j < FE_WIDTH; j = j + 1) begin
            if (j < count_reg) begin
                fetch_valid_o[j] = 1'b1;
                fetch_packet_o[j*PACKET_WIDTH +: PACKET_WIDTH] =
                    queue_read_packets[j*PACKET_WIDTH +: PACKET_WIDTH];
                fetch_pred_metadata_o[j*16 +: 16] = queue_read_metadata[j*16 +: 16];
            end
            if ((j < count_reg) && (deq_count == j) && fetch_ready_i[j])
                deq_count = deq_count + 1;
        end
    end

    always @* begin
        req_fire = if_req_valid_o && if_req_ready_i;
        resp_fire = if_resp_valid_i && if_resp_ready_o;
    end

    always @(posedge clk_i) begin
        if (reset_i) begin
            pc_reg <= 32'd0;
            epoch_reg <= {EPOCH_WIDTH{1'b0}};
            req_pending_reg <= 1'b0;
            frozen_reg <= 1'b0;
            head_reg <= {PTR_WIDTH{1'b0}};
            tail_reg <= {PTR_WIDTH{1'b0}};
            count_storage_reg <= 0;
            event_fetch_o <= 1'b0;
            event_redirect_o <= 1'b0;
            event_stall_o <= 1'b0;
            if (QUEUE_PAYLOAD_BANKS == 0) begin
            for (k = 0; k < FQ_DEPTH; k = k + 1) begin
                legacy_fq_pc[k] <= 32'd0;
                legacy_fq_inst[k] <= 32'd0;
                legacy_fq_pred_taken[k] <= 1'b0;
                legacy_fq_pred_target[k] <= 32'd0;
                legacy_fq_pred_kind[k] <= `RV32IM_PRED_NONE;
                legacy_fq_pred_btb_hit[k] <= 1'b0;
                legacy_fq_epoch[k] <= {EPOCH_WIDTH{1'b0}};
                legacy_fq_pred_metadata[k] <= 16'b0;
            end
            end
        end else begin
            event_fetch_o <= (deq_count != 0);
            event_redirect_o <= redirect_valid_i;
            event_stall_o <= (count_reg != 0) && (deq_count == 0);

            if (redirect_valid_i) begin
                pc_reg <= redirect_pc_i;
                epoch_reg <= redirect_epoch_i;
                req_pending_reg <= 1'b0;
                frozen_reg <= 1'b0;
                head_reg <= {PTR_WIDTH{1'b0}};
                tail_reg <= {PTR_WIDTH{1'b0}};
                count_storage_reg <= 0;
            end else begin
                if (resp_fire) begin
                    pc_reg <= next_pc_comb;
                    if (freeze_after_response || stop_i || error_i)
                        frozen_reg <= 1'b1;
                end
                if (stop_i || error_i)
                    frozen_reg <= 1'b1;

                case ({req_fire, resp_fire})
                    2'b10: req_pending_reg <= 1'b1;
                    2'b01: req_pending_reg <= 1'b0;
                    2'b11: req_pending_reg <= 1'b1;
                    default: req_pending_reg <= req_pending_reg;
                endcase

                if (resp_fire) begin
                    if (QUEUE_PAYLOAD_BANKS == 0) begin
                    for (i = 0; i < FE_WIDTH; i = i + 1) begin
                        if (i < bundle_count) begin
                            write_index = tail_reg + i;
                            if (write_index >= FQ_DEPTH)
                                write_index = write_index - FQ_DEPTH;
                            legacy_fq_pc[write_index] <= bundle_pc[i*32 +: 32];
                            legacy_fq_inst[write_index] <= bundle_inst[i*32 +: 32];
                            legacy_fq_pred_taken[write_index] <= bundle_pred_taken[i];
                            legacy_fq_pred_target[write_index] <= bundle_pred_target[i*32 +: 32];
                            legacy_fq_pred_kind[write_index] <= bundle_pred_kind[i*2 +: 2];
                            legacy_fq_pred_btb_hit[write_index] <= bundle_pred_btb_hit[i];
                            legacy_fq_epoch[write_index] <= bundle_epoch;
                            legacy_fq_pred_metadata[write_index] <= (PREDICTOR_META != 0) ?
                                if_resp_pred_metadata_i[i*16 +: 16] : 16'b0;
                        end
                    end
                    end
                    tail_reg <= tail_reg + bundle_count;
                end
                head_reg <= head_reg + deq_count;
                count_storage_reg <= count_reg + enq_count - deq_count;
            end
        end
    end

    initial begin
        if(QUEUE_PAYLOAD_BANKS != 0 && QUEUE_PAYLOAD_BANKS != 1)
            $fatal(1, "Invalid frontend payload bank mode");
        if ((FE_WIDTH != 1) && (FE_WIDTH != 2) && (FE_WIDTH != 4)) begin
            $display("ERROR: invalid FE_WIDTH=%0d; expected 1, 2, or 4", FE_WIDTH);
            $finish;
        end
        if ((FQ_DEPTH < FE_WIDTH) || ((FQ_DEPTH & (FQ_DEPTH - 1)) != 0)) begin
            $display("ERROR: invalid FQ_DEPTH=%0d; expected power of two >= FE_WIDTH", FQ_DEPTH);
            $finish;
        end
    end
endmodule

// Each bank owns an actual queue field and its local write selection.
(* keep_hierarchy = 1 *)
module rv32_frontend_queue_payload_bank #(
    parameter integer WIDTH=32,
    parameter integer FE_WIDTH=4,
    parameter integer PTR_WIDTH=4,
    parameter integer ROW_ID=0
) (
    input wire clk_i, reset_i, redirect_i,
    input wire [FE_WIDTH-1:0] write_valid_i,
    input wire [FE_WIDTH*PTR_WIDTH-1:0] write_slots_i,
    input wire [FE_WIDTH*WIDTH-1:0] write_data_i,
    output reg [WIDTH-1:0] data_o
);
    wire [FE_WIDTH-1:0] selected, granted;
    wire [FE_WIDTH-1:0] granted_local;
    rv32_frequency_control_tree #(.WIDTH(FE_WIDTH),.LEAVES(1)) write_tree (
        .signal_i(granted),.views_o(granted_local));
    genvar lane;
    generate for(lane=0;lane<FE_WIDTH;lane=lane+1) begin:g_lane
        assign selected[lane]=write_valid_i[lane] &&
            write_slots_i[lane*PTR_WIDTH +: PTR_WIDTH]==ROW_ID;
        if(lane==FE_WIDTH-1) assign granted[lane]=selected[lane];
        else assign granted[lane]=selected[lane] && !(|selected[FE_WIDTH-1:lane+1]);
    end endgenerate
    wire write_local;
    rv32_frequency_control_tree #(.LEAVES(1)) write_enable_tree (
        .signal_i(|granted_local),.views_o(write_local));
    reg [WIDTH-1:0] packet;
    integer source_lane;
    always @* begin
        packet=0;
        for(source_lane=0;source_lane<FE_WIDTH;source_lane=source_lane+1)
            packet=packet | ({WIDTH{granted_local[source_lane]}} & write_data_i[source_lane*WIDTH +: WIDTH]);
    end
    always @(posedge clk_i) begin
        // Empty/invalid rows have no architectural payload. Do not broadcast
        // reset or redirect to the stored data; queue control owns validity.
        if(write_local) data_o<=packet;
    end
endmodule
