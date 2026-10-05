"""Replace redundant full-line instruction muxes with each bank's own words."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A53_predictor_prefix_query_history'
TARGET = BASE / 'A54_predictor_bank_local_instruction_read'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A54_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/predictor/rv32_banked_predictor.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer PREFIX_QUERY_HISTORY = 0,',
        '    parameter integer PREFIX_QUERY_HISTORY = 0,\n    parameter integer BANK_LOCAL_INSTRUCTION_READ = 0,')
    text = once(text, '''            rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(4),.INDEX_WIDTH(3)) instruction_query (
                .rows_i(query_line_i),.index_i(word_index),.value_o(inst));''',
        '''            if(BANK_LOCAL_INSTRUCTION_READ!=0 && FE_WIDTH==4) begin:g_fixed_instruction
                // word_index[1:0] is this bank, even on a cross-line query.
                // Preserve the old padded-array zero on invalid words4..6.
                wire [1:0] within_line_views;
                rv32_frequency_control_tree #(.LEAVES(2)) within_line_tree (
                    .signal_i(!word_index[2]),.views_o(within_line_views));
                for(genvar part=0;part<2;part=part+1) begin:g_half_word
                    assign inst[part*16 +: 16]=query_line_i[bank*32+part*16 +: 16] &
                        {16{within_line_views[part]}};
                end
            end else if(BANK_LOCAL_INSTRUCTION_READ!=0 && FE_WIDTH==2) begin:g_two_instruction_words
                wire [63:0] bank_instruction_rows={query_line_i[(bank+2)*32 +: 32],
                    query_line_i[bank*32 +: 32]};
                // Its parity is fixed. The retained high index includes the
                // cross-line bit and padded rows therefore still return zero.
                rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(2),.INDEX_WIDTH(2)) instruction_query (
                    .rows_i(bank_instruction_rows),.index_i(word_index[2:1]),.value_o(inst));
            end else begin:g_original_instruction_query
                rv32_frequency_array_read #(.WIDTH(32),.ENTRIES(4),.INDEX_WIDTH(3)) instruction_query (
                    .rows_i(query_line_i),.index_i(word_index),.value_o(inst));
            end''')
    # Everything downstream of the instruction read, including predictions,
    # query-history choice, saved metadata and feedback, remains the parent.
    marker = '            assign bank_query_packets[bank*40 +: 40]='
    assert text[text.index(marker):] == original[original.index(marker):]
    assert len(re.findall(r'^\s*reg\s+', text, re.M)) == len(re.findall(r'^\s*reg\s+', original, re.M))
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_PREFIX_QUERY_HISTORY = 0,',
        '    parameter integer PREDICTOR_PREFIX_QUERY_HISTORY = 0,\n    parameter integer PREDICTOR_BANK_LOCAL_INSTRUCTION_READ = 0,')
    text = once(text, '.PREFIX_QUERY_HISTORY(PREDICTOR_PREFIX_QUERY_HISTORY && !SERIAL_BACKEND),',
        '.PREFIX_QUERY_HISTORY(PREDICTOR_PREFIX_QUERY_HISTORY && !SERIAL_BACKEND),\n                .BANK_LOCAL_INSTRUCTION_READ(PREDICTOR_BANK_LOCAL_INSTRUCTION_READ),')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_PREFIX_QUERY_HISTORY = 1,',
        '    parameter integer PREDICTOR_PREFIX_QUERY_HISTORY = 1,\n    parameter integer PREDICTOR_BANK_LOCAL_INSTRUCTION_READ = 1,')
    text = once(text, '.PREDICTOR_PREFIX_QUERY_HISTORY(PREDICTOR_PREFIX_QUERY_HISTORY),',
        '.PREDICTOR_PREFIX_QUERY_HISTORY(PREDICTOR_PREFIX_QUERY_HISTORY), .PREDICTOR_BANK_LOCAL_INSTRUCTION_READ(PREDICTOR_BANK_LOCAL_INSTRUCTION_READ),')
    changes[name] = text
    for name in parent['source_sha256']:
        dst = TARGET / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, dst)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT / 'candidate.json'),
        changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), tests_started=False, adopted=False)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], PREDICTOR_BANK_LOCAL_INSTRUCTION_READ=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], predictor_bank_local_instruction_read=True,
        predictor_internal_instruction_word_exact_including_invalid=True,
        bank_local_instruction_added_ff_bits=0, bank_local_instruction_added_sram_bits=0,
        bank_local_instruction_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Read only the instruction words belonging to a predictor bank: FE4 uses its fixed word with bounded16-bit invalid-query zero masks, FE2 reads its two parity-matched words, FE1 retains the original4-word read. Preserve the exact instruction value even on cross-line invalid queries; no query/history/training or pipeline contract change.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        full_line_instruction_mux_removed_from_fe4_predictor_banks=True,
        late_pc_low_bits_do_not_select_fe4_instruction_words=True,
        bank_local_instruction_mapped_cost_and_gain_unknown=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_PREDICTOR_BANK_LOCAL_INSTRUCTION_READ_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
        source_arguments=[
            'For bank mask M=FE_WIDTH-1, offset=(B-(W&M))&M and word_index=W+offset. Thus word_index&M=B. This identity holds for FE1/2/4 and every start word; the full3-bit word_index and its cross-line validity are retained.',
            'For FE4 a valid word_index is exactly B, so the old4-word read equals fixed line word B. When word_index[2]=1 the old INDEX_WIDTH3 array is in its padded zero rows; the new two16-bit masks also return exactly0. Unlike relaxing an invalid input contract, this preserves the internal instruction wire for invalid queries too.',
            'For FE2 the word parity is B. Its word lies in the fixed pair B,B+2; the retained word_index[2:1] chooses that pair and preserves padded zero rows for cross-line indexes. FE1 and mode0 retain the original read module.',
            'Four FE4 generic32-bit4-row instruction reads become fixed data wiring plus per-bank validity masks. Their dynamic low-bit address selection, row comparisons and OR combination are absent from the enabled source. This removes a late-PC selection dependency before branch/JALR decode and target formation, but exact synthesis pruning, buffering, total area and Fmax are unmeasured.',
            'All source after the instruction read is byte-exact to A53: queried histories, predictions, bank/lane routing, exact saved index, training, checkpoint update, recovery and counters. No FF/SRAM/pipeline edge is added and no architecture scope is changed.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. Future meaningful coverage includes every FE1/2/4 bank/start word, valid and cross-line invalid queries, random line values, all predictor modes/options, target/history metadata and optional fallback.'
        ])
    write(BASE / 'A54_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
