"""Correct untested A102 prequalification to the actual original age widths."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A102_report_recovery_prequalification'
TARGET=BASE/'A103_report_recovery_age_width'
REVIEW=BASE/'A103_source_review.json'
ORIGINAL=BASE/'A101_held_identity_row_query'


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    assert sha(PARENT/'candidate.json')=='a2d6f012cbde79af37bd12a8df47626c4df5aa272be22b7c659fdd6394e6d67d'
    parent=read(PARENT/'candidate.json')
    assert not parent['tests_started'] and not parent['adopted']
    for name,digest in parent['source_sha256'].items():assert sha(PARENT/name)==digest,name
    name='rtl/backend/rv32_backend_joint.v'
    baseline=(ORIGINAL/name).read_text(encoding='utf-8')
    assert '    integer producer_recovery_rob_slot;' in baseline
    assert '    reg [ROB_SLOT_WIDTH-1:0] producer_recovery_age;' in baseline
    assert '    reg [ROB_SLOT_WIDTH-1:0] producer_recovery_branch_age;' in baseline
    original=(PARENT/name).read_text(encoding='utf-8')
    old='''                // Match the original producer recovery loop's INTEGER32
                // context exactly; do not replace it with modular ages. The
                // final occupancy comparison retains its unsigned operand.
                wire signed [31:0] slot={
                    {(32-ROB_SLOT_WIDTH){1'b0}},tag[3 +: ROB_SLOT_WIDTH]};
                wire signed [31:0] age=slot-{
                    {(32-ROB_SLOT_WIDTH){1'b0}},recovery_head_views[4*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]};
                wire signed [31:0] branch_age={
                    {(32-ROB_SLOT_WIDTH){1'b0}},recovery_tag_views[6*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]}-{
                    {(32-ROB_SLOT_WIDTH){1'b0}},recovery_head_views[4*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]};'''
    new='''                // Original temporary slot is INTEGER32, but both original
                // age registers truncate to unsigned ROB_SLOT_WIDTH. Keep
                // exactly that modulo-2**ROB_SLOT_WIDTH subtraction and the
                // original unsigned branch-age / occupancy comparisons.
                wire [ROB_SLOT_WIDTH-1:0] slot=tag[3 +: ROB_SLOT_WIDTH];
                wire [ROB_SLOT_WIDTH-1:0] age=slot-
                    recovery_head_views[4*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
                wire [ROB_SLOT_WIDTH-1:0] branch_age=
                    recovery_tag_views[6*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]-
                    recovery_head_views[4*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];'''
    assert original.count(old)==1
    text=original.replace(old,new)
    for name in parent['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name,dest)
    name='rtl/backend/rv32_backend_joint.v'
    (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(status='SOURCE_REPORT_RECOVERY_PREQUALIFIED_ORIGINAL_MODULAR_AGE_WIDTH_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),source_root=str(TARGET),parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_from_parent_files=[name],
        source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},preparation_script_sha256=sha(Path(__file__)),
        source_review=str(REVIEW),tests_started=False,synthesis_started=False,timing_started=False,adopted=False,
        candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['enabled_profile']=dict(parent['enabled_profile'],report_recovery_age_width='ROB_SLOT_WIDTH unsigned, exact original register truncation')
    changes=list(parent['implemented_changes'])
    changes[-1]=changes[-1].replace('original32bit signed INTEGER age math and mixed unsigned occupancy comparison',
        'original unsigned ROB_SLOT_WIDTH age/branch_age register truncation and unsigned occupancy comparison')
    record['implemented_changes']=changes+[
        'Source declaration audit before any test found only originalslot temporary INTEGER32, while original age/branch_age are unsigned ROB_SLOT_WIDTH regs. Correct new independent candidate age expressions to exact original bitwidth and comparison types. This repairs untested A102 source-review assumption; all late-bool recovery optimization, realapply/valid/fullGEN and original public/state behavior retained. A102 remains immutable/unmeasured/unadopted, not an equivalent-profile reference.'
    ]
    write(TARGET/'candidate.json',record)
    proof=dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=[name],tests_started=False,
        new_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        original_declaration_evidence=dict(slot='integer32',age='reg unsigned ROB_SLOT_WIDTH',branch_age='reg unsigned ROB_SLOT_WIDTH'),
        superseded_a102_source_review_assumption='A102 argument2 incorrectly treated age/branch_age as signedINTEGER32; no tests or adoption occurred.',
        source_arguments=[
            'Originalslot temporary is32bitinteger containing zero-extended tag slot. Original subtraction assigned to unsignedROB_SLOT_WIDTH age truncates modulo2**ROB_SLOT_WIDTH. Direct unsignedSLOT_WIDTH slot-head wire gives exactly same lowbits for all slot/head values. Originalbranch_age unsignedreg has same width/tag/head subtraction, identical directwire. Both > and >= use same original unsigned types/width extension, including non-power-of-two originalROBmagnitude behavior; do not reinterpret moduloROB_ENTRIES.',
            'With these exact widths, function(originalpublictag) equals select(function(private saved/held tag),function(privatehead tag)) whenever actualLSQsource valid, by originalreportpack/identity equations. Existing optionalheld third candidate remains supported but disabled in courseprofile. Realapply/actualvalid/fullROBGEN and originaltargetlive update/genericALU/MDUbody retain A102 plan; original downstream state unchanged.',
            'Only A102 newcandidate age declarations change; suffix starting assign candidate_recovery_kill and all packet/headchoice/producerloop/core/top parameters/state remain byte-identical toparent. Existingoriginal age regs and fallback arithmetic unchanged. Three metrics unknown. OldA102source/script/review remainsfrozen; its equivalence claim is explicitly superseded by this correction, no retroactive rewriting.',
            'NoHDL/lint/formal/sim/synthesis/STA/unit tests orCPU builds. MainEsourceunadopted. NewA99 criticalrecovery-selectedtag evidence remains valid; next supported coherent batch pre-report, thenPPA gate beforeperf. Preserve fullRV32IM/OoO/inordercommit/MMIO/parameterizedgoal and final19+minimal4edge coverage.'
        ],goal_complete=False,adopted=False)
    write(REVIEW,proof)
    print({k:proof[k] for k in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__=='__main__':
    main()
