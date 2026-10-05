"""Split bank-PC word offset and late line carry, retaining exact full address."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A51_predictor_narrow_direction_read'
TARGET = BASE / 'A52_predictor_bank_pc_carry_select'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A52_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/predictor/rv32_banked_predictor.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer NARROW_DIRECTION_READ = 0,',
        '    parameter integer NARROW_DIRECTION_READ = 0,\n    parameter integer BANK_PC_CARRY_SELECT = 0,')
    text = once(text, '    wire [1:0] feedback_bank = feedback_pc_i[3:2] & BANK_MASK;',
        '''    wire [1:0] feedback_bank = feedback_pc_i[3:2] & BANK_MASK;
    // Compute this constant increment before the bank-dependent offset arrives.
    // Truncation preserves modulo-2^32 PC wrap after reattaching the low bits.
    wire [27:0] next_line_high=query_pc_i[31:4]+28'd1;''')
    text = once(text, "            wire [31:0] pc = query_pc_i + {28'd0, offset, 2'b00};",
        '''            wire [31:0] pc;
            if(BANK_PC_CARRY_SELECT!=0 && FE_WIDTH>1) begin:g_carry_select_pc
                wire [1:0] line_carry_views;
                rv32_frequency_control_tree #(.LEAVES(2)) line_carry_tree (
                    .signal_i(word_index[2]),.views_o(line_carry_views));
                assign pc[1:0]=query_pc_i[1:0];
                assign pc[3:2]=word_index[1:0];
                for(genvar pc_word=0;pc_word<2;pc_word=pc_word+1) begin:g_high_word
                    localparam integer LOW=pc_word*16;
                    localparam integer BITS=(28-LOW>=16)?16:28-LOW;
                    assign pc[4+LOW +: BITS]=line_carry_views[pc_word]?
                        next_line_high[LOW +: BITS]:query_pc_i[4+LOW +: BITS];
                end
            end else begin:g_original_pc
                assign pc=query_pc_i+{28'd0,offset,2'b00};
            end''')
    # The unchanged word_index still gates instruction/query validity. All
    # feedback, query packet routing, metadata/history and counters stay exact.
    marker = '            wire [31:0] inst;'
    assert text[text.index(marker):] == original[original.index(marker):]
    assert len(re.findall(r'^\s*reg\s+', text, re.M)) == len(re.findall(r'^\s*reg\s+', original, re.M))
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_NARROW_DIRECTION_READ = 0,',
        '    parameter integer PREDICTOR_NARROW_DIRECTION_READ = 0,\n    parameter integer PREDICTOR_BANK_PC_CARRY_SELECT = 0,')
    text = once(text, '.NARROW_DIRECTION_READ(PREDICTOR_NARROW_DIRECTION_READ),',
        '.NARROW_DIRECTION_READ(PREDICTOR_NARROW_DIRECTION_READ),\n                .BANK_PC_CARRY_SELECT(PREDICTOR_BANK_PC_CARRY_SELECT),')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_NARROW_DIRECTION_READ = 1,',
        '    parameter integer PREDICTOR_NARROW_DIRECTION_READ = 1,\n    parameter integer PREDICTOR_BANK_PC_CARRY_SELECT = 1,')
    text = once(text, '.PREDICTOR_NARROW_DIRECTION_READ(PREDICTOR_NARROW_DIRECTION_READ),',
        '.PREDICTOR_NARROW_DIRECTION_READ(PREDICTOR_NARROW_DIRECTION_READ), .PREDICTOR_BANK_PC_CARRY_SELECT(PREDICTOR_BANK_PC_CARRY_SELECT),')
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
    record['parameter_overrides'] = dict(parent['parameter_overrides'], PREDICTOR_BANK_PC_CARRY_SELECT=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], predictor_bank_pc_carry_select=True,
        full_bank_pc_retained_including_invalid_query=True,
        predictor_bank_pc_carry_added_ff_bits=0, predictor_bank_pc_carry_added_sram_bits=0,
        predictor_bank_pc_carry_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Precompute the shared28-bit next-line increment independently of late bank offset; retain exact3-bit base-word+offset sum, select current/next line high bits in16/12-bit domains, and preserve low2 PC bits. Exact full modulo2^32 bank PC including invalid queries, wrap and unaligned inputs; no validity/history/training or fetch-boundary change.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        bank_offset_to_high_pc_arithmetic_replaced_by_carry_select=True,
        predictor_bank_pc_carry_mapped_cost_and_gain_unknown=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_PREDICTOR_BANK_PC_CARRY_SELECT_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
        source_arguments=[
            'Let the PC be16*H+4*W+L, W=PC[3:2] and L=PC[1:0]. Offset O is0..3, so original PC+4*O equals16*(H+floor((W+O)/4))+4*((W+O)%4)+L. The unchanged3-bit word_index contains W+O: bit2 is the only high-part carry and low2 bits are the new word. High-part28-bit truncation exactly implements32-bit PC wrap.',
            'Shared next_line_high=H+1 is computed from PC independently of bank offset. A late word_index carry selects H or H+1 using two bounded16/12-bit controls, instead of entering the high-part adder. Low2 PC bits are copied, so correctness does not require an added alignment assumption.',
            'Invalid bank queries still receive the same full PC, including cross-line carry. Existing word_index<4 query validity, instruction read, folded BTB identity, BHT/chooser indexes, full target formation and saved exact training index are unchanged. This does not substitute a same-line PC for an invalid query or alter standalone diagnostics.',
            'Parameter0 retains the original full addition. FE1 also retains that original constant-offset implementation and instantiates no carry-selection tree. Core/banked defaults0; course top1. All feedback arbitration, table state, speculative history, recovery, counters and packet lane routing source remain byte-exact after the PC construction block.',
            'No FF/SRAM/pipeline edge is added. Precomputed increment and selection may map to a different area/load trade; low-bit selection can be slower even while higher-bit late carry paths shorten. No frequency or area improvement is asserted before measuring the whole batch.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. Future meaningful coverage includes FE1/2/4, each bank/start word, cross-line invalid queries and diagnostic indexes, near32-bit wrap and unaligned input behavior, direct/indirect/hybrid modes and optional-mode fallback.'
        ])
    write(BASE / 'A52_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
