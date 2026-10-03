"""Add two optional, registered transaction boundaries to the frozen CPU."""
from pathlib import Path
import re


DECODE_REGISTER = r'''
// One registered decode bundle, with ordered prefix consumption and refill.
// Data never falls through from input to output in the same cycle.
module rv32_decode_bundle_register #(
    parameter integer LANES = 4, PAYLOAD_WIDTH = 192,
    parameter integer CW = (LANES < 2) ? 1 : $clog2(LANES+1)
) (
    input wire clk_i, reset_i, flush_i,
    input wire [LANES-1:0] valid_i,
    output reg [LANES-1:0] ready_o,
    input wire [LANES*PAYLOAD_WIDTH-1:0] data_i,
    output reg [LANES-1:0] valid_o,
    input wire [LANES-1:0] ready_i,
    output wire [LANES*PAYLOAD_WIDTH-1:0] data_o
);
    reg [CW-1:0] count;
    reg [LANES*PAYLOAD_WIDTH-1:0] payload, next_payload;
    integer consumed, remaining, accepted, lane;
    reg prefix;
    assign data_o = payload;
    always @* begin
        valid_o = 0;
        ready_o = 0;
        consumed = 0;
        prefix = 1;
        for (lane=0; lane<LANES; lane=lane+1) begin
            valid_o[lane] = (lane < count) && !reset_i && !flush_i;
            if (prefix && valid_o[lane] && ready_i[lane])
                consumed = consumed + 1;
            else prefix = 0;
        end
        remaining = count - consumed;
        next_payload = payload >> (consumed*PAYLOAD_WIDTH);
        accepted = 0;
        prefix = 1;
        for (lane=0; lane<LANES; lane=lane+1) begin
            ready_o[lane] = prefix && (remaining+lane < LANES) && !reset_i && !flush_i;
            if (ready_o[lane] && valid_i[lane]) begin
                next_payload[(remaining+accepted)*PAYLOAD_WIDTH +: PAYLOAD_WIDTH] =
                    data_i[lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH];
                accepted = accepted + 1;
            end else prefix = 0;
        end
    end
    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            count <= 0;
            payload <= 0;
        end else begin
            count <= remaining + accepted;
            if (consumed != 0 || accepted != 0) payload <= next_payload;
        end
    end
endmodule
'''

ISSUE_REGISTER = r'''
// A selected instruction is removed from the RS only when this slot accepts it.
// Recovery retains older instructions; clearing every slot would lose work.
module rv32_issue_pipeline_slot #(
    parameter integer PAYLOAD_WIDTH=192, TAG_WIDTH=17, ROB_ENTRIES=64,
    parameter integer SW=(ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES)
) (
    input wire clk_i, reset_i, flush_i, recovery_i,
    input wire [SW-1:0] head_i,
    input wire [TAG_WIDTH-1:0] recovery_tag_i,
    input wire valid_i, eligible_i,
    output wire ready_o,
    input wire [PAYLOAD_WIDTH-1:0] data_i,
    input wire [TAG_WIDTH-1:0] tag_i,
    output wire valid_o,
    input wire ready_i,
    output reg [PAYLOAD_WIDTH-1:0] data_o
);
    reg occupied;
    reg [TAG_WIDTH-1:0] saved_tag;
    // ROB capacity is a power of two: truncation implements modular age.
    wire [SW-1:0] saved_age = saved_tag[3 +: SW] - head_i;
    wire [SW-1:0] branch_age = recovery_tag_i[3 +: SW] - head_i;
    assign valid_o = occupied && !reset_i && !flush_i && !recovery_i;
    assign ready_o = (!occupied || ready_i) && eligible_i &&
                     !reset_i && !flush_i && !recovery_i;
    always @(posedge clk_i) begin
        if (reset_i || flush_i) begin
            occupied <= 0;
            saved_tag <= 0;
            data_o <= 0;
        end else if (recovery_i) begin
            if (occupied && saved_age >= branch_age) occupied <= 0;
        end else if (ready_o && valid_i) begin
            occupied <= 1;
            saved_tag <= tag_i;
            data_o <= data_i;
        end else if (valid_o && ready_i) occupied <= 0;
    end
endmodule
'''


def replace_once(s, old, new):
    assert s.count(old) == 1, (old, s.count(old))
    return s.replace(old, new)


def transform(root):
    root = Path(root)
    p = root/'rtl/cpu_core.v'
    s = p.read_text(encoding='utf-8')
    s = replace_once(s, 'module cpu_core #(\n', 'module cpu_core #(\n    parameter integer DECODE_PIPELINE = 0, ISSUE_PIPELINE = 0,\n')
    s = replace_once(s, 'rv32_backend_joint #(', 'rv32_backend_joint #(.ISSUE_PIPELINE(ISSUE_PIPELINE), ')
    fields = [('trace_packet','PACKET_WIDTH'), ('trace_pred_metadata','16'),
              ('dec_legal','1'), ('dec_op','`RV32IM_OP_WIDTH'), ('dec_class','4'),
              ('dec_rd','5'), ('dec_rs1','5'), ('dec_rs2','5'),
              ('dec_rd_we','1'), ('dec_rs1_used','1'), ('dec_rs2_used','1'),
              ('dec_imm','32'), ('dec_load','1'), ('dec_store','1'),
              ('dec_branch','1'), ('dec_jump','1'), ('dec_serialize','1'),
              ('dec_mem_size','2'), ('dec_mem_unsigned','1'),
              ('dec_mem_base_mask','4'), ('dec_jalr_clear_lsb','1')]
    declarations = '\n    // Decode output is registered before rename/PRF access.\n'
    declarations += '    localparam integer DECODE_PAYLOAD_WIDTH = '+' + '.join(w for n,w in fields)+';\n'
    declarations += '    wire [BE_WIDTH-1:0] raw_trace_valid, raw_trace_ready;\n'
    declarations += ''.join(f'    wire [BE_WIDTH*{w}-1:0] raw_{n};\n' for n,w in fields)
    declarations += '    wire [BE_WIDTH*DECODE_PAYLOAD_WIDTH-1:0] decode_input, decode_output;\n'
    s = replace_once(s, '    genvar frontend_lane;', declarations+'\n    genvar frontend_lane;')
    s = replace_once(s, 'assign fetch_ready[frontend_lane] = trace_ready[frontend_lane];', 'assign fetch_ready[frontend_lane] = raw_trace_ready[frontend_lane];')
    start = s.index('            if (decode_lane < FE_WIDTH)')
    end = s.index('            assign trace_pc', start)
    block = s[start:end]
    for name in ('trace_pred_metadata','trace_valid','trace_packet'):
        block = re.sub(r'\b'+name+r'\b', 'raw_'+name, block)
    s = s[:start]+block+s[end:]
    start = s.index('            rv32im_decoder #(')
    end = s.index('            // HALT commits', start)
    block = s[start:end].replace('trace_inst[decode_lane*32 +: 32]', 'raw_trace_packet[decode_lane*PACKET_WIDTH+32 +: 32]')
    for name,w in fields:
        if name.startswith('dec_'):
            block = re.sub(r'\b'+name+r'\b', 'raw_'+name, block)
    def lane_fields(prefix):
        return ', '.join(f'{prefix}{n}[decode_lane*{w} +: {w}]' for n,w in fields)
    block += '            assign decode_input[decode_lane*DECODE_PAYLOAD_WIDTH +: DECODE_PAYLOAD_WIDTH] = {'+lane_fields('raw_')+'};\n'
    block += '            assign {'+lane_fields('')+'} = decode_output[decode_lane*DECODE_PAYLOAD_WIDTH +: DECODE_PAYLOAD_WIDTH];\n\n'
    s = s[:start]+block+s[end:]
    pipeline = '''
    generate if (DECODE_PIPELINE != 0) begin : g_decode_pipeline
        rv32_decode_bundle_register #(.LANES(BE_WIDTH), .PAYLOAD_WIDTH(DECODE_PAYLOAD_WIDTH)) pipe (
            .clk_i(clk), .reset_i(reset), .flush_i(redirect_valid || halted || error),
            .valid_i(raw_trace_valid), .ready_o(raw_trace_ready), .data_i(decode_input),
            .valid_o(trace_valid), .ready_i(trace_ready), .data_o(decode_output));
    end else begin : g_decode_direct
        assign trace_valid = raw_trace_valid;
        assign raw_trace_ready = trace_ready;
        assign decode_output = decode_input;
    end endgenerate

'''
    s = replace_once(s, '    wire [BE_WIDTH-1:0] commit_valid,', pipeline+'    wire [BE_WIDTH-1:0] commit_valid,')
    p.write_text(s+DECODE_REGISTER, encoding='utf-8', newline='\n')

    p = root/'rtl/backend/rv32_backend_joint.v'
    s = p.read_text(encoding='utf-8')
    s = replace_once(s, 'module rv32_backend_joint #(\n', 'module rv32_backend_joint #(\n    parameter integer ISSUE_PIPELINE = 0,\n')
    fields = [('op','`RV32IM_OP_WIDTH'),('pc','32'),('tag','TAG_WIDTH'),('phys','PAW'),
              ('src1','32'),('src2','32'),('store','32'),('metadata','RS_METADATA_WIDTH'),
              ('slot','((RS_ENTRIES <= 1) ? 1 : $clog2(RS_ENTRIES))')]
    decl = '\n    // Registered RS selection / execution boundary.\n'
    decl += '    localparam integer ISSUE_PAYLOAD_WIDTH = '+' + '.join(w for n,w in fields)+';\n'
    decl += '    wire [BE_WIDTH-1:0] raw_rs_issue_valid, raw_rs_issue_ready;\n'
    decl += ''.join(f'    wire [BE_WIDTH*{w}-1:0] raw_rs_issue_{n};\n' for n,w in fields)
    start = s.index('    rv32_reservation_station #(')
    end = s.index('    genvar alu_lane;', start)
    block = s[start:end]
    for name in ['valid','ready']+[n for n,w in fields]:
        block = re.sub(r'\brs_issue_'+name+r'\b','raw_rs_issue_'+name,block)
    stage = '    genvar pipe_lane;\n    generate for (pipe_lane=0; pipe_lane<BE_WIDTH; pipe_lane=pipe_lane+1) begin : g_issue_pipeline\n'
    stage += '        if (ISSUE_PIPELINE != 0) begin : g_registered\n'
    stage += '            wire [ISSUE_PAYLOAD_WIDTH-1:0] in_payload, out_payload;\n'
    def issue_fields(prefix):
        return ', '.join(f'{prefix}rs_issue_{n}[pipe_lane*{w} +: {w}]' for n,w in fields)
    stage += '            assign in_payload = {'+issue_fields('raw_')+'};\n'
    stage += '            assign {'+issue_fields('')+'} = out_payload;\n'
    stage += '            wire [`RV32IM_OP_WIDTH-1:0] raw_op = raw_rs_issue_op[pipe_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH];\n'
    stage += '            wire raw_mdu = '+' || '.join('(raw_op == `RV32IM_OP_'+op+')' for op in ('MUL','MULH','MULHSU','MULHU','DIV','DIVU','REM','REMU'))+';\n'
    stage += '''            rv32_issue_pipeline_slot #(.PAYLOAD_WIDTH(ISSUE_PAYLOAD_WIDTH),
                .TAG_WIDTH(TAG_WIDTH), .ROB_ENTRIES(ROB_ENTRIES)) pipe (
                .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i),
                .recovery_i(rob_recovery_accept), .recovery_tag_i(branch_pending_tag),
                .head_i(rob_head_views[5*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]),
                .valid_i(raw_rs_issue_valid[pipe_lane]),
                .eligible_i((pipe_lane < INT_ISSUE_WIDTH) || raw_mdu),
                .ready_o(raw_rs_issue_ready[pipe_lane]), .data_i(in_payload),
                .tag_i(raw_rs_issue_tag[pipe_lane*TAG_WIDTH +: TAG_WIDTH]),
                .valid_o(rs_issue_valid[pipe_lane]), .ready_i(rs_issue_ready[pipe_lane]),
                .data_o(out_payload));
        end else begin : g_direct
            assign rs_issue_valid[pipe_lane] = raw_rs_issue_valid[pipe_lane];
            assign raw_rs_issue_ready[pipe_lane] = rs_issue_ready[pipe_lane];
'''
    for n,w in fields:
        stage += f'            assign rs_issue_{n}[pipe_lane*{w} +: {w}] = raw_rs_issue_{n}[pipe_lane*{w} +: {w}];\n'
    stage += '        end\n    end endgenerate\n\n'
    s = s[:start]+decl+block+stage+s[end:]
    p.write_text(s+ISSUE_REGISTER, encoding='utf-8', newline='\n')
    p = root/'rtl/course/student_top.v'
    s = p.read_text(encoding='utf-8')
    s = replace_once(s, 'module student_top #(\n', 'module student_top #(\n    parameter integer DECODE_PIPELINE = 0, ISSUE_PIPELINE = 0,\n')
    s = replace_once(s, 'cpu_core #(', 'cpu_core #(.DECODE_PIPELINE(DECODE_PIPELINE), .ISSUE_PIPELINE(ISSUE_PIPELINE), ')
    p.write_text(s, encoding='utf-8', newline='\n')
