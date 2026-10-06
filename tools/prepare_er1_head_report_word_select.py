"""Bound the final head/saved report select and withdraw costly row-live mode."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A107_allocation_payload_preselect'
TARGET = BASE/'A108_head_report_word_select'
REVIEW = BASE/'A108_source_review.json'


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    assert sha(PARENT/'candidate.json') == '225ee7905cbba7104a4825b751aeecf25429291ae4e64f32f9cb7595086ff44d'
    parent = read(PARENT/'candidate.json')
    assert not parent['tests_started'] and not parent['adopted']
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    files = ['rtl/backend/rv32_lsq.v', 'rtl/course/student_top.v']
    originals = {n:(PARENT/n).read_text(encoding='utf-8') for n in files}
    texts = dict(originals)
    name = files[0]
    old = '''        assign prepared_report_payload=load_report_identity_head_o ?
            head_packet : saved_identity_tree[1][0 +: REPORT_BASE_WIDTH];'''
    new = '''        // A late head/saved choice must not drive the entire report word.
        // All priced tree leaves carry exactly the same original choice;
        // each leaf selects at most 16 payload bits, without another edge.
        localparam integer HEAD_CHOICE_WORDS=(REPORT_BASE_WIDTH+15)/16;
        wire [HEAD_CHOICE_WORDS-1:0] head_choice_views;
        rv32_frequency_control_tree #(.LEAVES(HEAD_CHOICE_WORDS)) head_choice_tree (
            .signal_i(load_report_identity_head_o),.views_o(head_choice_views));
        for(genvar head_choice_word=0;head_choice_word<HEAD_CHOICE_WORDS;head_choice_word=head_choice_word+1) begin:g_choice_word
            localparam integer LOW=head_choice_word*16;
            localparam integer BITS=(REPORT_BASE_WIDTH-LOW>=16)?16:REPORT_BASE_WIDTH-LOW;
            assign prepared_report_payload[LOW +: BITS]=head_choice_views[head_choice_word] ?
                head_packet[LOW +: BITS] : saved_identity_tree[1][LOW +: BITS];
        end'''
    assert texts[name].count(old) == 1
    texts[name] = texts[name].replace(old, new)
    marker = '    genvar report_row, report_node, report_word;'
    if marker in originals[name]:
        assert texts[name][texts[name].index(marker):] == originals[name][originals[name].index(marker):]
    suffix = originals[name][originals[name].index(old)+len(old):]
    assert texts[name].endswith(suffix)
    name = files[1]
    old = '    parameter integer ROB_RECOVERY_ROW_LIVE_QUALIFY = 1,'
    assert texts[name].count(old) == 1
    texts[name] = texts[name].replace(old, '    parameter integer ROB_RECOVERY_ROW_LIVE_QUALIFY = 0,')
    for name in parent['source_sha256']:
        dest = TARGET/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT/name, dest)
    for name, content in texts.items():
        (TARGET/name).write_text(content, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_WORD_BOUNDED_HEAD_REPORT_SELECT_ORIGINAL_ROB_LIVE_RESTORED_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(), source_root=str(TARGET), parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT/'candidate.json'), changed_from_parent_files=files,
        source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), source_review=str(REVIEW),
        tests_started=False, synthesis_started=False, timing_started=False, adopted=False,
        candidate_ipc=None, candidate_area_um2=None, candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], ROB_RECOVERY_ROW_LIVE_QUALIFY=0)
    record['enabled_profile'] = dict(parent['enabled_profile'], ROB_RECOVERY_ROW_LIVE_QUALIFY=0,
        head_report_final_word_select=True, head_report_select_bits_per_leaf_maximum=16,
        head_report_select_added_ff_bits=0, head_report_select_added_sram_bits=0,
        head_report_select_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'A105 original PPA ended274.236743MHz/36056.018078um2; no CPU/IPC. Disable optional ROB_RECOVERY_ROW_LIVE_QUALIFY in the new course profile to restore original selected9bit fullGEN reader and remove parallel-row query cost, without editing frozen A105 or attributing all batch regression to that option. Keep source option for other profiles.',
        'In the existing active head-packet branch, replace final whole REPORT_BASE_WIDTH-bit head/saved mux with the same mux sliced into <=16bit words. Original priced functional control tree carries exact load_report_identity_head_o to each word. All old values, choice policy and public packet equations are preserved, no state or latency change. Existing inactive head-packet branch unchanged.'
    ]
    write(TARGET/'candidate.json', record)
    proof = dict(status=record['status'], candidate=str(TARGET), candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'], changed_files=files, tests_started=False,
        new_declared_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0,
        head_report_mux_inputs_and_choice_policy_unchanged=True,
        lsq_all_state_and_other_report_logic_suffix_byte_identical=True,
        source_arguments=[
            'Original rv32_frequency_control_tree is a combinational inversion/restoration tree, each views_o bit equals signal_i for every binary input and supported LEAVES>=1. Divide payload width P into ceil(P/16) disjoint slices; every slice implements exactly h?head[slice]:saved[slice]. Concatenating all slices yields the exact original whole-packet h?head:saved equation, including invalid packets. P and BITS use existing PHYS_ADDR/TAG/ROB_TAG widths, no forward $bits parameter. Inactive HEAD_LOAD_PACKET_ACTIVE branch unchanged.',
            'Course PHYS6+ROB_TAG16+LSQ_TAG16+35 yields P73 and5 leaves (16,16,16,16,9bits). Late choice previously drove all73 packet bits directly. New real library tree limits each payload mux leaf to <=16bit; all buffers/capacitances remain priced by identical course synthesis/STA, no ideal blackboxes/false paths. Head/saved/held priority, physical destinations, full GEN/tags, value/error/cancel and every subsequent LSQ state owner remain identical.',
            'Original A105 terminal shows critical arrival3.586ns, OAI21_225574_529ps at43.73fF and1.1ns slew before source3 direct payload physbit4 (data[72]) then RS physical wake/issue and ALU. That mapped driver is not labeled with a source head-choice name; linking it specifically to the final wide mux is a source/structural inference, not an exact pin-to-RTL proof. Nonetheless the existing unbounded73bit final mux is an explicit source load, and bounded-equivalent selection targets this segment without weakening real recovery or fullGEN authority.',
            'A105 coherent A103-A105 batch failed both PPA gates, so its optional32row fullGEN compare mode is no longer enabled in new course profile. Restoring originalmode0 preserves same completebinary row-live equation; it reduces introduced replicated GEN comparators and queries but actual net area/frequency is unknown. Original A105 source/tools/run/reports remain frozen, and no single-component regression claim is made.',
            'A108 inherits A106 exact circular age comparisons and A107 early private allocation identity, all with original actual event/clock behavior. This new path also includes late CDB/RS arbitration and high-fanout occupancy launch; those remain possible constraints and are examined before any new batch measurement. Do not assume A94IPC or promise300MHz/36000. No HDL/lint/formal/sim/synthesis/STA/unit tests or CPU builds here. Goal complete/adopted false.'
        ], candidate_metrics=None, goal_complete=False, adopted=False)
    write(REVIEW, proof)
    print({k:proof[k] for k in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
