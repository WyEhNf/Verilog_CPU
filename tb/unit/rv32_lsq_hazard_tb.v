`timescale 1ns/1ps
// Compare static-slot hazard detection with an age-ordered reference scan.
module rv32_lsq_hazard_tb #(
    parameter integer ENTRIES = 8
);
    integer seed, trial, slot, offset, older, index, age, best, best_age;
    reg blocked;
    reg [19:0] load_mask, store_mask;
    rv32_lsq #(.BE_WIDTH(2), .LSQ_ENTRIES(ENTRIES)) dut (
        .clk_i(1'b0), .reset_i(1'b0), .flush_i(1'b0),
        .alloc_valid_i(2'b0), .store_commit_rob_tag_i(16'b0),
        .dcache_req_ready_i(1'b0), .dcache_resp_valid_i(1'b0),
        .dcache_resp_lsq_tag_i(16'b0)
    );
    initial begin
        seed = 32'h734ce103;
        dut.tail_reg = 0;
        for (trial = 0; trial < 3000; trial = trial + 1) begin
            dut.head_reg = ($random(seed) & 32'h7fffffff) % ENTRIES;
            dut.occupancy_reg = ($random(seed) & 32'h7fffffff) % (ENTRIES+1);
            for (slot = 0; slot < ENTRIES; slot = slot + 1) begin
                age = (slot + ENTRIES - dut.head_reg) % ENTRIES;
                dut.valid_mem[slot] = age < dut.occupancy_reg;
                dut.load_mem[slot] = $random(seed);
                dut.store_mem[slot] = !dut.load_mem[slot];
                dut.addr_ready_mem[slot] = $random(seed);
                dut.data_ready_mem[slot] = $random(seed);
                dut.request_sent_mem[slot] = $random(seed);
                dut.complete_mem[slot] = $random(seed);
                dut.store_commit_mem[slot] = $random(seed);
                dut.addr_mem[slot] = $random(seed) & 32'h3f;
                dut.mask_mem[slot] = $random(seed);
                dut.size_mem[slot] = $random(seed);
                dut.data_mem[slot] = $random(seed);
                dut.response_wait_mem[slot] = 0;
                dut.rob_tag_mem[slot] = slot*8+1;
                dut.generation_mem[slot] = 0;
                dut.generation_next_mem[slot] = 0;
            end
            #1;
            best = -1;
            best_age = ENTRIES+1;
            for (offset = 0; offset < ENTRIES; offset = offset + 1) begin
                index = (dut.head_reg + offset) % ENTRIES;
                if (offset < dut.occupancy_reg && dut.valid_mem[index]) begin
                    if (dut.load_mem[index] && dut.addr_ready_mem[index] &&
                        !dut.request_sent_mem[index] && !dut.complete_mem[index]) begin
                        blocked = 0;
                        case (dut.size_mem[index])
                            0: load_mask = 20'h1 << dut.addr_mem[index][3:0];
                            1: load_mask = 20'h3 << dut.addr_mem[index][3:0];
                            default: load_mask = 20'hf << dut.addr_mem[index][3:0];
                        endcase
                        for (older = 0; older < offset; older = older + 1) begin
                            slot = (dut.head_reg + older) % ENTRIES;
                            store_mask = {16'b0, dut.mask_mem[slot]} << dut.addr_mem[slot][3:0];
                            if (dut.valid_mem[slot] && dut.store_mem[slot] &&
                                (!dut.addr_ready_mem[slot] ||
                                 (!dut.data_ready_mem[slot] &&
                                  dut.addr_mem[slot][31:4] == dut.addr_mem[index][31:4] &&
                                  (store_mask & load_mask) != 0))) blocked = 1;
                        end
                        if (!blocked && best < 0) begin best = index; best_age = offset; end
                    end else if (dut.store_mem[index] && dut.addr_ready_mem[index] &&
                                 dut.data_ready_mem[index] && dut.store_commit_mem[index] &&
                                 !dut.request_sent_mem[index] && best < 0) begin
                        best = index; best_age = offset;
                    end
                end
            end
            if (dut.candidate_found !== (best >= 0) ||
                (best >= 0 && (dut.candidate != best || dut.candidate_age != best_age)))
                $fatal(1, "hazard mismatch trial=%0d head=%0d expected=%0d actual=%0d", trial, dut.head_reg, best, dut.candidate);
        end
        $display("PASS: LSQ static hazard ENTRIES=%0d trials=%0d", ENTRIES, trial);
        $finish;
    end
endmodule
