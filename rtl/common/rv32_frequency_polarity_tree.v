`timescale 1ns/1ps

// A filled four-way tree with an even number of actual inversion stages.
// Its virtual positive root drives <=4 first-stage inverter inputs per bit.
// Each actual internal driver owns <=4 child inverter inputs. Every output
// leaf is positive and owns its original consumer group; no alias leaf can
// expose an internal driver to a wide payload. No padded leaf is instantiated.
module rv32_frequency_polarity_tree #(
    parameter integer WIDTH=1, LEAVES=4
) (
    input wire [WIDTH-1:0] signal_i,
    output wire [WIDTH*LEAVES-1:0] views_o
);
    function automatic integer even_levels;
        input integer count;
        integer capacity,levels;
        begin
            capacity=16;levels=2;
            while(capacity<count) begin capacity=capacity*16;levels=levels+2;end
            even_levels=levels;
        end
    endfunction
    localparam integer LEVELS=even_levels(LEAVES);
    localparam integer GROUP_CAPACITY=4**(LEVELS-1);
    localparam integer GROUPS=(LEAVES+GROUP_CAPACITY-1)/GROUP_CAPACITY;
    genvar group_id;
    generate for(group_id=0;group_id<GROUPS;group_id=group_id+1) begin:g_group
        localparam integer OFFSET=group_id*GROUP_CAPACITY;
        localparam integer COUNT=(LEAVES-OFFSET>GROUP_CAPACITY)?GROUP_CAPACITY:LEAVES-OFFSET;
        rv32_frequency_polarity_node #(.WIDTH(WIDTH),.LEAVES(COUNT),.LEVELS(LEVELS)) node (
            .signal_i(signal_i),.views_o(views_o[OFFSET*WIDTH +: COUNT*WIDTH]));
    end endgenerate
endmodule

module rv32_frequency_polarity_node #(
    parameter integer WIDTH=1,LEAVES=4,LEVELS=2
) (
    input wire [WIDTH-1:0] signal_i,
    output wire [WIDTH*LEAVES-1:0] views_o
);
    wire [WIDTH-1:0] inverted;
    genvar bit_id,child;
    generate
        for(bit_id=0;bit_id<WIDTH;bit_id=bit_id+1) begin:g_driver
            (* keep=1,keep_hierarchy=1 *)
            rv32_frequency_inversion invert (
                .signal_i(signal_i[bit_id]),.signal_o(inverted[bit_id]));
        end
        if(LEVELS==1) begin:g_leaf
            assign views_o=inverted;
        end else begin:g_internal
            localparam integer CHILD_CAPACITY=4**(LEVELS-2);
            localparam integer CHILDREN=(LEAVES+CHILD_CAPACITY-1)/CHILD_CAPACITY;
            for(child=0;child<CHILDREN;child=child+1) begin:g_child
                localparam integer OFFSET=child*CHILD_CAPACITY;
                localparam integer COUNT=(LEAVES-OFFSET>CHILD_CAPACITY)?CHILD_CAPACITY:LEAVES-OFFSET;
                rv32_frequency_polarity_node #(.WIDTH(WIDTH),.LEAVES(COUNT),.LEVELS(LEVELS-1)) node (
                    .signal_i(inverted),.views_o(views_o[OFFSET*WIDTH +: COUNT*WIDTH]));
            end
        end
    endgenerate
endmodule
