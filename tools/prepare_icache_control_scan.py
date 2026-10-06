"""Prepare parallel, bounded Icache JAL target scan from CQ; no HDL/EDA."""
from prepare_staged_frequency_candidate import ROOT, change, prepare


def icache(source):
    for old in [
        '    integer control_word;\n',
        '    reg [31:0] control_inst;\n',
        '    reg [31:0] control_pc;\n',
        '    reg [31:0] control_candidate;\n',
        '    reg control_target_forward;\n',
    ]:
        source=change(source,old,'')
    source=change(source,'    reg control_target_valid;', '    wire control_target_valid;')
    source=change(source,'    reg [31:0] control_target;', '    wire [31:0] control_target;')
    start=source.index('    function [31:0] jal_immediate;')
    end=source.index('    always @* begin',start)
    source=source[:start]+source[end:]
    start=source.index('    // Inspect every returned line, including ordinary sequential prefetches,')
    end=source.index('        if (control_target_valid) begin',start)
    source=source[:start]+'''    // The former scan chooses the earliest forward outside-line JAL,
    // otherwise the earliest outside-line JAL. Four independent candidates
    // and scalar prefix grants retain that exact word priority.
    // Distribute the shared response address before its arithmetic/comparators.
    wire [127:0] control_base_views,control_candidates;
    wire [3:0] control_outside,control_forward,control_preferred,control_grants;
    wire control_has_forward=|control_forward;
    rv32_frequency_control_tree #(.WIDTH(32),.LEAVES(4)) control_base_tree (
        .signal_i(mem_resp_line_addr_i),.views_o(control_base_views));
    generate for(genvar control_lane=0;control_lane<4;control_lane=control_lane+1) begin:g_control_candidate
        wire [31:0] inst=mem_resp_data_i[control_lane*32 +: 32];
        wire [31:0] base=control_base_views[control_lane*32 +: 32];
        // A J-immediate is signed21 bits with bit0=0. Adding 0/4/8/12
        // fits signed22 bits, including the positive-limit carry. This moves
        // the word displacement off the shared full-width PC carry path.
        wire [21:0] displaced_immediate=
            {inst[31],inst[31],inst[19:12],inst[20],inst[30:21],1'b0}+22'(control_lane*4);
        wire [31:0] candidate=base+{{10{displaced_immediate[21]}},displaced_immediate};
        wire [31:0] pc=base+32'(control_lane*4);
        assign control_candidates[control_lane*32 +: 32]=candidate;
        assign control_outside[control_lane]=(inst[6:0]==7'b1101111) && candidate[31:4]!=base[31:4];
        // Preserve the original UNSIGNED comparison, including address wrap.
        assign control_forward[control_lane]=control_outside[control_lane] && candidate>pc;
        assign control_preferred[control_lane]=control_has_forward?
            control_forward[control_lane]:control_outside[control_lane];
        if(control_lane==0) begin:g_first
            assign control_grants[control_lane]=control_preferred[control_lane];
        end else begin:g_following
            assign control_grants[control_lane]=control_preferred[control_lane] && !(|control_preferred[control_lane-1:0]);
        end
    end endgenerate
    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(4),.PRIORITY(0)) control_target_selector (
        .events_i(control_grants),.values_i(control_candidates),
        .write_o(control_target_valid),.value_o(control_target));
    always @* begin
        control_target_present=1'b0;
''' + source[end:]
    return source


if __name__=='__main__':
    prepare('CR_icache_control_scan',ROOT/'CQ_mdu_launch_distribution',{
        'rtl/cache/rv32_icache_nonblocking.v':icache,
    }, 'CQ plus independent four-word JAL control-prefetch candidates, four bounded response-address arithmetic domains, signed22-bit word-displaced immediate and first-forward/otherwise-first-outside scalar grants with 16-bit target reduction. Exact unsigned wrap behavior and original word priority, outside-line checks, cache/MSHR presence, same allocation edge, prefetch policy and functional state preserved. No extra FF/SRAM/cycles or hardware tests; source-only candidate.')
