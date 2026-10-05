"""Prepare a single-cycle instruction-line filter; no HDL tools or tests."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
from manage_frozen_baseline_programs import read, sha, write
from review_frequency_dx_sources import blocks

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A11_compact_direct_cdb'
TARGET = BASE / 'A12_one_cycle_instruction_lines'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def interface():
    request = [('valid', ''), ('ready', ''), ('pc', '[31:0]'),
               ('epoch', '[EPOCH_WIDTH-1:0]')]
    response = [('valid', ''), ('ready', ''), ('pc', '[31:0]'),
                ('line_addr', '[31:0]'), ('line_data', '[127:0]'),
                ('epoch', '[EPOCH_WIDTH-1:0]'), ('error', '')]
    mapping = {}
    declarations, connections, direct = [], [], []
    for direction, fields in [('req', request), ('resp', response)]:
        for field, width in fields:
            is_input = ((direction == 'req') != (field == 'ready'))
            if direction == 'resp':
                is_input = field == 'ready'
            suffix = 'i' if is_input else 'o'
            public = f'if_{direction}_{field}_{suffix}'
            private = f'primary_if_{direction}_{field}'
            mapping[public] = private
            declarations.append(f'    wire {width} {private};')
            connections.append(f'            .{public}({public})')
            # Filter's primary response inputs and request outputs are the
            # inverse of its public frontend direction.
            primary_suffix = 'o' if is_input else 'i'
            connections.append(f'            .primary_{direction}_{field}_{primary_suffix}({private})')
            direct.append(f'        assign {private if is_input else public}={public if is_input else private};')
    connections = ',\n'.join(connections)
    prefix = '\n'.join(declarations) + '''
    // Cached instruction bytes survive redirects exactly as the primary
    // I-cache does. Only transaction validity is qualified by the epoch.
    generate if(LOOP_BUFFER_LINES!=0) begin:g_instruction_line_filter
        rv32_instruction_line_filter #(.LINES(LOOP_BUFFER_LINES),.EPOCH_WIDTH(EPOCH_WIDTH)) lines (
            .clk_i(clk_i),.reset_i(reset_i),.current_epoch_i(current_epoch_i),
''' + connections + ''');
    end else begin:g_no_instruction_line_filter
''' + '\n'.join(direct) + '''
    end endgenerate

'''
    return mapping, prefix


FILTER = r'''
// A small direct-mapped L0 over the immutable instruction-line interface.
// It has one registered response, at most one primary miss in flight, and
// accepts a replacement request on the same edge as a consumed response.
// There is no combinational path from a new request to response validity.
module rv32_instruction_line_filter #(
    parameter integer LINES=16,EPOCH_WIDTH=4,
    parameter integer INDEX_WIDTH=$clog2(LINES),
    parameter integer TAG_BITS=28-INDEX_WIDTH
) (
    input wire clk_i,reset_i,
    input wire [EPOCH_WIDTH-1:0] current_epoch_i,
    input wire if_req_valid_i,
    output wire if_req_ready_o,
    input wire [31:0] if_req_pc_i,
    input wire [EPOCH_WIDTH-1:0] if_req_epoch_i,
    output wire if_resp_valid_o,
    input wire if_resp_ready_i,
    output wire [31:0] if_resp_pc_o,if_resp_line_addr_o,
    output wire [127:0] if_resp_line_data_o,
    output wire [EPOCH_WIDTH-1:0] if_resp_epoch_o,
    output wire if_resp_error_o,
    output wire primary_req_valid_o,
    input wire primary_req_ready_i,
    output wire [31:0] primary_req_pc_o,
    output wire [EPOCH_WIDTH-1:0] primary_req_epoch_o,
    input wire primary_resp_valid_i,
    output wire primary_resp_ready_o,
    input wire [31:0] primary_resp_pc_i,primary_resp_line_addr_i,
    input wire [127:0] primary_resp_line_data_i,
    input wire [EPOCH_WIDTH-1:0] primary_resp_epoch_i,
    input wire primary_resp_error_i
);
    reg [LINES-1:0] valid;
    wire [TAG_BITS+128-1:0] row_payload [0:LINES-1];
    wire [LINES*128-1:0] row_lines;
    wire [LINES-1:0] hits;
    wire [LINES*28-1:0] request_line_views;
    rv32_frequency_control_tree #(.WIDTH(28),.LEAVES(LINES)) request_views (
        .signal_i(if_req_pc_i[31:4]),.views_o(request_line_views));
    wire [127:0] hit_line;
    rv32_frequency_event_select #(.WIDTH(128),.EVENTS(LINES),.PRIORITY(0)) line_select (
        .events_i(hits),.values_i(row_lines),.write_o(),.value_o(hit_line));
    wire hit=|hits;

    reg fast_valid,miss_pending;
    wire [31:0] fast_pc,pending_pc;
    wire [EPOCH_WIDTH-1:0] fast_epoch,pending_epoch;
    wire [127:0] fast_line;
    wire fast_live=fast_valid && fast_epoch==current_epoch_i;
    wire miss_live=miss_pending && pending_epoch==current_epoch_i;
    wire primary_live=miss_live && primary_resp_valid_i &&
        primary_resp_epoch_i==pending_epoch && primary_resp_pc_i==pending_pc;
    wire release_miss=primary_live && if_resp_ready_i;
    wire fast_slot_free=!fast_valid || !fast_live || if_resp_ready_i;
    wire can_start=!reset_i && (!miss_live || release_miss) && fast_slot_free;
    assign if_req_ready_o=can_start && (hit || primary_req_ready_i);
    wire request_fire=if_req_valid_i && if_req_ready_o;
    wire accept_hit=request_fire && hit && if_req_epoch_i==current_epoch_i;
    wire accept_miss=request_fire && !hit;
    assign primary_req_valid_o=if_req_valid_i && can_start && !hit;
    assign primary_req_pc_o=if_req_pc_i;
    assign primary_req_epoch_o=if_req_epoch_i;
    // Unexpected or epoch-stale primary outputs drain without publishing.
    // A live primary response obeys the original frontend backpressure.
    assign primary_resp_ready_o=!reset_i && (!primary_live || if_resp_ready_i);
    assign if_resp_valid_o=!reset_i && (fast_live || primary_live);
    localparam integer RESPONSE_WIDTH=65+128+EPOCH_WIDTH;
    rv32_frequency_event_select #(.WIDTH(RESPONSE_WIDTH),.EVENTS(2),.PRIORITY(0)) response_select (
        .events_i({fast_live,primary_live}),
        .values_i({fast_pc,{fast_pc[31:4],4'b0},fast_line,fast_epoch,1'b0,
            primary_resp_pc_i,primary_resp_line_addr_i,primary_resp_line_data_i,
            primary_resp_epoch_i,primary_resp_error_i}),.write_o(),
        .value_o({if_resp_pc_o,if_resp_line_addr_o,if_resp_line_data_o,if_resp_epoch_o,if_resp_error_o}));
    rv32_frequency_word_bank #(.WIDTH(32+EPOCH_WIDTH+128)) fast_response (
        .clk_i(clk_i),.write_i(accept_hit),.data_i({if_req_pc_i,if_req_epoch_i,hit_line}),
        .data_o({fast_pc,fast_epoch,fast_line}));
    rv32_frequency_word_bank #(.WIDTH(32+EPOCH_WIDTH)) miss_identity (
        .clk_i(clk_i),.write_i(accept_miss),.data_i({if_req_pc_i,if_req_epoch_i}),
        .data_o({pending_pc,pending_epoch}));
    wire fill=!reset_i && primary_live && if_resp_ready_i && !primary_resp_error_i &&
        primary_resp_line_addr_i=={primary_resp_pc_i[31:4],4'b0};
    genvar row;
    generate for(row=0;row<LINES;row=row+1) begin:g_row
        localparam [INDEX_WIDTH-1:0] ROW=row;
        wire [27:0] request_line=request_line_views[row*28 +: 28];
        wire [TAG_BITS-1:0] row_tag=row_payload[row][128 +: TAG_BITS];
        assign hits[row]=valid[row] && request_line[INDEX_WIDTH-1:0]==ROW &&
            request_line[27:INDEX_WIDTH]==row_tag;
        assign row_lines[row*128 +: 128]=row_payload[row][127:0];
        wire row_write=fill && primary_resp_line_addr_i[4 +: INDEX_WIDTH]==ROW;
        rv32_frequency_word_bank #(.WIDTH(TAG_BITS+128)) payload (
            .clk_i(clk_i),.write_i(row_write),
            .data_i({primary_resp_line_addr_i[31:4+INDEX_WIDTH],primary_resp_line_data_i}),
            .data_o(row_payload[row]));
        always @(posedge clk_i) begin
            if(reset_i) valid[row]<=1'b0;
            else if(row_write) valid[row]<=1'b1;
        end
    end endgenerate
    always @(posedge clk_i) begin
        if(reset_i) begin fast_valid<=1'b0;miss_pending<=1'b0;end
        else begin
            if(fast_slot_free) fast_valid<=1'b0;
            if(accept_hit) fast_valid<=1'b1;
            if(!miss_live || release_miss) miss_pending<=1'b0;
            if(accept_miss) miss_pending<=1'b1;
        end
    end
    initial begin
        if(LINES<2 || LINES>32 || (LINES & (LINES-1))!=0)
            $fatal(1,"Instruction line filter needs a power-of-two line count in 2..32");
    end
endmodule
'''


def main():
    assert not TARGET.exists(), TARGET
    pm = read(PARENT / 'candidate.json')
    for name, digest in pm['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/cache/rv32_icache_nonblocking.v'
    old = (PARENT / name).read_text(encoding='utf-8')
    start = old.index('    wire lookup_req_valid,lookup_req_ready;')
    end = old.index('\nendmodule', start)
    mapping, prefix = interface()
    body = old[start:end]
    # Named submodule port labels belong to that module's interface. Only
    # rename signals; renaming .if_req_pc_i(...) breaks the MSHR connection.
    pattern = re.compile(r'(?<!\.)\b(' + '|'.join(map(re.escape, mapping)) + r')\b')
    adapted = pattern.sub(lambda m: mapping[m.group(0)], body)
    assert re.findall(r'\.([A-Za-z_]\w*)\s*\(', adapted) == re.findall(r'\.([A-Za-z_]\w*)\s*\(', body)
    # Source-scoped proof: the primary cache's entire body is unchanged
    # after reversing only port renames. State, arbitration and SRAM code
    # do not acquire any edits from the new filter.
    inverse = {v: k for k, v in mapping.items()}
    reverse = re.compile(r'(?<!\.)\b(' + '|'.join(map(re.escape, inverse)) + r')\b')
    assert reverse.sub(lambda m: inverse[m.group(0)], adapted) == body
    assert blocks(adapted) == blocks(pattern.sub(lambda m: mapping[m.group(0)], body))
    text = old[:start] + prefix + adapted + old[end:] + FILTER
    text = once(text, '    parameter integer REQUEST_PIPELINE = 0,',
                '    parameter integer REQUEST_PIPELINE = 0,\n    parameter integer LOOP_BUFFER_LINES = 0,')
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer ICACHE_FAST_HIT = 1,',
                '    parameter integer ICACHE_LOOP_LINES = 0,\n    parameter integer ICACHE_FAST_HIT = 1,')
    text = once(text, '.LOCAL_RESPONSE_READY(ICACHE_LOCAL_RESPONSE_READY), .REQUEST_PIPELINE(1),',
                '.LOCAL_RESPONSE_READY(ICACHE_LOCAL_RESPONSE_READY), .REQUEST_PIPELINE(1),\n        .LOOP_BUFFER_LINES(ICACHE_LOOP_LINES),')
    assert blocks(text) == blocks((PARENT / name).read_text(encoding='utf-8'))
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer ICACHE_LOCAL_RESPONSE_READY = 1,',
                '    parameter integer ICACHE_LOOP_LINES = 16,\n    parameter integer ICACHE_LOCAL_RESPONSE_READY = 1,')
    text = once(text, '.ICACHE_MSHRS(ICACHE_MSHRS),',
                '.ICACHE_LOOP_LINES(ICACHE_LOOP_LINES), .ICACHE_MSHRS(ICACHE_MSHRS),')
    changes[name] = text
    for name in pm['source_sha256']:
        dest = TARGET / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, dest)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(pm)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
                  parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT / 'candidate.json'),
                  changed_from_parent_files=list(changes),
                  source_sha256={n: sha(TARGET / n) for n in pm['source_sha256']},
                  preparation_script_sha256=sha(Path(__file__)))
    record['parameter_overrides'] = dict(pm['parameter_overrides'], ICACHE_LOOP_LINES=16)
    record['enabled_profile'] = dict(pm['enabled_profile'], ICACHE_LOOP_LINES=16,
                                    instruction_filter_direct_index_bits=4,
                                    filter_warm_hit_request_to_response_edges=1,
                                    primary_warm_hit_request_to_response_edges=2)
    record['implemented_changes'] = list(pm['implemented_changes']) + [
        'Add 16-line direct-mapped instruction filter with registered one-edge hits, primary miss identity, unchanged primary cache and epoch/backpressure handling.'
    ]
    state_bits = 16 * (24 + 128 + 1) + (32 + 4 + 128) + (32 + 4) + 2
    record['material_gain_evidence'] = dict(pm['material_gain_evidence'],
                                          instruction_line_filter_declared_state_bits=state_bits,
                                          warm_hit_frontend_interval_edges_before=2,
                                          warm_hit_frontend_interval_edges_after=1,
                                          warm_hit_effective_bandwidth_ratio=2,
                                          filter_miss_can_add_backpressure_bubble=False)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_PROTOCOL_REVIEW_UNTESTED_NOT_FULL_CORE_PROOF', candidate=str(TARGET),
                 candidate_sha256=sha(TARGET / 'candidate.json'), parent_sha256=sha(PARENT / 'candidate.json'),
                 changed_files=list(changes), primary_body_unchanged_after_port_renames=True,
                 new_declared_state_bits=state_bits, tests_started=False, adopted=False,
                 source_argument=[
                     'Primary I-cache body including SRAM, MSHRs, prefetch, epoch checks and response holding is exactly unchanged after reversing interface renames.',
                     'L0 hit data is captured in a response owner on request acceptance; response validity does not depend combinationally on the new request.',
                     'At most one live primary miss is accepted; full PC and epoch identity qualify publishing. Unexpected/stale primary responses drain.',
                     'A held live response blocks new requests until accepted. A consumed response can accept the next request on the same edge.',
                     'Fast and primary live response ownership is mutually exclusive: primary acceptance clears the consumed fast response; fast acceptance retires or supersedes the primary miss.',
                     'Reset invalidates all line and transaction valid bits. Redirects invalidate transaction epochs; instruction bytes survive as in the primary cache.',
                     'Only accepted, matching, non-error primary responses fill rows. Error and full response payload pass unchanged on misses.',
                     'Six official performance programs are instruction-immutable; their loops exhibit repeated lines. Actual hit fraction, IPC, area and Fmax are not measured.',
                     'Source capacity is 16 lines of tag/data/valid plus response/miss owners, not an ASAP7 area estimate.',
                     'Standalone default LOOP_BUFFER_LINES=0 reconnects the original primary interface without the filter.'
                 ])
    write(BASE / 'A12_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'new_declared_state_bits', 'tests_started')})


if __name__ == '__main__':
    main()
