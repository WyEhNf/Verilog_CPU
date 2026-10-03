`timescale 1ns/1ps
`include "rv32im_defs.vh"

// Physical register file for the rename/issue boundary.
//
// Ports are flattened in lane order: lane n occupies the slice beginning at
// n*width.  A write in the highest numbered lane wins when multiple valid
// writes target the same physical register in one cycle.
module rv32_physical_register_file #(
    parameter integer BE_WIDTH = `RV32IM_BE_WIDTH_DEFAULT,
    parameter integer PHYS_REGS = `RV32IM_PHYS_REGS_DEFAULT,
    parameter integer READ_MUX_IMPL = 0,
    parameter integer LOCAL_VALUE_ROWS = 0,
    parameter integer PHYS_ADDR_WIDTH = (PHYS_REGS <= 1) ? 1 : $clog2(PHYS_REGS)
) (
    input  wire                         clk_i,
    input  wire                         reset_i,
    input  wire [(2*BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] read_phys_i,
    output reg  [(2*BE_WIDTH*32)-1:0]   read_data_o,
    output reg  [(2*BE_WIDTH)-1:0]      read_ready_o,
    input  wire [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] alloc_phys_i,
    input  wire [BE_WIDTH-1:0]           alloc_valid_i,
    input  wire [(BE_WIDTH*PHYS_ADDR_WIDTH)-1:0] write_phys_i,
    input  wire [(BE_WIDTH*32)-1:0]      write_data_i,
    input  wire [BE_WIDTH-1:0]           write_valid_i
);
    // Keep the value store as a word array so synthesis can implement it as
    // a compact multi-ported memory.  The previous flattened vector forced
    // every data bit into a flip-flop plus a large read mux.
    wire [31:0] value [0:PHYS_REGS-1];
    reg [31:0] value_legacy [0:PHYS_REGS-1];
    wire [PHYS_REGS-1:0] ready;
    reg [PHYS_REGS-1:0] ready_legacy;
    integer alloc_lane;
    integer write_lane;

    initial begin
        if ((BE_WIDTH != 1) && (BE_WIDTH != 2) && (BE_WIDTH != 4)) begin
            $display("ERROR: invalid PRF BE_WIDTH=%0d; expected 1, 2, or 4", BE_WIDTH);
            $finish;
        end
        if (PHYS_REGS < 33) begin
            $display("ERROR: invalid PRF PHYS_REGS=%0d; expected at least 33", PHYS_REGS);
            $finish;
        end
        if (PHYS_ADDR_WIDTH < $clog2(PHYS_REGS)) begin
            $display("ERROR: invalid PRF PHYS_ADDR_WIDTH=%0d for PHYS_REGS=%0d", PHYS_ADDR_WIDTH, PHYS_REGS);
            $finish;
        end
    end


    localparam integer READ_DOMAINS=4;
    wire [2*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] read_phys_local;
    wire [READ_DOMAINS*2*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] read_domain_queries;
    generate if(READ_MUX_IMPL!=0) begin:g_query_domains
        wire [(READ_DOMAINS+1)*2*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] queries;
        rv32_frequency_control_tree #(.WIDTH(2*BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(READ_DOMAINS+1)) query_tree (
            .signal_i(read_phys_i),.views_o(queries));
        assign read_domain_queries=queries[0 +: READ_DOMAINS*2*BE_WIDTH*PHYS_ADDR_WIDTH];
        assign read_phys_local=queries[READ_DOMAINS*2*BE_WIDTH*PHYS_ADDR_WIDTH +: 2*BE_WIDTH*PHYS_ADDR_WIDTH];
    end else begin:g_legacy_query
        rv32_frequency_control_tree #(.WIDTH(2*BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(1)) query_tree (
            .signal_i(read_phys_i),.views_o(read_phys_local));
        assign read_domain_queries=0;
    end endgenerate
    genvar owner_row,owner_lane;
    generate if(LOCAL_VALUE_ROWS!=0) begin:g_local_storage
        wire [PHYS_REGS-1:0] reset_views;
        rv32_frequency_control_tree #(.LEAVES(PHYS_REGS)) reset_tree (
            .signal_i(reset_i),.views_o(reset_views));
        wire [4*BE_WIDTH*32-1:0] write_values;
        wire [4*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] write_addresses,alloc_addresses;
        wire [4*BE_WIDTH-1:0] write_valids,alloc_valids;
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*32),.LEAVES(4)) value_tree (
            .signal_i(write_data_i),.views_o(write_values));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(4)) write_address_tree (
            .signal_i(write_phys_i),.views_o(write_addresses));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(4)) alloc_address_tree (
            .signal_i(alloc_phys_i),.views_o(alloc_addresses));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(4)) write_valid_tree (
            .signal_i(write_valid_i),.views_o(write_valids));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(4)) alloc_valid_tree (
            .signal_i(alloc_valid_i),.views_o(alloc_valids));
        for(owner_row=0;owner_row<PHYS_REGS;owner_row=owner_row+1) begin:g_row
            if(owner_row==0) begin:g_zero
                assign value[owner_row]=0;assign ready[owner_row]=1;
            end else begin:g_register
                localparam integer DOMAIN=(owner_row*4)/PHYS_REGS;
                wire [BE_WIDTH-1:0] writes,allocations;
                for(owner_lane=0;owner_lane<BE_WIDTH;owner_lane=owner_lane+1) begin:g_match
                    assign writes[owner_lane]=write_valids[DOMAIN*BE_WIDTH+owner_lane] &&
                        write_addresses[(DOMAIN*BE_WIDTH+owner_lane)*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==owner_row;
                    assign allocations[owner_lane]=alloc_valids[DOMAIN*BE_WIDTH+owner_lane] &&
                        alloc_addresses[(DOMAIN*BE_WIDTH+owner_lane)*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==owner_row;
                end
                rv32_prf_value_row #(.LANES(BE_WIDTH)) contents (
                    .clk_i(clk_i),.reset_i(reset_views[owner_row]),.alloc_i(|allocations),.write_matches_i(writes),
                    .write_values_i(write_values[DOMAIN*BE_WIDTH*32 +: BE_WIDTH*32]),
                    .value_o(value[owner_row]),.ready_o(ready[owner_row]));
            end
        end
    end else begin:g_legacy_alias
        for(owner_row=0;owner_row<PHYS_REGS;owner_row=owner_row+1) begin:g_row
            assign value[owner_row]=value_legacy[owner_row];
        end
        assign ready=ready_legacy;
    end endgenerate


    // Four query domains decode physical words independently. Data and ready
    // use separate bounded select leaves; the reductions have explicit depth.
    localparam integer READ_ROWS=(PHYS_REGS<=1)?1:(1<<$clog2(PHYS_REGS));
    genvar rp,row,wl,read_node;
    generate if(READ_MUX_IMPL!=0) begin:g_parallel_read
        for(rp=0;rp<2*BE_WIDTH;rp=rp+1) begin:g_port
            wire [PHYS_ADDR_WIDTH-1:0] address=read_phys_local[rp*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
            wire legal=address!=0 && address<PHYS_REGS;
            wire [31:0] stored_tree [1:2*READ_ROWS-1];
            wire ready_tree [1:2*READ_ROWS-1];
            wire [BE_WIDTH-1:0] bypass_match;
            wire [31:0] bypass_value;
            wire bypass_write;
            wire [1:0] bypass_select;
            for(row=0;row<READ_ROWS;row=row+1) begin:g_word
                if(row>0 && row<PHYS_REGS) begin:g_present
                    localparam integer DOMAIN=(row*READ_DOMAINS)/PHYS_REGS;
                    wire selected=read_domain_queries[(DOMAIN*2*BE_WIDTH+rp)*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==row;
                    wire [2:0] select_views;
                    rv32_frequency_control_tree #(.LEAVES(3)) selection_tree (
                        .signal_i(selected),.views_o(select_views));
                    assign stored_tree[READ_ROWS+row]={{16{select_views[1]}} & value[row][31:16],{16{select_views[0]}} & value[row][15:0]};
                    assign ready_tree[READ_ROWS+row]=select_views[2] && ready[row];
                end else begin:g_zero_or_padding
                    assign stored_tree[READ_ROWS+row]=0;
                    assign ready_tree[READ_ROWS+row]=0;
                end
            end
            for(read_node=1;read_node<READ_ROWS;read_node=read_node+1) begin:g_reduce
                assign stored_tree[read_node]=stored_tree[2*read_node] | stored_tree[2*read_node+1];
                assign ready_tree[read_node]=ready_tree[2*read_node] | ready_tree[2*read_node+1];
            end
            for(wl=0;wl<BE_WIDTH;wl=wl+1) begin:g_bypass
                assign bypass_match[wl]=legal && write_valid_i[wl] &&
                    write_phys_i[wl*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]==address;
            end
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(BE_WIDTH)) bypass_selector (
                .events_i(bypass_match),.values_i(write_data_i),.write_o(bypass_write),.value_o(bypass_value));
            rv32_frequency_control_tree #(.LEAVES(2)) bypass_choice_tree (
                .signal_i(bypass_write),.views_o(bypass_select));
            always @* begin
                read_data_o[rp*32 +: 32]={bypass_select[1]?bypass_value[31:16]:stored_tree[1][31:16],bypass_select[0]?bypass_value[15:0]:stored_tree[1][15:0]};
                read_ready_o[rp]=(address==0) || ready_tree[1] || bypass_write;
            end
        end
    end else begin : g_original_read
    // Reads are combinational.  Each generated process has constant output
    // slices; @* also expands the word-array dependency for simulators.
    genvar read_port;
        for (read_port = 0; read_port < (2*BE_WIDTH); read_port = read_port + 1) begin : g_read_port
            integer bypass_lane;
            always @* begin
                bypass_lane = 0;
                read_data_o[(read_port*32) +: 32] = 32'b0;
                read_ready_o[read_port] = 1'b0;
                if (read_phys_local[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] == 0) begin
                    read_ready_o[read_port] = 1'b1;
                end else if (read_phys_local[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] < PHYS_REGS) begin
                    read_data_o[(read_port*32) +: 32] = value[read_phys_local[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]];
                    read_ready_o[read_port] = ready[read_phys_local[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]];
                    // When ready is low this data is architecturally don't-care;
                    // consumers must wait for writeback rather than depend on a
                    // reset value in the data array.
                    for (bypass_lane = 0; bypass_lane < BE_WIDTH; bypass_lane = bypass_lane + 1) begin
                        if (write_valid_i[bypass_lane] &&
                            (write_phys_i[(bypass_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] ==
                             read_phys_local[(read_port*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH])) begin
                            read_data_o[(read_port*32) +: 32] = write_data_i[(bypass_lane*32) +: 32];
                            read_ready_o[read_port] = 1'b1;
                        end
                    end
                end
            end
        end

    end endgenerate

    generate if(LOCAL_VALUE_ROWS==0) begin:g_legacy_storage
    always @(posedge clk_i) begin
        if (reset_i) begin
            ready_legacy <= {{(PHYS_REGS-1){1'b0}}, 1'b1};
        end else begin
            // Rename allocation makes a destination unavailable.  Writeback
            // is processed afterwards and therefore has higher priority.
            for (alloc_lane = 0; alloc_lane < BE_WIDTH; alloc_lane = alloc_lane + 1) begin
                if (alloc_valid_i[alloc_lane] &&
                    (alloc_phys_i[(alloc_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] != 0) &&
                    (alloc_phys_i[(alloc_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] < PHYS_REGS)) begin
                    ready_legacy[alloc_phys_i[(alloc_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]] <= 1'b0;
                end
            end
            // Iterating low-to-high makes the highest lane deterministic.
            // P0 is hardwired and out-of-range encoded addresses are ignored.
            for (write_lane = 0; write_lane < BE_WIDTH; write_lane = write_lane + 1) begin
                if (write_valid_i[write_lane] &&
                    (write_phys_i[(write_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] != 0) &&
                    (write_phys_i[(write_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH] < PHYS_REGS)) begin
                    value_legacy[write_phys_i[(write_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]] <= write_data_i[(write_lane*32) +: 32];
                    ready_legacy[write_phys_i[(write_lane*PHYS_ADDR_WIDTH) +: PHYS_ADDR_WIDTH]] <= 1'b1;
                end
            end
            ready_legacy[0] <= 1'b1;
        end
    end
    end endgenerate
endmodule

// Highest valid lane wins. Value payload has no later reset mux; the final
// write enable already excludes reset before its priced local driver.
module rv32_prf_value_row #(parameter integer LANES=4) (
    input wire clk_i,reset_i,alloc_i,
    input wire [LANES-1:0] write_matches_i,
    input wire [LANES*32-1:0] write_values_i,
    output reg [31:0] value_o,
    output reg ready_o
);
    wire [1:0] write_views;
    wire write_event;
    wire [31:0] next_value;
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(LANES)) value_selector (
        .events_i(write_matches_i),.values_i(write_values_i),.write_o(write_event),.value_o(next_value));
    rv32_frequency_control_tree #(.LEAVES(2)) write_tree (
        .signal_i(!reset_i && write_event),.views_o(write_views));
    always @(posedge clk_i) if(write_views[0]) value_o[15:0]<=next_value[15:0];
    always @(posedge clk_i) if(write_views[1]) value_o[31:16]<=next_value[31:16];
    always @(posedge clk_i) begin
        if(reset_i) ready_o<=0;
        else if(|write_matches_i) ready_o<=1;
        else if(alloc_i) ready_o<=0;
    end
endmodule
