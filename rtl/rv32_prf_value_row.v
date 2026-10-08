`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Highest valid lane wins. Value payload has no later reset mux; the final
// write enable already excludes reset before its priced local driver.
module rv32_prf_value_row #(parameter integer LANES=4, parameter integer VALUE_SRAM=0, parameter integer RAW_SRAM_OUTPUT=0, parameter integer RAW_SRAM_WRITE=0) (
    input wire clk_i,reset_i,alloc_i,
    input wire [LANES-1:0] write_matches_i,
    input wire [LANES*32-1:0] write_values_i,
    input wire [LANES-1:0] recent_matches_i,
    input wire [LANES*32-1:0] recent_values_i,
    output wire [31:0] value_o,
    output reg ready_o
);
    wire write_event;
    wire [31:0] next_value;
    initial if((RAW_SRAM_WRITE!=0 && RAW_SRAM_WRITE!=1) || (RAW_SRAM_WRITE!=0 && VALUE_SRAM==0))
        $fatal(1,"Raw PRF write data requires SRAM storage");
    generate if(RAW_SRAM_WRITE!=0) begin:g_raw_write
        // The SRAM consumes WDATA only on its actual write event. Its idle
        // input can be lane zero, eliminating a redundant row-wide zero mask.
        // Higher matching lanes retain the original last-write priority.
        wire [31:0] choices [0:LANES-1];
        assign write_event=|write_matches_i;
        assign choices[0]=write_values_i[31:0];
        for(genvar lane=1;lane<LANES;lane=lane+1) begin:g_priority
            wire [1:0] selects;
            rv32_frequency_control_tree #(.LEAVES(2)) choice_tree (
                .signal_i(write_matches_i[lane]),.views_o(selects));
            assign choices[lane]={selects[1]?write_values_i[lane*32+16 +: 16]:choices[lane-1][31:16],
                                  selects[0]?write_values_i[lane*32 +: 16]:choices[lane-1][15:0]};
        end
        assign next_value=choices[LANES-1];
    end else begin:g_qualified_write
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(LANES)) value_selector (
        .events_i(write_matches_i),.values_i(write_values_i),.write_o(write_event),.value_o(next_value));
    end endgenerate
    generate if(VALUE_SRAM!=0) begin:g_sram
        wire [31:0] stored_value,recent_value;
        wire recent_write;
        // Each row is a real 1RW synchronous SRAM word. Idle rows read every
        // edge. A written row's output is invalid for that cycle, so the shared
        // previous writeback stream supplies its exact last write instead.
        sram_fakeram #(.DEPTH(1),.WIDTH(32)) storage (
            .clk(clk_i),.en(!reset_i),.we(write_event),.wmask(1'b1),
            .addr(1'b0),.wdata(next_value),.rdata(stored_value));
        if(RAW_SRAM_OUTPUT!=0) begin:g_raw_word
            assign value_o=stored_value;
        end else begin:g_row_forward
        rv32_frequency_event_select #(.WIDTH(32),.EVENTS(LANES)) recent_selector (
            .events_i(recent_matches_i),.values_i(recent_values_i),
            .write_o(recent_write),.value_o(recent_value));
        wire [1:0] recent_views;
        rv32_frequency_control_tree #(.LEAVES(2)) recent_tree (
            .signal_i(recent_write),.views_o(recent_views));
        assign value_o={recent_views[1] ? recent_value[31:16] : stored_value[31:16],
                       recent_views[0] ? recent_value[15:0] : stored_value[15:0]};
        end
    end else begin:g_ff
        reg [31:0] stored_value;
        wire [1:0] write_views;
        rv32_frequency_control_tree #(.LEAVES(2)) write_tree (
            .signal_i(!reset_i && write_event),.views_o(write_views));
        always @(posedge clk_i) if(write_views[0]) stored_value[15:0]<=next_value[15:0];
        always @(posedge clk_i) if(write_views[1]) stored_value[31:16]<=next_value[31:16];
        assign value_o=stored_value;
    end endgenerate
    always @(posedge clk_i) begin
        if(reset_i)
            ready_o<=0;
        else
            if(|write_matches_i)
                ready_o<=1;
            else
                if(alloc_i)
                    ready_o<=0;
    end
endmodule
