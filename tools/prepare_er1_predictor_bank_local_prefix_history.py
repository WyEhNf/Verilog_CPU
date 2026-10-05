"""Use fixed FE4 bank identity before prefix-history formation, without HDL runs."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A54_predictor_bank_local_instruction_read'
TARGET = BASE / 'A55_predictor_bank_local_prefix_history'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A55_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/predictor/rv32_banked_predictor.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer BANK_LOCAL_INSTRUCTION_READ = 0,',
        '    parameter integer BANK_LOCAL_INSTRUCTION_READ = 0,\n    parameter integer BANK_LOCAL_PREFIX_HISTORY = 0,')
    text = once(text, '''                    assign preceding_conditions[word]=
                        query_line_i[word*32 +: 7]==7'b1100011 &&
                        query_pc_i[3:2]<=word && word_index>word && !word_index[2];''',
        '''                    if(BANK_LOCAL_PREFIX_HISTORY!=0 && FE_WIDTH==4) begin:g_fixed_bank_prefix
                        if(word<bank) begin:g_earlier_word
                            assign preceding_conditions[word]=
                                query_line_i[word*32 +: 7]==7'b1100011 && query_pc_i[3:2]<=word;
                        end else begin:g_not_earlier
                            assign preceding_conditions[word]=1'b0;
                        end
                    end else begin:g_original_prefix_mask
                        assign preceding_conditions[word]=
                            query_line_i[word*32 +: 7]==7'b1100011 &&
                            query_pc_i[3:2]<=word && word_index>word && !word_index[2];
                    end''')
    marker = '                wire [1:0] preceding_count='
    assert text[text.index(marker):] == original[original.index(marker):]
    assert len(re.findall(r'^\s*reg\s+', text, re.M)) == len(re.findall(r'^\s*reg\s+', original, re.M))
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_BANK_LOCAL_INSTRUCTION_READ = 0,',
        '    parameter integer PREDICTOR_BANK_LOCAL_INSTRUCTION_READ = 0,\n    parameter integer PREDICTOR_BANK_LOCAL_PREFIX_HISTORY = 0,')
    text = once(text, '.BANK_LOCAL_INSTRUCTION_READ(PREDICTOR_BANK_LOCAL_INSTRUCTION_READ),',
        '.BANK_LOCAL_INSTRUCTION_READ(PREDICTOR_BANK_LOCAL_INSTRUCTION_READ),\n                .BANK_LOCAL_PREFIX_HISTORY(PREDICTOR_BANK_LOCAL_PREFIX_HISTORY),')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_BANK_LOCAL_INSTRUCTION_READ = 1,',
        '    parameter integer PREDICTOR_BANK_LOCAL_INSTRUCTION_READ = 1,\n    parameter integer PREDICTOR_BANK_LOCAL_PREFIX_HISTORY = 1,')
    text = once(text, '.PREDICTOR_BANK_LOCAL_INSTRUCTION_READ(PREDICTOR_BANK_LOCAL_INSTRUCTION_READ),',
        '.PREDICTOR_BANK_LOCAL_INSTRUCTION_READ(PREDICTOR_BANK_LOCAL_INSTRUCTION_READ), .PREDICTOR_BANK_LOCAL_PREFIX_HISTORY(PREDICTOR_BANK_LOCAL_PREFIX_HISTORY),')
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
    record['parameter_overrides'] = dict(parent['parameter_overrides'], PREDICTOR_BANK_LOCAL_PREFIX_HISTORY=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], predictor_bank_local_prefix_history=True,
        bank_local_prefix_query_history_exact_to_a54=True,
        bank_local_prefix_added_ff_bits=0, bank_local_prefix_added_sram_bits=0,
        bank_local_prefix_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Use the fixed FE4 bank word number when forming preceding-condition masks. A valid word is B; an invalid bank has start W>B and all fixed preceding positions are before W. Replace word_index arithmetic/comparison/validity dependencies with constant earlier-word membership and start<=word, retaining exact A54 query history for valid and invalid banks.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        word_index_arithmetic_dependency_removed_from_fe4_prefix_history=True,
        bank_local_prefix_mapped_cost_and_gain_unknown=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_PREDICTOR_BANK_LOCAL_PREFIX_HISTORY_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
        source_arguments=[
            'For FE4, bank B and start word W give word_index=B when B>=W, otherwise B+4. In the valid case the A54 mask is opcode(word)==branch and W<=word<B. In the invalid case A54 masks all flags to0; the new mask also returns0 because every statically earlier word is <B<W. Therefore every preceding flag, count and query-history value is exact to A54, including invalid banks.',
            'Generate-time word<bank eliminates impossible preceding positions. Remaining masks compare start word against constants and read fixed opcode bits; neither late offset subtraction, word_index addition nor high-word validity enters prefix history. No previous predicted direction enters another bank query.',
            'The count, constant shifts, all predictor and feedback logic, metadata checkpoints, accepted-history updates and recovery source stay byte-exact. FE1/2 and option0 retain A54 masks. PREFIX_QUERY_HISTORY off or DIRECT_BRANCH_TARGET!=2 instantiates no new mask logic.',
            'No FF/SRAM/pipeline edge is added. The source dependency reduction does not quantify total combinational cost, Fmax or IPC gain. A53 changed query semantics as documented; A55 only factors its enabled implementation.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. Future meaningful coverage includes all FE4 bank/start words and opcode flags, invalid bank histories, exact saved/trained indexes, FE1/2 and option fallback, plus existing prefix-history recovery/backpressure checks.'
        ])
    write(BASE / 'A55_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
