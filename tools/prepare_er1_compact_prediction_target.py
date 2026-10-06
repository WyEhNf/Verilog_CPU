"""Compact direct-mode prediction metadata without truncating fetch addresses."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A25_sram_axi_read_payload'
TARGET=BASE/'A26_compact_prediction_target'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/frontend/rv32_fetch_frontend.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer PREDICTOR_META = 0',
        '    parameter integer COMPACT_PRED_TARGET = 0,\n    parameter integer PREDICTOR_META = 0')
    text=once(text,'            assign bundle_pred_taken[response_lane]=if_resp_pred_taken_i[response_lane];','''            // Raw full-target prediction still controls fetch and bundle
            // boundaries. This flag is only the saved resolution metadata.
            // JALR is always taken: an out-of-page prediction is marked
            // not-taken so resolution must redirect even if low bits alias.
            wire target_in_page=if_resp_pred_target_i[response_lane*32+12 +: 20]==
                bundle_pc[response_lane*32+12 +: 20];
            assign bundle_pred_taken[response_lane]=if_resp_pred_taken_i[response_lane] &&
                ((COMPACT_PRED_TARGET==0) ||
                 (if_resp_pred_kind_i[response_lane*2 +: 2]!=`RV32IM_PRED_JALR) || target_in_page);''')
    text=once(text,'            assign bundle_pred_target[response_lane*32 +: 32]=if_resp_pred_target_i[response_lane*32 +: 32];','''            // Only indirect page-offset targets need to travel through
            // FQ/decode/dispatch/RS. Direct branch/JAL targets are determined
            // by the saved PC/instruction; noncontrol metadata is unused.
            assign bundle_pred_target[response_lane*32 +: 32]=(COMPACT_PRED_TARGET!=0)?
                {20'b0,((if_resp_pred_kind_i[response_lane*2 +: 2]==`RV32IM_PRED_JALR)?
                    if_resp_pred_target_i[response_lane*32 +: 12]:12'b0)}:
                if_resp_pred_target_i[response_lane*32 +: 32];''')
    # Raw predictor results still drive next PC, speculative history and all
    # accepted instruction boundaries. Neither next-PC arithmetic nor any
    # clocked validity/count/recovery state changes.
    state='    always @* begin\n        // Form the largest contiguous bundle'
    assert text[text.index(state):]==original[original.index(state):]
    changes[name]=text
    name='rtl/rv32i_alu.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer FORWARD_METADATA = 0,',
        '    parameter integer FORWARD_METADATA = 0,\n    parameter integer COMPACT_PRED_TARGET = 0,')
    text=once(text,'''    assign calc_redirect_valid=calc_is_branch &&
        ((issue_pred_taken_i!=calc_branch_taken) ||
         (calc_branch_taken && issue_pred_target_i!=calc_branch_target));''','''    wire [31:0] indirect_predicted_target={issue_pc_i[31:12],issue_pred_target_i[11:0]};
    // Direct-mode conditional/JAL targets are exact PC+decoded immediate.
    // For JALR only, reconstruct the page-qualified metadata. The frontend
    // forces an out-of-page raw prediction to a direction mismatch, so an
    // alias of these low bits can never conceal a wrong fetch target.
    wire predicted_target_mismatch=(COMPACT_PRED_TARGET!=0)?
        ((issue_op_i==`RV32IM_OP_JALR) && indirect_predicted_target!=calc_branch_target):
        (issue_pred_target_i!=calc_branch_target);
    assign calc_redirect_valid=calc_is_branch &&
        ((issue_pred_taken_i!=calc_branch_taken) ||
         (calc_branch_taken && predicted_target_mismatch));''')
    state='    localparam integer AUX_WIDTH='
    # Entire arithmetic, output packet owners and ready/valid/recovery state
    # are unchanged apart from the redirect comparison above.
    assert text.replace('    parameter integer COMPACT_PRED_TARGET = 0,\n','').replace(
        text[text.index('    wire [31:0] indirect_predicted_target='):text.index('    localparam',text.index('    wire [31:0] indirect_predicted_target='))],
        original[original.index('    assign calc_redirect_valid='):original.index('    localparam',original.index('    assign calc_redirect_valid='))])==original
    changes[name]=text
    name='rtl/backend/rv32_backend_joint.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer PREDICTOR_META = 0,',
        '    parameter integer PREDICTOR_META = 0,\n    parameter integer COMPACT_PRED_TARGET = 0,')
    text=once(text,'.SHIFT_SHARED_BARREL(SHIFT_SHARED_BARREL), .FORWARD_METADATA(RS_ISSUE_METADATA)',
        '.SHIFT_SHARED_BARREL(SHIFT_SHARED_BARREL), .COMPACT_PRED_TARGET(COMPACT_PRED_TARGET), .FORWARD_METADATA(RS_ISSUE_METADATA)')
    text=once(text,'''            assign feedback_values[feedback_source*FEEDBACK_PACKET_WIDTH +: FEEDBACK_PACKET_WIDTH]={
                slot,pc,kind,alu_exec_branch_taken[feedback_source],
                alu_exec_branch_target[feedback_source*32 +: 32],pred_taken,pred_target};''','''            // Expand only after execution, outside FQ/dispatch/RS storage.
            // Training receives the full expected target for a page-qualified
            // JALR or the exact computed target for direct control flow.
            wire [31:0] full_pred_target=(COMPACT_PRED_TARGET!=0)?
                ((kind==`RV32IM_PRED_JALR)?{pc[31:12],pred_target[11:0]}:
                    alu_exec_branch_target[feedback_source*32 +: 32]):pred_target;
            assign feedback_values[feedback_source*FEEDBACK_PACKET_WIDTH +: FEEDBACK_PACKET_WIDTH]={
                slot,pc,kind,alu_exec_branch_taken[feedback_source],
                alu_exec_branch_target[feedback_source*32 +: 32],pred_taken,full_pred_target};''')
    changes[name]=text
    name='rtl/cpu_core.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer PREDICTOR_HISTORY_BITS = 6,',
        '    parameter integer PREDICTOR_HISTORY_BITS = 6,\n    parameter integer PREDICTOR_COMPACT_TARGET = 0,')
    text=once(text,'    wire redirect_valid;','''    localparam integer COMPACT_TARGET_ACTIVE=(PREDICTOR_COMPACT_TARGET!=0) &&
        (SERIAL_BACKEND==0) && (PREDICTOR_DIRECT_BRANCH_TARGET==1);
    wire redirect_valid;''')
    text=once(text,'.PREDICTOR_META(PREDICTOR_DIRECT_BRANCH_TARGET == 2), .LEGACY_SENTINEL_HALT',
        '.COMPACT_PRED_TARGET(COMPACT_TARGET_ACTIVE), .PREDICTOR_META(PREDICTOR_DIRECT_BRANCH_TARGET == 2), .LEGACY_SENTINEL_HALT')
    text=once(text,'.PREDICTOR_META(PREDICTOR_DIRECT_BRANCH_TARGET == 2), .INT_ISSUE_WIDTH',
        '.COMPACT_PRED_TARGET(COMPACT_TARGET_ACTIVE), .PREDICTOR_META(PREDICTOR_DIRECT_BRANCH_TARGET == 2), .INT_ISSUE_WIDTH')
    changes[name]=text
    name='rtl/course/student_top.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer PREDICTOR_HISTORY_BITS = 6,',
        '    parameter integer PREDICTOR_HISTORY_BITS = 6,\n    parameter integer PREDICTOR_COMPACT_TARGET = 1,')
    text=once(text,'.PREDICTOR_HISTORY_BITS(PREDICTOR_HISTORY_BITS),',
        '.PREDICTOR_HISTORY_BITS(PREDICTOR_HISTORY_BITS), .PREDICTOR_COMPACT_TARGET(PREDICTOR_COMPACT_TARGET),')
    changes[name]=text
    for name in parent['source_sha256']:
        dest=TARGET/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['parameter_overrides']=dict(parent['parameter_overrides'],PREDICTOR_COMPACT_TARGET=1)
    record['enabled_profile']=dict(parent['enabled_profile'],PREDICTOR_COMPACT_TARGET=1,
        indirect_prediction_offset_bits=12,full_fetch_target_preserved=True,
        cross_page_indirect_prediction_forces_recovery=True)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Use12-bit page-qualified indirect prediction metadata across FQ/decode/dispatch/RS/ALU; direct targets require no saved target. Preserve full fetch addresses; force JALR recovery for out-of-page raw predictions.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        prediction_target_constant_bits_per_payload=20,
        prediction_target_ff_copies_lower_bound=16+2+4+8+2,
        prediction_target_removed_declared_ff_bits_lower_bound=20*(16+2+4+8+2),
        prediction_target_removed_ff_area_component_um2=20*(16+2+4+8+2)*.2916,
        prediction_target_copy_count_is_source_argument_not_mapped_count=True,
        compact_target_new_ipc_area_fmax_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_PAGE_QUALIFIED_PREDICTION_METADATA_UNTESTED',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),tests_started=False,
        source_arguments=[
            'Core enables compact encoding only for OoO direct-target mode1; standalone defaults, mode0 BTB conditional targets, mode2 history predictor and serial backend retain original full-target semantics.',
            'Frontend raw full32-bit predictor/RAS targets still control fetch PC and taken bundle boundaries. Only saved resolution metadata changes; no fetch address is truncated.',
            'Direct conditional/JAL targets in mode1 are PC+decoded immediate in both predictor and ALU. Correct direction necessarily means correct target, so target comparison/storage is redundant for these operations.',
            'JALR raw target in the same4KiB page is represented by low12 bits and reconstructed with the saved instruction PC high20 bits. Target equality then compares the complete actual address, including page crossing.',
            'If a raw JALR prediction points outside its instruction page, saved predicted-taken is forced0. Legal JALR actual-taken is1, requiring recovery regardless of low-bit alias or whether its actual target returns inside the source page. This retains full arbitrary-address correctness at the cost of such a recovery.',
            'Prediction feedback is expanded after registered execution; direct expected target reuses full actual branch target, indirect expected target uses saved PC/offset. Actual target training, architectural link value, selective cancellation, target tag ownership, and in-order commit remain unchanged.',
            'No new state/nominal pipeline edge. Twenty bits per prediction payload become constant across FQ/decode/dispatch/RS/ALU. Estimate640 declared bits includes16FQ+2decode+4dispatch+8RS+2ALU copies; this source count is not a mapped-area result and frontend page check/feedback mux add logic.',
            'No HDL build, lint, simulation, synthesis, STA, perf or unit tests. Relevant later coverage must include direct forward/backward/page-crossing, JALR same/cross-page and false upper-page aliases, RAS returns, simultaneous recovery, and held metadata.'
        ])
    write(BASE/'A26_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':
    main()
