`timescale 1ns/1ps

// Independent age-ordered procedural reference. Formal inputs are entirely
// unrestricted, including duplicate tags and arbitrary readiness/payloads.
module rv32_store_address_select_reference #(
    parameter integer LSQ_ENTRIES = 16,
    parameter integer RS_ENTRIES = 16,
    parameter integer TAG_WIDTH = 17,
    parameter integer ROB_TAG_WIDTH = TAG_WIDTH,
    parameter integer HEAD_WIDTH = (LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES)
) (
    input wire [HEAD_WIDTH-1:0] head_i,
    input wire [LSQ_ENTRIES-1:0] pending_i,
    input wire [LSQ_ENTRIES*TAG_WIDTH-1:0] lsq_tag_i,
    input wire [LSQ_ENTRIES*ROB_TAG_WIDTH-1:0] store_rob_tag_i,
    input wire [RS_ENTRIES-1:0] base_ready_i,
    input wire [RS_ENTRIES*ROB_TAG_WIDTH-1:0] rs_rob_tag_i,
    input wire [RS_ENTRIES*32-1:0] base_value_i,
    output reg valid_o,
    output reg [TAG_WIDTH-1:0] lsq_tag_o,
    output reg [ROB_TAG_WIDTH-1:0] rob_tag_o,
    output reg [31:0] base_value_o
);
    integer age, row, entry;
    always @* begin
        valid_o = 0;
        lsq_tag_o = 0;
        rob_tag_o = 0;
        base_value_o = 0;
        row = 0;
        for (age = 0; age < LSQ_ENTRIES; age = age + 1) begin
            row = head_i + age;
            if (row >= LSQ_ENTRIES) row = row - LSQ_ENTRIES;
            for (entry = 0; entry < RS_ENTRIES; entry = entry + 1) begin
                if (!valid_o && pending_i[row] && base_ready_i[entry] &&
                    store_rob_tag_i[row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH] ==
                    rs_rob_tag_i[entry*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]) begin
                    valid_o = 1;
                    lsq_tag_o = lsq_tag_i[row*TAG_WIDTH +: TAG_WIDTH];
                    rob_tag_o = store_rob_tag_i[row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH];
                    base_value_o = base_value_i[entry*32 +: 32];
                end
            end
        end
    end
endmodule

module rv32_store_address_select_miter #(
    parameter integer LSQ_ENTRIES = 16,
    parameter integer RS_ENTRIES = 16,
    parameter integer TAG_WIDTH = 17,
    parameter integer ROB_TAG_WIDTH = TAG_WIDTH,
    parameter integer HEAD_WIDTH = (LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES)
) (
    input wire [HEAD_WIDTH-1:0] head_i,
    input wire [LSQ_ENTRIES-1:0] pending_i,
    input wire [LSQ_ENTRIES*TAG_WIDTH-1:0] lsq_tag_i,
    input wire [LSQ_ENTRIES*ROB_TAG_WIDTH-1:0] store_rob_tag_i,
    input wire [RS_ENTRIES-1:0] base_ready_i,
    input wire [RS_ENTRIES*ROB_TAG_WIDTH-1:0] rs_rob_tag_i,
    input wire [RS_ENTRIES*32-1:0] base_value_i,
    output wire equivalent_o
);
    wire gv, dv;
    wire [TAG_WIDTH-1:0] gt, dt;
    wire [ROB_TAG_WIDTH-1:0] gr, dr;
    wire [31:0] gb, db;
    rv32_store_address_select_reference #(.LSQ_ENTRIES(LSQ_ENTRIES), .RS_ENTRIES(RS_ENTRIES),
        .TAG_WIDTH(TAG_WIDTH), .ROB_TAG_WIDTH(ROB_TAG_WIDTH)) reference_model (
        .head_i(head_i), .pending_i(pending_i), .lsq_tag_i(lsq_tag_i), .store_rob_tag_i(store_rob_tag_i),
        .base_ready_i(base_ready_i), .rs_rob_tag_i(rs_rob_tag_i), .base_value_i(base_value_i),
        .valid_o(gv), .lsq_tag_o(gt), .rob_tag_o(gr), .base_value_o(gb)
    );
    rv32_store_address_select #(.LSQ_ENTRIES(LSQ_ENTRIES), .RS_ENTRIES(RS_ENTRIES),
        .TAG_WIDTH(TAG_WIDTH), .ROB_TAG_WIDTH(ROB_TAG_WIDTH)) dut (
        .head_i(head_i), .pending_i(pending_i), .lsq_tag_i(lsq_tag_i), .store_rob_tag_i(store_rob_tag_i),
        .base_ready_i(base_ready_i), .rs_rob_tag_i(rs_rob_tag_i), .base_value_i(base_value_i),
        .valid_o(dv), .lsq_tag_o(dt), .rob_tag_o(dr), .base_value_o(db)
    );
    assign equivalent_o = gv == dv && gt == dt && gr == dr && gb == db;
endmodule

`ifndef SYNTHESIS
module rv32_store_address_select_tb #(
    parameter integer LSQ_ENTRIES = 16,
    parameter integer RS_ENTRIES = 16,
    parameter integer TAG_WIDTH = 17,
    parameter integer HEAD_WIDTH = (LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES)
);
    reg [HEAD_WIDTH-1:0] head;
    reg [LSQ_ENTRIES-1:0] pending;
    reg [LSQ_ENTRIES*TAG_WIDTH-1:0] lsq_tag, store_rob_tag;
    reg [RS_ENTRIES-1:0] base_ready;
    reg [RS_ENTRIES*TAG_WIDTH-1:0] rs_rob_tag;
    reg [RS_ENTRIES*32-1:0] base_value;
    wire equivalent;
    integer cycle, row, entry, seed, picked;
    rv32_store_address_select_miter #(.LSQ_ENTRIES(LSQ_ENTRIES), .RS_ENTRIES(RS_ENTRIES), .TAG_WIDTH(TAG_WIDTH)) miter (
        .head_i(head), .pending_i(pending), .lsq_tag_i(lsq_tag), .store_rob_tag_i(store_rob_tag),
        .base_ready_i(base_ready), .rs_rob_tag_i(rs_rob_tag), .base_value_i(base_value), .equivalent_o(equivalent)
    );
    initial begin
        seed = 32'h49a6721b;
        head = 0; pending = 0; lsq_tag = 0; store_rob_tag = 0;
        base_ready = 0; rs_rob_tag = 0; base_value = 0;
        for (cycle = 0; cycle < 2000; cycle = cycle + 1) begin
            head = $random(seed);
            pending = $random(seed);
            base_ready = $random(seed);
            for (entry = 0; entry < RS_ENTRIES; entry = entry + 1) begin
                rs_rob_tag[entry*TAG_WIDTH +: TAG_WIDTH] = $random(seed);
                base_value[entry*32 +: 32] = $random(seed);
                if (entry > 0 && cycle % 7 == 0)
                    rs_rob_tag[entry*TAG_WIDTH +: TAG_WIDTH] = rs_rob_tag[0 +: TAG_WIDTH];
            end
            for (row = 0; row < LSQ_ENTRIES; row = row + 1) begin
                lsq_tag[row*TAG_WIDTH +: TAG_WIDTH] = $random(seed);
                store_rob_tag[row*TAG_WIDTH +: TAG_WIDTH] = $random(seed);
                picked = ($random(seed) & 32'h7fffffff) % RS_ENTRIES;
                if ((cycle + row) % 2 == 0)
                    store_rob_tag[row*TAG_WIDTH +: TAG_WIDTH] = rs_rob_tag[picked*TAG_WIDTH +: TAG_WIDTH];
            end
            if (cycle % 13 == 0) pending = 0;
            if (cycle % 17 == 0) base_ready = 0;
            #1;
            if (equivalent !== 1'b1) $fatal(1, "store-address selection differs at cycle %0d", cycle);
        end
        $display("PASS: shared store-address selector LSQ=%0d RS=%0d", LSQ_ENTRIES, RS_ENTRIES);
        $finish;
    end
endmodule
`endif
