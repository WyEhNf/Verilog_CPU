`timescale 1ns/1ps

// A complete functional RTL module. ABC maps this inversion to real library
// logic. The hierarchy boundary prevents cancellation with the next inversion;
// keep on each instance prevents identical sibling instances from merging.
// No external cell declaration, blackbox, whitebox, or area override is used.
(* keep_hierarchy = 1 *)
module rv32_frequency_inversion(input wire signal_i, output wire signal_o);
    assign signal_o = ~signal_i;
endmodule

// Internal distribution receives a NEGATIVE representation and returns
// positive leaves. Every leaf has its own inverter; internal nodes retain a
// negative representation using two real inverters and at most four children.
// Thus no alias leaf can expose a parent directly to its payload consumer load.
module rv32_frequency_negative_subtree #(
    parameter integer WIDTH=1,LEAVES=1
) (
    input wire [WIDTH-1:0] negative_i,
    output wire [WIDTH*LEAVES-1:0] views_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign views_o = {LEAVES{~negative_i}};
`else
    localparam integer CHILDREN=LEAVES>4?4:LEAVES;
    localparam integer BASE_COUNT=LEAVES/CHILDREN;
    localparam integer EXTRA_COUNT=LEAVES%CHILDREN;
    genvar bit_id,child;
    generate if(LEAVES==1) begin:g_leaf
        for(bit_id=0;bit_id<WIDTH;bit_id=bit_id+1) begin:g_driver
            (* keep=1,keep_hierarchy=1 *)
            rv32_frequency_inversion restore_positive (
                .signal_i(negative_i[bit_id]),.signal_o(views_o[bit_id]));
        end
    end else begin:g_internal
        wire [WIDTH-1:0] positive,distributed_negative;
        for(bit_id=0;bit_id<WIDTH;bit_id=bit_id+1) begin:g_driver
            (* keep=1,keep_hierarchy=1 *)
            rv32_frequency_inversion invert_root (
                .signal_i(negative_i[bit_id]),.signal_o(positive[bit_id]));
            (* keep=1,keep_hierarchy=1 *)
            rv32_frequency_inversion invert_output (
                .signal_i(positive[bit_id]),.signal_o(distributed_negative[bit_id]));
        end
        for(child=0;child<CHILDREN;child=child+1) begin:g_child
            localparam integer COUNT=BASE_COUNT+(child<EXTRA_COUNT);
            localparam integer OFFSET=child*BASE_COUNT+
                (child<EXTRA_COUNT?child:EXTRA_COUNT);
            rv32_frequency_negative_subtree #(.WIDTH(WIDTH),.LEAVES(COUNT)) subtree (
                .negative_i(distributed_negative),
                .views_o(views_o[OFFSET*WIDTH +: COUNT*WIDTH]));
        end
    end endgenerate
`endif
endmodule

// One inversion produces a negative representation at the root. Negative
// internal nodes distribute it; individual leaf inverters restore the original
// positive signal. For LEAVES>1 this removes two serial inversions on every
// path and LEAVES+1 inverter instances per bit versus the old positive-node
// tree. Each internal driver still owns at most four child gate inputs.
// LEAVES=1 remains a two-inverter, positive-output leaf.
module rv32_frequency_control_tree #(
    parameter integer WIDTH=1,
    parameter integer LEAVES=4
) (
    input wire [WIDTH-1:0] signal_i,
    output wire [WIDTH*LEAVES-1:0] views_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign views_o = {LEAVES{signal_i}};
`else
    localparam integer CHILDREN=LEAVES>4?4:LEAVES;
    localparam integer BASE_COUNT=LEAVES/CHILDREN;
    localparam integer EXTRA_COUNT=LEAVES%CHILDREN;
    wire [WIDTH-1:0] negative;
    genvar bit_id,child;
    generate
        for(bit_id=0;bit_id<WIDTH;bit_id=bit_id+1) begin:g_driver
            (* keep=1,keep_hierarchy=1 *)
            rv32_frequency_inversion invert_root (
                .signal_i(signal_i[bit_id]),.signal_o(negative[bit_id]));
        end
        if(LEAVES==1) begin:g_leaf
            rv32_frequency_negative_subtree #(.WIDTH(WIDTH),.LEAVES(1)) subtree (
                .negative_i(negative),.views_o(views_o));
        end else begin:g_branches
            for(child=0;child<CHILDREN;child=child+1) begin:g_child
                localparam integer COUNT=BASE_COUNT+(child<EXTRA_COUNT);
                localparam integer OFFSET=child*BASE_COUNT+
                    (child<EXTRA_COUNT?child:EXTRA_COUNT);
                rv32_frequency_negative_subtree #(.WIDTH(WIDTH),.LEAVES(COUNT)) subtree (
                    .negative_i(negative),
                    .views_o(views_o[OFFSET*WIDTH +: COUNT*WIDTH]));
            end
        end
    endgenerate
`endif
endmodule

// Preserve the legacy optional interface without importing external cells.
module rv32_asap7_fanout #(
    parameter integer WIDTH = 1,
    parameter integer LEAVES = 16,
    parameter integer ENABLED = 0
) (
    input wire [WIDTH-1:0] signal_i,
    output wire [WIDTH*LEAVES-1:0] replicas_o
);
    genvar leaf;
    generate
        if (ENABLED != 0) begin:g_distribution
            rv32_frequency_control_tree #(.WIDTH(WIDTH), .LEAVES(LEAVES)) tree (
                .signal_i(signal_i), .views_o(replicas_o));
        end else begin:g_aliases
            for (leaf=0; leaf<LEAVES; leaf=leaf+1) begin:g_leaf
                assign replicas_o[leaf*WIDTH +: WIDTH] = signal_i;
            end
        end
    endgenerate
endmodule

// Write ownership is distributed AFTER qualification. Each last driver
// controls at most 16 existing payload hold muxes, with no payload reset.
module rv32_frequency_word_bank #(parameter integer WIDTH=32) (
    input wire clk_i, write_i,
    input wire [WIDTH-1:0] data_i,
    output reg [WIDTH-1:0] data_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    always @(posedge clk_i) if (write_i) data_o <= data_i;
`else
    localparam integer WORDS=(WIDTH+15)/16;
    wire [WORDS-1:0] write_words;
    rv32_frequency_control_tree #(.LEAVES(WORDS)) write_tree (
        .signal_i(write_i), .views_o(write_words));
    genvar word_id;
    generate for(word_id=0;word_id<WORDS;word_id=word_id+1) begin:g_word
        localparam integer LOW=word_id*16;
        localparam integer BITS=WIDTH-LOW>=16 ? 16 : WIDTH-LOW;
        always @(posedge clk_i) if(write_words[word_id])
            data_o[LOW +: BITS]<=data_i[LOW +: BITS];
    end endgenerate
`endif
endmodule


// Last event wins, matching ordered nonblocking writes. Qualification takes
// place before distribution; each select leaf drives at most 16 payload bits.
module rv32_frequency_event_select #(
    parameter integer WIDTH=32,EVENTS=4,
    parameter integer LEAVES=1<<$clog2(EVENTS),
    parameter integer WORDS=(WIDTH+15)/16,
    // 0 requires mutually exclusive events; 1 preserves last-event priority.
    parameter integer PRIORITY=1
) (
    input wire [EVENTS-1:0] events_i,
    input wire [EVENTS*WIDTH-1:0] values_i,
    output wire write_o,
    output wire [WIDTH-1:0] value_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    reg [WIDTH-1:0] selected;
    integer event_id;
    localparam integer EVENT_INDEX_WIDTH=(EVENTS<=1)?1:$clog2(EVENTS);
    reg [EVENT_INDEX_WIDTH-1:0] event_index;
    wire [WIDTH-1:0] event_values [0:EVENTS-1];
    genvar word_event;
    generate for(word_event=0;word_event<EVENTS;word_event=word_event+1) begin:g_sim_values
        assign event_values[word_event]=values_i[word_event*WIDTH +: WIDTH];
    end endgenerate
    wire [EVENTS-1:0] remaining=events_i & (events_i-EVENTS'(1));
    always @* begin
        selected=0;event_id=0;event_index=0;
        if(|events_i) begin
            if(PRIORITY!=0 || remaining==0) begin
                // Ceil(log2((events >> 1)+1)) is the highest set-bit index.
                // Last-event priority and a single-event OR share this path.
                event_index=EVENT_INDEX_WIDTH'($clog2((events_i>>1)+EVENTS'(1)));
                selected=event_values[event_index];
            end else begin
                // Preserve arbitrary simultaneous events in the OR mode.
                for(event_id=0;event_id<EVENTS;event_id=event_id+1)
                    if(events_i[event_id]) selected=selected | event_values[event_id];
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


// Merge the first two entries of each half concurrently. Every node owns
// only two short indices; payload routing is a separate bounded operation.
module rv32_frequency_first_two #(
    parameter integer ENTRIES=8,
    parameter integer INDEX_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES),
    parameter integer LEAVES=1<<$clog2(ENTRIES)
) (
    input wire [ENTRIES-1:0] candidates_i,
    output wire first_valid_o,second_valid_o,
    output wire [INDEX_WIDTH-1:0] first_index_o,second_index_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    wire [ENTRIES-1:0] after_first=candidates_i & (candidates_i-ENTRIES'(1));
    wire [ENTRIES-1:0] first_onehot=candidates_i & (~candidates_i+ENTRIES'(1));
    wire [ENTRIES-1:0] second_onehot=after_first & (~after_first+ENTRIES'(1));
    assign first_valid_o=|candidates_i;
    assign second_valid_o=|after_first;
    assign first_index_o=INDEX_WIDTH'($clog2(first_onehot));
    assign second_index_o=INDEX_WIDTH'($clog2(second_onehot));
`else
    wire first_valid [1:2*LEAVES-1];
    wire second_valid [1:2*LEAVES-1];
    wire [INDEX_WIDTH-1:0] first_index [1:2*LEAVES-1];
    wire [INDEX_WIDTH-1:0] second_index [1:2*LEAVES-1];
    assign first_valid_o=first_valid[1];
    assign second_valid_o=second_valid[1];
    assign first_index_o=first_index[1];
    assign second_index_o=second_index[1];
    genvar slot,node;
    generate
        for(slot=0;slot<LEAVES;slot=slot+1) begin:g_leaf
            if(slot<ENTRIES) begin:g_present
                assign first_valid[LEAVES+slot]=candidates_i[slot];
                assign first_index[LEAVES+slot]=candidates_i[slot]?INDEX_WIDTH'(slot):{INDEX_WIDTH{1'b0}};
            end else begin:g_padding
                assign first_valid[LEAVES+slot]=1'b0;
                assign first_index[LEAVES+slot]=0;
            end
            assign second_valid[LEAVES+slot]=1'b0;
            assign second_index[LEAVES+slot]=0;
        end
        for(node=1;node<LEAVES;node=node+1) begin:g_merge
            assign first_valid[node]=first_valid[2*node] || first_valid[2*node+1];
            assign second_valid[node]=second_valid[2*node] ||
                (first_valid[2*node] && first_valid[2*node+1]) || second_valid[2*node+1];
            assign first_index[node]=first_valid[2*node]?first_index[2*node]:first_index[2*node+1];
            assign second_index[node]=second_valid[2*node]?second_index[2*node]:
                (first_valid[2*node]?first_index[2*node+1]:second_index[2*node+1]);
        end
    endgenerate
`endif
endmodule


// Four-row query domains, sixteen-bit selection leaves and a binary OR tree.
// Payload remains unqualified here: its transaction validity is checked by
// the consumer at the same point as the former dynamic array read.
module rv32_frequency_array_read #(
    parameter integer WIDTH=32,ENTRIES=8,
    parameter integer INDEX_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES),
    parameter integer DOMAINS=(ENTRIES+3)/4,
    parameter integer WORDS=(WIDTH+15)/16,
    parameter integer LEAVES=1<<$clog2(ENTRIES)
) (
    input wire [ENTRIES*WIDTH-1:0] rows_i,
    input wire [INDEX_WIDTH-1:0] index_i,
    output wire [WIDTH-1:0] value_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    wire [WIDTH-1:0] word_rows [0:ENTRIES-1];
    genvar sim_row;
    generate for(sim_row=0;sim_row<ENTRIES;sim_row=sim_row+1) begin:g_sim_rows
        assign word_rows[sim_row]=rows_i[sim_row*WIDTH +: WIDTH];
    end endgenerate
    assign value_o=(index_i<ENTRIES)?word_rows[index_i]:{WIDTH{1'b0}};
`else
    wire [DOMAINS*INDEX_WIDTH-1:0] query_views;
    wire [WIDTH-1:0] reads [1:2*LEAVES-1];
    rv32_frequency_control_tree #(.WIDTH(INDEX_WIDTH),.LEAVES(DOMAINS)) query_tree (
        .signal_i(index_i),.views_o(query_views));
    assign value_o=reads[1];
    genvar row,word,node;
    generate
        for(row=0;row<LEAVES;row=row+1) begin:g_row
            if(row<ENTRIES) begin:g_present
                wire [WORDS-1:0] selects;
                wire hit=query_views[(row/4)*INDEX_WIDTH +: INDEX_WIDTH]==row;
                rv32_frequency_control_tree #(.LEAVES(WORDS)) select_tree (
                    .signal_i(hit),.views_o(selects));
                for(word=0;word<WORDS;word=word+1) begin:g_word
                    localparam integer LOW=word*16;
                    localparam integer BITS=(WIDTH-LOW>=16)?16:WIDTH-LOW;
                    assign reads[LEAVES+row][LOW +: BITS]=
                        {BITS{selects[word]}} & rows_i[row*WIDTH+LOW +: BITS];
                end
            end else begin:g_padding
                assign reads[LEAVES+row]=0;
            end
        end
        for(node=1;node<LEAVES;node=node+1) begin:g_reduce
            assign reads[node]=reads[2*node] | reads[2*node+1];
        end
    endgenerate
`endif
endmodule


// Five binary shift stages. Each amount-bit leaf selects <=16 mux bits;
// right-shift logical/arithmetic behavior differs only in the fill bit.
// Immediate and register amounts keep separate networks, so this change
// does not add an opcode-selected amount mux ahead of the barrel stages.
module rv32_frequency_barrel32 (
    input wire [31:0] value_i,
    input wire [4:0] amount_i,
    input wire fill_i,
    output wire [31:0] left_o,
    output wire [31:0] right_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign left_o = value_i << amount_i;
    // The fill is independent of value_i[31], including for logical shifts.
    assign right_o = (value_i >> amount_i) |
        (fill_i ? ~(32'hffffffff >> amount_i) : 32'b0);
`else
    wire [19:0] amount_views;
    wire [4:0] fill_views;
    wire [31:0] left_stage [0:5];
    wire [31:0] right_stage [0:5];
    rv32_frequency_control_tree #(.WIDTH(5),.LEAVES(4)) amount_tree (
        .signal_i(amount_i),.views_o(amount_views));
    rv32_frequency_control_tree #(.LEAVES(5)) fill_tree (
        .signal_i(fill_i),.views_o(fill_views));
    assign left_stage[0]=value_i;
    assign right_stage[0]=value_i;
    assign left_o=left_stage[5];
    assign right_o=right_stage[5];
    genvar stage,bit_id;
    generate for(stage=0;stage<5;stage=stage+1) begin:g_stage
        localparam integer DISTANCE=1<<stage;
        for(bit_id=0;bit_id<32;bit_id=bit_id+1) begin:g_bit
            if(bit_id>=DISTANCE) begin:g_left_data
                assign left_stage[stage+1][bit_id]=amount_views[(bit_id/16)*5+stage]?
                    left_stage[stage][bit_id-DISTANCE]:left_stage[stage][bit_id];
            end else begin:g_left_zero
                assign left_stage[stage+1][bit_id]=!amount_views[(bit_id/16)*5+stage] && left_stage[stage][bit_id];
            end
            if(bit_id+DISTANCE<32) begin:g_right_data
                assign right_stage[stage+1][bit_id]=amount_views[(2+bit_id/16)*5+stage]?
                    right_stage[stage][bit_id+DISTANCE]:right_stage[stage][bit_id];
            end else begin:g_right_fill
                assign right_stage[stage+1][bit_id]=amount_views[(2+bit_id/16)*5+stage]?
                    fill_views[stage]:right_stage[stage][bit_id];
            end
        end
    end endgenerate
`endif
endmodule


// Full 128-bit logical shift semantics, retaining zero fill even for an
// unaligned byte window near the end of a line. Only bits needed by the
// eventual 32-bit result are routed through the four byte-offset stages.
// Each amount leaf owns at most sixteen actual mux bits; no state/cycle.
module rv32_frequency_line_extract32 (
    input wire [127:0] line_i,
    input wire [3:0] offset_i,
    input wire [1:0] size_i,
    input wire unsigned_i,
    output wire [31:0] value_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    wire [127:0] shifted_line = line_i >> {offset_i,3'b0};
    wire [31:0] shifted = shifted_line[31:0];
    assign value_o = (size_i==2'd0) ? {{24{!unsigned_i && shifted[7]}},shifted[7:0]} :
        ((size_i==2'd1) ? {{16{!unsigned_i && shifted[15]}},shifted[15:0]} : shifted);
`else
    wire [87:0] shift64;
    wire [55:0] shift32;
    wire [39:0] shift16;
    wire [31:0] shifted;
    wire [5:0] amount64;
    wire [3:0] amount32;
    wire [2:0] amount16;
    wire [1:0] amount8;
    rv32_frequency_control_tree #(.LEAVES(6)) amount64_tree (
        .signal_i(offset_i[3]),.views_o(amount64));
    rv32_frequency_control_tree #(.LEAVES(4)) amount32_tree (
        .signal_i(offset_i[2]),.views_o(amount32));
    rv32_frequency_control_tree #(.LEAVES(3)) amount16_tree (
        .signal_i(offset_i[1]),.views_o(amount16));
    rv32_frequency_control_tree #(.LEAVES(2)) amount8_tree (
        .signal_i(offset_i[0]),.views_o(amount8));
    genvar bit_id;
    generate
        for(bit_id=0;bit_id<88;bit_id=bit_id+1) begin:g_shift64
            if(bit_id+64<128) begin:g_data
                assign shift64[bit_id]=amount64[bit_id/16]?line_i[bit_id+64]:line_i[bit_id];
            end else begin:g_zero
                assign shift64[bit_id]=!amount64[bit_id/16] && line_i[bit_id];
            end
        end
        for(bit_id=0;bit_id<56;bit_id=bit_id+1) begin:g_shift32
            assign shift32[bit_id]=amount32[bit_id/16]?shift64[bit_id+32]:shift64[bit_id];
        end
        for(bit_id=0;bit_id<40;bit_id=bit_id+1) begin:g_shift16
            assign shift16[bit_id]=amount16[bit_id/16]?shift32[bit_id+16]:shift32[bit_id];
        end
        for(bit_id=0;bit_id<32;bit_id=bit_id+1) begin:g_shift8
            assign shifted[bit_id]=amount8[bit_id/16]?shift16[bit_id+8]:shift16[bit_id];
        end
    endgenerate
    // RV32IM_MEM_BYTE=0, RV32IM_MEM_HALF=1; both remaining codes
    // retain the former function's default full-word behavior.
    wire [7:0] format_views;
    rv32_frequency_control_tree #(.WIDTH(4),.LEAVES(2)) format_tree (
        .signal_i({size_i==2'd0,size_i==2'd1,
                   !unsigned_i && shifted[7],!unsigned_i && shifted[15]}),
        .views_o(format_views));
    generate for(bit_id=0;bit_id<32;bit_id=bit_id+1) begin:g_format
        wire byte_load,half_load,byte_sign,half_sign;
        assign {byte_load,half_load,byte_sign,half_sign}=format_views[(bit_id/16)*4 +: 4];
        if(bit_id<8) begin:g_low
            assign value_o[bit_id]=shifted[bit_id];
        end else if(bit_id<16) begin:g_byte_extend
            assign value_o[bit_id]=byte_load?byte_sign:shifted[bit_id];
        end else begin:g_half_extend
            assign value_o[bit_id]=byte_load?byte_sign:(half_load?half_sign:shifted[bit_id]);
        end
    end endgenerate
`endif
endmodule


// Insert an access-relative word at any byte offset, preserving the original
// 128-bit left shift and overflow truncation. Increasing intermediate widths
// retain all reachable bits; each amount leaf owns <=16 actual mux bits.
module rv32_frequency_line_insert32 (
    input wire [31:0] value_i,
    input wire [3:0] offset_i,
    output wire [127:0] line_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign line_o = {96'b0,value_i} << {offset_i,3'b0};
`else
    wire [39:0] shift8;
    wire [55:0] shift16;
    wire [87:0] shift32;
    wire [127:0] original [0:3];
    wire [127:0] shifted [0:3];
    wire [2:0] amount8;
    wire [3:0] amount16;
    wire [5:0] amount32;
    wire [7:0] amount64;
    assign original[0]={96'b0,value_i};
    assign shifted[0]={88'b0,value_i,8'b0};
    assign original[1]={88'b0,shift8};
    assign shifted[1]={72'b0,shift8,16'b0};
    assign original[2]={72'b0,shift16};
    assign shifted[2]={40'b0,shift16,32'b0};
    assign original[3]={40'b0,shift32};
    assign shifted[3]={shift32[63:0],64'b0};
    rv32_frequency_control_tree #(.LEAVES(3)) amount8_tree (
        .signal_i(offset_i[0]),.views_o(amount8));
    rv32_frequency_control_tree #(.LEAVES(4)) amount16_tree (
        .signal_i(offset_i[1]),.views_o(amount16));
    rv32_frequency_control_tree #(.LEAVES(6)) amount32_tree (
        .signal_i(offset_i[2]),.views_o(amount32));
    rv32_frequency_control_tree #(.LEAVES(8)) amount64_tree (
        .signal_i(offset_i[3]),.views_o(amount64));
    genvar bit_id;
    generate
        for(bit_id=0;bit_id<40;bit_id=bit_id+1) begin:g_shift8
            assign shift8[bit_id]=amount8[bit_id/16]?shifted[0][bit_id]:original[0][bit_id];
        end
        for(bit_id=0;bit_id<56;bit_id=bit_id+1) begin:g_shift16
            assign shift16[bit_id]=amount16[bit_id/16]?shifted[1][bit_id]:original[1][bit_id];
        end
        for(bit_id=0;bit_id<88;bit_id=bit_id+1) begin:g_shift32
            assign shift32[bit_id]=amount32[bit_id/16]?shifted[2][bit_id]:original[2][bit_id];
        end
        for(bit_id=0;bit_id<128;bit_id=bit_id+1) begin:g_shift64
            assign line_o[bit_id]=amount64[bit_id/16]?shifted[3][bit_id]:original[3][bit_id];
        end
    endgenerate
`endif
endmodule


// Execution ownership uses the registered recovery snapshot, not a late
// dynamic ROB read. Packet layout: {apply,occupancy,head,branch_relative_age}.
// Default-disabled instances retain old standalone interfaces and semantics.
module rv32_execution_recovery_cancel #(
    parameter integer TAG_WIDTH=17, ROB_ENTRIES=64, ENABLED=0, KILL_BRANCH=0,
    parameter integer SW=(ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES),
    parameter integer CW=$clog2(ROB_ENTRIES+1),
    parameter integer WIDTH=1+2*SW+CW
) (
    input wire [WIDTH-1:0] packet_i,
    input wire active_i,
    input wire [TAG_WIDTH-1:0] tag_i,
    output wire cancel_o
);
    generate if(ENABLED!=0) begin:g_enabled
        wire apply;
        wire [CW-1:0] occupancy;
        wire [SW-1:0] head,branch_age;
        wire [SW-1:0] age=tag_i[3 +: SW]-head;
        assign {apply,occupancy,head,branch_age}=packet_i;
        assign cancel_o=active_i && apply && (!tag_i[0] || age>=occupancy ||
            (KILL_BRANCH ? age>=branch_age : age>branch_age));
    end else begin:g_disabled
        assign cancel_o=1'b0;
    end endgenerate
endmodule


// Sixteen parallel four-bit adders generate block G/P and both sum choices.
// A four-level prefix tree resolves block carries; each late carry controls
// only four sum bits. Exact modulo-2^64 addition, with no state or new edge.
module rv32_frequency_add64_select (
    input wire [63:0] lhs_i,rhs_i,
    output wire [63:0] sum_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign sum_o = lhs_i + rhs_i;
`else
    wire [15:0] generate_stage [0:4];
    wire [15:0] propagate_stage [0:4];
    wire [3:0] sum_zero [0:15],sum_one [0:15];
    genvar block_index,prefix_level;
    generate
        for(block_index=0;block_index<16;block_index=block_index+1) begin:g_block
            wire [4:0] block_sum={1'b0,lhs_i[block_index*4 +: 4]}+
                {1'b0,rhs_i[block_index*4 +: 4]};
            assign sum_zero[block_index]=block_sum[3:0];
            assign sum_one[block_index]=block_sum[3:0]+4'd1;
            assign generate_stage[0][block_index]=block_sum[4];
            assign propagate_stage[0][block_index]=
                &(lhs_i[block_index*4 +: 4] ^ rhs_i[block_index*4 +: 4]);
            if(block_index==0) begin:g_first
                assign sum_o[0 +: 4]=sum_zero[0];
            end else begin:g_selected
                assign sum_o[block_index*4 +: 4]=generate_stage[4][block_index-1] ?
                    sum_one[block_index] : sum_zero[block_index];
            end
        end
        for(prefix_level=0;prefix_level<4;prefix_level=prefix_level+1) begin:g_prefix
            localparam integer DISTANCE=1<<prefix_level;
            for(block_index=0;block_index<16;block_index=block_index+1) begin:g_block
                if(block_index>=DISTANCE) begin:g_combine
                    assign generate_stage[prefix_level+1][block_index]=generate_stage[prefix_level][block_index] |
                        (propagate_stage[prefix_level][block_index] && generate_stage[prefix_level][block_index-DISTANCE]);
                    assign propagate_stage[prefix_level+1][block_index]=propagate_stage[prefix_level][block_index] &&
                        propagate_stage[prefix_level][block_index-DISTANCE];
                end else begin:g_copy
                    assign generate_stage[prefix_level+1][block_index]=generate_stage[prefix_level][block_index];
                    assign propagate_stage[prefix_level+1][block_index]=propagate_stage[prefix_level][block_index];
                end
            end
        end
    endgenerate
`endif
endmodule


// Eight independent four-bit adders produce block G/P and both sum choices.
// Three prefix levels resolve carries. Each late carry selects four bits.
// Exact modulo-2^32 addition with no registers or additional clock edge.
(* keep_hierarchy = 1 *)
module rv32_frequency_add32_select (
    input wire [31:0] lhs_i,rhs_i,
    output wire [31:0] sum_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign sum_o = lhs_i + rhs_i;
`else
    wire [7:0] generate_stage [0:3];
    wire [7:0] propagate_stage [0:3];
    wire [3:0] sum_zero [0:7],sum_one [0:7];
    genvar block_index,prefix_level;
    generate
        for(block_index=0;block_index<8;block_index=block_index+1) begin:g_block
            wire [4:0] block_sum={1'b0,lhs_i[block_index*4 +: 4]}+
                {1'b0,rhs_i[block_index*4 +: 4]};
            assign sum_zero[block_index]=block_sum[3:0];
            assign sum_one[block_index]=block_sum[3:0]+4'd1;
            assign generate_stage[0][block_index]=block_sum[4];
            assign propagate_stage[0][block_index]=
                &(lhs_i[block_index*4 +: 4] ^ rhs_i[block_index*4 +: 4]);
            if(block_index==0) begin:g_first
                assign sum_o[0 +: 4]=sum_zero[0];
            end else begin:g_selected
                assign sum_o[block_index*4 +: 4]=generate_stage[3][block_index-1] ?
                    sum_one[block_index] : sum_zero[block_index];
            end
        end
        for(prefix_level=0;prefix_level<3;prefix_level=prefix_level+1) begin:g_prefix
            localparam integer DISTANCE=1<<prefix_level;
            for(block_index=0;block_index<8;block_index=block_index+1) begin:g_block
                if(block_index>=DISTANCE) begin:g_combine
                    assign generate_stage[prefix_level+1][block_index]=generate_stage[prefix_level][block_index] |
                        (propagate_stage[prefix_level][block_index] && generate_stage[prefix_level][block_index-DISTANCE]);
                    assign propagate_stage[prefix_level+1][block_index]=propagate_stage[prefix_level][block_index] &&
                        propagate_stage[prefix_level][block_index-DISTANCE];
                end else begin:g_copy
                    assign generate_stage[prefix_level+1][block_index]=generate_stage[prefix_level][block_index];
                    assign propagate_stage[prefix_level+1][block_index]=propagate_stage[prefix_level][block_index];
                end
            end
        end
    endgenerate
`endif
endmodule


// Addition of an RV32 load/store signed 12-bit displacement. The low twelve
// bits use three carry-select blocks. The upper word changes only by -1, 0,
// or +1; its increment/decrement prefixes are independent of the low carry.
// No state, and all arithmetic wraps modulo 2^32.
(* keep_hierarchy = 1 *)
module rv32_frequency_add_simm12 #(
    parameter integer CLASS_COMPARE=0
) (
    input wire [31:0] base_i,
    input wire [11:0] immediate_i,
    output wire [31:0] sum_o,
    output wire [2:0] class_flags_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign sum_o = base_i + {{20{immediate_i[11]}},immediate_i};
    assign class_flags_o = CLASS_COMPARE ?
        {sum_o[1:0]==2'b00,!sum_o[0],sum_o[31:28]==4'b0} : 3'b0;
`else
    wire [2:0] generate_stage [0:2];
    wire [2:0] propagate_stage [0:2];
    wire [3:0] sum_zero [0:2],sum_one [0:2];
    wire [19:0] ones_prefix [0:5],zeros_prefix [0:5];
    wire increment = generate_stage[2][2] && !immediate_i[11];
    wire decrement = !generate_stage[2][2] && immediate_i[11];
    wire [9:0] adjustment_views;
    rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(5)) adjustment_tree (
        .signal_i({decrement,increment}),.views_o(adjustment_views));
    assign ones_prefix[0]=base_i[31:12];
    assign zeros_prefix[0]=~base_i[31:12];
    genvar block_index,prefix_level,upper_bit;
    generate
        for(block_index=0;block_index<3;block_index=block_index+1) begin:g_low_block
            wire [4:0] block_sum={1'b0,base_i[block_index*4 +: 4]}+
                {1'b0,immediate_i[block_index*4 +: 4]};
            assign sum_zero[block_index]=block_sum[3:0];
            assign sum_one[block_index]=block_sum[3:0]+4'd1;
            assign generate_stage[0][block_index]=block_sum[4];
            assign propagate_stage[0][block_index]=
                &(base_i[block_index*4 +: 4] ^ immediate_i[block_index*4 +: 4]);
            if(block_index==0) begin:g_first
                assign sum_o[0 +: 4]=sum_zero[0];
            end else begin:g_select
                assign sum_o[block_index*4 +: 4]=generate_stage[2][block_index-1] ?
                    sum_one[block_index] : sum_zero[block_index];
            end
        end
        for(prefix_level=0;prefix_level<2;prefix_level=prefix_level+1) begin:g_low_prefix
            localparam integer DISTANCE=1<<prefix_level;
            for(block_index=0;block_index<3;block_index=block_index+1) begin:g_block
                if(block_index>=DISTANCE) begin:g_combine
                    assign generate_stage[prefix_level+1][block_index]=generate_stage[prefix_level][block_index] |
                        (propagate_stage[prefix_level][block_index] && generate_stage[prefix_level][block_index-DISTANCE]);
                    assign propagate_stage[prefix_level+1][block_index]=propagate_stage[prefix_level][block_index] &&
                        propagate_stage[prefix_level][block_index-DISTANCE];
                end else begin:g_copy
                    assign generate_stage[prefix_level+1][block_index]=generate_stage[prefix_level][block_index];
                    assign propagate_stage[prefix_level+1][block_index]=propagate_stage[prefix_level][block_index];
                end
            end
        end
        for(prefix_level=0;prefix_level<5;prefix_level=prefix_level+1) begin:g_upper_prefix
            localparam integer DISTANCE=1<<prefix_level;
            for(upper_bit=0;upper_bit<20;upper_bit=upper_bit+1) begin:g_bit
                if(upper_bit>=DISTANCE) begin:g_combine
                    assign ones_prefix[prefix_level+1][upper_bit]=ones_prefix[prefix_level][upper_bit] &&
                        ones_prefix[prefix_level][upper_bit-DISTANCE];
                    assign zeros_prefix[prefix_level+1][upper_bit]=zeros_prefix[prefix_level][upper_bit] &&
                        zeros_prefix[prefix_level][upper_bit-DISTANCE];
                end else begin:g_copy
                    assign ones_prefix[prefix_level+1][upper_bit]=ones_prefix[prefix_level][upper_bit];
                    assign zeros_prefix[prefix_level+1][upper_bit]=zeros_prefix[prefix_level][upper_bit];
                end
            end
        end
        for(upper_bit=0;upper_bit<20;upper_bit=upper_bit+1) begin:g_upper_sum
            localparam integer DOMAIN=upper_bit/4;
            wire increment_bit=adjustment_views[DOMAIN*2];
            wire decrement_bit=adjustment_views[DOMAIN*2+1];
            if(upper_bit==0) begin:g_first
                assign sum_o[12]=base_i[12] ^ (increment_bit || decrement_bit);
            end else begin:g_later
                assign sum_o[12+upper_bit]=base_i[12+upper_bit] ^
                    ((increment_bit && ones_prefix[5][upper_bit-1]) ||
                     (decrement_bit && zeros_prefix[5][upper_bit-1]));
            end
        end
    endgenerate
    // A signed12 displacement changes base[31:12] by only -1,0,+1.
    // Classify each possible high word before the existing low12 carry;
    // do not form four late adjusted sum bits and then reduce them.
    generate if(CLASS_COMPARE!=0) begin:g_class_compare
        wire high_zero=base_i[31:28]==4'h0;
        wire high_ones=base_i[31:28]==4'hf;
        wire high_one=base_i[31:28]==4'h1;
        // These exact lower16 reductions already exist for the full sum.
        wire middle_ones=ones_prefix[5][15];
        wire middle_zero=zeros_prefix[5][15];
        wire ram_increment=middle_ones ? high_ones : high_zero;
        wire ram_decrement=middle_zero ? high_one : high_zero;
        wire ram_carry_zero=immediate_i[11] ? ram_decrement : high_zero;
        wire ram_carry_one=immediate_i[11] ? high_zero : ram_increment;
        wire ram=generate_stage[2][2] ? ram_carry_one : ram_carry_zero;
        assign class_flags_o={sum_o[1:0]==2'b00,!sum_o[0],ram};
    end else begin:g_no_class_compare
        assign class_flags_o=3'b0;
    end endgenerate
`endif
endmodule


// Read a packed row array using two already-decoded index banks. A selected
// input bit drives bounded row groups; no encoded-index decode follows the
// late report selection. The caller retains the full normal generation check.
(* keep_hierarchy = 1 *)
module rv32_frequency_array_read_bank_masks #(
    parameter integer WIDTH=9,ENTRIES=64,
    parameter integer INDEX_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES),
    parameter integer LOW_BITS=(INDEX_WIDTH+1)/2,
    parameter integer HIGH_BITS=INDEX_WIDTH-LOW_BITS,
    parameter integer LOW_ROWS=1<<LOW_BITS,HIGH_ROWS=1<<HIGH_BITS,
    parameter integer WORDS=(WIDTH+15)/16,
    parameter integer LEAVES=1<<$clog2(ENTRIES)
) (
    input wire [ENTRIES*WIDTH-1:0] rows_i,
    input wire [LOW_ROWS+HIGH_ROWS-1:0] query_i,
    output wire [WIDTH-1:0] value_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    reg [WIDTH-1:0] selected;
    integer row;
    always @* begin
        selected = 0;
        for (row=0; row<ENTRIES; row=row+1)
            if (row < (1<<INDEX_WIDTH) && query_i[row%LOW_ROWS] && query_i[LOW_ROWS+row/LOW_ROWS])
                selected = selected | rows_i[row*WIDTH +: WIDTH];
    end
    assign value_o = selected;
`else
    wire [2*(LOW_ROWS+HIGH_ROWS)-1:0] query_views;
    wire [WIDTH-1:0] reads [1:2*LEAVES-1];
    rv32_frequency_control_tree #(.WIDTH(LOW_ROWS+HIGH_ROWS),.LEAVES(2)) query_tree (
        .signal_i(query_i),.views_o(query_views));
    assign value_o=reads[1];
    genvar row,word,node;
    generate
        for(row=0;row<LEAVES;row=row+1) begin:g_row
            if(row<ENTRIES && row<(1<<INDEX_WIDTH)) begin:g_present
                localparam integer DOMAIN=(row*2)/ENTRIES;
                wire [WORDS-1:0] selects;
                wire hit=query_views[DOMAIN*(LOW_ROWS+HIGH_ROWS)+(row%LOW_ROWS)] &&
                    query_views[DOMAIN*(LOW_ROWS+HIGH_ROWS)+LOW_ROWS+(row/LOW_ROWS)];
                rv32_frequency_control_tree #(.LEAVES(WORDS)) select_tree (
                    .signal_i(hit),.views_o(selects));
                for(word=0;word<WORDS;word=word+1) begin:g_word
                    localparam integer LOW=word*16;
                    localparam integer BITS=(WIDTH-LOW>=16)?16:WIDTH-LOW;
                    assign reads[LEAVES+row][LOW +: BITS]=
                        {BITS{selects[word]}} & rows_i[row*WIDTH+LOW +: BITS];
                end
            end else begin:g_padding
                assign reads[LEAVES+row]=0;
            end
        end
        for(node=1;node<LEAVES;node=node+1) begin:g_reduce
            assign reads[node]=reads[2*node] | reads[2*node+1];
        end
    endgenerate
`endif
endmodule


// Narrow table read: each row hit directly drives at most four data masks.
// Retain the original four-row index distribution and balanced OR reduction;
// wide payload reads still use the original bounded word/select trees.
module rv32_frequency_narrow_array_read #(
    parameter integer WIDTH=3,ENTRIES=64,
    parameter integer INDEX_WIDTH=(ENTRIES<=1)?1:$clog2(ENTRIES),
    parameter integer DOMAINS=(ENTRIES+3)/4,
    parameter integer LEAVES=1<<$clog2(ENTRIES)
) (
    input wire [ENTRIES*WIDTH-1:0] rows_i,
    input wire [INDEX_WIDTH-1:0] index_i,
    output wire [WIDTH-1:0] value_o
);
// Equivalent two-state word form for the cycle-accurate simulator.
// Synthesis retains the original fanout/carry/ownership structure.
`ifdef CPU2026_WORD_SIM
    assign value_o = (index_i < ENTRIES) ? rows_i[index_i*WIDTH +: WIDTH] : {WIDTH{1'b0}};
    initial if (WIDTH < 1 || WIDTH > 4) $fatal(1,"Narrow array read width must be1..4");
`else
    wire [DOMAINS*INDEX_WIDTH-1:0] query_views;
    wire [WIDTH-1:0] reads [1:2*LEAVES-1];
    rv32_frequency_control_tree #(.WIDTH(INDEX_WIDTH),.LEAVES(DOMAINS)) query_tree (
        .signal_i(index_i),.views_o(query_views));
    assign value_o=reads[1];
    genvar row,node;
    generate
        for(row=0;row<LEAVES;row=row+1) begin:g_row
            if(row<ENTRIES) begin:g_present
                wire hit=query_views[(row/4)*INDEX_WIDTH +: INDEX_WIDTH]==row;
                assign reads[LEAVES+row]={WIDTH{hit}} & rows_i[row*WIDTH +: WIDTH];
            end else begin:g_padding
                assign reads[LEAVES+row]=0;
            end
        end
        for(node=1;node<LEAVES;node=node+1) begin:g_reduce
            assign reads[node]=reads[2*node] | reads[2*node+1];
        end
    endgenerate
    initial begin
        if(WIDTH<1 || WIDTH>4)
            $fatal(1,"Narrow array read width must be1..4");
    end
`endif
endmodule
