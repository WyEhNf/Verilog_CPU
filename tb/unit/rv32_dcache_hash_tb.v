`timescale 1ns/1ps
module rv32_dcache_hash_tb #(
    parameter integer INDEX_HASH = 1,
    parameter integer CACHE_LINES = 64,
    parameter integer CACHE_WAYS = 1,
    parameter integer PREFETCH = 1,
    parameter integer TAG_SRAM = 0,
    parameter integer STATIC_UPDATES = 0,
    parameter integer REGISTERED_INDEX = 0,
    parameter integer LOCAL_METADATA_QUERY = 0,
    parameter integer LOCAL_ACTION_DECODE = 0,
    parameter integer METADATA_GROUP_ROWS = 16
);
    reg clk = 0, reset = 1;
    always #5 clk = ~clk;
    reg req_valid = 0, req_load = 0, req_store = 0;
    reg [31:0] req_addr = 0;
    reg [15:0] req_mask = 0, req_tag = 1;
    reg [127:0] req_data = 0;
    wire req_ready, resp_valid, resp_error, ack_valid, ack_error;
    wire [31:0] resp_word;
    wire [15:0] resp_tag, ack_tag;
    wire mem_valid, mem_ready, mem_write, mem_resp_valid, mem_resp_ready, mem_error;
    wire [31:0] mem_addr, mem_resp_addr;
    wire [127:0] mem_data, mem_resp_data;
    wire [15:0] mem_mask;
    wire [7:0] mem_id, mem_resp_id;
    // Directed conflicts use up to three full cache-capacity strides. Keep
    // reference/real memory in range for every legal cache geometry instead
    // of reading X beyond the original 4KiB small-cache fixture.
    localparam integer MEMORY_BYTES = (CACHE_LINES*64 < 4096) ? 4096 : CACHE_LINES*64;
    reg [7:0] reference [0:MEMORY_BYTES-1];
    integer seed, trial, byte_index;
    reg [31:0] address_a, address_b, address_c, random_address, random_data, inverse_address;
    reg [3:0] random_mask;
    reg saw_victim_write = 0;

`ifdef SYNTH_CACHE_FIXED
    // Yosys emitted modules have fixed geometry and no parameter declarations.
    // The runner must specialize the netlist to these same TB parameters.
    rv32_dcache_nonblocking dut (
`else
    rv32_dcache_nonblocking #(.CACHE_LINES(CACHE_LINES), .CACHE_WAYS(CACHE_WAYS),
        .INDEX_HASH(INDEX_HASH),
        .PREFETCH(PREFETCH), .TAG_WIDTH(16), .TAG_SRAM(TAG_SRAM),
        .STATIC_UPDATES(STATIC_UPDATES), .REGISTERED_INDEX(REGISTERED_INDEX),
        .LOCAL_METADATA_QUERY(LOCAL_METADATA_QUERY),
        .LOCAL_ACTION_DECODE(LOCAL_ACTION_DECODE),
        .METADATA_GROUP_ROWS(METADATA_GROUP_ROWS)) dut (
`endif
        .clk_i(clk), .reset_i(reset), .flush_i(1'b0),
        .dcache_req_valid_i(req_valid), .dcache_req_ready_o(req_ready),
        .dcache_req_is_load_i(req_load), .dcache_req_is_store_i(req_store),
        .dcache_req_addr_i(req_addr), .dcache_req_size_i(2'd2), .dcache_req_unsigned_i(1'b1),
        .dcache_req_mask_i(req_mask), .dcache_req_wdata_i(req_data),
        .dcache_req_rob_tag_i(req_tag), .dcache_req_lsq_tag_i(req_tag),
        .dcache_resp_valid_o(resp_valid), .dcache_resp_ready_i(1'b1),
        .dcache_resp_word_data_o(resp_word), .dcache_resp_lsq_tag_o(resp_tag), .dcache_resp_error_o(resp_error),
        .dcache_store_ack_valid_o(ack_valid), .dcache_store_ack_ready_i(1'b1),
        .dcache_store_ack_lsq_tag_o(ack_tag), .dcache_store_ack_error_o(ack_error),
        .mem_req_valid_o(mem_valid), .mem_req_ready_i(mem_ready), .mem_req_write_o(mem_write),
        .mem_req_line_addr_o(mem_addr), .mem_req_wdata_o(mem_data), .mem_req_wmask_o(mem_mask), .mem_req_id_o(mem_id),
        .mem_resp_valid_i(mem_resp_valid), .mem_resp_ready_o(mem_resp_ready), .mem_resp_line_addr_i(mem_resp_addr),
        .mem_resp_data_i(mem_resp_data), .mem_resp_id_i(mem_resp_id), .mem_resp_error_i(mem_error)
    );
    initial if (dut.LOCAL_ACTION_DECODE != LOCAL_ACTION_DECODE ||
                dut.METADATA_GROUP_ROWS != METADATA_GROUP_ROWS)
        $fatal(1,"Action/geometry parameters did not reach actual Cache");
    generate if (STATIC_UPDATES == 2) begin : g_geometry_check
        localparam integer EXPECT_ROWS = (METADATA_GROUP_ROWS < CACHE_LINES) ?
                                            METADATA_GROUP_ROWS : CACHE_LINES;
        initial if (dut.g_banked_updates.GROUP_ROWS != EXPECT_ROWS ||
                    dut.g_banked_updates.GROUP_COUNT != CACHE_LINES/EXPECT_ROWS)
            $fatal(1,"Actual Cache metadata bank geometry mismatch");
    end endgenerate
    integer registered_index_checks = 0;
    integer metadata_query_checks = 0;
    localparam integer INDEX_WIDTH = $clog2(CACHE_LINES/CACHE_WAYS);
    function [INDEX_WIDTH-1:0] reference_index;
        input [31:0] address;
        begin
            reference_index = address >> 4;
            if (INDEX_HASH != 0)
                reference_index = reference_index ^ (address >> (INDEX_WIDTH+4));
        end
    endfunction
    initial if (dut.REGISTERED_INDEX != REGISTERED_INDEX)
        $fatal(1,"Registered-index parameter did not reach real Cache");
    initial if (dut.LOCAL_METADATA_QUERY != LOCAL_METADATA_QUERY)
        $fatal(1,"Local metadata query parameter did not reach real Cache");
    generate if (TAG_SRAM != 0) begin : g_index_scoreboard
        integer check_way;
        always @(negedge clk) if (!reset && dut.g_sram_tags.query_valid) begin
            if (dut.request_index !== reference_index(dut.core_req_addr) ||
                dut.prefetch_index !== reference_index({dut.core_req_addr[31:4],4'b0} + 32'd16))
                $fatal(1,"Hash/prefetch index differs from captured address");
            registered_index_checks = registered_index_checks + 1;
            for (check_way = 0; check_way < CACHE_WAYS; check_way = check_way + 1) begin
                if (dut.request_query_valid[check_way] !==
                        dut.valid_bits[reference_index(dut.core_req_addr)*CACHE_WAYS+check_way] ||
                    dut.request_query_dirty[check_way] !==
                        dut.dirty_bits[reference_index(dut.core_req_addr)*CACHE_WAYS+check_way] ||
                    dut.prefetch_query_valid[check_way] !==
                        dut.valid_bits[reference_index({dut.core_req_addr[31:4],4'b0}+32'd16)*CACHE_WAYS+check_way] ||
                    dut.prefetch_query_dirty[check_way] !==
                        dut.dirty_bits[reference_index({dut.core_req_addr[31:4],4'b0}+32'd16)*CACHE_WAYS+check_way])
                    $fatal(1,"Live bank metadata query differs from independent address/state lookup");
            end
            if (dut.request_query_lru !== dut.lru_way_mem[reference_index(dut.core_req_addr)] ||
                dut.prefetch_query_lru !== dut.lru_way_mem[reference_index({dut.core_req_addr[31:4],4'b0}+32'd16)])
                $fatal(1,"Bank LRU query differs from independent address/state lookup");
            metadata_query_checks = metadata_query_checks + 1;
        end
    end endgenerate
    rv32im_memory_model #(.MEMORY_SIZE(MEMORY_BYTES), .LATENCY(3)) memory (
        .clk_i(clk), .reset_i(reset), .i_req_valid_i(1'b0), .i_req_line_addr_i(32'b0),
        .i_req_id_i(8'b0), .i_resp_ready_i(1'b1),
        .d_req_valid_i(mem_valid), .d_req_ready_o(mem_ready), .d_req_write_i(mem_write),
        .d_req_line_addr_i(mem_addr), .d_req_wdata_i(mem_data), .d_req_wmask_i(mem_mask), .d_req_id_i(mem_id),
        .d_resp_valid_o(mem_resp_valid), .d_resp_ready_i(mem_resp_ready), .d_resp_line_addr_o(mem_resp_addr),
        .d_resp_data_o(mem_resp_data), .d_resp_id_o(mem_resp_id), .d_resp_error_o(mem_error)
    );
    always @(posedge clk)
        if (!reset && mem_valid && mem_ready && mem_write && mem_addr == address_a)
            saw_victim_write <= 1;
    initial begin
        #1000000;
        $fatal(1, "cache test timeout");
    end

    task access_word;
        input [31:0] address;
        input store;
        input [31:0] data;
        input [3:0] mask;
        reg [31:0] expected;
        integer b;
        begin
            @(negedge clk);
            req_tag = req_tag + 1;
            req_addr = address;
            req_load = !store;
            req_store = store;
            req_data = {96'b0, data} << (address[3:0]*8);
            req_mask = {12'b0, mask} << address[3:0];
            req_valid = 1;
            #1;
            while (!req_ready) begin @(negedge clk); #1; end
            @(negedge clk);
            req_valid = 0;
            if (store) begin
                while (!ack_valid) @(negedge clk);
                if (ack_error || ack_tag != req_tag) $fatal(1, "store acknowledgement mismatch");
                for (b = 0; b < 4; b = b + 1)
                    if (mask[b]) reference[address+b] = data[b*8 +: 8];
            end else begin
                while (!resp_valid) @(negedge clk);
                expected = {reference[address+3], reference[address+2], reference[address+1], reference[address]};
                if (resp_error || resp_tag != req_tag || resp_word !== expected)
                    $fatal(1, "load mismatch addr=%h expected=%h actual=%h", address, expected, resp_word);
            end
        end
    endtask

    initial begin
        seed = 32'h7543bc12;
        for (byte_index = 0; byte_index < MEMORY_BYTES; byte_index = byte_index + 1) reference[byte_index] = 0;
        address_a = CACHE_LINES*16 + (INDEX_HASH ? 16 : 0);
        address_b = CACHE_LINES*32 + (INDEX_HASH ? 32 : 0);
        address_c = CACHE_LINES*48 + (INDEX_HASH ? 48 : 0);
        if (CACHE_WAYS == 2) begin
            address_a = 0;
            address_b = ((CACHE_LINES/CACHE_WAYS) + (INDEX_HASH ? 1 : 0))*16;
            address_c = ((CACHE_LINES/CACHE_WAYS)*2 + (INDEX_HASH ? 2 : 0))*16;
        end
        repeat (3) @(negedge clk);
        reset = 0;
        for (trial = 0; trial < 1000; trial = trial + 1) begin
            random_address = $random(seed);
`ifndef SYNTH_CACHE_FIXED
            // Function hierarchy disappears in the synthesized module. Its
            // inverse-address behavior is still checked externally below by
            // the dirty victim address/data checks and complete memory sweep.
            inverse_address = dut.victim_line_address(random_address >> ($clog2(CACHE_LINES/CACHE_WAYS)+4), dut.cache_index(random_address));
            if (inverse_address !== {random_address[31:4], 4'b0}) $fatal(1, "index inversion failed");
`endif
        end
        access_word(address_a, 1, 32'h89abcdef, 4'hf);
        access_word(address_a, 0, 0, 4'hf);
        access_word(address_b, 0, 0, 4'hf);
        if (CACHE_WAYS == 2) access_word(address_c, 0, 0, 4'hf);
        if (!saw_victim_write || {memory.memory[address_a+3], memory.memory[address_a+2],
            memory.memory[address_a+1], memory.memory[address_a]} !== 32'h89abcdef)
            $fatal(1, "dirty victim physical address/data corrupted");
        access_word(address_a, 0, 0, 4'hf);
        for (trial = 0; trial < 500; trial = trial + 1) begin
            random_address = ($random(seed) & 1023)*4;
            random_data = $random(seed);
            random_mask = $random(seed);
            access_word(random_address, 1, random_data, random_mask);
            access_word(random_address, 0, 0, 4'hf);
        end
        // Revisit every word after many dirty evictions, not just the latest
        // store-buffer forwarded value.
        for (trial = 0; trial < 1024; trial = trial + 1)
            access_word(trial*4, 0, 0, 4'hf);
        if (TAG_SRAM != 0 && registered_index_checks == 0)
            $fatal(1,"No registered-index query checks executed");
        $display("PASS: registered index scoreboard mode=%0d tag=%0d checks=%0d",REGISTERED_INDEX,TAG_SRAM,registered_index_checks);
        $display("PASS: live metadata query scoreboard mode=%0d tag=%0d checks=%0d",LOCAL_METADATA_QUERY,TAG_SRAM,metadata_query_checks);
        $display("PASS: D-cache tag_sram=%0d hash=%0d lines=%0d ways=%0d prefetch=%0d", TAG_SRAM, INDEX_HASH, CACHE_LINES, CACHE_WAYS, PREFETCH);
        $finish;
    end
endmodule
