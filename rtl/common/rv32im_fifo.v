`timescale 1ns/1ps

module rv32im_fifo #(
    parameter integer WIDTH = 32,
    parameter integer DEPTH = 8,
    parameter integer LANES = 1
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire                         flush_i,
    input  wire [LANES-1:0]             push_valid_i,
    input  wire [((LANES <= 1) ? 1 : $clog2(LANES + 1))-1:0] push_count_i,
    input  wire [(LANES*WIDTH)-1:0]     push_payload_i,
    output wire                         push_ready_o,
    input  wire                         pop_ready_i,
    output wire                         pop_valid_o,
    output wire [((LANES <= 1) ? 1 : $clog2(LANES + 1))-1:0] pop_count_o,
    output wire [(LANES*WIDTH)-1:0]     pop_payload_o,
    input  wire [((DEPTH <= 2) ? 1 : $clog2(DEPTH + 1))-1:0] flush_count_i,
    output wire [((DEPTH <= 2) ? 1 : $clog2(DEPTH + 1))-1:0] occupancy_o,
    output wire [((DEPTH <= 2) ? 1 : $clog2(DEPTH + 1))-1:0] free_count_o
);
    /* verilator lint_off WIDTHEXPAND */
    /* verilator lint_off WIDTHTRUNC */
    localparam integer COUNT_WIDTH = (LANES <= 1) ? 1 : $clog2(LANES + 1);
    localparam integer PTR_WIDTH = (DEPTH <= 2) ? 1 : $clog2(DEPTH);
    localparam integer OCC_WIDTH = (DEPTH <= 2) ? 1 : $clog2(DEPTH + 1);
    integer i;
    integer j;
    reg [WIDTH-1:0] storage [0:DEPTH-1];
    reg [PTR_WIDTH-1:0] head_reg;
    reg [PTR_WIDTH-1:0] tail_reg;
    reg [OCC_WIDTH-1:0] occupancy_reg;
    reg [(LANES*WIDTH)-1:0] pop_payload_reg;
    reg [COUNT_WIDTH-1:0] pop_count_reg;
    reg push_fire;
    reg pop_fire;
    reg [OCC_WIDTH-1:0] push_count_ext;
    reg [OCC_WIDTH-1:0] pop_count_ext;
    reg [OCC_WIDTH-1:0] pop_count_calc;

    assign occupancy_o = occupancy_reg;
    assign free_count_o = DEPTH - occupancy_reg;
    assign push_ready_o = !flush_i && (free_count_o >= push_count_i);
    assign pop_valid_o = (occupancy_reg != 0);
    assign pop_count_o = pop_count_reg;
    assign pop_payload_o = pop_payload_reg;

    always @* begin
        pop_count_calc = occupancy_reg;
        if (pop_count_calc > LANES)
            pop_count_calc = LANES;
        pop_count_reg = pop_count_calc[COUNT_WIDTH-1:0];
        for (i = 0; i < LANES; i = i + 1) begin
            if (i < pop_count_calc)
                pop_payload_reg[(i*WIDTH) +: WIDTH] = storage[(head_reg + i) & (DEPTH - 1)];
            else
                pop_payload_reg[(i*WIDTH) +: WIDTH] = {WIDTH{1'b0}};
        end
        push_fire = push_valid_i[0] && push_ready_o;
        pop_fire = pop_ready_i && pop_valid_o;
        push_count_ext = push_count_i;
        pop_count_ext = pop_count_reg;
    end

    always @(posedge clk_i) begin
        if (reset_i) begin
            head_reg <= {PTR_WIDTH{1'b0}};
            tail_reg <= {PTR_WIDTH{1'b0}};
            occupancy_reg <= {OCC_WIDTH{1'b0}};
        end else if (flush_i) begin
            if (flush_count_i >= occupancy_reg) begin
                head_reg <= head_reg;
                tail_reg <= head_reg;
                occupancy_reg <= {OCC_WIDTH{1'b0}};
            end else begin
                tail_reg <= (tail_reg - flush_count_i) & (DEPTH - 1);
                occupancy_reg <= occupancy_reg - flush_count_i;
            end
        end else begin
            if (push_fire) begin
                for (j = 0; j < LANES; j = j + 1)
                    if (j < push_count_i)
                        storage[(tail_reg + j) & (DEPTH - 1)] <= push_payload_i[(j*WIDTH) +: WIDTH];
                tail_reg <= (tail_reg + push_count_i) & (DEPTH - 1);
            end
            if (pop_fire)
                head_reg <= (head_reg + pop_count_reg) & (DEPTH - 1);
            if (push_fire && !pop_fire)
                occupancy_reg <= occupancy_reg + push_count_ext;
            else if (!push_fire && pop_fire)
                occupancy_reg <= occupancy_reg - pop_count_ext;
        end
    end
    /* verilator lint_on WIDTHTRUNC */
    /* verilator lint_on WIDTHEXPAND */
endmodule
