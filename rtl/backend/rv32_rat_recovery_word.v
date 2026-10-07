`timescale 1ns/1ps
`include "rv32im_defs.vh"
`ifdef CPU2026_WORD_SIM
// Equivalent two-state simulation form: scan each ROB row once rather
// than repeating the scan for each architectural register. The original
// module remains the synthesis implementation and geometry fallback.
module rv32_rat_recovery_word #(
    parameter integer ROB_ENTRIES = 32,
    parameter integer PAW = 6,
    parameter integer IMPL = 1,
    // Caller guarantees rat_i is the current speculative map and old_phys_i
    // records every accepted rename in program order. Suffix undo already
    // keeps the branch's own destination under this contract.
    parameter integer SUFFIX_KEEPS_BRANCH_MAPPING = 0,
    parameter integer SLOT_WIDTH = $clog2(ROB_ENTRIES),
    parameter integer COUNT_WIDTH = $clog2(ROB_ENTRIES + 1)
) (
    input wire [32*PAW-1:0] rat_i,
    input wire [SLOT_WIDTH-1:0] head_i,
    input wire [SLOT_WIDTH-1:0] branch_slot_i,
    input wire [COUNT_WIDTH-1:0] occupancy_i,
    input wire [ROB_ENTRIES-1:0] valid_i,
    input wire [ROB_ENTRIES-1:0] rd_we_i,
    input wire [ROB_ENTRIES*5-1:0] rd_i,
    input wire [ROB_ENTRIES*PAW-1:0] old_phys_i,
    input wire branch_rd_we_i,
    input wire [4:0] branch_rd_i,
    input wire [PAW-1:0] branch_new_phys_i,
    output wire [32*PAW-1:0] restore_o
);
    genvar arch;
    // The compositional proof covers exactly the default geometry and
    // both branch-mapping policies. Other parameters use the original RTL.
    generate if(IMPL!=2 || ROB_ENTRIES!=32 || PAW!=6 ||
                SLOT_WIDTH!=5 || COUNT_WIDTH!=6) begin:g_original_loop
        rv32_rat_recovery #(.ROB_ENTRIES(ROB_ENTRIES),.PAW(PAW),.IMPL(IMPL),
            .SUFFIX_KEEPS_BRANCH_MAPPING(SUFFIX_KEEPS_BRANCH_MAPPING),
            .SLOT_WIDTH(SLOT_WIDTH),.COUNT_WIDTH(COUNT_WIDTH)) original (
            .rat_i(rat_i),.head_i(head_i),.branch_slot_i(branch_slot_i),.occupancy_i(occupancy_i),
            .valid_i(valid_i),.rd_we_i(rd_we_i),.rd_i(rd_i),.old_phys_i(old_phys_i),
            .branch_rd_we_i(branch_rd_we_i),.branch_rd_i(branch_rd_i),
            .branch_new_phys_i(branch_new_phys_i),.restore_o(restore_o));
    end else begin:g_row_scan
        reg [PAW-1:0] words [0:31];
        reg [31:0] any_seen,upper_seen;
        reg [COUNT_WIDTH-1:0] branch_age_count,row_age_count;
        reg [SLOT_WIDTH-1:0] branch_age_narrow,row_age_narrow;
        reg [4:0] destination;
        reg killed;
        integer r,a;
        always @* begin
            any_seen=0;upper_seen=0;
            branch_age_count=COUNT_WIDTH'((branch_slot_i>=head_i)?32'(branch_slot_i)-32'(head_i):
                ROB_ENTRIES+32'(branch_slot_i)-32'(head_i));
            branch_age_narrow=branch_slot_i-head_i;
            row_age_count=0;row_age_narrow=0;destination=0;killed=0;
            for(a=0;a<32;a=a+1) words[a]=rat_i[a*PAW +: PAW];
            // First physical row wins ordinarily; the first row above the
            // branch overrides it. Each row is examined only once.
            for(r=0;r<ROB_ENTRIES;r=r+1) begin
                row_age_count=COUNT_WIDTH'((r>=head_i)?r-32'(head_i):ROB_ENTRIES+r-32'(head_i));
                row_age_narrow=SLOT_WIDTH'(r-32'(head_i));
                destination=rd_i[r*5 +: 5];
                killed=valid_i[r] && rd_we_i[r] &&
                    ((IMPL==1)?(row_age_count>branch_age_count && row_age_count<occupancy_i):
                               (row_age_narrow>branch_age_narrow && 6'(row_age_narrow)<occupancy_i));
                if(killed && destination!=0) begin
                    if(!any_seen[destination]) begin
                        words[destination]=old_phys_i[r*PAW +: PAW];
                        any_seen[destination]=1;
                    end
                    if(r>branch_slot_i && !upper_seen[destination]) begin
                        words[destination]=old_phys_i[r*PAW +: PAW];
                        upper_seen[destination]=1;
                    end
                end
            end
        end
        for(arch=0;arch<32;arch=arch+1) begin:g_output
            assign restore_o[arch*PAW +: PAW]=(SUFFIX_KEEPS_BRANCH_MAPPING==0 && arch!=0 &&
                branch_rd_we_i && branch_rd_i==arch)?branch_new_phys_i:words[arch];
        end
    end endgenerate
    initial begin
        if (ROB_ENTRIES < 2 || (ROB_ENTRIES & (ROB_ENTRIES-1)) != 0 ||
            PAW < 1 || (IMPL < 0 || IMPL > 2)) begin
            $display("ERROR: invalid standalone RAT recovery geometry");
            $finish;
        end
    end
endmodule
`endif
