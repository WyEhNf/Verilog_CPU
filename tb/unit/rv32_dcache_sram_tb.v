`timescale 1ns/1ps
// Exercise the official four-state SRAM model, not a zero-filled stand-in.
module rv32_dcache_sram_tb #(
    parameter integer MERGE_DELAY = 0,
    parameter integer CACHE_WAYS = 1,
    parameter integer TAG_SRAM = 0,
    parameter integer STATIC_UPDATES = 0
);
    reg clk = 0, reset = 1, flush = 0;
    always #5 clk = ~clk;
    reg req_valid = 0, req_load = 1, req_store = 0;
    reg [31:0] req_addr = 0;
    reg [1:0] req_size = 2;
    reg req_unsigned = 1;
    reg [15:0] req_mask = 16'hf, req_tag = 0;
    reg [127:0] req_data = 0;
    wire req_ready, resp_valid, resp_error, ack_valid, ack_error;
    reg resp_ready = 0, ack_ready = 1;
    wire [31:0] resp_word, resp_addr;
    wire [127:0] resp_line;
    wire [15:0] resp_tag, ack_tag;
    wire mem_valid, mem_write, mem_resp_ready;
    reg mem_ready = 1, mem_resp_valid = 0;
    wire [31:0] mem_addr;
    wire [127:0] mem_data;
    wire [7:0] mem_id;
    reg [31:0] mem_resp_addr = 0;
    reg [127:0] mem_resp_data = 0;
    reg [7:0] mem_resp_id = 0;
    reg [127:0] line_a = 128'hffeeddccbbaa99887766554489abcdef;
    reg [127:0] line_b = 128'h112233445566778899aabbcc76543210;
    reg [7:0] saved_id;
    reg [15:0] saved_load_tag;
    integer step;
    integer read_count = 0, write_count = 0, held_reads;
    reg [127:0] merged_line;
    reg [7:0] held_id;
    reg [15:0] waiter_tag;
    reg [15:0] second_waiter_tag;
    reg [31:0] held_addr;
    integer ack_fires = 0, saved_ack_fires;
    reg [15:0] last_ack_tag;
    always @(posedge clk) if (!reset && ack_valid && ack_ready) begin
        ack_fires = ack_fires + 1;
        last_ack_tag = ack_tag;
        if (ack_error) $fatal(1, "unexpected store acknowledgement error");
    end
    always @(posedge clk) if (!reset && mem_valid && mem_ready) begin
        if (mem_write) write_count = write_count + 1;
        else read_count = read_count + 1;
    end
    rv32_dcache_nonblocking #(.CACHE_LINES(16), .CACHE_WAYS(CACHE_WAYS),
        .MSHR_ENTRIES(4), .PREFETCH(0), .TAG_WIDTH(16),
        .STORE_MERGE_DELAY(MERGE_DELAY), .TAG_SRAM(TAG_SRAM),
        .STATIC_UPDATES(STATIC_UPDATES)) dut (
        .clk_i(clk), .reset_i(reset), .flush_i(flush),
        .dcache_req_valid_i(req_valid), .dcache_req_ready_o(req_ready),
        .dcache_req_is_load_i(req_load), .dcache_req_is_store_i(req_store),
        .dcache_req_addr_i(req_addr), .dcache_req_size_i(req_size),
        .dcache_req_unsigned_i(req_unsigned), .dcache_req_mask_i(req_mask),
        .dcache_req_wdata_i(req_data), .dcache_req_rob_tag_i(req_tag),
        .dcache_req_lsq_tag_i(req_tag), .dcache_resp_valid_o(resp_valid),
        .dcache_resp_ready_i(resp_ready), .dcache_resp_lsq_tag_o(resp_tag),
        .dcache_resp_addr_o(resp_addr), .dcache_resp_line_data_o(resp_line),
        .dcache_resp_word_data_o(resp_word), .dcache_resp_error_o(resp_error),
        .dcache_store_ack_valid_o(ack_valid), .dcache_store_ack_ready_i(ack_ready),
        .dcache_store_ack_lsq_tag_o(ack_tag),
        .dcache_store_ack_error_o(ack_error), .mem_req_valid_o(mem_valid),
        .mem_req_ready_i(mem_ready), .mem_req_write_o(mem_write),
        .mem_req_line_addr_o(mem_addr), .mem_req_wdata_o(mem_data),
        .mem_req_id_o(mem_id), .mem_resp_valid_i(mem_resp_valid),
        .mem_resp_ready_o(mem_resp_ready), .mem_resp_line_addr_i(mem_resp_addr),
        .mem_resp_data_i(mem_resp_data), .mem_resp_id_i(mem_resp_id),
        .mem_resp_error_i(1'b0)
    );
    initial begin #100000; $fatal(1, "SRAM protocol test timeout step=%0d", step); end
    task submit;
        input [31:0] address;
        input store;
        input [127:0] data;
        input [15:0] mask;
        input [1:0] size;
        input unsigned_load;
        begin
            @(negedge clk);
            req_tag = req_tag + 1;
            req_addr = address; req_load = !store; req_store = store;
            req_data = data; req_mask = mask; req_size = size;
            req_unsigned = unsigned_load; req_valid = 1;
            #1;
            while (!req_ready) begin @(negedge clk); #1; end
            @(negedge clk);
            req_valid = 0;
            if (store && (!ack_valid || ack_error)) $fatal(1, "store hit ack missing");
            if (TAG_SRAM != 0) @(negedge clk);
        end
    endtask
    task refill;
        input [31:0] address;
        input [127:0] data;
        begin
            while (!mem_valid) @(negedge clk);
            if (mem_write || mem_addr !== address) $fatal(1, "unexpected refill request");
            saved_id = mem_id;
            @(negedge clk);
            mem_resp_valid = 1; mem_resp_addr = address;
            mem_resp_id = saved_id; mem_resp_data = data;
            #1;
            while (!mem_resp_ready) begin @(negedge clk); #1; end
            @(negedge clk); mem_resp_valid = 0;
        end
    endtask
    task check_word;
        input [31:0] expected;
        begin
            if (!resp_valid || resp_error || resp_tag !== req_tag || resp_word !== expected)
                $fatal(1, "response step=%0d expected=%h actual=%h tag=%h/%h",
                       step, expected, resp_word, resp_tag, req_tag);
        end
    endtask
    task consume;
        input [31:0] expected;
        begin
            while (!resp_valid) @(negedge clk);
            check_word(expected);
            resp_ready = 1;
            @(negedge clk); resp_ready = 0;
        end
    endtask
    initial begin
        step = 0;
        repeat (3) @(negedge clk); reset = 0;
        submit(0, 0, 0, 16'hf, 2, 1); refill(0, line_a); consume(line_a[31:0]);
        submit(16, 0, 0, 16'hf, 2, 1); refill(16, line_b); consume(line_b[31:0]);
        step = 1;
        // Hit response is visible after the same read edge, not an added bubble.
        submit(0, 0, 0, 16'hf, 2, 1); check_word(line_a[31:0]);
        saved_id = req_tag;
        @(negedge clk);
        if (TAG_SRAM == 0 && ^dut.data_rdata !== 1'bx)
            $fatal(1, "official idle SRAM output must be undefined");
        check_word(line_a[31:0]);
        // Write the *same* line while its older read is backpressured.
        submit(2, 1, 128'h00810000, 16'h4, 0, 0);
        line_a[23:16] = 8'h81;
        req_tag = saved_id;
        repeat (4) begin
            if (!resp_valid || resp_word !== 32'h89abcdef || resp_line !==
                128'hffeeddccbbaa99887766554489abcdef) $fatal(1, "held hit changed during write/idle");
            @(negedge clk);
        end
        consume(32'h89abcdef);
        step = 2;
        submit(2, 0, 0, 16'h4, 0, 0); consume(32'hffffff81);
        submit(2, 0, 0, 16'h4, 0, 1); consume(32'h81);
        submit(2, 1, 128'h0000fedc0000, 16'hc, 1, 0);
        line_a[31:16] = 16'hfedc;
        submit(2, 0, 0, 16'hc, 1, 0); consume(32'hfffffedc);
        submit(2, 0, 0, 16'hc, 1, 1); consume(32'hfedc);
        step = 3;
        // Two hits can complete in consecutive cycles on a continuously ready port.
        @(negedge clk); resp_ready = 1; req_valid = 1;
        req_addr = 0; req_size = 2; req_mask = 16'hf; req_tag = req_tag + 1;
        saved_load_tag = req_tag;
        @(negedge clk);
        check_word(line_a[31:0]);
        req_addr = 16; req_tag = req_tag + 1;
        @(negedge clk); req_valid = 0;
        check_word(line_b[31:0]);
        @(negedge clk); resp_ready = 0;
        step = 4;
        // A store-miss refill emits no load response, so the read must stall
        // specifically because of the SRAM port, not the response-slot arbiter.
        submit(48, 1, 128'h01234567, 16'hf, 2, 1);
        while (!mem_valid) @(negedge clk);
        saved_id = mem_id;
        @(negedge clk);
        mem_resp_valid = 1; mem_resp_addr = 48; mem_resp_id = saved_id;
        mem_resp_data = 128'haabbccdd;
        req_valid = 1; req_store = 0; req_load = 1; req_addr = 0;
        #1;
        if (!mem_resp_ready || req_ready || dut.response_emits_load)
            $fatal(1, "refill/read priority not enforced independently of response slot");
        @(negedge clk); mem_resp_valid = 0;
        #1;
        if (!req_ready) $fatal(1, "hit read did not resume after store refill");
        @(negedge clk); req_valid = 0;
        consume(line_a[31:0]);
        submit(48, 0, 0, 16'hf, 2, 1); consume(32'h01234567);
        // A successful refill owns the one data port and stalls a simultaneous hit write.
        submit(32, 0, 0, 16'hf, 2, 1);
        while (!mem_valid) @(negedge clk);
        saved_id = mem_id;
        @(negedge clk);
        mem_resp_valid = 1; mem_resp_addr = 32; mem_resp_id = saved_id;
        mem_resp_data = 128'hdeadbeef;
        req_valid = 1; req_store = 1; req_load = 0; req_addr = 16;
        req_data = 128'h00001234; req_mask = 16'h3;
        #1;
        if (!mem_resp_ready || req_ready) $fatal(1, "refill/write priority not enforced");
        @(negedge clk); mem_resp_valid = 0;
        #1;
        if (!req_ready) $fatal(1, "hit write did not resume after refill");
        @(negedge clk); req_valid = 0;
        if (!ack_valid || ack_error) $fatal(1, "resumed store ack missing");
        if (TAG_SRAM != 0) @(negedge clk);
        consume(32'hdeadbeef);
        line_b[15:0] = 16'h1234;
        submit(16, 0, 0, 16'hf, 2, 1); consume(line_b[31:0]);
        step = 5;
        if (CACHE_WAYS == 2) begin
            submit(128, 0, 0, 16'hf, 2, 1);
            refill(128, 128'habc01234); consume(32'habc01234);
        end
        // Read a dirty victim once, then keep its captured line stable while
        // memory is stalled and the SRAM executes unrelated writes and idles.
        mem_ready = 0;
        submit(256, 0, 0, 16'hf, 2, 1);
        saved_load_tag = req_tag;
        saved_id = mem_id;
        if (!mem_valid || !mem_write || mem_addr !== 0 || mem_data !== line_a)
            $fatal(1, "synchronous victim bypass invalid");
        submit(16, 1, 128'h5555, 16'h3, 1, 0);
        flush = 1;
        repeat (4) begin
            if (!mem_valid || !mem_write || mem_addr !== 0 || mem_data !== line_a)
                $fatal(1, "dirty victim changed under write/idle/flush");
            @(negedge clk);
        end
        flush = 0; mem_ready = 1;
        @(negedge clk);
        mem_resp_valid = 1; mem_resp_addr = 0; mem_resp_id = saved_id;
        #1;
        if (!mem_resp_ready) $fatal(1, "writeback response not accepted");
        @(negedge clk); mem_resp_valid = 0;
        refill(256, 128'hcafebabe);
        req_tag = saved_load_tag;
        consume(32'hcafebabe);
        step = 6;
        // Reset validity, not the storage. Stale SRAM payload may not become a hit.
        reset = 1; repeat (2) @(negedge clk); reset = 0;
        submit(16, 0, 0, 16'hf, 2, 1);
        if (resp_valid) $fatal(1, "warm reset exposed stale SRAM data");
        refill(16, 0); consume(0);
        if (MERGE_DELAY != 0) begin
            step = 7;
            held_reads = read_count;
            merged_line = 128'h44444444333333332222222211111111;
            // A load needing an uncovered word joins the store MSHR. Complete
            // the mask before the bounded delay expires: no external RFO.
            submit(64, 1, merged_line, 16'h000f, 2, 1);
            submit(68, 0, 0, 16'h00f0, 2, 1); waiter_tag = req_tag;
            submit(68, 1, merged_line, 16'h00f0, 2, 1);
            submit(72, 1, merged_line, 16'h0f00, 2, 1);
            submit(76, 1, merged_line, 16'hf000, 2, 1);
            req_tag = waiter_tag;
            consume(32'h22222222);
            if (read_count != held_reads) $fatal(1, "full mask issued an unnecessary RFO");
            submit(76, 0, 0, 16'hf000, 2, 1); consume(32'h44444444);
            if (read_count != held_reads) $fatal(1, "locally installed line missed");
            step = 8;
            // Partial stores time out and preserve every uncovered byte.
            submit(80, 1, 128'h000000aa, 16'h0001, 0, 1);
            refill(80, 128'h1234567889abcdef01234567deadbeef);
            submit(80, 0, 0, 16'h000f, 2, 1); consume(32'hdeadbeaa);
            submit(84, 0, 0, 16'h00f0, 2, 1); consume(32'h01234567);
            step = 9;
            // A read which was offered under ready=0 must remain valid even
            // when later stores fill all bytes. It may not become local fill.
            mem_ready = 0;
            submit(96, 1, merged_line, 16'h000f, 2, 1);
            while (!mem_valid) @(negedge clk);
            held_id = mem_id; held_addr = mem_addr;
            @(negedge clk); // sample the offer before completing its mask
            submit(100, 1, merged_line, 16'h00f0, 2, 1);
            submit(104, 1, merged_line, 16'h0f00, 2, 1);
            submit(108, 1, merged_line, 16'hf000, 2, 1);
            flush = 1;
            repeat (3) begin
                if (!mem_valid || mem_write || mem_id !== held_id || mem_addr !== held_addr)
                    $fatal(1, "offered RFO withdrawn/changed after full merge or flush");
                @(negedge clk);
            end
            flush = 0; mem_ready = 1;
            refill(96, 0);
            submit(104, 0, 0, 16'h0f00, 2, 1); consume(32'h33333333);
            step = 10;
            if (CACHE_WAYS == 2) begin
                submit(192, 0, 0, 16'hf, 2, 1);
                refill(192, 128'hdef05678); consume(32'hdef05678);
            end
            // A full-line store evicting dirty data must write the older line
            // back first; only after its B-equivalent response may it install
            // the new fully known line without issuing a read.
            mem_ready = 0; held_reads = read_count;
            submit(320, 1, 128'haabbccddeeff00112233445566778899, 16'hffff, 2, 1);
            if (!mem_valid || !mem_write || mem_addr !== 64 || mem_data !== merged_line)
                $fatal(1, "full-line store lost dirty victim before local fill");
            held_id = mem_id;
            repeat (3) @(negedge clk);
            if (!mem_valid || !mem_write || mem_data !== merged_line)
                $fatal(1, "dirty victim did not persist");
            mem_ready = 1; @(negedge clk);
            mem_resp_valid = 1; mem_resp_addr = 64; mem_resp_id = held_id;
            #1; if (!mem_resp_ready) $fatal(1, "dirty writeback ack blocked");
            @(negedge clk); mem_resp_valid = 0;
            repeat (3) @(negedge clk);
            submit(320, 0, 0, 16'h000f, 2, 1); consume(32'h66778899);
            if (read_count != held_reads) $fatal(1, "dirty full-line overwrite issued RFO");
            step = 11;
            // The MSHR can be reused while completed waiters still occupy the
            // queue. A new local fill must not overwrite their saved payload.
            submit(112, 1, merged_line, 16'h000f, 2, 1);
            submit(116, 0, 0, 16'h00f0, 2, 1); waiter_tag = req_tag;
            submit(120, 0, 0, 16'h0f00, 2, 1); second_waiter_tag = req_tag;
            submit(116, 1, merged_line, 16'h00f0, 2, 1);
            submit(120, 1, merged_line, 16'h0f00, 2, 1);
            submit(124, 1, merged_line, 16'hf000, 2, 1);
            while (!resp_valid) @(negedge clk);
            submit(128, 1, 128'hffffffffffffffffffffffffffffffff, 16'hffff, 2, 1);
            repeat (3) @(negedge clk);
            req_tag = waiter_tag; consume(32'h22222222);
            req_tag = second_waiter_tag; consume(32'h33333333);
            step = 12;
            reset = 1; repeat (2) @(negedge clk); reset = 0;
            mem_ready = 0;
            submit(144, 1, 128'haa, 16'h0001, 0, 1);
            submit(160, 0, 0, 16'h000f, 2, 1);
            saved_load_tag = req_tag;
            held_id = mem_id; held_addr = mem_addr;
            if (!mem_valid || mem_write || held_addr !== 160)
                $fatal(1, "demand read not selected during older store grace");
            // The lower-index store becomes eligible while the higher-index
            // demand is held. Priority rescanning must not change the offer.
            repeat (MERGE_DELAY + 2) begin
                if (!mem_valid || mem_write || mem_id !== held_id || mem_addr !== held_addr)
                    $fatal(1, "lower-index eligibility changed locked request");
                @(negedge clk);
            end
            mem_ready = 1; @(negedge clk);
            mem_resp_valid = 1; mem_resp_addr = 160; mem_resp_id = held_id;
            mem_resp_data = 128'h87654321;
            #1; if (!mem_resp_ready) $fatal(1, "locked demand response rejected");
            @(negedge clk); mem_resp_valid = 0;
            req_tag = saved_load_tag; consume(32'h87654321);
            @(negedge clk);
            mem_resp_valid = 1; mem_resp_addr = 144; mem_resp_id = 0;
            mem_resp_data = 128'hdeadbeef;
            #1; if (!mem_resp_ready) $fatal(1, "older partial store did not issue after unlock");
            @(negedge clk); mem_resp_valid = 0;
            submit(144, 0, 0, 16'h000f, 2, 1); consume(32'hdeadbeaa);
            $display("PASS: bounded store merge, full-line RFO skip, uncovered load waiter, partial-byte preservation, offered-read stability, dirty-victim writeback");
        end
        if (TAG_SRAM != 0) begin
            step = 13;
            reset = 1; repeat (2) @(negedge clk); reset = 0;
            submit(0, 0, 0, 16'h000f, 2, 1); refill(0, line_a); consume(line_a[31:0]);
            if (CACHE_WAYS == 2) begin
                submit(128, 0, 0, 16'h000f, 2, 1);
                refill(128, line_b); consume(line_b[31:0]);
            end
            mem_ready = 0;
            submit(256, 0, 0, 16'h000f, 2, 1); saved_load_tag = req_tag;
            saved_id = mem_id;
            mem_ready = 1; @(negedge clk);
            submit(0, 0, 0, 16'h000f, 2, 1); second_waiter_tag = req_tag;
            if (resp_valid) $fatal(1, "conflicting lookup incorrectly completed before refill");
            mem_resp_valid = 1; mem_resp_addr = 256; mem_resp_id = saved_id;
            mem_resp_data = 128'hcafebabe;
            #1; if (!mem_resp_ready) $fatal(1, "conflicting refill not accepted");
            @(negedge clk); mem_resp_valid = 0;
            req_tag = saved_load_tag; consume(32'hcafebabe);
            // Saved query tags must reflect the replacement. Old tag0 with
            // valid=1 would silently return line256's payload as address0.
            refill(0, line_a);
            req_tag = second_waiter_tag; consume(line_a[31:0]);
            $display("PASS: synchronous replicated tag SRAM, parallel bank one-cycle hit latency/throughput, held-query refill forwarding");

            step = 14;
            // Hit ownership moves on the write edge, not a later ack edge.
            // Backpressure must convert the bypass into one stable reply;
            // flushing in between must not discard this committed write.
            @(negedge clk); ack_ready = 0; saved_ack_fires = ack_fires;
            req_valid = 1; req_load = 0; req_store = 1; req_addr = 0;
            req_tag = req_tag + 1; req_size = 0; req_data = 128'h5a; req_mask = 16'h1;
            #1; if (!req_ready) $fatal(1, "ack test hit query blocked");
            @(negedge clk); req_valid = 0;
            if (!ack_valid || ack_error || ack_tag !== req_tag)
                $fatal(1, "store hit did not acknowledge in first query cycle");
            @(negedge clk); flush = 1;
            repeat (4) begin
                if (!ack_valid || ack_error || ack_tag !== req_tag || ack_fires != saved_ack_fires)
                    $fatal(1, "held store hit acknowledgement changed/was consumed");
                @(negedge clk);
            end
            flush = 0; ack_ready = 1;
            @(negedge clk);
            if (ack_fires != saved_ack_fires+1 || last_ack_tag !== req_tag || ack_valid)
                $fatal(1, "store hit acknowledgement lost or duplicated");
            line_a[7:0] = 8'h5a;
            submit(0, 0, 0, 16'hf, 2, 1); consume(line_a[31:0]);

            step = 15;
            // Store misses have the same early ownership edge. Preserve the
            // absorbed bytes and held ack across flush and RFO backpressure.
            @(negedge clk); ack_ready = 0; mem_ready = 0; saved_ack_fires = ack_fires;
            req_valid = 1; req_load = 0; req_store = 1; req_addr = 65;
            req_tag = req_tag + 1; req_size = 0; req_data = 128'h5500; req_mask = 16'h2;
            #1; if (!req_ready) $fatal(1, "ack test miss query blocked");
            @(negedge clk); req_valid = 0;
            if (!ack_valid || ack_error || ack_tag !== req_tag)
                $fatal(1, "store miss did not acknowledge in first query cycle");
            @(negedge clk); flush = 1;
            repeat (4) begin
                if (!ack_valid || ack_error || ack_tag !== req_tag || ack_fires != saved_ack_fires)
                    $fatal(1, "held store miss acknowledgement changed/was consumed");
                @(negedge clk);
            end
            flush = 0; ack_ready = 1;
            @(negedge clk);
            if (ack_fires != saved_ack_fires+1 || last_ack_tag !== req_tag || ack_valid)
                $fatal(1, "store miss acknowledgement lost or duplicated");
            mem_ready = 1; refill(64, 128'h00112233);
            submit(64, 0, 0, 16'hf, 2, 1); consume(32'h00115533);
            if (ack_fires != saved_ack_fires+1) $fatal(1, "store refill acknowledged twice");

            step = 16;
            @(negedge clk); saved_ack_fires = ack_fires;
            req_valid = 1; req_load = 0; req_store = 1; req_addr = 64;
            req_tag = req_tag + 1; req_size = 0; req_data = 128'haa; req_mask = 16'h1;
            #1; if (!req_ready) $fatal(1, "ready-ack hit query blocked");
            @(negedge clk); req_valid = 0;
            if (!ack_valid || ack_error || ack_tag !== req_tag || ack_fires != saved_ack_fires)
                $fatal(1, "ready-ack hit bypass absent or acknowledged before write edge");
            @(negedge clk);
            if (ack_valid || ack_fires != saved_ack_fires+1 || last_ack_tag !== req_tag)
                $fatal(1, "ready-ack hit bypass duplicated/never consumed");
            submit(64, 0, 0, 16'hf, 2, 1); consume(32'h001155aa);
            $display("PASS: one-cycle store hit/miss ownership acknowledgement, held-ack flush durability, exactly-once bypass");

            step = 17;
            @(negedge clk); saved_ack_fires = ack_fires;
            req_valid = 1; req_load = 0; req_store = 1; req_addr = 64;
            req_tag = req_tag + 1; waiter_tag = req_tag;
            req_size = 0; req_data = 128'hbb; req_mask = 16'h1;
            #1; if (!req_ready) $fatal(1, "first pipelined store query blocked");
            @(negedge clk);
            req_addr = 65; req_tag = req_tag + 1; req_data = 128'hcc00; req_mask = 16'h2;
            #1;
            if (!req_ready || !ack_valid || ack_tag !== waiter_tag)
                $fatal(1, "next store tag query did not overlap prior data write");
            @(negedge clk); req_valid = 0;
            if (!ack_valid || ack_tag !== req_tag || ack_fires != saved_ack_fires+1)
                $fatal(1, "pipelined store acknowledgement order incorrect");
            @(negedge clk);
            if (ack_valid || ack_fires != saved_ack_fires+2)
                $fatal(1, "pipelined store acknowledged twice or lost");
            submit(64, 0, 0, 16'hf, 2, 1); consume(32'h0011ccbb);

            step = 18;
            reset = 1; repeat (2) @(negedge clk); reset = 0;
            submit(0, 0, 0, 16'hf, 2, 1); refill(0, line_a); consume(line_a[31:0]);
            submit(0, 1, 128'haaaabbbb, 16'hf, 2, 1);
            if (CACHE_WAYS == 2) begin
                submit(128, 0, 0, 16'hf, 2, 1);
                refill(128, line_b); consume(line_b[31:0]);
            end
            @(negedge clk); mem_ready = 0; saved_ack_fires = ack_fires;
            req_valid = 1; req_load = 0; req_store = 1;
            req_addr = (CACHE_WAYS == 2) ? 128 : 0;
            req_tag = req_tag + 1; waiter_tag = req_tag;
            req_size = 2; req_data = 128'h11112222; req_mask = 16'hf;
            #1; if (!req_ready) $fatal(1, "dirty overlap first query blocked");
            @(negedge clk);
            req_addr = 256; req_tag = req_tag + 1; req_data = 128'h33334444;
            #1; if (!req_ready) $fatal(1, "dirty miss tags cannot overlap data write");
            @(negedge clk); req_valid = 0; flush = 1;
            if (ack_valid) $fatal(1, "dirty metadata-only miss acknowledged before victim read");
            @(negedge clk);
            if (!ack_valid || ack_tag !== req_tag)
                $fatal(1, "deferred victim read did not unblock committed store");
            @(negedge clk);
            merged_line = line_a;
            merged_line[31:0] = (CACHE_WAYS == 2) ? 32'haaaabbbb : 32'h11112222;
            if (!mem_valid || !mem_write || mem_addr !== 0 || mem_data !== merged_line)
                $fatal(1, "deferred victim read captured undefined/stale/wrong-way data");
            held_id = mem_id;
            repeat (3) begin
                if (!mem_valid || !mem_write || mem_data !== merged_line || ack_valid ||
                    ack_fires != saved_ack_fires+2)
                    $fatal(1, "dirty overlap flush/backpressure corrupted ownership");
                @(negedge clk);
            end
            flush = 0; mem_ready = 1; @(negedge clk);
            mem_resp_valid = 1; mem_resp_addr = 0; mem_resp_id = held_id;
            #1; if (!mem_resp_ready) $fatal(1, "deferred victim writeback response blocked");
            @(negedge clk); mem_resp_valid = 0;
            refill(256, 128'h88889999);
            submit(256, 0, 0, 16'hf, 2, 1); consume(32'h33334444);
            if (ack_fires != saved_ack_fires+2) $fatal(1, "deferred dirty miss acknowledged twice");
            $display("PASS: one-store-per-cycle tag/write overlap, deferred dirty victim read, flush/backpressure exact data");
        end
        $display("PASS: D-cache SRAM hit latency, backpressure, masked byte/half, consecutive hits, refill arbitration, victim capture, flush, warm reset");
        $finish;
    end
endmodule
