"""Use constant start-word bounds in response bypass and parallel bundle control."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A59_frontend_response_word_offset_read'
TARGET = BASE / 'A60_frontend_direct_word_bounds'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A60_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/frontend/rv32_fetch_frontend.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer RESPONSE_WORD_OFFSET_READ = 0,',
        '    parameter integer RESPONSE_WORD_OFFSET_READ = 0,\n    parameter integer DIRECT_WORD_BOUNDS = 0,')
    text = once(text, '''            assign bypass_lane_valid[bypass_lane]=response_bypass && bypass_prefix[bypass_lane] &&
                word_number<3'd4;''',
        '''            assign bypass_lane_valid[bypass_lane]=response_bypass && bypass_prefix[bypass_lane] &&
                ((DIRECT_WORD_BOUNDS!=0) ?
                    (response_base_pc[3:2]<=(3-bypass_lane)) : (word_number<3'd4));''')
    text = once(text, '.LEGACY_SENTINEL_HALT(LEGACY_SENTINEL_HALT)) control (',
        '.LEGACY_SENTINEL_HALT(LEGACY_SENTINEL_HALT),.DIRECT_WORD_BOUNDS(DIRECT_WORD_BOUNDS)) control (')
    text = once(text, '    parameter integer FE_WIDTH=4,FQ_DEPTH=16,LEGACY_SENTINEL_HALT=0\n',
        '    parameter integer FE_WIDTH=4,FQ_DEPTH=16,LEGACY_SENTINEL_HALT=0,\n    parameter integer DIRECT_WORD_BOUNDS=0\n')
    text = once(text, "        wire [2:0] word_number={1'b0,base_pc_i[3:2]}+3'(lane);",
        '''        wire [2:0] word_number={1'b0,base_pc_i[3:2]}+3'(lane);
        wire word_in_line,word_is_last;
        if(DIRECT_WORD_BOUNDS!=0) begin:g_direct_bound
            localparam [1:0] LAST_START=3-lane;
            assign word_in_line=base_pc_i[3:2]<=LAST_START;
            assign word_is_last=base_pc_i[3:2]==LAST_START;
        end else begin:g_original_bound
            assign word_in_line=word_number<3'd4;
            assign word_is_last=word_number==3'd3;
        end''')
    text = once(text, '''        assign lane_live[lane]=!response_error_i && prior_prefix_live && word_number<3'd4;
        wire ends_bundle=lane_live[lane] &&
            (stops[lane] || (lane==FE_WIDTH-1) || word_number==3'd3);''',
        '''        assign lane_live[lane]=!response_error_i && prior_prefix_live && word_in_line;
        wire ends_bundle=lane_live[lane] &&
            (stops[lane] || (lane==FE_WIDTH-1) || word_is_last);''')
    # The main frontend state/update/accept block is not rewritten. The helper
    # event packets, capacity comparisons and PC selector are also unchanged.
    a = '    assign current_epoch_o = epoch_reg;'
    b = '// Same accepted prefix as bundle_count, without count encoding/decoding on'
    assert text[text.index(a):text.index(b)] == original[original.index(a):original.index(b)]
    marker = '        // An error has no bundle. Otherwise exactly one live lane ends it.'
    assert text[text.index(marker):] == original[original.index(marker):]
    assert text.count('always @(posedge clk_i)') == original.count('always @(posedge clk_i)')
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer FRONTEND_RESPONSE_WORD_OFFSET_READ = 0,',
        '    parameter integer FRONTEND_RESPONSE_WORD_OFFSET_READ = 0,\n    parameter integer FRONTEND_DIRECT_WORD_BOUNDS = 0,')
    text = once(text, '.RESPONSE_WORD_OFFSET_READ(FRONTEND_RESPONSE_WORD_OFFSET_READ),',
        '.RESPONSE_WORD_OFFSET_READ(FRONTEND_RESPONSE_WORD_OFFSET_READ),\n        .DIRECT_WORD_BOUNDS(FRONTEND_DIRECT_WORD_BOUNDS),')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer FRONTEND_RESPONSE_WORD_OFFSET_READ = 1,',
        '    parameter integer FRONTEND_RESPONSE_WORD_OFFSET_READ = 1,\n    parameter integer FRONTEND_DIRECT_WORD_BOUNDS = 1,')
    text = once(text, '.FRONTEND_RESPONSE_WORD_OFFSET_READ(FRONTEND_RESPONSE_WORD_OFFSET_READ),',
        '.FRONTEND_RESPONSE_WORD_OFFSET_READ(FRONTEND_RESPONSE_WORD_OFFSET_READ), .FRONTEND_DIRECT_WORD_BOUNDS(FRONTEND_DIRECT_WORD_BOUNDS),')
    changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, destination)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT / 'candidate.json'),
        changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), tests_started=False, adopted=False)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], FRONTEND_DIRECT_WORD_BOUNDS=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], frontend_direct_word_bounds=True,
        frontend_lane_word_add_removed_from_bypass_and_parallel_control=True,
        direct_word_bounds_added_ff_bits=0, direct_word_bounds_added_sram_bits=0,
        direct_word_bounds_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Use W<=3-L for lane-in-line validity and W==3-L for the last line word in empty-FQ bypass and parallel bundle PC/capacity control. Replace start+lane addition/comparison on those controls; retain original prefix, error, queue/capacity and state-update logic, including legacy bundle_count enumeration.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        word_start_plus_lane_dependency_removed_from_bypass_and_parallel_control=True,
        direct_word_bounds_mapped_gain_unknown=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_FRONTEND_DIRECT_WORD_BOUNDS_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
        source_arguments=[
            'For binary2-bit start W and each constant lane L0..3, W+L<4 iff W<=3-L, and W+L==3 iff W==3-L. The original3-bit sum cannot overflow because its maximum is6. Direct comparisons against constant2-bit LAST_START therefore preserve every valid/invalid/last-word predicate in FE1/2/4.',
            'Only empty-FQ bypass lane-valid bounds and the parallel-control helper word bounds change. Prior-prefix stopping, predicted-taken/sentinel priority, response-error qualification, target versus sequential event data, queue capacity comparisons and no-dequeue-credit policy remain exact source.',
            'All main frontend code from public epoch outputs through state owners and queue-payload module is byte-exact. Legacy bundle_count/enq_count/deq_count enumeration and accept/redirect/stop/error/epoch/chained-request ownership remain unchanged. Helper source after lane_live/ends_bundle is byte-exact.',
            'Frontend/core/helper default0 preserve original arithmetic; course top1. PARALLEL_BUNDLE_CONTROL0 retains its old next-PC/count logic while the optional bypass bound can still use the equal direct comparison. No FF/SRAM/pipeline edge or architectural scope change.',
            'The enabled source removes start+lane addition from bypass validity and from parallel next-PC/capacity word qualification. Mapping may already simplify portions of the parent arithmetic; actual area, load, frequency and IPC are unknown. This is source algebra, not HDL equivalence.',
            'No HDL/lint/simulation/synthesis/STA/unit execution; A55R2 remains frozen on A55. Future coverage includes FE1/2/4/all starts/lanes/line endings, empty/full queue boundaries, sentinel/taken/error/backpressure/chained-request/reset/redirect cases and independent option fallbacks.'
        ])
    write(BASE / 'A60_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
