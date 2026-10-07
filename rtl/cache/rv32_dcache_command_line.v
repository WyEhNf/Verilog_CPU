`timescale 1ns/1ps
`include "rv32im_defs.vh"

// One command owner per way, replacing four identical 32-bit address
// decoders. The storage remains sixteen DEPTH x 8 single-port macros.
// No registers, new edge, read port, or command acceptance are introduced.
(* keep_hierarchy = 1 *)
module rv32_dcache_command_line #(
    parameter integer SETS=512, WAYS=2, WAY=0,
    parameter integer IW=$clog2(SETS), EW=$clog2(SETS*WAYS)
) (
    input wire clk_i, reset_i,
    input wire refill_i, local_i, store_i, input_read_i, deferred_read_i,
    input wire [EW-1:0] refill_entry_i, local_entry_i, hit_entry_i,
    input wire [IW-1:0] input_index_i, deferred_index_i,
    input wire [127:0] response_data_i, response_store_data_i,
    input wire response_store_i,
    input wire [15:0] response_mask_i,
    input wire [127:0] local_data_i, store_data_i,
    input wire [15:0] store_mask_i,
    output wire [127:0] data_o
);
    // Priority depends on the global command, even in the unwritten way.
    wire refill_way=refill_i && ((32'(refill_entry_i)%WAYS)==WAY);
    wire local_way=!refill_i && local_i && ((32'(local_entry_i)%WAYS)==WAY);
    wire store_way=!refill_i && !local_i && store_i && ((32'(hit_entry_i)%WAYS)==WAY);
    wire writing=refill_way || local_way || store_way;
    wire full_write=refill_way || local_way;
    wire enabled=!reset_i && (writing || input_read_i || deferred_read_i);
    wire [IW-1:0] refill_set=IW'(32'(refill_entry_i)/WAYS);
    wire [IW-1:0] local_set=IW'(32'(local_entry_i)/WAYS);
    wire [IW-1:0] hit_set=IW'(32'(hit_entry_i)/WAYS);
    wire [IW-1:0] read_set=deferred_read_i?deferred_index_i:input_index_i;
    // Qualified grants are mutually exclusive. Select the complete address
    // in parallel instead of nesting victim/local/store/read address muxes.
    wire [IW-1:0] address=({IW{refill_way}} & refill_set) |
        ({IW{local_way}} & local_set) | ({IW{store_way}} & hit_set) |
        ({IW{!writing}} & read_set);
    localparam integer PIN_WIDTH=IW+3;
    wire [16*PIN_WIDTH-1:0] pin_views;
    rv32_frequency_control_tree #(.WIDTH(PIN_WIDTH),.LEAVES(16)) pin_tree (
        .signal_i({enabled,writing,full_write,address}),.views_o(pin_views));
    // Each final grant leaf selects only sixteen write-data bits. The raw
    // local/refill command never drives the wide payload selection again.
    wire [15:0] data_select_views;
    rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(8)) data_select_tree (
        .signal_i({refill_way,local_way}),.views_o(data_select_views));
    genvar byte_id;
    generate for(byte_id=0;byte_id<16;byte_id=byte_id+1) begin:g_byte
        wire port_enable,port_write,port_full_write;
        wire [IW-1:0] port_address;
        assign {port_enable,port_write,port_full_write,port_address}=
            pin_views[byte_id*PIN_WIDTH +: PIN_WIDTH];
        wire refill_select=data_select_views[(byte_id/2)*2+1];
        wire local_select=data_select_views[(byte_id/2)*2];
        // Qualify before a preserved boundary. The raw store-response
        // command reaches sixteen byte qualifications, not 128 data mux bits.
        // Each final byte selection controls only eight payload mux bits.
        wire merge_store_byte;
        rv32_frequency_control_tree #(.LEAVES(1)) merge_selection_tree (
            .signal_i(response_store_i && response_mask_i[byte_id]),
            .views_o(merge_store_byte));
        wire [7:0] refill_data=merge_store_byte?
            response_store_data_i[byte_id*8 +: 8]:response_data_i[byte_id*8 +: 8];
        wire [7:0] write_data=refill_select?refill_data:
            local_select?local_data_i[byte_id*8 +: 8]:store_data_i[byte_id*8 +: 8];
        // Keep global writing on every byte. The original FakeRAM wrapper
        // gates masked-byte CE; a zero mask must not turn that byte into a read.
        sram_fakeram #(.DEPTH(SETS),.WIDTH(8),.WRITE_GRANULARITY(8)) storage (
            .clk(clk_i),.en(port_enable),.we(port_write),
            .wmask(port_full_write || store_mask_i[byte_id]),
            .addr(port_address),.wdata(write_data),.rdata(data_o[byte_id*8 +: 8]));
    end endgenerate
endmodule
