"""Prepare an independent one-edge earlier frontend redirect; no HDL runs."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A22_load_return_wake_only'
TARGET=BASE/'A23_early_frontend_redirect'


def once(text, old, new):
    assert text.count(old)==1, old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/backend/rv32_backend_joint.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer LOAD_WAKE_BYPASS = 0,',
        '    parameter integer LOAD_WAKE_BYPASS = 0,\n    parameter integer EARLY_FRONT_REDIRECT = 0,')
    declarations='''    localparam integer BRANCH_CAPTURE_WIDTH=TAG_WIDTH+PAW+65;
    wire [BE_WIDTH-1:0] branch_capture_match,branch_capture_grant;
    wire [BE_WIDTH*BRANCH_CAPTURE_WIDTH-1:0] branch_capture_values;
    wire branch_capture_write;
    wire [BRANCH_CAPTURE_WIDTH-1:0] branch_capture_next,branch_capture_saved;
'''
    text=once(text,declarations,'')
    text=once(text,'''    // Front-end redirect is issued during preview. Backend recovery is a
    // registered transaction applied on the following edge.
    reg branch_pending;''','''    // The accepted live branch can redirect fetch on its capture edge.
    // Backend preview/capture/apply and its sole epoch increment stay staged.
'''+declarations+'''    reg branch_pending;''')
    text=once(text,'''    assign redirect_valid_o = recovery_preview_fire;
    assign redirect_pc_o = rob_redirect_pc;''','''    generate if(EARLY_FRONT_REDIRECT!=0 && PREDICTOR_META==0) begin:g_early_front_redirect
        // Same first-lane grant and full ROB-generation authority used to
        // acquire branch_pending. The pending queue blocks a second redirect
        // until recovery applies. Do not redirect again on the preview edge.
        assign redirect_valid_o=branch_capture_write;
        assign redirect_pc_o=branch_capture_next[31:0];
    end else begin:g_preview_front_redirect
        // History-indexed prediction retains its registered history snapshot.
        assign redirect_valid_o=recovery_preview_fire;
        assign redirect_pc_o=rob_redirect_pc;
    end endgenerate''')
    # The actual recovery packet acquisition, history, queue owner and every
    # descriptor/apply register are identical. Only frontend publication moves.
    tail='    genvar capture_lane;'
    assert text.split(tail,1)[1]==original.split(tail,1)[1]
    clock='    rv32_frequency_word_bank #(.WIDTH(CHECK_RAT_WIDTH)) rat_descriptor_owner ('
    end='    // Only accepted live redirects'
    assert text[text.index(clock):text.index(end)]==original[original.index(clock):original.index(end)]
    changes[name]=text
    for name,default in [('rtl/cpu_core.v',0),('rtl/course/student_top.v',1)]:
        text=(PARENT/name).read_text(encoding='utf-8')
        text=once(text,f'    parameter integer LOAD_WAKE_BYPASS = {default if default else 0},',
            f'    parameter integer LOAD_WAKE_BYPASS = {default if default else 0},\n    parameter integer EARLY_FRONT_REDIRECT = {default},')
        text=once(text,'.LOAD_WAKE_BYPASS(LOAD_WAKE_BYPASS),',
            '.LOAD_WAKE_BYPASS(LOAD_WAKE_BYPASS), .EARLY_FRONT_REDIRECT(EARLY_FRONT_REDIRECT),')
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
    record['parameter_overrides']=dict(parent['parameter_overrides'],EARLY_FRONT_REDIRECT=1)
    record['enabled_profile']=dict(parent['enabled_profile'],EARLY_FRONT_REDIRECT=1,
        frontend_mispredict_wait_edges_removed=1,early_redirect_added_state_bits=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Redirect frontend from the same accepted full-tag-live branch capture, one edge before ROB preview; keep backend recovery descriptor/apply and epoch update unchanged.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        accepted_branch_to_frontend_redirect_edges_before=2,
        accepted_branch_to_frontend_redirect_edges_after=1,
        early_redirect_added_state_bits=0,early_redirect_ipc_and_fmax_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_FRONTEND_REDIRECT_ONE_EDGE_EARLIER_UNTESTED',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),tests_started=False,
        source_arguments=[
            'Existing branch capture requires a valid/accepted ALU redirect, no reset/flush/pending branch, and full ROB generation/valid authority. Same priority grant selects frontend target and saved recovery packet.',
            'Course mode PREDICTOR_META=0 needs no registered global-history repair; history-indexed mode and disabled parameter keep the original preview redirect.',
            'ROB redirect_epoch_o is unconditionally epoch_reg+1; its only nonreset increment remains recovery apply. Early frontend uses that epoch, and no duplicate preview redirect is published.',
            'branch_pending capture/clear, saved target/tag/value, descriptor capture, selective kill, RAT restore/reclaim and in-order commit logic remain exact parent source.',
            'New-epoch fetched packets may wait behind original branch_pending until apply; old frontend/decode packets are cleared one edge sooner. No backend flush or recovery boundary is bypassed.',
            'No state/cycles are added; removes one frontend wait edge per accepted misprediction. Dynamic IPC gain and full live-check-to-frontend timing remain unknown, requiring a coherent later measurement.',
            'Source inspection only. No HDL build, lint, simulation, synthesis, STA or unit tests. Main EU tree and earlier frozen candidates/runs unchanged.'
        ])
    write(BASE/'A23_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':
    main()
