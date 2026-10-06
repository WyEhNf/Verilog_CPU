"""Prepare exact recovery classification before late LSQ report choice."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import ROOT, read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A101_held_identity_row_query'
TARGET = BASE/'A102_report_recovery_prequalification'
REVIEW = BASE/'A102_source_review.json'
REFERENCE = ROOT/'build/cpu2026/er1_a99_ppa_result_20261006.json'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    assert sha(PARENT/'candidate.json')=='ccc8fda2c30ac2dbb869f2f0a273974b64e555e1031ca1ade1073216c92546f7'
    assert sha(REFERENCE)=='c7a0983b6acfa224fb3def9a825f524b3b046d13db4ba5ec139c6c0aa9df7fad'
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/backend/rv32_backend_joint.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    marker='    parameter integer LSQ_HELD_LOAD_IDENTITY_QUERY = 0,'
    text=once(original,marker,marker+'\n    parameter integer LSQ_REPORT_RECOVERY_PREQUALIFY = 0,')
    marker='    localparam integer LSQ_REPORT_IDENTITY_CANDIDATES=(LSQ_HELD_LOAD_IDENTITY_ACTIVE!=0)?3:2;'
    text=once(text,marker,marker+'''
    localparam integer LSQ_REPORT_RECOVERY_PREQUALIFY_ACTIVE=(LSQ_REPORT_RECOVERY_PREQUALIFY!=0) && LSQ_HEAD_LOAD_IDENTITY_ACTIVE;
    wire lsq_report_identity_recovery_kill;''')
    marker='        wire [LSQ_REPORT_IDENTITY_CANDIDATES-1:0] candidate_live;'
    text=once(text,marker,marker+'\n        wire [LSQ_REPORT_IDENTITY_CANDIDATES-1:0] candidate_recovery_kill;')
    marker='            wire [ROB_LIVE_WIDTH-1:0] live_state;'
    text=once(text,marker,'''            if(LSQ_REPORT_RECOVERY_PREQUALIFY_ACTIVE!=0) begin:g_recovery_class
                // Match the original producer recovery loop's INTEGER32
                // context exactly; do not replace it with modular ages. The
                // final occupancy comparison retains its unsigned operand.
                wire signed [31:0] slot={
                    {(32-ROB_SLOT_WIDTH){1'b0}},tag[3 +: ROB_SLOT_WIDTH]};
                wire signed [31:0] age=slot-{
                    {(32-ROB_SLOT_WIDTH){1'b0}},recovery_head_views[4*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]};
                wire signed [31:0] branch_age={
                    {(32-ROB_SLOT_WIDTH){1'b0}},recovery_tag_views[6*TAG_WIDTH+3 +: ROB_SLOT_WIDTH]}-{
                    {(32-ROB_SLOT_WIDTH){1'b0}},recovery_head_views[4*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH]};
                assign candidate_recovery_kill[identity_candidate]=!tag[0] ||
                    (age>branch_age) || (age>=recovery_descriptor_occupancy);
            end else begin:g_no_recovery_class
                assign candidate_recovery_kill[identity_candidate]=1'b0;
            end
'''+marker)
    marker='        if(LSQ_HELD_LOAD_IDENTITY_ACTIVE!=0) begin:g_choose_held'
    text=once(text,marker,'''        if(LSQ_HELD_LOAD_IDENTITY_ACTIVE!=0) begin:g_choose_recovery_held
            assign lsq_report_identity_recovery_kill=lsq_report_identity_held ? candidate_recovery_kill[2] :
                (lsq_report_identity_head ? candidate_recovery_kill[1] : candidate_recovery_kill[0]);
        end else begin:g_choose_recovery_original
            assign lsq_report_identity_recovery_kill=lsq_report_identity_head ?
                candidate_recovery_kill[1] : candidate_recovery_kill[0];
        end
'''+marker)
    marker="        assign lsq_report_identity_live=1'b0;"
    text=once(text,marker,marker+"\n        assign lsq_report_identity_recovery_kill=1'b0;")
    old='''                producer_recovery_rob_slot =
                    producer_tag_r[(producer_recovery_index*TAG_WIDTH) + 3 +: ROB_SLOT_WIDTH];
                producer_recovery_age = producer_recovery_rob_slot - recovery_head_views[4*ROB_SLOT_WIDTH +: ROB_SLOT_WIDTH];
                if (producer_valid_r[producer_recovery_index] &&
                    (!producer_tag_r[producer_recovery_index*TAG_WIDTH] ||
                     (producer_recovery_age > producer_recovery_branch_age) ||
                     (producer_recovery_age >= recovery_descriptor_occupancy)))
                    producer_target_live_r[producer_recovery_index] = 1'b0;'''
    new='''                if(LSQ_REPORT_RECOVERY_PREQUALIFY_ACTIVE!=0 && producer_recovery_index==LSQ_SOURCE) begin
                    // Candidate identities are saved before late head-report
                    // choice. Real recovery apply and original valid still
                    // gate this exact original target-live update.
                    if(producer_valid_r[producer_recovery_index] && lsq_report_identity_recovery_kill)
                        producer_target_live_r[producer_recovery_index]=1'b0;
                end else begin:g_original_selected_tag_recovery
'''+old+'''
                end'''
    text=once(text,old,new)
    assert old in text
    marker='    assign producer_valid = producer_valid_r;'
    assert text[text.index(marker):]==original[original.index(marker):]
    changes[name]=text
    for name in ['rtl/cpu_core.v','rtl/course/student_top.v']:
        original=(PARENT/name).read_text(encoding='utf-8')
        default=1 if name.endswith('student_top.v') else 0
        marker='    parameter integer LSQ_HELD_LOAD_IDENTITY_QUERY = '+str(default)+','
        text=once(original,marker,marker+'\n    parameter integer LSQ_REPORT_RECOVERY_PREQUALIFY = '+str(default)+',')
        text=once(text,'.LSQ_HELD_LOAD_IDENTITY_QUERY(LSQ_HELD_LOAD_IDENTITY_QUERY)',
            '.LSQ_HELD_LOAD_IDENTITY_QUERY(LSQ_HELD_LOAD_IDENTITY_QUERY), .LSQ_REPORT_RECOVERY_PREQUALIFY(LSQ_REPORT_RECOVERY_PREQUALIFY)')
        if name.endswith('student_top.v'):
            text=once(text,'    parameter integer LSQ_HELD_LOAD_IDENTITY_QUERY = 1,',
                '    parameter integer LSQ_HELD_LOAD_IDENTITY_QUERY = 0,')
        changes[name]=text
    for name in parent['source_sha256']:
        destination=TARGET/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():(TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(status='SOURCE_SAVED_LSQ_REPORT_RECOVERY_CLASSIFICATION_PREQUALIFIED_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),source_root=str(TARGET),parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_from_parent_files=list(changes),
        source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},preparation_script_sha256=sha(Path(__file__)),
        source_review=str(REVIEW),tests_started=False,synthesis_started=False,timing_started=False,adopted=False,
        candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides']=dict(parent['parameter_overrides'],LSQ_HELD_LOAD_IDENTITY_QUERY=0,LSQ_REPORT_RECOVERY_PREQUALIFY=1)
    record['enabled_profile']=dict(parent['enabled_profile'],LSQ_HELD_LOAD_IDENTITY_QUERY=0,LSQ_REPORT_RECOVERY_PREQUALIFY=1,
        active_report_identity_candidates=2,independent_held_identity_extra_rob_live_queries=0,
        report_recovery_new_ff_bits=0,report_recovery_new_sram_bits=0,report_recovery_new_pipeline_edges=0,
        independent_held_identity_optional_disabled_for_new_recovery_path=True)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Classify exact original producer recovery kill independently for saved/held and head LSQ ROB identities before late report head choice; original apply and actual sourcevalid gate the same target_live0 update, latechoice selects one boolean. Preserve original32bit signed INTEGER age math and mixed unsigned occupancy comparison, full ROBvalid/GEN check, actualpublic tag/query/payload, sourceorder/handshake/CDB/PRF/RS/LSQ state. Disable optional A100/A101 independent-held third query in course frequencyprofile to control84um2 margin and focus new recovery-selected-tag path; feature retained and supported ifenabled.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        original_a99_ppa_proof_sha256=sha(REFERENCE),recovery_prequalification_limit='A99 top5start branch capture and recovery preview0.6154/distribution0.7736 -> publicLSQ ROBtagbit5 in completiondata79 at1.823 -> CDB2.202 -> PRF2.499 -> admit2.982 -> LSQwrite/FF3.414ns. Producer recovery loop takes this late selected tag then computes age/branch/occupancy classification before source eligibility. Private saved/held andhead identities alreadyprepared; exact conditions can be classified independently and latehead choice select1bit. Need141.276ps improvement, area84.2415um2. Extra smallcandidateclass logic possiblecost or otherbranch paths maydominate; no guaranteed gain.')
    write(TARGET/'candidate.json',record)
    proof=dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,
        added_declared_ff_bits=0,added_sram_bits=0,added_pipeline_edges=0,active_report_identity_candidates=2,
        measured_reference=str(REFERENCE),measured_reference_sha256=sha(REFERENCE),
        source_arguments=[
            'For any actual publicLSQ completion in HEAD_LOAD_IDENTITY_ACTIVE profile, original private saved/held orhead candidate selected by headflag equals public complete ROBtag; source byte equations proved in A89/A91/A99. If optional A100/A101 held mode enabled, originalH chooses held candidate exactly by fullLSQslot/GEN uniqueness. New killboolean is original function applied independently to every candidate, then selected by same H/head. Function selection commutes, so selected result equals original function(publictag) under every actualsourcevalid condition, without new event or unreachable-state suppression.',
            'Original producer_recovery_rob_slot/age/branch_age are signed INTEGER32. New slot zero-extends original slotfield to32; age andbranch_age each use original head/tag views, zero-extended widths, assign signed32 results. Firstcomparison signedage>signedbranch_age; finalcomparison uses original unsigned recovery_descriptor_occupancy so originalVerilog unsignedconversion retained. Do not replace negative ages with moduloROBages, change wrap behavior or omit invalidtag predicate. Actualapply remains original outer recovery_domains[6]; actualproducer_valid stillgates targetlive0. Original fullROBvalid/allGEN separate filter unchanged.',
            'Only LSQsource original recovery body takes newoption. ALU/MDU sourcebody remains original text, baseline option0 retains same allsource loop; sourcevalid/dataflags, initialtargetlive, fullGEN filtering, recoveryactivation and branch_age assignments unchanged. Backend suffix from producer_valid assignments through CDB/PRF/RS/LSQ request/state and helper modules byte-identical; entireLSQ/ROB/PRF/completion/MDU sources byte-identical toparent.',
            'Course profile chooses existing HELD_LOAD_IDENTITY_QUERY0 so A100normalextra tree/held reader andthirdROBquery statically inactive; A101optional per-row decode also inactive. This restores A99twoidentity behavior/cost while preserving alternate sourcefeature, all functionality and parameterized support. New flag core/backend0/top1, gatedbyoriginalHEAD_LOAD_IDENTITY_ACTIVE. No ISA/GEN/portcapacity/queue/cache/predictor/state/pipeline changes.',
            'OriginalA99PPA287.802136MHz/35915.758478um2 didnotpass frequency, originaltaskterminal andperformance deferred, noIPC/CPU build. New top5recovery-selectedtag path direct evidence, extraidentity recoverylogic may increasearea ormapping/newbottleneck maynegategain. Candidate unmeasured. NoHDL/lint/formal/sim/synthesis/STA/unit tests; preserveoldsuccessful scripts/evidence andmainEsource. Inspect remaining admissioncontrol load before any pre-reported coherent nextmeasurement; final numeric/19correctness/minimal4edge/parameter scope unchanged.'
        ],goal_complete=False,adopted=False)
    write(REVIEW,proof)
    print({k:proof[k] for k in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__=='__main__':
    main()
