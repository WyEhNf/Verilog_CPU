`timescale 1ns/1ps

// Exact circular age < full count for power-of-two queues. Upper count bits
// cover the entire ring; otherwise one low sum/carry describes both intervals.
// No valid/window invariant or generation-width reduction is used.
(* keep_hierarchy = 1 *)
module rv32_lsq_report_range_carry #(
    parameter integer ENTRIES=16,
    parameter integer SLOT_WIDTH=$clog2(ENTRIES),
    parameter integer COUNT_WIDTH=$clog2(ENTRIES+1),
    parameter integer DOMAINS=(ENTRIES+3)/4
) (
    input wire [SLOT_WIDTH-1:0] head_i,
    input wire [COUNT_WIDTH-1:0] count_i,
    output wire [ENTRIES-1:0] range_o
);
    wire [SLOT_WIDTH-1:0] propagate=head_i ^ count_i[SLOT_WIDTH-1:0];
    wire [SLOT_WIDTH-1:0] generate_bits=head_i & count_i[SLOT_WIDTH-1:0];
    wire [SLOT_WIDTH:0] carry;
    wire [SLOT_WIDTH-1:0] end_low;
    wire full_ring;
    assign carry[0]=0;
    for(genvar position=1;position<=SLOT_WIDTH;position=position+1) begin:g_prefix
        wire [position-1:0] terms;
        for(genvar source=0;source<position;source=source+1) begin:g_term
            if(source==position-1) assign terms[source]=generate_bits[source];
            else assign terms[source]=generate_bits[source] &&
                (&propagate[position-1:source+1]);
        end
        assign carry[position]=|terms;
    end
    for(genvar bit_id=0;bit_id<SLOT_WIDTH;bit_id=bit_id+1) begin:g_sum
        assign end_low[bit_id]=propagate[bit_id] ^ carry[bit_id];
    end
    generate if(COUNT_WIDTH>SLOT_WIDTH) begin:g_full_count
        assign full_ring=|count_i[COUNT_WIDTH-1:SLOT_WIDTH];
    end else begin:g_short_count
        assign full_ring=0;
    end endgenerate
    localparam integer WIDTH=2*SLOT_WIDTH+2;
    wire [DOMAINS*WIDTH-1:0] views;
    rv32_frequency_control_tree #(.WIDTH(WIDTH),.LEAVES(DOMAINS)) predicate_tree (
        .signal_i({full_ring,carry[SLOT_WIDTH],head_i,end_low}),.views_o(views));
    for(genvar row=0;row<ENTRIES;row=row+1) begin:g_row
        wire all_rows,wrapped_end;
        wire [SLOT_WIDTH-1:0] head,end_offset;
        assign {all_rows,wrapped_end,head,end_offset}=views[(row/4)*WIDTH +: WIDTH];
        wire before_head=SLOT_WIDTH'(row)<head;
        wire before_end=SLOT_WIDTH'(row)<end_offset;
        assign range_o[row]=all_rows ||
            (before_head ? (wrapped_end && before_end) : (wrapped_end || before_end));
    end
    initial if(ENTRIES<2 || ENTRIES>32 || ENTRIES!=(1<<SLOT_WIDTH) ||
        COUNT_WIDTH<SLOT_WIDTH || DOMAINS!=(ENTRIES+3)/4)
        $fatal(1,"Carry range requires exact power-of-two geometry and complete count");
endmodule
