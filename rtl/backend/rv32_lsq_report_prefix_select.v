`timescale 1ns/1ps

// Select the oldest physical/wrap class independently of occupied range.
// The caller supplies the exact age<count prefix; the selected oldest row is
// covered iff any eligible row is covered. No valid/head/tail invariant is used.
(* keep_hierarchy = 1 *)
module rv32_lsq_report_prefix_select #(
    parameter integer ENTRIES=16,
    parameter integer DOMAINS=(ENTRIES+3)/4
) (
    input wire [ENTRIES-1:0] eligible_i,wrapped_i,range_i,
    output wire [ENTRIES-1:0] grants_o,
    output wire covered_o
);
    wire [ENTRIES-1:0] upper=eligible_i & ~wrapped_i;
    wire [DOMAINS-1:0] no_upper;
    rv32_frequency_control_tree #(.LEAVES(DOMAINS)) class_tree (
        .signal_i(!(|upper)),.views_o(no_upper));
    for(genvar row=0;row<ENTRIES;row=row+1) begin:g_row
        if(row==0) begin:g_first
            assign grants_o[row]=upper[row] || (no_upper[row/4] && eligible_i[row]);
        end else begin:g_later
            assign grants_o[row]=(upper[row] && !(|upper[row-1:0])) ||
                (no_upper[row/4] && eligible_i[row] && !(|eligible_i[row-1:0]));
        end
    end
    assign covered_o=|(grants_o & range_i);
    initial if(ENTRIES<2 || ENTRIES>32 || (ENTRIES&(ENTRIES-1))!=0 || DOMAINS!=(ENTRIES+3)/4)
        $fatal(1,"Report prefix selection requires power-of-two entries2..32");
endmodule
