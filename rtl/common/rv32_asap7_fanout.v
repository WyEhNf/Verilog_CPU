`timescale 1ns/1ps

// A complete functional RTL module. ABC maps this inversion to real library
// logic. The hierarchy boundary prevents cancellation with the next inversion;
// keep on each instance prevents identical sibling instances from merging.
// No external cell declaration, blackbox, whitebox, or area override is used.
(* keep_hierarchy = 1 *)
module rv32_frequency_inversion(input wire signal_i, output wire signal_o);
    assign signal_o = ~signal_i;
endmodule

// Four-way recursive distribution with a pair of real inversions at each
// node. Every internal driver has at most four child consumers. Leaf outputs
// must be attached to bounded groups of actual consumers by the caller.
// Combinational only: the observable signal and cycle remain unchanged.
module rv32_frequency_control_tree #(
    parameter integer WIDTH = 1,
    parameter integer LEAVES = 4
) (
    input wire [WIDTH-1:0] signal_i,
    output wire [WIDTH*LEAVES-1:0] views_o
);
    localparam integer CHILDREN = LEAVES > 4 ? 4 : LEAVES;
    localparam integer BASE_COUNT = LEAVES / CHILDREN;
    localparam integer EXTRA_COUNT = LEAVES % CHILDREN;
    wire [WIDTH-1:0] inverted, distributed;
    genvar bit_id, child;
    generate
        for (bit_id=0; bit_id<WIDTH; bit_id=bit_id+1) begin:g_driver
            (* keep = 1, keep_hierarchy = 1 *)
            rv32_frequency_inversion invert_root (
                .signal_i(signal_i[bit_id]), .signal_o(inverted[bit_id]));
            (* keep = 1, keep_hierarchy = 1 *)
            rv32_frequency_inversion invert_output (
                .signal_i(inverted[bit_id]), .signal_o(distributed[bit_id]));
        end
        if (LEAVES == 1) begin:g_leaf
            assign views_o = distributed;
        end else begin:g_branches
            for (child=0; child<CHILDREN; child=child+1) begin:g_child
                localparam integer COUNT = BASE_COUNT + (child < EXTRA_COUNT);
                localparam integer OFFSET = child*BASE_COUNT +
                    (child < EXTRA_COUNT ? child : EXTRA_COUNT);
                rv32_frequency_control_tree #(.WIDTH(WIDTH), .LEAVES(COUNT)) subtree (
                    .signal_i(distributed),
                    .views_o(views_o[OFFSET*WIDTH +: COUNT*WIDTH]));
            end
        end
    endgenerate
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
endmodule


// Insert an access-relative word at any byte offset, preserving the original
// 128-bit left shift and overflow truncation. Increasing intermediate widths
// retain all reachable bits; each amount leaf owns <=16 actual mux bits.
module rv32_frequency_line_insert32 (
    input wire [31:0] value_i,
    input wire [3:0] offset_i,
    output wire [127:0] line_o
);
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
endmodule
