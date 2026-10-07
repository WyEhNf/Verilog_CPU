`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Functional storage row: owns all MSHR state and decodes updates locally.
module rv32_icache_mshr_state_bank #(
    parameter integer EPOCH_WIDTH = 4,
    parameter integer ROW = 0
) (
    input wire clk_i,
    input wire reset_i,
    input wire [EPOCH_WIDTH-1:0] current_epoch_i,
    input wire request_fire_i,
    input wire request_hit_i,
    input wire request_match_found_i,
    input wire [31:0] request_match_index_i,
    input wire [31:0] free_index_i,
    input wire [31:0] if_req_pc_i,
    input wire [31:0] request_line_i,
    input wire [EPOCH_WIDTH-1:0] if_req_epoch_i,
    input wire prefetch_step_allocates_i,
    input wire prefetch_control_stream_i,
    input wire [31:0] prefetch_next_line_i,
    input wire [EPOCH_WIDTH-1:0] prefetch_epoch_i,
    input wire mem_req_valid_i,
    input wire mem_req_ready_i,
    input wire [31:0] send_index_i,
    input wire mem_resp_valid_i,
    input wire mem_resp_ready_i,
    input wire response_target_found_i,
    input wire [31:0] response_index_i,
    input wire control_target_allocate_i,
    input wire [31:0] control_target_i,
    output reg valid_o,
    output reg sent_o,
    output reg prefetch_o,
    output reg control_prefetch_o,
    output wire [31:0] pc_o,
    output wire [31:0] line_o,
    output wire [EPOCH_WIDTH-1:0] demand_epoch_o,
    output wire [EPOCH_WIDTH-1:0] txn_epoch_o
);

    localparam integer MSHR_PAYLOAD_WIDTH=32+EPOCH_WIDTH;
    wire enabled=!reset_i;
    wire demand=enabled && request_fire_i && !request_hit_i;
    wire demand_match=demand && request_match_found_i && request_match_index_i==ROW;
    wire demand_new=demand && !request_match_found_i && free_index_i==ROW;
    wire prefetch_allocate=enabled && prefetch_step_allocates_i && free_index_i==ROW;
    wire control_allocate=enabled && control_target_allocate_i && response_index_i==ROW;
    wire [2:0] pc_events={control_allocate,prefetch_allocate,demand_match || demand_new};
    wire [2:0] line_events={control_allocate,prefetch_allocate,demand_new};
    wire [3*MSHR_PAYLOAD_WIDTH-1:0] pc_values={
        current_epoch_i,control_target_i,prefetch_epoch_i,prefetch_next_line_i,if_req_epoch_i,if_req_pc_i};
    wire [3*MSHR_PAYLOAD_WIDTH-1:0] line_values={
        current_epoch_i,control_target_i[31:4],4'b0,prefetch_epoch_i,prefetch_next_line_i,if_req_epoch_i,request_line_i};
    wire pc_write,line_write;
    wire [MSHR_PAYLOAD_WIDTH-1:0] next_pc,next_line,saved_pc,saved_line;
    rv32_frequency_event_select #(.WIDTH(MSHR_PAYLOAD_WIDTH),.EVENTS(3)) pc_selector (
        .events_i(pc_events),.values_i(pc_values),.write_o(pc_write),.value_o(next_pc));
    rv32_frequency_event_select #(.WIDTH(MSHR_PAYLOAD_WIDTH),.EVENTS(3)) line_selector (
        .events_i(line_events),.values_i(line_values),.write_o(line_write),.value_o(next_line));
    rv32_frequency_word_bank #(.WIDTH(MSHR_PAYLOAD_WIDTH)) pc_owner (
        .clk_i(clk_i),.write_i(pc_write),.data_i(next_pc),.data_o(saved_pc));
    rv32_frequency_word_bank #(.WIDTH(MSHR_PAYLOAD_WIDTH)) line_owner (
        .clk_i(clk_i),.write_i(line_write),.data_i(next_line),.data_o(saved_line));
    assign {demand_epoch_o,pc_o}=saved_pc;
    assign {txn_epoch_o,line_o}=saved_line;

    always @(posedge clk_i) begin
        if (reset_i)
        begin
            valid_o <= 1'b0;
            sent_o <= 1'b0;
            prefetch_o <= 1'b0;
            control_prefetch_o <= 1'b0;
        end
        else
        begin
            if (valid_o &&
            (txn_epoch_o != current_epoch_i) &&
            !control_prefetch_o)
            begin
                valid_o <= 1'b0;
                sent_o <= 1'b0;
                control_prefetch_o <= 1'b0;
            end
            if (request_fire_i && !request_hit_i)
            begin
                if (request_match_found_i)
                begin
                    if (request_match_index_i == ROW)
                    begin
                        prefetch_o <= 1'b0;
                    end
                end
                else
                    if (free_index_i == ROW)
                    begin
                        valid_o <= 1'b1;
                        sent_o <= 1'b0;
                        prefetch_o <= 1'b0;
                        control_prefetch_o <= 1'b0;
                    end
            end
            if (prefetch_step_allocates_i && (free_index_i == ROW))
            begin
                valid_o <= 1'b1;
                sent_o <= 1'b0;
                prefetch_o <= 1'b1;
                control_prefetch_o <= prefetch_control_stream_i;
            end
            if (mem_req_valid_i && mem_req_ready_i && (send_index_i == ROW))
                sent_o <= 1'b1;
            if (mem_resp_valid_i && mem_resp_ready_i &&
            response_target_found_i && (response_index_i == ROW))
            begin
                valid_o <= 1'b0;
                sent_o <= 1'b0;
                control_prefetch_o <= 1'b0;
            end
            if (control_target_allocate_i && (response_index_i == ROW))
            begin
                valid_o <= 1'b1;
                sent_o <= 1'b0;
                prefetch_o <= 1'b1;
                control_prefetch_o <= 1'b1;
            end
        end
    end
endmodule
