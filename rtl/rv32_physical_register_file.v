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

    wire [2*BE_WIDTH*PHYS_ADDR_WIDTH-1:0] read_phys_local;
    rv32_frequency_control_tree #(.WIDTH(2*BE_WIDTH*PHYS_ADDR_WIDTH),.LEAVES(1)) read_query_tree (
        .signal_i(read_phys_i),.views_o(read_phys_local));
    genvar owner_row,owner_lane;
    generate if(LOCAL_VALUE_ROWS!=0) begin:g_local_storage
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
                    .clk_i(clk_i),.reset_i(reset_i),.alloc_i(|allocations),.write_matches_i(writes),
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

    // Decode each read word once and select data in parallel. Preserve zero
    // register, out-of-range behavior, and last-lane write bypass priority.
    genvar rp, row, wl;
    generate if (READ_MUX_IMPL != 0) begin : g_parallel_read
        for (rp = 0; rp < 2*BE_WIDTH; rp = rp + 1) begin : g_port
            wire [PHYS_ADDR_WIDTH-1:0] address = read_phys_local[rp*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH];
            wire legal = address != 0 && address < PHYS_REGS;
            wire [PHYS_REGS-1:0] word_select;
            wire [BE_WIDTH-1:0] bypass_match, bypass_grant;
            for (row = 0; row < PHYS_REGS; row = row + 1) begin : g_word
                assign word_select[row] = (row != 0) && address == row;
            end
            for (wl = 0; wl < BE_WIDTH; wl = wl + 1) begin : g_bypass
                assign bypass_match[wl] = legal && write_valid_i[wl] &&
                    write_phys_i[wl*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH] == address;
                if (wl == BE_WIDTH-1) assign bypass_grant[wl] = bypass_match[wl];
                else assign bypass_grant[wl] = bypass_match[wl] && !(|bypass_match[BE_WIDTH-1:wl+1]);
            end
            reg [31:0] stored_value, bypass_value;
            reg stored_ready;
            integer read_word, bypass_index;
            always @* begin
                stored_value = 0;
                stored_ready = address == 0;
                bypass_value = 0;
                for (read_word = 1; read_word < PHYS_REGS; read_word = read_word + 1) begin
                    stored_value = stored_value | ({32{word_select[read_word]}} & value[read_word]);
                    stored_ready = stored_ready | (word_select[read_word] && ready[read_word]);
                end
                for (bypass_index = 0; bypass_index < BE_WIDTH; bypass_index = bypass_index + 1)
                    bypass_value = bypass_value | ({32{bypass_grant[bypass_index]}} & write_data_i[bypass_index*32 +: 32]);
                read_data_o[rp*32 +: 32] = (|bypass_match) ? bypass_value : stored_value;
                read_ready_o[rp] = stored_ready || (|bypass_match);
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
    wire [LANES-1:0] grants,local_grants;
    wire write_local;
    genvar lane;
    generate for(lane=0;lane<LANES;lane=lane+1) begin:g_grant
        if(lane==LANES-1) assign grants[lane]=write_matches_i[lane];
        else assign grants[lane]=write_matches_i[lane] && !(|write_matches_i[LANES-1:lane+1]);
    end endgenerate
    rv32_frequency_control_tree #(.WIDTH(LANES),.LEAVES(1)) grant_tree (
        .signal_i(grants),.views_o(local_grants));
    rv32_frequency_control_tree #(.LEAVES(1)) write_tree (
        .signal_i(!reset_i && (|write_matches_i)),.views_o(write_local));
    reg [31:0] next_value;
    integer port;
    always @* begin
        next_value=0;
        for(port=0;port<LANES;port=port+1)
            next_value=next_value | ({32{local_grants[port]}} & write_values_i[port*32 +: 32]);
    end
    always @(posedge clk_i) if(write_local) value_o<=next_value;
    always @(posedge clk_i) begin
        if(reset_i) ready_o<=0;
        else if(|write_matches_i) ready_o<=1;
        else if(alloc_i) ready_o<=0;
    end
endmodule
