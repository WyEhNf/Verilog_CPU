"""Implement a reserved rename-to-dispatch boundary without running EDA.

R allocates ROB/destination registers and reserves RS/LSQ slots. D consumes
one saved bundle on every unheld clock. Thus R ready has no D payload/ready
feedback. Recovery owns saved entries because their ROB allocation is real.
"""
import re
from prepare_staged_frequency_candidate import change, prepare, ROOT

FIELDS = [
    ('pc','32','trace_pc_i'), ('op','`RV32IM_OP_WIDTH','trace_op_i'),
    ('imm','32','trace_imm_i'), ('is_load','1','trace_is_load_i'),
    ('is_store','1','trace_is_store_i'), ('mem_size','2','trace_mem_size_i'),
    ('mem_unsigned','1','trace_mem_unsigned_i'),
    ('store_data','32','trace_store_data_relative'),
    ('pred_taken','1','trace_pred_taken_i'),
    ('pred_target','32','trace_pred_target_i'), ('pred_kind','2','trace_pred_kind_i'),
    ('new_phys','PAW','rename_new_phys'),
    ('src1_phys','PAW','rename_rs1_phys'), ('src2_phys','PAW','rename_rs2_phys'),
]


def slice_name(name,width,lane):
    return f'{name}[{lane}]' if width=='1' else f'{name}[{lane}*{width} +: {width}]'


PACKET=r'''

// A deterministic one-bundle pipeline. Its resource reservations guarantee
// complete D admission, so no RS/LSQ admission signal feeds back into R.
module rv32_reserved_dispatch_packet #(
    parameter integer LANES=4,PAYLOAD_WIDTH=160,TAG_WIDTH=17,ROB_ENTRIES=64,
    parameter integer SW=(ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES),
    parameter integer GW=TAG_WIDTH-SW-3
) (
    input wire clk_i,reset_i,flush_i,hold_i,recovery_i,
    input wire [SW-1:0] recovery_head_i,
    input wire [TAG_WIDTH-1:0] recovery_tag_i,
    input wire [15:0] recovery_occupancy_i,
    input wire [ROB_ENTRIES-1:0] rob_valid_i,
    input wire [ROB_ENTRIES*GW-1:0] rob_generation_i,
    input wire [LANES-1:0] valid_i,
    input wire [LANES*TAG_WIDTH-1:0] tag_i,
    input wire [LANES*PAYLOAD_WIDTH-1:0] data_i,
    input wire [LANES-1:0] saved_is_memory_i,
    output wire [LANES-1:0] valid_o,
    output wire [LANES*TAG_WIDTH-1:0] tag_o,
    output wire [LANES*PAYLOAD_WIDTH-1:0] data_o,
    output reg [15:0] reserved_rs_o,reserved_lsq_o
);
    reg [LANES-1:0] valid_q;
    reg [TAG_WIDTH-1:0] tag_q [0:LANES-1];
    wire [LANES-1:0] recovery_keep;
    wire normal=!reset_i && !flush_i && !hold_i && !recovery_i;
    wire [SW-1:0] branch_age=recovery_tag_i[3 +: SW]-recovery_head_i;
    genvar lane;
    generate for(lane=0;lane<LANES;lane=lane+1) begin:g_lane
        wire [SW-1:0] slot=tag_q[lane][3 +: SW];
        wire [SW-1:0] age=slot-recovery_head_i;
        wire generation_live=rob_valid_i[slot] &&
            tag_q[lane][3+SW +: GW]==rob_generation_i[slot*GW +: GW];
        assign recovery_keep[lane]=valid_q[lane] && tag_q[lane][0] &&
            generation_live && age<branch_age && age<recovery_occupancy_i;
        assign valid_o[lane]=normal && valid_q[lane];
        assign tag_o[lane*TAG_WIDTH +: TAG_WIDTH]=tag_q[lane];
        wire write_local;
        rv32_frequency_control_tree #(.LEAVES(1)) tag_write_tree (
            .signal_i(normal && valid_i[lane]),.views_o(write_local));
        always @(posedge clk_i) if(write_local) tag_q[lane]<=tag_i[lane*TAG_WIDTH +: TAG_WIDTH];
        rv32_frequency_word_bank #(.WIDTH(PAYLOAD_WIDTH)) payload_owner (
            .clk_i(clk_i),.write_i(normal && valid_i[lane]),
            .data_i(data_i[lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]),
            .data_o(data_o[lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]));
    end endgenerate
    integer count_lane;
    always @* begin
        reserved_rs_o=0;reserved_lsq_o=0;
        for(count_lane=0;count_lane<LANES;count_lane=count_lane+1) begin
            if(valid_q[count_lane]) reserved_rs_o=reserved_rs_o+1'b1;
            if(valid_q[count_lane] && saved_is_memory_i[count_lane])
                reserved_lsq_o=reserved_lsq_o+1'b1;
        end
    end
    always @(posedge clk_i) begin
        if(reset_i || flush_i) valid_q<=0;
        else if(recovery_i) valid_q<=recovery_keep;
        else if(!hold_i) valid_q<=valid_i;
    end
endmodule
'''


def stage_backend(t):
    t=change(t,'    parameter integer ISSUE_PIPELINE = 0,',
               '    parameter integer ISSUE_PIPELINE = 0,\n    parameter integer DISPATCH_PIPELINE = 0,')
    decl='''    // R owns ROB/destination allocation; D owns operand reads and queues.
    localparam integer DISPATCH_PAYLOAD_WIDTH='''+' + '.join(w for _,w,_ in FIELDS)+''';
    wire [BE_WIDTH-1:0] d_valid;
    wire [BE_WIDTH*TAG_WIDTH-1:0] d_tag;
    wire [15:0] d_reserved_rs,d_reserved_lsq;
    wire [BE_WIDTH*DISPATCH_PAYLOAD_WIDTH-1:0] d_payload_in,d_payload_out;
'''
    decl+=''.join(f'    wire [BE_WIDTH*{w}-1:0] d_{n};\n' for n,w,_ in FIELDS)
    t=change(t,'    wire [(BE_WIDTH*PAW)-1:0] rename_rs1_phys, rename_rs2_phys;',
               '    wire [(BE_WIDTH*PAW)-1:0] rename_rs1_phys, rename_rs2_phys;\n'+decl)
    anchor='    assign rs_alloc_valid = rob_alloc_valid;'
    unpack=',\n                '.join(slice_name('d_'+n,w,'dispatch_lane') for n,w,_ in FIELDS)
    pack=',\n                '.join(slice_name(n,w,'dispatch_lane') for _,w,n in FIELDS)
    pipeline='''    genvar dispatch_lane;
    generate
        for(dispatch_lane=0;dispatch_lane<BE_WIDTH;dispatch_lane=dispatch_lane+1) begin:g_dispatch_fields
            assign d_payload_in[dispatch_lane*DISPATCH_PAYLOAD_WIDTH +: DISPATCH_PAYLOAD_WIDTH]={
                '''+pack+'''};
            assign {'''+unpack+'''}=d_payload_out[dispatch_lane*DISPATCH_PAYLOAD_WIDTH +: DISPATCH_PAYLOAD_WIDTH];
        end
        if(DISPATCH_PIPELINE!=0) begin:g_reserved_dispatch
            rv32_reserved_dispatch_packet #(.LANES(BE_WIDTH),.PAYLOAD_WIDTH(DISPATCH_PAYLOAD_WIDTH),
                .TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES)) packet (
                .clk_i(clk_i),.reset_i(reset_i),.flush_i(flush_i),.hold_i(branch_busy_domains[3]),
                .recovery_i(recovery_domains[7]),
                .recovery_head_i(recovery_head_views[0 +: ROB_SLOT_WIDTH]),
                .recovery_tag_i(recovery_tag_views[0 +: TAG_WIDTH]),
                .recovery_occupancy_i({{(16-ROB_COUNT_WIDTH){1'b0}},recovery_descriptor_occupancy}),
                .rob_valid_i(rob_entry_valid),.rob_generation_i(rob_entry_generation),
                .valid_i(dispatch_valid & rob_alloc_fire),.tag_i(rob_alloc_tag),.data_i(d_payload_in),
                .saved_is_memory_i(d_is_load | d_is_store),
                .valid_o(d_valid),.tag_o(d_tag),.data_o(d_payload_out),
                .reserved_rs_o(d_reserved_rs),.reserved_lsq_o(d_reserved_lsq));
        end else begin:g_direct_dispatch
            assign d_valid=dispatch_valid;
            assign d_tag=rob_alloc_tag;
            assign d_payload_out=d_payload_in;
            assign d_reserved_rs=0;assign d_reserved_lsq=0;
        end
    endgenerate
    assign rs_alloc_valid = d_valid;'''
    t=change(t,anchor,pipeline)
    t=change(t,'    assign lsq_alloc_valid = dispatch_valid & (trace_is_load_i | trace_is_store_i);',
               '    assign lsq_alloc_valid = d_valid & (d_is_load | d_is_store);')
    t=change(t,"        {BE_WIDTH{1'b0}} : (trace_is_store_i & rename_valid);",
               "        {BE_WIDTH{1'b0}} : (d_is_store & d_valid);")
    # Queries alone change to saved sources; write-side allocation stays at R.
    for tag_lane in (1,2):
        t=change(t,f'rename_rs{tag_lane}_phys[tag_lane*PAW +: PAW];',
                   f'd_src{tag_lane}_phys[tag_lane*PAW +: PAW];')
    start=t.index('    genvar io_lane;')
    stop=t.index('    // Ready is a contiguous',start)
    part=t[start:stop]
    replacements={n:'d_'+f for f,_,n in FIELDS if n.startswith('trace_') and n!='trace_store_data_relative'}
    replacements.update(rename_rs1_phys='d_src1_phys',rename_rs2_phys='d_src2_phys')
    for old,new in replacements.items(): part=re.sub(r'\b'+old+r'\b',new,part)
    part=change(part,'dispatch_valid[io_lane] && d_is_store[io_lane]',
                     'd_valid[io_lane] && d_is_store[io_lane]')
    t=t[:start]+part+t[stop:]
    # The operand read cannot use younger live rename fields. The old explicit
    # same-bundle correction is only needed when the boundary is disabled.
    start=t.index('    // Rename and PRF form the operand/producer boundary.')
    dependency=t.index('            // Free physical registers',start)
    part=t[start:dependency]
    for old,new in [('rename_rs1_phys','d_src1_phys'),('rename_rs2_phys','d_src2_phys')]:
        part=re.sub(r'\b'+old+r'\b',new,part)
    t=t[:start]+part+t[dependency:]
    t=change(t,'            for (dependency_lane = 0; dependency_lane < BE_WIDTH; dependency_lane = dependency_lane + 1) begin',
               '            if(DISPATCH_PIPELINE==0) for (dependency_lane = 0; dependency_lane < BE_WIDTH; dependency_lane = dependency_lane + 1) begin')
    # Rewrite only the D allocation inputs; never change child port names.
    t=change(t,'.alloc_op_i(trace_op_i), .alloc_pc_i(trace_pc_i), .alloc_rob_tag_i(rob_alloc_tag), .alloc_target_live_i(rob_alloc_valid), .alloc_phys_rd_i(rename_new_phys)',
               '.alloc_op_i(d_op), .alloc_pc_i(d_pc), .alloc_rob_tag_i(d_tag), .alloc_target_live_i(d_valid), .alloc_phys_rd_i(d_new_phys)')
    t=change(t,'.alloc_is_load_i(trace_is_load_i), .alloc_is_store_i(trace_is_store_i), .alloc_rob_tag_i(rob_alloc_tag), .alloc_size_i(trace_mem_size_i), .alloc_unsigned_i(trace_mem_unsigned_i)',
               '.alloc_is_load_i(d_is_load), .alloc_is_store_i(d_is_store), .alloc_rob_tag_i(d_tag), .alloc_size_i(d_mem_size), .alloc_unsigned_i(d_mem_unsigned)')
    assert t.count('.alloc_store_data_i(trace_store_data_relative)')==2
    t=t.replace('.alloc_store_data_i(trace_store_data_relative)','.alloc_store_data_i(d_store_data)')
    # Reservation accounting: F'-Q'=F-Q-A+releases. Omitting releases is
    # conservative and avoids any D payload/free-on-this-edge ready feedback.
    t=change(t,'    // At the next edge actual free slots', '''    function [CREDIT_WIDTH-1:0] reserved_credit;
        input [15:0] available,reserved;
        input [CREDIT_WIDTH-1:0] newly_reserved;
        reg [15:0] unreserved;
        begin
            unreserved=(available>=reserved)?available-reserved:16'b0;
            reserved_credit=bounded_credit(unreserved,newly_reserved);
        end
    endfunction
    // At the next edge actual free slots''')
    t=change(t,'            rs_credit<=bounded_credit(rs_free_count,used_rs_credit);',
               '            rs_credit<=reserved_credit(rs_free_count,d_reserved_rs,used_rs_credit);')
    t=change(t,'            lsq_credit<=bounded_credit(lsq_free_count,used_lsq_credit);',
               '            lsq_credit<=reserved_credit(lsq_free_count,d_reserved_lsq,used_lsq_credit);')
    # Map actual LSQ allocations at D, after tags have become real. Reset
    # these arrays in the same owner to avoid introducing multiple writers.
    t=change(t,'                rob_to_lsq_mem[map_index] <= 0;\n','')
    t=change(t,'''            for (map_index = 0; map_index < LSQ_ENTRIES; map_index = map_index + 1)
                lsq_phys_mem[map_index] <= 0;
''','')
    t=change(t,'''                    if (trace_is_load_i[map_lane] || trace_is_store_i[map_lane]) begin
                        map_lsq_slot = lsq_alloc_tag[map_lane*TAG_WIDTH + 3 +: LSQ_SLOT_WIDTH];
                        rob_to_lsq_mem[map_rob_slot] <=
                            lsq_alloc_tag[map_lane*TAG_WIDTH +: TAG_WIDTH];
                        lsq_phys_mem[map_lsq_slot] <= rename_new_phys[map_lane*PAW +: PAW];
                    end
''','')
    t=change(t,'    assign rob_store_ack_valid = lsq_store_ack_valid;', '''    integer d_map_lane,d_map_reset;
    reg [ROB_SLOT_WIDTH-1:0] d_map_rob_slot;
    reg [LSQ_SLOT_WIDTH-1:0] d_map_lsq_slot;
    always @(posedge clk_i) begin
        if(reset_i) begin
            for(d_map_reset=0;d_map_reset<ROB_ENTRIES;d_map_reset=d_map_reset+1)
                rob_to_lsq_mem[d_map_reset]<=0;
            for(d_map_reset=0;d_map_reset<LSQ_ENTRIES;d_map_reset=d_map_reset+1)
                lsq_phys_mem[d_map_reset]<=0;
        end else begin
            for(d_map_lane=0;d_map_lane<BE_WIDTH;d_map_lane=d_map_lane+1)
                if(d_valid[d_map_lane] && lsq_alloc_fire[d_map_lane]) begin
                    d_map_rob_slot=d_tag[d_map_lane*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
                    d_map_lsq_slot=lsq_alloc_tag[d_map_lane*TAG_WIDTH+3 +: LSQ_SLOT_WIDTH];
                    rob_to_lsq_mem[d_map_rob_slot]<=lsq_alloc_tag[d_map_lane*TAG_WIDTH +: TAG_WIDTH];
                    lsq_phys_mem[d_map_lsq_slot]<=d_new_phys[d_map_lane*PAW +: PAW];
                end
        end
    end

    assign rob_store_ack_valid = lsq_store_ack_valid;''')
    return t+PACKET


def enable(t):
    return change(t,'    rv32_backend_joint #(.ISSUE_PIPELINE(ISSUE_PIPELINE),',
                  '    rv32_backend_joint #(.DISPATCH_PIPELINE(1), .ISSUE_PIPELINE(ISSUE_PIPELINE),')


if __name__=='__main__':
    prepare('AD_reserved_dispatch_boundary', ROOT/'AC_visible_state_optimization',
            {'rtl/backend/rv32_backend_joint.v':stage_backend,'rtl/cpu_core.v':enable},
            'AC plus real rename/ROB to operand/RS/LSQ stage, single reserved bundle with selective recovery, conservative F-Q-A RS/LSQ credits, destination busy/tag at R and LSQ mapping at D; ordinary integer pipeline adds one level, no D-ready feedback to R; no EDA run')
