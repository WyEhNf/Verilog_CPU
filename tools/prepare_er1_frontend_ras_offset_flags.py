"""Remove late start+lane arithmetic from predecoded RAS flag selection."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A56_frontend_ras_predecode'
TARGET = BASE / 'A57_frontend_ras_offset_flags'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A57_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/cpu_core.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '            wire query_valid = if_resp_valid && (query_word_index < 3\'d4);',
        '''            wire query_valid = if_resp_valid && ((FRONTEND_RAS_PREDECODE==2) ?
                (response_base_pc[3:2]<=(3-predictor_lane)) : (query_word_index<3'd4));''')
    text = once(text, '''            if(FRONTEND_RAS_PREDECODE!=0) begin:g_predecoded_ras_query
                rv32_frequency_narrow_array_read #(.WIDTH(2),.ENTRIES(4),.INDEX_WIDTH(3)) flags_query (
                    .rows_i(ras_line_flags),.index_i(query_word_index),.value_o(query_ras_flags));''',
        '''            if(FRONTEND_RAS_PREDECODE==2) begin:g_offset_ras_query
                // Constant lane shift pads the unavailable final words with00.
                // Dynamic selection now uses only the original start word.
                wire [7:0] lane_flag_rows=ras_line_flags>>(predictor_lane*2);
                rv32_frequency_narrow_array_read #(.WIDTH(2),.ENTRIES(4),.INDEX_WIDTH(2)) flags_query (
                    .rows_i(lane_flag_rows),.index_i(response_base_pc[3:2]),.value_o(query_ras_flags));
            end else if(FRONTEND_RAS_PREDECODE!=0) begin:g_predecoded_ras_query
                rv32_frequency_narrow_array_read #(.WIDTH(2),.ENTRIES(4),.INDEX_WIDTH(3)) flags_query (
                    .rows_i(ras_line_flags),.index_i(query_word_index),.value_o(query_ras_flags));''')
    marker = '            assign ras_query_flags[predictor_lane*2 +: 2]='
    assert text[text.index(marker):] == original[original.index(marker):]
    assert text.count('always @(posedge clk)') == original.count('always @(posedge clk)')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer FRONTEND_RAS_PREDECODE = 1,',
        '    parameter integer FRONTEND_RAS_PREDECODE = 2,')
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
    record['parameter_overrides'] = dict(parent['parameter_overrides'], FRONTEND_RAS_PREDECODE=2)
    record['enabled_profile'] = dict(parent['enabled_profile'], frontend_ras_offset_flags=True,
        ras_start_plus_lane_removed_from_flag_selection=True,
        ras_offset_flags_added_ff_bits=0, ras_offset_flags_added_sram_bits=0, ras_offset_flags_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'For lane L, statically shift the8-bit fixed-word RAS flag vector right by2*L and query with unmodified2-bit start W. This equals the old padded flag lookup at W+L, including beyond-line00; replace RAS query validity W+L<4 with W<=3-L. No late lane addition enters flag selection or validity.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        ras_start_plus_lane_dependency_removed_from_flags_and_validity=True,
        ras_offset_flags_mapped_area_frequency_gain_unknown=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_FRONTEND_RAS_OFFSET_FLAGS_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
        source_arguments=[
            'Let F be the unsigned8-bit concatenation of four2-bit flags, W the2-bit start and L a constant lane0..3. The selected flag at index W of F>>(2*L) is (F>>(2*(W+L)))&3. If W+L>=4 the original A56 padded lookup and constant-shifted vector both produce00. No alignment or history assumption is added.',
            'For W,L in0..3, W+L<4 iff W<=3-L. The mode2 query_valid uses this exact constant-bound comparison; if_resp_valid and ENABLE_PREDICTOR/ras_count override gates are unchanged. No late start+lane adder enters either RAS flag selection or its query-valid check.',
            'All source after the per-lane flag selection is byte-exact A56: call/return classification, effective prediction outputs, accepted prefix priority, stack addresses/owners/pointer/count, frontend/decode/backend/retirement logic. FE1/2/4 retain their original accepted line boundaries.',
            'Mode0 retains the original32-bit read; mode1 retains A56 narrow3-bit word-index lookup; course top now uses mode2. No FF/SRAM/pipeline edge is added. Query data width is2 and index width2 instead of A56 index width3. Synthesis pruning, load, area and Fmax/IPC are unknown.',
            'No HDL/lint/simulation/synthesis/STA/unit execution; A55R2 remains on the older immutable source. Future coverage includes FE1/2/4, every start/lane including out-of-line flags, all call/return predicate and stack/prefix/backpressure/reset/redirect cases, and mode0/1/2 fallback.'
        ])
    write(BASE / 'A57_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
