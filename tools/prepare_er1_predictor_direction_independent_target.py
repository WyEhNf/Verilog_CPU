"""Prepare direct branch targets before direction, with compact-core guarding."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A49_frontend_parallel_bundle_control'
TARGET = BASE / 'A50_predictor_direction_independent_target'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A50_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/predictor/rv32_branch_predictor.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer HYBRID_DIRECTION = 0,',
        '''    parameter integer HYBRID_DIRECTION = 0,
    // Optional candidate-target contract: a conditional direct target can be
    // meaningful even when not taken. Caller selects it only when taken, and
    // omits unused direct targets from saved resolution metadata.
    parameter integer DIRECTION_INDEPENDENT_TARGET = 0,''')
    text = once(text, '''    assign target_classes[0]=!pred_taken_o;
    assign target_classes[1]=pred_taken_o && pred_kind_o==`RV32IM_PRED_BRANCH &&
        ((DIRECT_BRANCH_TARGET!=0) || !pred_btb_hit_o);
    assign target_classes[2]=pred_taken_o && pred_kind_o==`RV32IM_PRED_JAL;
    assign target_classes[3]=pred_taken_o &&
        (pred_kind_o==`RV32IM_PRED_JALR ||
         (pred_kind_o==`RV32IM_PRED_BRANCH && DIRECT_BRANCH_TARGET==0 && pred_btb_hit_o));''',
        '''    generate if(DIRECTION_INDEPENDENT_TARGET!=0 && DIRECT_BRANCH_TARGET!=0) begin:g_early_target
        // Kind/BTB query is independent of direction-table readout. Compute
        // a conditional target before the global/bimodal/choice decision;
        // frontend direction remains the final target-versus-sequential choice.
        assign target_classes[1]=pred_kind_o==`RV32IM_PRED_BRANCH;
        assign target_classes[2]=pred_kind_o==`RV32IM_PRED_JAL;
        assign target_classes[3]=pred_kind_o==`RV32IM_PRED_JALR && pred_btb_hit_o;
        assign target_classes[0]=!(|target_classes[3:1]);
    end else begin:g_qualified_target
        assign target_classes[0]=!pred_taken_o;
        assign target_classes[1]=pred_taken_o && pred_kind_o==`RV32IM_PRED_BRANCH &&
            ((DIRECT_BRANCH_TARGET!=0) || !pred_btb_hit_o);
        assign target_classes[2]=pred_taken_o && pred_kind_o==`RV32IM_PRED_JAL;
        assign target_classes[3]=pred_taken_o &&
            (pred_kind_o==`RV32IM_PRED_JALR ||
             (pred_kind_o==`RV32IM_PRED_BRANCH && DIRECT_BRANCH_TARGET==0 && pred_btb_hit_o));
    end endgenerate''')
    # Owners, query indexing, direction/choice training, speculative metadata,
    # accepted-feedback counters and target arithmetic remain the original.
    marker = '    wire prediction_write=reset_i || feedback_valid_i;'
    assert text[text.index(marker):] == original[original.index(marker):]
    a = '    wire [1:0] bht'; z = '    assign target_classes[0]=!pred_taken_o;'
    assert text[text.index(a):text.index('    generate if(DIRECTION_INDEPENDENT_TARGET')] == original[original.index(a):original.index(z)]
    assert len(re.findall(r'^\s*reg\s+', text, re.M)) == len(re.findall(r'^\s*reg\s+', original, re.M))
    changes[name] = text
    name = 'rtl/predictor/rv32_banked_predictor.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer HYBRID_DIRECTION = 0,',
        '    parameter integer HYBRID_DIRECTION = 0,\n    parameter integer DIRECTION_INDEPENDENT_TARGET = 0,')
    text = once(text, '.HYBRID_DIRECTION(HYBRID_DIRECTION),',
        '.HYBRID_DIRECTION(HYBRID_DIRECTION), .DIRECTION_INDEPENDENT_TARGET(DIRECTION_INDEPENDENT_TARGET),')
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_HYBRID_DIRECTION = 0,',
        '    parameter integer PREDICTOR_HYBRID_DIRECTION = 0,\n    parameter integer PREDICTOR_DIRECTION_INDEPENDENT_TARGET = 0,')
    text = once(text, '.HYBRID_DIRECTION(PREDICTOR_HYBRID_DIRECTION && !SERIAL_BACKEND),',
        '''.HYBRID_DIRECTION(PREDICTOR_HYBRID_DIRECTION && !SERIAL_BACKEND),
                .DIRECTION_INDEPENDENT_TARGET(PREDICTOR_DIRECTION_INDEPENDENT_TARGET && COMPACT_TARGET_ACTIVE),''')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_HYBRID_DIRECTION = 1,',
        '    parameter integer PREDICTOR_HYBRID_DIRECTION = 1,\n    parameter integer PREDICTOR_DIRECTION_INDEPENDENT_TARGET = 1,')
    text = once(text, '.PREDICTOR_HYBRID_DIRECTION(PREDICTOR_HYBRID_DIRECTION),',
        '.PREDICTOR_HYBRID_DIRECTION(PREDICTOR_HYBRID_DIRECTION), .PREDICTOR_DIRECTION_INDEPENDENT_TARGET(PREDICTOR_DIRECTION_INDEPENDENT_TARGET),')
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
    record['parameter_overrides'] = dict(parent['parameter_overrides'], PREDICTOR_DIRECTION_INDEPENDENT_TARGET=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], predictor_direction_independent_target=True,
        target_contract_guarded_by_compact_metadata=True, frontend_selects_targets_only_when_taken=True,
        predictor_early_target_added_ff_bits=0, predictor_early_target_added_sram_bits=0,
        predictor_early_target_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Direct conditional target class depends only on decoded prediction kind; direction selects target-versus-sequential only in frontend. Preserve exact JAL/JALR/invalid target behavior, table/history/training state and compact saved metadata. Enable only for compact-target OoO core, preserving standalone/full-target/serial defaults.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        conditional_direction_to_predictor_target_selection_removed=True,
        fetch_wait_and_metadata_width_unchanged=True,
        candidate_frequency_and_area_unmeasured=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_PREDICTOR_DIRECTION_INDEPENDENT_TARGET_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
        source_arguments=[
            'The only changed predictor value is a valid direct conditional branch target when predicted not taken: it now presents PC+branch immediate as a candidate instead of PC+4. Taken conditional targets, JAL, valid JALR hit/miss, invalid query and noncontrol outputs retain their original target values. The direction/kind/hit/counter/raw-component metadata is unchanged.',
            'No conditional direction-table output enters target_classes in active mode. Query opcode/kind and JALR BTB hit determine four mutually exclusive/exhaustive candidate classes; original target arithmetic, event-select word ownership and bank routing remain exact.',
            'The core activates this mode only with COMPACT_TARGET_ACTIVE, which excludes serial backend and full-target metadata. Frontend only uses a branch target for next-PC on predicted taken, and compact saved branch/JAL/noncontrol targets are0 independent of raw candidate value. JALR raw target stays exact, so page qualification and saved low12 bits are unchanged. RAS return override is unchanged.',
            'Accepted prefix/history updates depend on unchanged directions/kinds. ALU uses the original exact direct PC+immediate target and direction mismatch, with the same compact metadata. Training payload and accepted full-generation feedback, recovery/history repair and all state owners remain source-exact.',
            'Parameter0 and DIRECT_BRANCH_TARGET0 retain the original direction-qualified target contract. Core/standalone defaults0 and course top1; full-target/serial core overrides keep the old contract even when the top optional knob is1. This is an explicit optional predictor candidate-target contract, not an assertion that the old standalone raw target bus remains identical under mode1.',
            'This removes one serialized conditional direction-to-32-bit target selection before bank/RAS/frontend routing, in the measured A41 critical frontend region. No added state, SRAM or fetch boundary. Mapping may choose different gates/loads, and area/Fmax/IPC are not inferred from source simplification.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. Later coverage must check taken/not-taken/cold/trained conditional predictions, all JAL/JALR and RAS paths, raw candidate versus compact saved packet, prefix next-PC and page qualification, invalid/noncontrol queries and legacy/full-target/serial parameter fallback.'
        ])
    write(BASE / 'A50_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
