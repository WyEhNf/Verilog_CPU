"""Prepare parallel per-instruction gshare history; do not execute HDL."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A52_predictor_bank_pc_carry_select'
TARGET = BASE / 'A53_predictor_prefix_query_history'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A53_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/predictor/rv32_banked_predictor.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer BANK_PC_CARRY_SELECT = 0,',
        '    parameter integer BANK_PC_CARRY_SELECT = 0,\n    parameter integer PREFIX_QUERY_HISTORY = 0,')
    text = once(text, '            wire [31:0] inst;', '''            wire [7:0] bank_query_history;
            if(PREFIX_QUERY_HISTORY!=0 && DIRECT_BRANCH_TARGET==2 && FE_WIDTH>1) begin:g_prefix_history
                wire [2:0] preceding_conditions;
                for(genvar word=0;word<3;word=word+1) begin:g_preceding_word
                    // A later accepted instruction implies every earlier
                    // conditional in this prefix was predicted not taken.
                    // Inspect fixed line words, never another table's output.
                    assign preceding_conditions[word]=
                        query_line_i[word*32 +: 7]==7'b1100011 &&
                        query_pc_i[3:2]<=word && word_index>word && !word_index[2];
                end
                wire [1:0] preceding_count={
                    (preceding_conditions[0]&preceding_conditions[1]) |
                    (preceding_conditions[0]&preceding_conditions[2]) |
                    (preceding_conditions[1]&preceding_conditions[2]),
                    preceding_conditions[0]^preceding_conditions[1]^preceding_conditions[2]};
                assign bank_query_history=
                    ({8{preceding_count==2'd0}} & (global_history & HISTORY_MASK)) |
                    ({8{preceding_count==2'd1}} & ((global_history<<1) & HISTORY_MASK)) |
                    ({8{preceding_count==2'd2}} & ((global_history<<2) & HISTORY_MASK)) |
                    ({8{preceding_count==2'd3}} & ((global_history<<3) & HISTORY_MASK));
            end else begin:g_original_history
                assign bank_query_history=global_history;
            end
            wire [31:0] inst;''')
    text = once(text, '.query_history_i(global_history),', '.query_history_i(bank_query_history),')
    text = once(text, '''    // Parallel queries share the pre-bundle history and disjoint PC banks.
    // Save that exact table index, plus a per-instruction program-order
    // history checkpoint. Only accepted prefix instructions advance history.''',
        '''    // Save the exact index used by each parallel query, plus its
    // program-order history checkpoint. Optional prefix query history is
    // formed independently of directions; accepted-prefix update stays here.''')
    # Training/arbitration is unchanged. The checkpoint, accepted-history
    # update, repair priority, and counters remain byte-exact.
    marker = '    always @* begin\n        history_after_bundle = global_history;'
    assert text[text.index(marker):] == original[original.index(marker):]
    marker = '            wire update_valid,update_taken,update_pred_taken;'
    before_predictor = '            rv32_branch_predictor #('
    assert text[text.index(marker):text.index(before_predictor)] == original[original.index(marker):original.index(before_predictor)]
    assert len(re.findall(r'^\s*reg\s+', text, re.M)) == len(re.findall(r'^\s*reg\s+', original, re.M))
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_BANK_PC_CARRY_SELECT = 0,',
        '    parameter integer PREDICTOR_BANK_PC_CARRY_SELECT = 0,\n    parameter integer PREDICTOR_PREFIX_QUERY_HISTORY = 0,')
    text = once(text, '.BANK_PC_CARRY_SELECT(PREDICTOR_BANK_PC_CARRY_SELECT),',
        '.BANK_PC_CARRY_SELECT(PREDICTOR_BANK_PC_CARRY_SELECT),\n                .PREFIX_QUERY_HISTORY(PREDICTOR_PREFIX_QUERY_HISTORY && !SERIAL_BACKEND),')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_BANK_PC_CARRY_SELECT = 1,',
        '    parameter integer PREDICTOR_BANK_PC_CARRY_SELECT = 1,\n    parameter integer PREDICTOR_PREFIX_QUERY_HISTORY = 1,')
    text = once(text, '.PREDICTOR_BANK_PC_CARRY_SELECT(PREDICTOR_BANK_PC_CARRY_SELECT),',
        '.PREDICTOR_BANK_PC_CARRY_SELECT(PREDICTOR_BANK_PC_CARRY_SELECT), .PREDICTOR_PREFIX_QUERY_HISTORY(PREDICTOR_PREFIX_QUERY_HISTORY),')
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
    record['parameter_overrides'] = dict(parent['parameter_overrides'], PREDICTOR_PREFIX_QUERY_HISTORY=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], predictor_prefix_query_history=True,
        accepted_branch_query_uses_its_program_order_history=True,
        prefix_history_added_ff_bits=0, prefix_history_added_sram_bits=0,
        prefix_history_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Form per-instruction gshare query history by counting earlier conditional opcodes in the current line prefix and shifting pre-bundle history by that count with zero inserted bits. No earlier direction-table result feeds later table queries. Save the actual queried index through unchanged metadata/feedback ownership; accepted-history advancement and recovery stay byte-exact.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        gshare_index_history_matches_accepted_instruction_checkpoint=True,
        prior_direction_results_not_serialized_into_query_index=True,
        prefix_history_ipc_frequency_and_area_gain_unknown=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_PREDICTOR_PREFIX_QUERY_HISTORY_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
        source_arguments=[
            'An accepted later instruction is preceded only by accepted instructions with effective prediction not taken. In cpu_core RAS overrides only a return/JALR, not a conditional branch. Thus every preceding conditional direction is zero, so its pre-instruction checkpoint equals (global_history << preceding_conditional_count) & HISTORY_MASK. This is a program-order source argument, not measured predictor accuracy.',
            'Fixed line-word opcode reads match the child predictor branch classification exactly. The mask includes only words at/after the current start and before this bank word. word_index[2] excludes cross-line invalid queries; only words0..2 can precede a valid current word. Three flags use parity and pairwise majority to form a2-bit population count without a dependent sum chain.',
            'Each shift is constant and selected using that count. No direction, BHT/chooser output, RAS output, accepted-history combinational loop, or previous bank query feeds another query. New opcode/count/shift selection does add a combinational path before gshare lookup; area and Fmax must be measured for the cumulative candidate.',
            'The exact query index still comes from pred_training_index_o and passes through the existing16-bit per-instruction metadata, ROB ownership, full feedback packet and same-bank priority. Feedback/history checkpoint advancement/recovery/counter source remains byte-exact. Bimodal/chooser PC indexes and their training are unchanged. Predictions and raw gshare metadata can change in this enabled mode, including unused queries beyond a terminating branch; do not claim all prediction buses identical.',
            'Mode0, DIRECT_BRANCH_TARGET!=2 and FE1 retain the original shared-history query. Core gates the option off for SERIAL_BACKEND. No FF/SRAM/pipeline edge is added, and no ISA/commit/MMIO/M-extension scope is removed.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. Meaningful future coverage includes FE1/2/4, each line start, zero/one/two/three preceding conditional branches, taken-prefix termination, RAS/JALR/sentinel/error/backpressure, exact query/training indexes, simultaneous feedback and recovery, and history widths/fallback.'
        ])
    write(BASE / 'A53_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
