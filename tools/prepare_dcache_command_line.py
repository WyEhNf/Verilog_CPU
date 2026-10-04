"""Prepare per-way SRAM command ownership, with no EDA or CPU tests."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def command_line(t):
    t = change(t, '''        assign request_data_ready = query_data_valid;
        for (tag_way = 0; tag_way < CACHE_WAYS; tag_way = tag_way + 1) begin : g_data_way''', '''        assign request_data_ready = query_data_valid;
        // Each way owns one command decode. The final controls and address
        // reach individual byte macros only through bounded distributions.
        localparam integer DATA_COMMAND_WIDTH=7;
        localparam integer DATA_ADDRESS_WIDTH=3*CACHE_ENTRY_WIDTH+2*CACHE_INDEX_WIDTH;
        wire [CACHE_WAYS*DATA_COMMAND_WIDTH-1:0] data_command_views;
        wire [CACHE_WAYS*DATA_ADDRESS_WIDTH-1:0] data_address_views;
        if(LOCAL_SRAM_COMMANDS!=0) begin:g_data_command_distribution
            rv32_frequency_control_tree #(.WIDTH(DATA_COMMAND_WIDTH),.LEAVES(CACHE_WAYS)) command_tree (
                .signal_i({reset_i,refill_array_write,local_array_write,
                           (request_fire && request_is_store && request_hit),
                           input_data_read,deferred_data_read,query_response_mshr_store}),
                .views_o(data_command_views));
            rv32_frequency_control_tree #(.WIDTH(DATA_ADDRESS_WIDTH),.LEAVES(CACHE_WAYS)) address_tree (
                .signal_i({query_response_mshr_victim_entry,query_local_mshr_victim_entry,
                           request_hit_entry,cache_index(dcache_req_addr_i),core_request_index}),
                .views_o(data_address_views));
        end else begin:g_unused_data_command_views
            assign data_command_views=0;
            assign data_address_views=0;
        end
        for (tag_way = 0; tag_way < CACHE_WAYS; tag_way = tag_way + 1) begin : g_data_way''')
    t = change(t, '''                for (genvar word_lane=0;word_lane<4;word_lane=word_lane+1) begin:g_word
                    rv32_dcache_command_word #(.SETS(CACHE_SETS),.WAYS(CACHE_WAYS),
                        .WAY(tag_way),.IW(CACHE_INDEX_WIDTH),.EW(CACHE_ENTRY_WIDTH)) port_bank (
                        .clk_i(clk_i),.reset_i(reset_i),
                        .refill_i(refill_array_write),.local_i(local_array_write),
                        .store_i(request_fire && request_is_store && request_hit),
                        .input_read_i(input_data_read),.deferred_read_i(deferred_data_read),
                        .refill_entry_i(query_response_mshr_victim_entry),
                        .local_entry_i(query_local_mshr_victim_entry),.hit_entry_i(request_hit_entry),
                        .input_index_i(cache_index(dcache_req_addr_i)),.deferred_index_i(core_request_index),
                        .response_data_i(mem_resp_data_i[word_lane*32 +: 32]),
                        .response_store_i(query_response_mshr_store),
                        .response_store_data_i(query_response_mshr_wdata[word_lane*32 +: 32]),
                        .response_mask_i(query_response_mshr_mask[word_lane*4 +: 4]),
                        .local_data_i(query_local_mshr_wdata[word_lane*32 +: 32]),
                        .store_data_i(core_req_wdata[word_lane*32 +: 32]),
                        .store_mask_i(core_req_mask[word_lane*4 +: 4]),
                        .data_o(bank_rdata[tag_way*128+word_lane*32 +: 32]));
                end''', '''                wire command_reset,command_refill,command_local,command_store;
                wire command_input_read,command_deferred_read,command_response_store;
                wire [CACHE_ENTRY_WIDTH-1:0] command_refill_entry,command_local_entry,command_hit_entry;
                wire [CACHE_INDEX_WIDTH-1:0] command_input_index,command_deferred_index;
                assign {command_reset,command_refill,command_local,command_store,
                        command_input_read,command_deferred_read,command_response_store}=
                    data_command_views[tag_way*DATA_COMMAND_WIDTH +: DATA_COMMAND_WIDTH];
                assign {command_refill_entry,command_local_entry,command_hit_entry,
                        command_input_index,command_deferred_index}=
                    data_address_views[tag_way*DATA_ADDRESS_WIDTH +: DATA_ADDRESS_WIDTH];
                rv32_dcache_command_line #(.SETS(CACHE_SETS),.WAYS(CACHE_WAYS),
                    .WAY(tag_way),.IW(CACHE_INDEX_WIDTH),.EW(CACHE_ENTRY_WIDTH)) port_bank (
                    .clk_i(clk_i),.reset_i(command_reset),
                    .refill_i(command_refill),.local_i(command_local),.store_i(command_store),
                    .input_read_i(command_input_read),.deferred_read_i(command_deferred_read),
                    .refill_entry_i(command_refill_entry),.local_entry_i(command_local_entry),
                    .hit_entry_i(command_hit_entry),.input_index_i(command_input_index),
                    .deferred_index_i(command_deferred_index),
                    .response_data_i(mem_resp_data_i),.response_store_i(command_response_store),
                    .response_store_data_i(query_response_mshr_wdata),.response_mask_i(query_response_mshr_mask),
                    .local_data_i(query_local_mshr_wdata),.store_data_i(core_req_wdata),.store_mask_i(core_req_mask),
                    .data_o(bank_rdata[tag_way*128 +: 128]));''')
    return t + r'''

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
    wire refill_way=refill_i && ((refill_entry_i%WAYS)==WAY);
    wire local_way=!refill_i && local_i && ((local_entry_i%WAYS)==WAY);
    wire store_way=!refill_i && !local_i && store_i && ((hit_entry_i%WAYS)==WAY);
    wire writing=refill_way || local_way || store_way;
    wire full_write=refill_way || local_way;
    wire enabled=!reset_i && (writing || input_read_i || deferred_read_i);
    wire [IW-1:0] refill_set=refill_entry_i/WAYS;
    wire [IW-1:0] local_set=local_entry_i/WAYS;
    wire [IW-1:0] hit_set=hit_entry_i/WAYS;
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
        wire [7:0] refill_data=(response_store_i && response_mask_i[byte_id])?
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
'''


if __name__ == '__main__':
    prepare('DE_dcache_command_line', ROOT/'DD_lsq_circular_hazards',
            {'rtl/cache/rv32_dcache_nonblocking.v': command_line},
            'DD plus per-way single command/address decode, bounded command and metadata domains, '
            'parallel qualified address selection, sixteen byte-level real SRAM command domains '
            'and sixteen-bit write-data selects; no extra cycle or changed SRAM capacity')
