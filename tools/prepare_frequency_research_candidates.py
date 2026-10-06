"""Prepare reviewable RTL candidates from a measured snapshot, without tests.

This file does not import subprocess or invoke compilers, simulators, synthesis,
STA, formal tools or linters. Its assertions only guard source transformations.
"""
from collections import Counter
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil

BASE = Path('F:/CPU2026CourseRuns/current_adopted_20261003/source')
OUT = Path('F:/CPU2026Candidates/frequency_research_20261003')
EVIDENCE = Path('E:/Verilog_cpu/reports/frequency_research_20261003')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def once(text, before, after):
    assert text.count(before) == 1, before[:160]
    return text.replace(before, after, 1)


def payload_decoupling(files):
    name = 'rtl/frontend/rv32_fetch_frontend.v'
    text = files[name]
    text = once(text, '    wire queue_space =', '''    // Payload may be written on an invalidating edge: occupancy discards
    // those rows. Architectural response acceptance remains redirect-qualified.
    wire payload_response_write = if_resp_valid_i && response_live && queue_space;
    wire queue_space =''')
    text = once(text, 'assign payload_write_valid[payload_lane]=resp_fire &&',
                'assign payload_write_valid[payload_lane]=payload_response_write &&')
    text = once(text, '.clk_i(clk_i), .reset_i(reset_i), .redirect_i(redirect_valid_i),',
                '.clk_i(clk_i), .reset_i(1\'b0), .redirect_i(1\'b0),')
    text = once(text, '''        if(reset_i) data_o<=0;
        else if(!redirect_i && (|selected)) data_o<=packet;''', '''        // Empty/invalid rows have no architectural payload. Do not broadcast
        // reset or redirect to the stored data; queue control owns validity.
        if(|selected) data_o<=packet;''')
    files[name] = text

    name = 'rtl/cpu_core.v'
    text = files[name]
    text = once(text, '    wire [LANES-1:0] push = valid_i & ready_o;', '''    // Raw storage writes agree with public acceptance on ordinary cycles.
    // During invalidation arbitrary payload writes are harmless: count=0 wins.
    reg [LANES-1:0] storage_push;
    reg [LANES-1:0] storage_ready;
    reg [CW-1:0] storage_consumed;
    wire invalidate = reset_i || flush_i;''')
    before = '''        consumed=0;accepted=0;valid_o=0;ready_o=0;prefix=1;
        for(lane=0;lane<LANES;lane=lane+1) begin
            valid_o[lane]=(lane<count) && !reset_i && !flush_i;
            if(prefix && valid_o[lane] && ready_i[lane]) consumed=consumed+1'b1;
            else prefix=0;
        end
        capacity=LANES-count+consumed;
        prefix=1;
        for(lane=0;lane<LANES;lane=lane+1) begin
            ready_o[lane]=prefix && (lane<capacity) && !reset_i && !flush_i;
            if(ready_o[lane] && valid_i[lane]) accepted=accepted+1'b1;
            else prefix=0;
        end'''
    after = '''        consumed=0;accepted=0;valid_o=0;ready_o=0;prefix=1;
        storage_consumed=0;storage_push=0;storage_ready=0;
        for(lane=0;lane<LANES;lane=lane+1) begin
            valid_o[lane]=(lane<count) && !invalidate;
            if(prefix && (lane<count) && ready_i[lane])
                storage_consumed=storage_consumed+1'b1;
            else prefix=0;
        end
        capacity=LANES-count+storage_consumed;
        prefix=1;
        for(lane=0;lane<LANES;lane=lane+1) begin
            storage_ready[lane]=prefix && (lane<capacity);
            storage_push[lane]=storage_ready[lane] && valid_i[lane];
            ready_o[lane]=storage_ready[lane] && !invalidate;
            if(ready_o[lane] && valid_i[lane]) accepted=accepted+1'b1;
            if(!storage_push[lane]) prefix=0;
        end
        if(!invalidate) consumed=storage_consumed;'''
    text = once(text, before, after)
    text = once(text, '.clk_i(clk_i),.reset_i(reset_i),.flush_i(flush_i),.tail_i(tail),',
                '.clk_i(clk_i),.reset_i(1\'b0),.flush_i(1\'b0),.tail_i(tail),')
    text = once(text, '.push_i(push),.data_i(inputs)', '.push_i(storage_push),.data_i(inputs)')
    text = once(text, '''        if(reset_i) data_o<=0;
        else if(!flush_i && (|selected)) data_o<=next_data;''', '''        // Count/head/tail invalidate the queue on the same edge. Every row
        // is fully rewritten before it becomes valid again.
        if(|selected) data_o<=next_data;''')
    files[name] = text


TREE = '''
// Actual priced ASAP7 cells preserve separate electrical domains through ABC.
// No cycle is added. Each output must be wired to its own real consumers.
module rv32_frequency_control_tree #(
    parameter integer WIDTH=1, LEAVES=4
) (
    input wire [WIDTH-1:0] signal_i,
    output wire [WIDTH*LEAVES-1:0] views_o
);
    wire [WIDTH-1:0] trunk;
    genvar bit_id, leaf;
    generate for(bit_id=0;bit_id<WIDTH;bit_id=bit_id+1) begin:g_bit
        (* keep=1 *) BUFx16f_ASAP7_75t_R root_cell (
            .A(signal_i[bit_id]),.Y(trunk[bit_id]));
        for(leaf=0;leaf<LEAVES;leaf=leaf+1) begin:g_leaf
            (* keep=1 *) BUFx16f_ASAP7_75t_R leaf_cell (
                .A(trunk[bit_id]),.Y(views_o[leaf*WIDTH+bit_id]));
        end
    end endgenerate
endmodule
'''


def control_domains(files):
    files['rtl/common/rv32_asap7_fanout.v'] += TREE

    name = 'rtl/backend/rv32_rob.v'
    text = files[name]
    for port in ('recovery_accept_o', 'redirect_valid_o', 'checkpoint_restore_valid_o'):
        text = once(text, '    output reg                          ' + port + ',',
                    '    output wire                         ' + port + ',')
        text = once(text, f'        {port} = recovery_found;\n', '')
    text = once(text, '    reg recovery_found;', '''    reg recovery_found;
    wire [5:0] recovery_domains;
    rv32_frequency_control_tree #(.LEAVES(6)) recovery_tree (
        .signal_i(recovery_found),.views_o(recovery_domains));
    assign recovery_accept_o=recovery_domains[0];
    assign redirect_valid_o=recovery_domains[1];
    assign checkpoint_restore_valid_o=recovery_domains[2];''')
    text = once(text, 'assign head_next = recovery_accept_o ?',
                'assign head_next = recovery_domains[3] ?')
    text = once(text, 'assign alloc_ready_o = (alloc_count_o != 0) && !recovery_accept_o;',
                'assign alloc_ready_o = (alloc_count_o != 0) && !recovery_domains[3];')
    text = once(text, 'assign reclaim_eligible[reclaim_entry] = recovery_found &&',
                'assign reclaim_eligible[reclaim_entry] = recovery_domains[4] &&')
    text = once(text, '        if (recovery_found) begin', '        if (recovery_domains[4]) begin')
    text = once(text, '        if (!recovery_found && !halted_o && !error_o) begin',
                '        if (!recovery_domains[5] && !halted_o && !error_o) begin')
    text = once(text, '        end else if (recovery_accept_o) begin',
                '        end else if (recovery_domains[5]) begin')
    files[name] = text

    name = 'rtl/backend/rv32_backend_joint.v'
    text = files[name]
    text = once(text, '    wire rob_recovery_accept, rob_redirect_valid, rob_checkpoint_restore_valid;',
                '''    wire rob_recovery_accept_source, rob_redirect_valid, rob_checkpoint_restore_valid;
    wire [7:0] recovery_domains;
    rv32_frequency_control_tree #(.LEAVES(8)) recovery_tree (
        .signal_i(rob_recovery_accept_source),.views_o(recovery_domains));''')
    # Different source regions consume different leaves. No alias/replicated
    # expression is relied upon to survive flattening or optimization.
    region = 0
    changed = []
    anchors = {
        '    // The ROB owns the physical mappings': 1,
        '    // External flushes clear the station.': 2,
        '    // Completions may be queued': 3,
        '    // Rename and PRF form': 1,
        '    // Registered RS selection': 4,
        '    rv32_lsq #(': 5,
        '    // Keep producer positions fixed.': 6,
        '    always @(posedge clk_i) begin': 7,
    }
    for line in text.splitlines(keepends=True):
        for anchor, leaf in anchors.items():
            if line.startswith(anchor):
                region = leaf
        if '.recovery_accept_o(rob_recovery_accept)' in line:
            line = line.replace('.recovery_accept_o(rob_recovery_accept)',
                                '.recovery_accept_o(rob_recovery_accept_source)')
        else:
            line = re.sub(r'\brob_recovery_accept\b', f'recovery_domains[{region}]', line)
        changed.append(line)
    text = ''.join(changed)
    assert not re.search(r'\brob_recovery_accept\b', text)
    files[name] = text

    name = 'rtl/cpu_core.v'
    text = files[name]
    text = once(text, '    wire redirect_valid;', '''    wire redirect_valid;
    wire [2:0] redirect_domains;
    rv32_frequency_control_tree #(.LEAVES(3)) redirect_tree (
        .signal_i(redirect_valid),.views_o(redirect_domains));''')
    text = once(text, '!redirect_valid && !halted && !error)',
                '!redirect_domains[1] && !halted && !error)')
    text = once(text, '.recovery_valid_i(redirect_valid)', '.recovery_valid_i(redirect_domains[1])')
    text = once(text, '.redirect_valid_i(redirect_valid)', '.redirect_valid_i(redirect_domains[0])')
    text = once(text, '.flush_i(redirect_valid || halted || error)',
                '.flush_i(redirect_domains[2] || halted || error)')
    text = once(text, '    wire invalidate = reset_i || flush_i;', '''    wire invalidate = reset_i || flush_i;
    wire [1:0] invalidate_domains;
    rv32_frequency_control_tree #(.LEAVES(2)) invalidate_tree (
        .signal_i(invalidate),.views_o(invalidate_domains));''')
    # Only the decode module owns the newly introduced invalidate symbol.
    text = text.replace(' && !invalidate;', ' && !invalidate_domains[0];')
    text = once(text, '        if(!invalidate) consumed=storage_consumed;',
                '        if(!invalidate_domains[0]) consumed=storage_consumed;')
    text = once(text, '        if(reset_i || flush_i) begin count<=0;head<=0;tail<=0;end',
                '        if(invalidate_domains[1]) begin count<=0;head<=0;tail<=0;end')
    # Data-word controls are separate physical leaves, beside their consumers.
    text = once(text, '    wire [LANES-1:0] selected;', '''    wire [LANES-1:0] selected;
    wire [LANES-1:0] selected_local;
    rv32_frequency_control_tree #(.WIDTH(LANES),.LEAVES(1)) select_tree (
        .signal_i(selected),.views_o(selected_local));''')
    text = once(text, '{WIDTH{selected[lane]}}', '{WIDTH{selected_local[lane]}}')
    text = once(text, '    reg [WIDTH-1:0] next_data;', '''    wire write_local;
    rv32_frequency_control_tree #(.LEAVES(1)) write_enable_tree (
        .signal_i(|selected_local),.views_o(write_local));
    reg [WIDTH-1:0] next_data;''')
    text = once(text, 'if(|selected) data_o<=next_data;', 'if(write_local) data_o<=next_data;')
    files[name] = text

    name = 'rtl/frontend/rv32_fetch_frontend.v'
    text = files[name]
    text = once(text, '    wire [FE_WIDTH-1:0] selected, granted;', '''    wire [FE_WIDTH-1:0] selected, granted;
    wire [FE_WIDTH-1:0] granted_local;
    rv32_frequency_control_tree #(.WIDTH(FE_WIDTH),.LEAVES(1)) write_tree (
        .signal_i(granted),.views_o(granted_local));''')
    text = once(text, '{WIDTH{granted[source_lane]}}', '{WIDTH{granted_local[source_lane]}}')
    text = once(text, '    reg [WIDTH-1:0] packet;', '''    wire write_local;
    rv32_frequency_control_tree #(.LEAVES(1)) write_enable_tree (
        .signal_i(|granted_local),.views_o(write_local));
    reg [WIDTH-1:0] packet;''')
    text = once(text, 'if(|selected) data_o<=packet;', 'if(write_local) data_o<=packet;')
    files[name] = text


def pipelined_multiplier(original):
    # Reuse the exact public port declarations; the enclosing MDU supports
    # multiple inflight multiply requests and tagged, arbitrated completions.
    start = original.index('module rv32m_multiplier #(')
    end = original.index('    function [63:0] csa_sum3;')
    interface = original[start:end]
    body = '''    function [63:0] csa_sum3;
        input [63:0] a,b,c;
        begin csa_sum3=a^b^c; end
    endfunction
    function [63:0] csa_carry3;
        input [63:0] a,b,c;
        begin csa_carry3=((a&b)|(a&c)|(b&c))<<1; end
    endfunction

    // Signed high halves are corrected in carry-save form, modulo 2^64:
    // U=A*B; signed correction is -(Anegative*B + Bnegative*A)<<32.
    // Each negative term is {~operand,0} plus 1<<32. No absolute-value
    // carry-propagate adder precedes the partial-product tree.
    wire neg_a=((req_op_i==`RV32IM_OP_MULH)||
                (req_op_i==`RV32IM_OP_MULHSU)) && req_src1_i[31];
    wire neg_b=(req_op_i==`RV32IM_OP_MULH) && req_src2_i[31];
    wire [63:0] pp [0:35];
    genvar row;
    generate for(row=0;row<32;row=row+1) begin:g_pp
        assign pp[row]=req_src2_i[row]?({32'b0,req_src1_i}<<row):64'b0;
    end endgenerate
    assign pp[32]=neg_a?{~req_src2_i,32'b0}:64'b0;
    assign pp[33]=neg_a?64'h0000000100000000:64'b0;
    assign pp[34]=neg_b?{~req_src1_i,32'b0}:64'b0;
    assign pp[35]=neg_b?64'h0000000100000000:64'b0;
'''
    previous = 'pp'
    for stage, (inputs, outputs) in enumerate(((36,24),(24,16),(16,11),(11,8)), 1):
        target = f'l{stage}'
        body += reduce_level(previous, target, inputs, outputs)
        previous = target
    body += '''    reg s1_valid;
    reg [63:0] s1_rows [0:7];
    reg [OP_WIDTH-1:0] s1_op;
    reg [TAG_WIDTH-1:0] s1_tag;
    reg [PHYS_ADDR_WIDTH-1:0] s1_phys;
    reg s1_live;
    reg out_valid;
    reg [31:0] out_value;
    reg [TAG_WIDTH-1:0] out_tag;
    reg [PHYS_ADDR_WIDTH-1:0] out_phys;
    reg out_live;
    wire s1_discard=s1_valid && (!s1_live ||
        (live_tag_valid_i && s1_tag!=live_tag_i));
    wire out_discard=out_valid && (!out_live ||
        (live_tag_valid_i && out_tag!=live_tag_i));
    wire out_ready=!out_valid || resp_ready_i || out_discard;
    wire s1_ready=!s1_valid || out_ready || s1_discard;
    wire [8:0] s1_write_domains;
    wire [1:0] out_write_domains;
    // A single ready/valid gate must not directly drive 512 payload hold muxes.
    rv32_frequency_control_tree #(.LEAVES(9)) s1_write_tree (
        .signal_i(req_valid_i && req_ready_o),.views_o(s1_write_domains));
    rv32_frequency_control_tree #(.LEAVES(2)) out_write_tree (
        .signal_i(out_ready && s1_valid && !s1_discard),.views_o(out_write_domains));
    assign req_ready_o=!flush_i && s1_ready;
    assign resp_valid_o=out_valid && out_live &&
        (!live_tag_valid_i || out_tag==live_tag_i);
    assign resp_value_o=out_value;
    assign resp_rob_tag_o=out_tag;
    assign resp_phys_rd_o=out_phys;
    assign resp_rd_we_o=1'b1;
'''
    previous = 's1_rows'
    for stage, (inputs, outputs) in enumerate(((8,6),(6,4),(4,3),(3,2)), 5):
        target = f'l{stage}'
        body += reduce_level(previous, target, inputs, outputs)
        previous = target
    body += '''    wire [63:0] product=l8[0]+l8[1];
    // Invalid payload may be overwritten even on a reset edge. Valid bits
    // below discard it; each newly valid transaction has all fields written.
    generate for(row=0;row<8;row=row+1) begin:g_s1_storage
        always @(posedge clk_i) if(s1_write_domains[row])
            s1_rows[row]<=l4[row];
    end endgenerate
    always @(posedge clk_i) begin
        if(reset_i || flush_i) begin
            s1_valid<=1'b0;
            out_valid<=1'b0;
        end else begin
            if(s1_ready) begin
                s1_valid<=req_valid_i && req_ready_o;
                if(s1_write_domains[8]) begin
                    s1_op<=req_op_i;
                    s1_tag<=req_rob_tag_i;
                    s1_phys<=req_phys_rd_i;
                    s1_live<=req_target_live_i && req_rob_tag_i[0];
                end
            end
            if(out_ready) begin
                out_valid<=s1_valid && !s1_discard;
            end
            if(out_write_domains[0]) begin
                    case(s1_op)
                        `RV32IM_OP_MUL: out_value<=product[31:0];
                        `RV32IM_OP_MULH,`RV32IM_OP_MULHSU,`RV32IM_OP_MULHU:
                            out_value<=product[63:32];
                        default: out_value<=32'b0;
                    endcase
            end
            if(out_write_domains[1]) begin
                    out_tag<=s1_tag;
                    out_phys<=s1_phys;
                    out_live<=s1_live;
            end
        end
    end
endmodule
'''
    return '`timescale 1ns/1ps\n`include "rv32im_defs.vh"\n\n// Two genuinely split arithmetic stages; one request per cycle when unstalled.\n' + interface + body


def reduce_level(source, target, inputs, outputs):
    groups, remainder = divmod(inputs, 3)
    assert outputs == 2*groups + remainder
    text = f'    wire [63:0] {target} [0:{outputs-1}];\n'
    for group in range(groups):
        args = ','.join(f'{source}[{3*group+k}]' for k in range(3))
        text += f'    assign {target}[{2*group}]=csa_sum3({args});\n'
        text += f'    assign {target}[{2*group+1}]=csa_carry3({args});\n'
    for row in range(remainder):
        text += f'    assign {target}[{2*groups+row}]={source}[{3*groups+row}];\n'
    return text


def main():
    assert not OUT.exists(), 'Preserve existing candidates'
    baseline = json.loads((BASE.parent / 'source_manifest.json').read_text(encoding='utf-8'))
    paths = sorted(p for p in BASE.rglob('*') if p.is_file() and '.deps' not in p.parts)
    original = {}
    for path in paths:
        name = path.relative_to(BASE).as_posix()
        if name in baseline['snapshot_sha256']:
            assert sha(path) == baseline['snapshot_sha256'][name].lower(), name
        original[name] = path.read_text(encoding='utf-8')
    work = dict(original)
    payload_decoupling(work)
    variants = [('A_payload_acceptance_decoupling', dict(work), 'No intended cycle changes')]
    control_domains(work)
    variants.append(('B_priced_control_domains', dict(work), 'No intended cycle changes; real library buffers'))
    work['rtl/rv32m_multiplier.v'] = pipelined_multiplier(work['rtl/rv32m_multiplier.v'])
    variants.append(('C_split_signed_multiplier', dict(work), 'Multiplier latency +1; initiation interval remains 1'))
    for label, files, behavior in variants:
        directory = OUT / label
        directory.mkdir(parents=True)
        changed, diffs = [], []
        for name, content in files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if content == original[name]:
                shutil.copyfile(BASE / name, path)
            else:
                path.write_text(content, encoding='utf-8', newline='\n')
            if content != original[name]:
                changed.append(name)
                diffs.extend(difflib.unified_diff(original[name].splitlines(keepends=True),
                                                content.splitlines(keepends=True),
                                                fromfile='measured/' + name, tofile=label + '/' + name))
        manifest = dict(status='PREPARED_UNTESTED_NOT_ADOPTED', source_root=str(directory),
                        measured_baseline=str(BASE), measured_baseline_manifest_sha256=sha(BASE.parent / 'source_manifest.json'),
                        parameter_overrides=baseline['parameter_overrides'],
                        official_framework_root=str(BASE / '.deps/RISC-V-CPU-2026'),
                        framework_commit=baseline['framework_commit'], testcases_commit=baseline['testcases_commit'],
                        latency=10, measurement_host='Windows native only', behavior=behavior,
                        tests_started=False, synthesis_started=False, timing_started=False,
                        changed_files=changed, source_sha256={name: sha(directory / name) for name in files},
                        preparation_script_sha256=sha(Path(__file__)))
        (directory / 'candidate.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (directory / 'review.patch').write_text(''.join(diffs), encoding='utf-8')
        print(json.dumps(dict(candidate=label, changed_files=changed, status=manifest['status']), ensure_ascii=False))
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / 'candidate_index.json').write_text(json.dumps(dict(root=str(OUT), variants=[v[0] for v in variants],
        status='PREPARED_UNTESTED_NOT_ADOPTED', no_tests_started=True), indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
