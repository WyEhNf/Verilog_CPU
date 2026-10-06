"""Resolve bank-word identity algebraically before predictor PC/validity logic."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A57_frontend_ras_offset_flags'
TARGET = BASE / 'A58_predictor_direct_bank_word_index'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A58_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/predictor/rv32_banked_predictor.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer BANK_LOCAL_PREFIX_HISTORY = 0,',
        '    parameter integer BANK_LOCAL_PREFIX_HISTORY = 0,\n    parameter integer BANK_DIRECT_WORD_INDEX = 0,')
    text = once(text, "            wire [2:0] word_index = {1'b0, query_pc_i[3:2]} + {1'b0, offset};",
        '''            wire [2:0] word_index;
            if(BANK_DIRECT_WORD_INDEX!=0 && FE_WIDTH==4) begin:g_direct_four_word
                // W+((B-W)&3) is B, or B+4 when this bank precedes W.
                assign word_index={query_pc_i[3:2]>BANK_NUMBER,BANK_NUMBER};
            end else if(BANK_DIRECT_WORD_INDEX!=0 && FE_WIDTH==2) begin:g_direct_two_word
                if(bank==0) begin:g_even_bank
                    // Round W up to the next even word, including invalid4.
                    assign word_index={query_pc_i[3]&query_pc_i[2],
                        query_pc_i[3]^query_pc_i[2],1'b0};
                end else begin:g_odd_bank
                    // The next odd word is W with its low bit set.
                    assign word_index={1'b0,query_pc_i[3],1'b1};
                end
            end else begin:g_original_word_index
                assign word_index={1'b0,query_pc_i[3:2]}+{1'b0,offset};
            end''')
    marker = '            wire [31:0] pc;'
    assert text[text.index(marker):] == original[original.index(marker):]
    assert text.count('always @(posedge clk_i)') == original.count('always @(posedge clk_i)')
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_BANK_LOCAL_PREFIX_HISTORY = 0,',
        '    parameter integer PREDICTOR_BANK_LOCAL_PREFIX_HISTORY = 0,\n    parameter integer PREDICTOR_BANK_DIRECT_WORD_INDEX = 0,')
    text = once(text, '.BANK_LOCAL_PREFIX_HISTORY(PREDICTOR_BANK_LOCAL_PREFIX_HISTORY),',
        '.BANK_LOCAL_PREFIX_HISTORY(PREDICTOR_BANK_LOCAL_PREFIX_HISTORY),\n                .BANK_DIRECT_WORD_INDEX(PREDICTOR_BANK_DIRECT_WORD_INDEX),')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_BANK_LOCAL_PREFIX_HISTORY = 1,',
        '    parameter integer PREDICTOR_BANK_LOCAL_PREFIX_HISTORY = 1,\n    parameter integer PREDICTOR_BANK_DIRECT_WORD_INDEX = 1,')
    text = once(text, '.PREDICTOR_BANK_LOCAL_PREFIX_HISTORY(PREDICTOR_BANK_LOCAL_PREFIX_HISTORY),',
        '.PREDICTOR_BANK_LOCAL_PREFIX_HISTORY(PREDICTOR_BANK_LOCAL_PREFIX_HISTORY), .PREDICTOR_BANK_DIRECT_WORD_INDEX(PREDICTOR_BANK_DIRECT_WORD_INDEX),')
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
    record['parameter_overrides'] = dict(parent['parameter_overrides'], PREDICTOR_BANK_DIRECT_WORD_INDEX=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], predictor_direct_bank_word_index=True,
        exact_three_bit_word_index_preserved=True, bank_word_index_added_ff_bits=0,
        bank_word_index_added_sram_bits=0, bank_word_index_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Replace bank-offset subtraction followed by word-index addition with direct identities: FE4 word_index={W>B,B}; FE2 even bank rounds W up to an even word and odd bank sets its low bit. Preserve full3-bit invalid/wrapped word index, carry-selected full bank PC, instruction and history query values; FE1/mode0 retain original arithmetic.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        bank_offset_subtraction_then_word_add_dependency_removed=True,
        direct_bank_word_index_mapped_gain_unknown=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_PREDICTOR_DIRECT_BANK_WORD_INDEX_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
        source_arguments=[
            'For FE4 and W,B in0..3, O=(B-W)&3. If B>=W then W+O=B; otherwise W+O=B+4. Thus the original3-bit word_index is exactly{W>B,B}. Its low bits are compile-time bank constants, and its high bit is a2-bit comparison against that constant rather than a subtraction/addition chain.',
            'For FE2 even bank0, O=W[0] and W+O rounds W up to an even word. Its high bit is W[1]&W[0], middle bit W[1]^W[0], low bit0. For odd bank1, O=!W[0] and W+O equals{0,W[1],1}. The invalid even result at W3 is4 and remains invalid; the maximum4 fits the old3-bit value.',
            'All source from PC formation onward is byte-exact to A57. The full word-index value is equal, so current/next-line high selection, instruction padding, query validity, optional prefix masks, exact history/index metadata, feedback and training behavior are unchanged. BANK_PC_CARRY_SELECT0 still forms PC using the retained original offset, preserving all option combinations.',
            'FE1 and mode0 retain original subtraction/addition. Core/banked defaults0 and course top1. No alignment restriction, change to invalid bank diagnostics, FF/SRAM/pipeline edge or architecture scope is added. This is source algebra, not HDL equivalence.',
            'The source removes offset subtraction/addition from the enabled FE4/FE2 word-index path, including the FE4 full-PC carry control and instruction/query-valid gates. Existing mapping might already simplify parts of it; actual combinational cost, fanout and Fmax/IPC are unmeasured.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. Prepared independently of A55R2. Future coverage includes FE1/2/4 and each bank/start word, valid/invalid queries, fullPC wrap/unaligned input, carry-select on/off, local-word/prefix options and mode0 fallback.'
        ])
    write(BASE / 'A58_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
