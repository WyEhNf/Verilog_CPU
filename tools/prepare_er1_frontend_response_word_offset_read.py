"""Select constant-shifted line words with the unmodified start index."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A58_predictor_direct_bank_word_index'
TARGET = BASE / 'A59_frontend_response_word_offset_read'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A59_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/frontend/rv32_fetch_frontend.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer PARALLEL_BUNDLE_CONTROL = 0,',
        '    parameter integer PARALLEL_BUNDLE_CONTROL = 0,\n    parameter integer RESPONSE_WORD_OFFSET_READ = 0,')
    text = once(text, '''            rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(4),.INDEX_WIDTH(3)) instruction_word_reader (
                .rows_i(if_resp_line_data_i),.index_i(index),.value_o(response_words[response_lane*32 +: 32]));''',
        '''            if(RESPONSE_WORD_OFFSET_READ!=0) begin:g_offset_word_read
                // Shift is constant wiring. Unavailable trailing words are0.
                wire [127:0] lane_words=if_resp_line_data_i>>(response_lane*32);
                rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(4),.INDEX_WIDTH(2)) instruction_word_reader (
                    .rows_i(lane_words),.index_i(response_base_pc[3:2]),
                    .value_o(response_words[response_lane*32 +: 32]));
            end else begin:g_original_word_read
                rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(4),.INDEX_WIDTH(3)) instruction_word_reader (
                    .rows_i(if_resp_line_data_i),.index_i(index),.value_o(response_words[response_lane*32 +: 32]));
            end''')
    marker = '            if(PARALLEL_BUNDLE_CONTROL==0) begin:g_legacy_next_pc'
    assert text[text.index(marker):] == original[original.index(marker):]
    assert text.count('always @(posedge clk_i)') == original.count('always @(posedge clk_i)')
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer FRONTEND_RAS_PREDECODE = 0,',
        '    parameter integer FRONTEND_RAS_PREDECODE = 0,\n    parameter integer FRONTEND_RESPONSE_WORD_OFFSET_READ = 0,')
    text = once(text, '.PARALLEL_BUNDLE_CONTROL(FRONTEND_PARALLEL_BUNDLE_CONTROL),',
        '.PARALLEL_BUNDLE_CONTROL(FRONTEND_PARALLEL_BUNDLE_CONTROL),\n        .RESPONSE_WORD_OFFSET_READ(FRONTEND_RESPONSE_WORD_OFFSET_READ),')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer FRONTEND_RAS_PREDECODE = 2,',
        '    parameter integer FRONTEND_RAS_PREDECODE = 2,\n    parameter integer FRONTEND_RESPONSE_WORD_OFFSET_READ = 1,')
    text = once(text, '.FRONTEND_RAS_PREDECODE(FRONTEND_RAS_PREDECODE),',
        '.FRONTEND_RAS_PREDECODE(FRONTEND_RAS_PREDECODE), .FRONTEND_RESPONSE_WORD_OFFSET_READ(FRONTEND_RESPONSE_WORD_OFFSET_READ),')
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
    record['parameter_overrides'] = dict(parent['parameter_overrides'], FRONTEND_RESPONSE_WORD_OFFSET_READ=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], frontend_response_word_offset_read=True,
        response_word_start_plus_lane_dependency_removed=True,
        response_word_offset_added_ff_bits=0, response_word_offset_added_sram_bits=0,
        response_word_offset_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'For frontend lane L, statically shift the128-bit response line right by32*L and select its32-bit word at the unmodified2-bit start W. Equal to the old padded index W+L including beyond-line zero; remove start+lane arithmetic and third index bit from response instruction selection without changing packets or acceptance.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        response_word_start_plus_lane_dependency_removed=True,
        response_word_offset_mapped_gain_unknown=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_FRONTEND_RESPONSE_WORD_OFFSET_READ_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
        source_arguments=[
            'For unsigned128-bit line F,2-bit start W and constant lane L0..3, selecting word W from F>>(32*L) equals (F>>(32*(W+L)))&0xffffffff. If W+L>=4 both original INDEX_WIDTH3 padded array and the new constant-shifted vector return0. Full internal response_words, including unused later lanes, are preserved.',
            'The right shift is compile-time wiring, not a dynamic barrel shifter. The enabled read keeps WIDTH32 and ENTRIES4 but changes INDEX_WIDTH3 to2 and removes the W+L arithmetic dependency. Padding/corresponding OR leaves and control domains may prune differently; no gate-count, area or frequency saving is claimed as measured.',
            'Response PC, all prediction metadata, sentinel/freeze classification, bypass/public packets, queue acceptance/capacity/counts, epochs/chained requests and state owners are unchanged. All source after the response-word reader is byte-exact parent. The same original line identity/validity authority remains.',
            'Frontend/core default0 retain the original read; course top1. FE1/2/4 each use their original lane count and line boundaries. No FF/SRAM/pipeline edge or ISA/retirement scope is added or removed.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. Prepared independently of A55R2. Future coverage includes FE1/2/4/all starts/lanes, invalid-word zero values, random line data, bypass/queue/public packet agreement, sentinel/predicted-taken/error/backpressure/epoch/redirect cases and option0 fallback.'
        ])
    write(BASE / 'A59_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
