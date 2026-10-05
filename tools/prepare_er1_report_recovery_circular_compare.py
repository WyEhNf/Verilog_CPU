"""Prepare exact unsigned circular recovery comparisons; no HDL tests."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A105_rob_recovery_row_live'
TARGET = BASE/'A106_report_recovery_circular_compare'
REVIEW = BASE/'A106_source_review.json'
FLAG = 'LSQ_REPORT_RECOVERY_CIRCULAR_COMPARE'


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    assert sha(PARENT/'candidate.json') == '7eb963391d62ecbd793d09b90d01a3210f5cbf94a5856575b49fe95d434f698d'
    parent = read(PARENT/'candidate.json')
    assert not parent['adopted']
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    files = ['rtl/backend/rv32_backend_joint.v', 'rtl/cpu_core.v', 'rtl/course/student_top.v']
    originals = {n:(PARENT/n).read_text(encoding='utf-8') for n in files}
    modified = dict(originals)
    for name in files:
        default = 1 if name.endswith('student_top.v') else 0
        old = f'    parameter integer LSQ_REPORT_RECOVERY_PREQUALIFY = {default},'
        modified[name] = replace_once(modified[name], old,
            old + f'\n    parameter integer {FLAG} = {default},')
        if name != files[0]:
            old = '.LSQ_REPORT_RECOVERY_PREQUALIFY(LSQ_REPORT_RECOVERY_PREQUALIFY),'
            modified[name] = replace_once(modified[name], old,
                old + f' .{FLAG}({FLAG}),')

    name = files[0]
    old = '        wire [LSQ_REPORT_IDENTITY_CANDIDATES-1:0] candidate_recovery_kill;'
    shared = old + '''
        // W-bit ages wrap modulo 2**W, including non-power-of-two ROBs.
        // Compute the unwrapped occupied range end once, independently of
        // each candidate. W+count-width bounds retain every binary count.
        localparam integer RECOVERY_RANGE_WIDTH =
            ((ROB_SLOT_WIDTH>ROB_COUNT_WIDTH)?ROB_SLOT_WIDTH:ROB_COUNT_WIDTH)+1;
        wire [ROB_SLOT_WIDTH-1:0] range_head =
            recovery_head_views[4*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
        wire [ROB_SLOT_WIDTH-1:0] range_branch =
            recovery_tag_views[6*TAG_WIDTH+3 +: ROB_SLOT_WIDTH];
        wire [RECOVERY_RANGE_WIDTH-1:0] range_end =
            {{(RECOVERY_RANGE_WIDTH-ROB_SLOT_WIDTH){1'b0}},range_head} +
            {{(RECOVERY_RANGE_WIDTH-ROB_COUNT_WIDTH){1'b0}},recovery_descriptor_occupancy};
        wire branch_wrap = range_branch<range_head;
        wire end_first_turn = range_end[ROB_SLOT_WIDTH +: RECOVERY_RANGE_WIDTH-ROB_SLOT_WIDTH]==0;
        wire end_second_turn = range_end[ROB_SLOT_WIDTH +: RECOVERY_RANGE_WIDTH-ROB_SLOT_WIDTH]==1;'''
    modified[name] = replace_once(modified[name], old, shared)
    old = '''                // Original temporary slot is INTEGER32, but both original
                // age registers truncate to unsigned ROB_SLOT_WIDTH. Keep
                // exactly that modulo-2**ROB_SLOT_WIDTH subtraction and the
                // original unsigned branch-age / occupancy comparisons.
                wire [ROB_SLOT_WIDTH-1:0] slot=tag[3 +: ROB_SLOT_WIDTH];
                wire [ROB_SLOT_WIDTH-1:0] age=slot-
                    recovery_head_views[4*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
                wire [ROB_SLOT_WIDTH-1:0] branch_age=
                    recovery_tag_views[6*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]-
                    recovery_head_views[4*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
                assign candidate_recovery_kill[identity_candidate]=!tag[0] ||
                    (age>branch_age) || (age>=recovery_descriptor_occupancy);'''
    new = '''                wire [ROB_SLOT_WIDTH-1:0] slot=tag[3 +: ROB_SLOT_WIDTH];
                if(LSQ_REPORT_RECOVERY_CIRCULAR_COMPARE!=0) begin:g_circular
                    wire slot_wrap=slot<range_head;
                    // Wrapped positions follow every unwrapped position;
                    // within either group the ordinary slot order applies.
                    wire younger=(slot_wrap && !branch_wrap) ||
                        ((slot_wrap==branch_wrap) && (slot>range_branch));
                    wire slot_at_or_past_end=slot>=range_end[0 +: ROB_SLOT_WIDTH];
                    // position = slot, or 2**W+slot when slot<head. Compare
                    // position with head+count using its turn and low slot.
                    // An end in turn 2 or above contains every W-bit age.
                    wire outside=(end_first_turn && (slot_wrap || slot_at_or_past_end)) ||
                        (end_second_turn && slot_wrap && slot_at_or_past_end);
                    assign candidate_recovery_kill[identity_candidate]=!tag[0] || younger || outside;
                end else begin:g_original_age
                    // Preserve A103's exact unsigned W-bit truncation.
                    wire [ROB_SLOT_WIDTH-1:0] age=slot-
                        recovery_head_views[4*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
                    wire [ROB_SLOT_WIDTH-1:0] branch_age=
                        recovery_tag_views[6*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]-
                        recovery_head_views[4*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
                    assign candidate_recovery_kill[identity_candidate]=!tag[0] ||
                        (age>branch_age) || (age>=recovery_descriptor_occupancy);
                end'''
    modified[name] = replace_once(modified[name], old, new)
    marker = '            wire [ROB_LIVE_WIDTH-1:0] live_state;'
    assert modified[name][modified[name].index(marker):] == originals[name][originals[name].index(marker):]
    assert 'localparam integer ROB_SLOT_WIDTH = (ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES);' in originals[name]
    assert 'localparam integer ROB_COUNT_WIDTH = (ROB_ENTRIES <= 1) ? 1 : $clog2(ROB_ENTRIES + 1);' in originals[name]
    for name in parent['source_sha256']:
        dest = TARGET/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT/name, dest)
    for name, content in modified.items():
        (TARGET/name).write_text(content, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_EXACT_UNSIGNED_CIRCULAR_REPORT_RECOVERY_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(), source_root=str(TARGET),
        parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=files, source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), source_review=str(REVIEW),
        tests_started=False, synthesis_started=False, timing_started=False, adopted=False,
        candidate_ipc=None, candidate_area_um2=None, candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], **{FLAG:1})
    record['enabled_profile'] = dict(parent['enabled_profile'],
        report_recovery_circular_compare=True, report_recovery_modulus='2**ROB_SLOT_WIDTH',
        report_recovery_candidate_age_subtractors_removed=True,
        report_recovery_range_end_shared=True, report_recovery_circular_added_ff_bits=0,
        report_recovery_circular_added_sram_bits=0, report_recovery_circular_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Replace each private LSQ report candidate modular age subtraction and age comparison with exact circular slot comparisons. Share an extended unsigned head+occupancy endpoint and branch wrap classification before the candidates. Keep A103 old-age mode as default0 in core/backend, course1 enables new combinational equations. Actual apply/valid/fullGEN, head/held choice, producer selection and every downstream state equation unchanged. Parent A105 is being characterized separately; none of its metrics are assumed for A106.'
    ]
    write(TARGET/'candidate.json', record)
    proof = dict(status=record['status'], candidate=str(TARGET), candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'], changed_files=files,
        tests_started=False, new_declared_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0,
        downstream_from_rob_live_read_byte_identical=True,
        source_arguments=[
            'Let W=ROB_SLOT_WIDTH and M=2**W. Original unsigned age a=(slot-head) mod M equals position-head, where position=slot when slot>=head and M+slot otherwise. This uses original W-bit truncation, not modulo ROB_ENTRIES. Branch has the same definition. Wrapped ages occupy [M-head,M-1] and unwrapped ages [0,M-head-1]; hence a>b iff slot_wrap&&!branch_wrap OR (equal wraps AND slot>branch_slot). Equal slots give equal ages and are never younger.',
            'For unsigned original count c of ROB_COUNT_WIDTH bits, a>=c iff position>=head+c. Extended endpoint width max(W,COUNT_WIDTH)+1 holds the maximum head+c without overflow. With end=q*M+e, q=0 gives outside=slot_wrap OR slot>=e; q=1 gives outside=slot_wrap AND slot>=e; q>=2 gives outside=false since position<2*M. These three equations cover every binary raw count including c=0, c=M, and c>M, not just reachable ROB occupancies. Only the low W-bit slot comparator follows a candidate tag; endpoint addition and q classification are shared independently.',
            'These equations hold for W>=1, ROB_ENTRIES1, powers of two and nonpowers, tag slots outside actual geometry, every branch/head binary value and every count. They do not alter the original separate fullGEN/currentlive/out-of-range guards. Candidate kill still ORs original !tagvalid, selection still uses original head/optional held choice, and actual producer_valid/recovery_domains gate the same targetlive update. A102 erroneous signed32 age assumption remains superseded by A103.',
            'Only the three flag plumbing files and the private recovery classifier change. Source suffix from first candidate live_state declaration through original backend end is byte-identical; original producer loop, downstream completion/PRF/RS/LSQ/ROB/MMIO/GEN/recovery state is untouched. No FF, SRAM or clock edges added. Width parameters are declared before localparam use; no $bits on forward-declared wires. Default0 keeps original ages; new flag has no effect unless existing report recovery prequalification is active.',
            'A99 real recovery critical chain justifies removal of the candidate-age carry chain before CDB eligibility; A105 independent row-live batch is still measured separately. Comparator/endpoint area and synthesis restructuring are unknown; do not claim MHz, IPC or area without a new coherent pre-reported measurement. No HDL/lint/formal/sim/synthesis/STA/unit tests or CPU builds are run here; main E source and frozen A105 run/tool/source remain untouched.'
        ], candidate_metrics=None, goal_complete=False, adopted=False)
    write(REVIEW, proof)
    print({k:proof[k] for k in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
