`timescale 1ns/1ps
// Replicate an EXISTING clock boundary for bounded-fanout control consumers.
// All banks sample the same next-state value and enable on the same edge.
// These are ordinary, fully priced RTL flops, not memory or external cells.
module rv32_control_register_bank #(
    parameter integer WIDTH = 1,
    parameter integer LEAVES = 16,
    parameter integer ENABLED = 0,
    parameter [WIDTH-1:0] RESET_VALUE = {WIDTH{1'b0}}
) (
    input wire clk_i,
    input wire reset_i,
    input wire update_en_i,
    input wire [WIDTH-1:0] value_i,
    output wire [WIDTH*LEAVES-1:0] replicas_o
);
    initial begin
        if (WIDTH < 1 || LEAVES < 1 || LEAVES > 32 ||
            (ENABLED != 0 && ENABLED != 1))
            $fatal(1, "invalid control register-bank configuration");
    end
    genvar leaf;
    generate
        if (ENABLED != 0) begin : g_register_banks
            for (leaf = 0; leaf < LEAVES; leaf = leaf + 1) begin : g_bank
                (* keep = 1 *) reg [WIDTH-1:0] value_q;
                // Keep the real sequential cells, rather than just aliases:
                // preserving wire names alone would not prevent FF merging.
                (* keep = 1 *) always @(posedge clk_i)
                    if (reset_i) value_q <= RESET_VALUE;
                else if (update_en_i) value_q <= value_i;
                assign replicas_o[leaf*WIDTH +: WIDTH] = value_q;
            end
        end else begin : g_shared_register
            (* keep = 1 *) reg [WIDTH-1:0] value_q;
            always @(posedge clk_i)
                if (reset_i) value_q <= RESET_VALUE;
                else if (update_en_i) value_q <= value_i;
            for (leaf = 0; leaf < LEAVES; leaf = leaf + 1) begin : g_alias
                assign replicas_o[leaf*WIDTH +: WIDTH] = value_q;
            end
        end
    endgenerate
endmodule
