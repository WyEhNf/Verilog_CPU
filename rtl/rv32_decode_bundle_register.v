`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Ordered elastic bundle implemented as a ring: dequeue changes a pointer,
// never shifts the entire decoded payload through a recovery/ready mux.
module rv32_decode_bundle_register #(
    parameter integer LANES=4, PAYLOAD_WIDTH=194, CAPACITY=2*LANES,
    parameter integer CW=(CAPACITY<2)?1:$clog2(CAPACITY+1),
    parameter integer PW=(CAPACITY<2)?1:$clog2(CAPACITY)
) (
    input wire clk_i,reset_i,flush_i,
    input wire [LANES-1:0] valid_i,
    output reg [LANES-1:0] ready_o,
    input wire [LANES*PAYLOAD_WIDTH-1:0] data_i,
    output reg [LANES-1:0] valid_o,
    input wire [LANES-1:0] ready_i,
    output wire [LANES*PAYLOAD_WIDTH-1:0] data_o
);
    localparam integer WORDS=(PAYLOAD_WIDTH+15)/16;
    reg [CW-1:0] count;
    reg [PW-1:0] head,tail;
    reg [CW-1:0] consumed,accepted;
    integer lane,capacity;
    reg prefix;
    // Raw storage writes agree with public acceptance on ordinary cycles.
    // During invalidation arbitrary payload writes are harmless: count=0 wins.
    reg [LANES-1:0] storage_push;
    reg [LANES-1:0] storage_ready;
    reg [CW-1:0] storage_consumed;
    wire invalidate = reset_i || flush_i;
    wire [1:0] invalidate_domains;
    rv32_frequency_control_tree #(.LEAVES(2)) invalidate_tree (
        .signal_i(invalidate),.views_o(invalidate_domains));
    wire [CAPACITY*PAYLOAD_WIDTH-1:0] rows;
    always @* begin
        consumed=0;accepted=0;valid_o=0;ready_o=0;prefix=1;
        storage_consumed=0;storage_push=0;storage_ready=0;
        for(lane=0;lane<LANES;lane=lane+1) begin
            valid_o[lane]=(lane<count) && !invalidate_domains[0];
            if(prefix && (lane<count) && ready_i[lane])
                storage_consumed=storage_consumed+1'b1;
            else prefix=0;
        end
        // Upstream space is determined solely by registered occupancy.
        capacity=CAPACITY-32'(count);
        prefix=1;
        for(lane=0;lane<LANES;lane=lane+1) begin
            storage_ready[lane]=prefix && (lane<capacity);
            storage_push[lane]=storage_ready[lane] && valid_i[lane];
            ready_o[lane]=storage_ready[lane] && !invalidate_domains[0];
            if(ready_o[lane] && valid_i[lane]) accepted=accepted+1'b1;
            if(!storage_push[lane]) prefix=0;
        end
        if(!invalidate_domains[0]) consumed=storage_consumed;
    end
    always @(posedge clk_i) begin
        if(invalidate_domains[1])
        begin
            count<=0;
            head<=0;
            tail<=0;
        end
        else
        begin
            count<=count-consumed+accepted;
            head<=PW'((32'(head)+32'(consumed))%CAPACITY);
            tail<=PW'((32'(tail)+32'(accepted))%CAPACITY);
        end
    end
    genvar slot,word_id,read_lane;
    generate for(slot=0;slot<CAPACITY;slot=slot+1) begin:g_slot
        for(word_id=0;word_id<WORDS;word_id=word_id+1) begin:g_field
            localparam integer W=((PAYLOAD_WIDTH-word_id*16)<16)?(PAYLOAD_WIDTH-word_id*16):16;
            wire [LANES*W-1:0] inputs;
            for(genvar writer=0;writer<LANES;writer=writer+1) begin:g_input
                assign inputs[writer*W +: W]=data_i[writer*PAYLOAD_WIDTH+word_id*16 +: W];
            end
            rv32_decode_field_bank #(.LANES(LANES),.WIDTH(W),.ROW(slot),.PW(PW),.CAPACITY(CAPACITY)) bank (
                .clk_i(clk_i),.reset_i(1'b0),.flush_i(1'b0),.tail_i(tail),
                .push_i(storage_push),.data_i(inputs),.data_o(rows[slot*PAYLOAD_WIDTH+word_id*16 +: W]));
        end
    end

    localparam integer READ_LEAVES=1<<$clog2(CAPACITY);
    wire [CAPACITY*LANES*WORDS-1:0] read_selections;
    genvar read_row,read_word,read_node;
    for(read_row=0;read_row<CAPACITY;read_row=read_row+1) begin:g_head_selection
        wire selected=head==read_row;
        rv32_frequency_control_tree #(.LEAVES(LANES*WORDS)) selection_tree (
            .signal_i(selected),.views_o(read_selections[read_row*LANES*WORDS +: LANES*WORDS]));
    end
    for(read_lane=0;read_lane<LANES;read_lane=read_lane+1) begin:g_read
        wire [PAYLOAD_WIDTH-1:0] payload_tree [1:2*READ_LEAVES-1];
        for(read_row=0;read_row<READ_LEAVES;read_row=read_row+1) begin:g_row
            if(read_row<CAPACITY) begin:g_present
                localparam integer HEAD_ROW=(read_row+CAPACITY-read_lane)%CAPACITY;
                for(read_word=0;read_word<WORDS;read_word=read_word+1) begin:g_word
                    localparam integer LOW=read_word*16;
                    localparam integer BITS=PAYLOAD_WIDTH-LOW>=16 ? 16 : PAYLOAD_WIDTH-LOW;
                    assign payload_tree[READ_LEAVES+read_row][LOW +: BITS]=
                        {BITS{read_selections[(HEAD_ROW*LANES+read_lane)*WORDS+read_word]}} &
                        rows[read_row*PAYLOAD_WIDTH+LOW +: BITS];
                end
            end else begin:g_padding
                assign payload_tree[READ_LEAVES+read_row]=0;
            end
        end
        for(read_node=1;read_node<READ_LEAVES;read_node=read_node+1) begin:g_or
            assign payload_tree[read_node]=payload_tree[2*read_node] | payload_tree[2*read_node+1];
        end
        assign data_o[read_lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]=payload_tree[1];
    end
    endgenerate
    initial begin
        if(CAPACITY<LANES || (CAPACITY & (CAPACITY-1))!=0)
            $fatal(1,"Decode queue capacity must be a power of two >= LANES");
    end

endmodule
