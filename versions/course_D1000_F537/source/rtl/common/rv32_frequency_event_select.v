`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Last event wins, matching ordered nonblocking writes. Qualification takes
// place before distribution; each select leaf drives at most 16 payload bits.
module rv32_frequency_event_select #(
    parameter integer WIDTH=32,EVENTS=4,
    parameter integer LEAVES=1<<$clog2(EVENTS),
    parameter integer WORDS=(WIDTH+15)/16,
    // 0 requires mutually exclusive events;

//  1 preserves last-event priority.
    parameter integer PRIORITY=1
) (
    input wire [EVENTS-1:0] events_i,
    input wire [EVENTS*WIDTH-1:0] values_i,
    output wire write_o,
    output wire [WIDTH-1:0] value_o
);
    wire unused_LEAVES_bits = &{1'b0, (LEAVES != 0)};

    wire unused_WORDS_bits = &{1'b0, (WORDS != 0)};

// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    reg [WIDTH-1:0] selected;
    integer event_id;
    localparam integer EVENT_INDEX_WIDTH=(EVENTS<=1)?1:$clog2(EVENTS);
    reg [EVENT_INDEX_WIDTH-1:0] event_index;
    wire [EVENTS-1:0] remaining=events_i & (events_i-EVENTS'(1));
    always @* begin
        selected=0;event_id=0;event_index=0;
        if(|events_i) begin
            if(PRIORITY!=0 || remaining==0) begin
                // Ceil(log2((events >> 1)+1)) is the highest set-bit index.
                // Last-event priority and a single-event OR share this path.
                event_index=EVENT_INDEX_WIDTH'($clog2((events_i>>1)+EVENTS'(1)));
                selected=values_i[(32'(event_index)*WIDTH) +: WIDTH];
            end else begin
                // Preserve arbitrary simultaneous events in the OR mode.
                for(event_id=0;event_id<EVENTS;event_id=event_id+1)
                    if(events_i[event_id]) selected=selected | values_i[event_id*WIDTH +: WIDTH];
            end
        end
    end
    assign write_o=|events_i;
    assign value_o=selected;
`else
    wire [EVENTS-1:0] grants;
    wire [WIDTH-1:0] mux_tree [1:2*LEAVES-1];
    assign write_o=|events_i;
    assign value_o=mux_tree[1];
    genvar event_id,word_id,node_id;
    generate
        for(event_id=0;event_id<LEAVES;event_id=event_id+1) begin:g_event
            if(event_id<EVENTS) begin:g_present
                wire [WORDS-1:0] selections;
                if(PRIORITY==0 || event_id==EVENTS-1) begin:g_last
                    assign grants[event_id]=events_i[event_id];
                end else begin:g_priority
                    assign grants[event_id]=events_i[event_id] && !(|events_i[EVENTS-1:event_id+1]);
                end
                rv32_frequency_control_tree #(.LEAVES(WORDS)) selection_tree (
                    .signal_i(grants[event_id]),.views_o(selections));
                for(word_id=0;word_id<WORDS;word_id=word_id+1) begin:g_word
                    localparam integer LOW=word_id*16;
                    localparam integer BITS=WIDTH-LOW>=16 ? 16 : WIDTH-LOW;
                    assign mux_tree[LEAVES+event_id][LOW +: BITS]=
                        {BITS{selections[word_id]}} & values_i[event_id*WIDTH+LOW +: BITS];
                end
            end else begin:g_padding
                assign mux_tree[LEAVES+event_id]=0;
            end
        end
        for(node_id=1;node_id<LEAVES;node_id=node_id+1) begin:g_or
            assign mux_tree[node_id]=mux_tree[2*node_id] | mux_tree[2*node_id+1];
        end
    endgenerate
`endif
endmodule
