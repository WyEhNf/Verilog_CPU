"""Prepare coherent redirect-edge fetch ownership; no HDL tools are run."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read,sha,write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A68_retain_free_pool_restore'
TARGET=BASE/'A69_same_edge_redirect_fetch'
REVIEW=BASE/'A69_source_review.json'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/frontend/rv32_fetch_frontend.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer RESPONSE_LOCAL_PC = 0,',
        '''    parameter integer RESPONSE_LOCAL_PC = 0,
    // Caller supplies the redirect epoch to its registered-response cache on
    // this same edge. Old responses remain blocked while the new PC is offered.
    parameter integer REDIRECT_REQUEST = 0,''')
    text=once(text,'''    assign if_req_valid_o = !reset_i && !frozen_reg && !stop_i && !error_i &&
                            (!req_pending_reg || response_can_chain);''',
        '''    wire redirect_request=(REDIRECT_REQUEST!=0) && redirect_valid_i;
    wire [3:0] redirect_request_views;
    rv32_frequency_control_tree #(.LEAVES(4)) redirect_request_tree (
        .signal_i(redirect_request),.views_o(redirect_request_views));
    assign if_req_valid_o = !reset_i && !stop_i && !error_i &&
        (!frozen_reg || redirect_request_views[0]) &&
        (!req_pending_reg || response_can_chain || redirect_request_views[0]);''')
    text=once(text,'''        assign if_req_pc_o[request_half*16 +: 16]=chain_views[request_half]?
            next_pc_comb[request_half*16 +: 16]:pc_reg[request_half*16 +: 16];''',
        '''        assign if_req_pc_o[request_half*16 +: 16]=redirect_request_views[request_half+1]?
             redirect_pc_i[request_half*16 +: 16]:(chain_views[request_half]?
             next_pc_comb[request_half*16 +: 16]:pc_reg[request_half*16 +: 16]);''')
    text=once(text,'    assign if_req_epoch_o = epoch_reg;',
        '    assign if_req_epoch_o = redirect_request_views[3] ? redirect_epoch_i : epoch_reg;')
    text=once(text,'''            if (redirect_valid_i) begin
                req_pending_reg <= 1'b0;''',
        '''            if (redirect_valid_i) begin
                // PC/epoch owners take the redirect regardless of readiness.
                // Record pending ownership only for the new accepted request.
                req_pending_reg <= (REDIRECT_REQUEST!=0) && req_fire;''')
    for marker in [
        'assign if_resp_ready_o = !reset_i && !redirect_valid_i && response_live && queue_space;',
        '.events_i({reset_i,redirect_valid_i,resp_fire})',
        '.events_i({reset_i,redirect_valid_i})',
        'assign current_epoch_o = epoch_reg;',
        '(req_pending_reg && if_resp_pc_i==pc_reg)',
    ]:
        assert marker in text,marker
    changes[name]=text
    name='rtl/cpu_core.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer FRONTEND_RESPONSE_LOCAL_PC = 0,',
        '    parameter integer FRONTEND_RESPONSE_LOCAL_PC = 0,\n    parameter integer FRONTEND_REDIRECT_REQUEST = 0,')
    marker='    wire branch_feedback_valid, branch_feedback_taken, branch_feedback_pred_taken;'
    epoch='''    // Only the cached nonblocking registered-response profile can accept a
    // redirect request on this edge. Other cache/serial profiles retain the
    // original registered epoch and original frontend request contract.
    localparam integer REDIRECT_REQUEST_ACTIVE=(FRONTEND_REDIRECT_REQUEST!=0) &&
        (ENABLE_CACHES!=0) && (ICACHE_MSHRS>1) &&
        (ICACHE_COMBINATIONAL_HIT==0) && (DECODE_PIPELINE!=0) && (SERIAL_BACKEND==0);
    wire [EPOCH_WIDTH-1:0] icache_effective_epoch=
        (REDIRECT_REQUEST_ACTIVE!=0 && redirect_domains[0])?redirect_epoch:frontend_epoch;
'''
    text=once(text,marker,epoch+marker)
    text=once(text,'.PARALLEL_BUNDLE_CONTROL(FRONTEND_PARALLEL_BUNDLE_CONTROL),',
        '.PARALLEL_BUNDLE_CONTROL(FRONTEND_PARALLEL_BUNDLE_CONTROL), .REDIRECT_REQUEST(REDIRECT_REQUEST_ACTIVE),')
    a='    if (ICACHE_MSHRS > 1) begin : g_nonblocking_icache'
    b='    end else begin : g_blocking_icache'
    old_nonblocking=text[text.index(a):text.index(b)]
    new_nonblocking=once(old_nonblocking,'.current_epoch_i(frontend_epoch)',
        '.current_epoch_i(icache_effective_epoch)')
    text=once(text,old_nonblocking,new_nonblocking)
    # Blocking/uncached cache, AXI and all backend/decoder/MMIO code untouched.
    assert text[text.index(b):]==original[original.index(b):]
    assert text.count('.current_epoch_i(frontend_epoch)')==original.count('.current_epoch_i(frontend_epoch)')-1
    changes[name]=text
    name='rtl/course/student_top.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer FRONTEND_RESPONSE_LOCAL_PC = 1,',
        '    parameter integer FRONTEND_RESPONSE_LOCAL_PC = 1,\n    parameter integer FRONTEND_REDIRECT_REQUEST = 1,')
    text=once(text,'.FRONTEND_RESPONSE_LOCAL_PC(FRONTEND_RESPONSE_LOCAL_PC),',
        '.FRONTEND_RESPONSE_LOCAL_PC(FRONTEND_RESPONSE_LOCAL_PC), .FRONTEND_REDIRECT_REQUEST(FRONTEND_REDIRECT_REQUEST),')
    changes[name]=text
    cache=(PARENT/'rtl/cache/rv32_icache_nonblocking.v').read_text(encoding='utf-8')
    for marker in [
        'wire fast_live=fast_valid && fast_epoch==current_epoch_i;',
        'wire miss_live=miss_pending && pending_epoch==current_epoch_i;',
        'wire accept_hit=request_fire && hit && if_req_epoch_i==current_epoch_i;',
        'if(accept_hit) fast_valid<=1\'b1;',
        'if(accept_miss) miss_pending<=1\'b1;',
        'wire stale=count!=0 && epoch_o!=current_epoch_i;',
        'mshr_txn_epoch[response_index] ==',
    ]:
        assert marker in cache,marker
    for name in parent['source_sha256']:
        destination=TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(status='SOURCE_SAME_EDGE_REDIRECT_FETCH_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_from_parent_files=list(changes),
        source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),
        tests_started=False,synthesis_started=False,timing_started=False,adopted=False,
        candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides']=dict(parent['parameter_overrides'],FRONTEND_REDIRECT_REQUEST=1)
    record['enabled_profile']=dict(parent['enabled_profile'],same_edge_redirect_request=True,
        redirect_cache_effective_epoch=True,new_redirect_request_pending_state_bits=0,
        redirect_request_added_ff_bits=0,redirect_request_added_sram_bits=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Offer redirect PC/epoch to the registered-response nonblocking ICache on the qualified redirect edge. Override old pending/frozen request ownership but retain reset/stop/error gates and block all old response acceptance. On that edge PC/epoch owners take the redirect and pending records only actual new request fire. ICache effective epoch matches that offered epoch immediately; full stale response/transaction authority is unchanged.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        redirect_request_prefetch_edge_removed_when_ready=True,
        direct_apply_retained_pool_combination_can_expose_earlier_fetch=True,
        redirected_hot_hit_useful_cycle_gain_unknown=True,
        redirect_request_limit='Same-edge fire requires ICache readiness; full stale queue/cold miss and downstream delays can hide improvement. Added redirect-PC/epoch/control paths may threaten >300MHz.')
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_SAME_EDGE_REDIRECT_FETCH_UNTESTED',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),tests_started=False,adopted=False,
        new_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        icache_source_sha256=sha(TARGET/'rtl/cache/rv32_icache_nonblocking.v'),icache_source_unchanged=True,
        source_arguments=[
            'On a qualified redirect edge, request payload becomes exactly redirect PC/epoch. Valid may bypass the obsolete pending/frozen state but still requires !reset,!stop,!error. Old response acceptance is unconditionally suppressed by redirect, so old FQ/predictor/RAS/decoder response side effects remain absent.',
            'The existing PC and epoch owners preserve reset > redirect > accepted-response precedence. New pending is exactly the same-edge new request fire. If cache refuses, pending clears and the saved redirected PC/epoch is retried normally afterward. If accepted, the saved PC/epoch becomes that request identity; no second copy is reissued while pending.',
            'Only the nonblocking cached registered-response/decode-pipeline/nonserial profile sees effective cache epoch=redirect epoch on this edge. Frontend current_epoch output and response PC identity remain registered, and redirect blocks consumption until those owners update. Blocking/uncached/serial/option0 profiles preserve the old contract.',
            'The unchanged filter compares fast/miss epochs to that effective epoch. Old slots become stale before acceptance; new hit/miss acceptance wins their existing stale clear on the edge. Registered FakeRAM read/fast identity is selected by the new PC, while no old primary response can fill through frontend ready on redirect.',
            'The unchanged query queue drains stale head requests. A full queue cannot accept until capacity exists; pending/fire observes actual ready. Primary cache lookup uses the original request pipeline; MSHR invalidation/free/match/sent/response tests retain transaction epoch/ID and current demand epoch checks. Control-prefetch old transactions remain preserved by their original exception, with demand promotion still separately qualified.',
            'All ICache/MSHR/filter/FakeRAM/AXI source and external transaction IDs remain byte-exact. Internal old-generation offers can become stale one edge sooner, while accepted external transactions remain owned by the unchanged AXI bridge and their responses drain under exact old ID/epoch checks. No new epoch value or extra increment is introduced.',
            'With A65 direct apply and A68 retained free candidates, an earlier hot-hit target bundle may now reach rename earlier, where the old staged recovery/free-pool barrier previously hid it. Cold misses, full stale queue, pool-empty recovery or other stalls can reduce/hide the benefit; no dynamic saved-cycle or IPC1.1 claim.',
            'No FF/SRAM/pipeline state added. New redirect result -> request PC/SRAM read and redirect valid -> effective epoch -> ICache ownership/ready paths need STA. Source reasoning only; no HDL/lint/sim/synth/STA/unit execution. Future batch covers hit/miss/busy filter, held response, refused/accepted redirect request, simultaneous old return/fill, control-prefetch promotion, transaction ID/epoch reuse, reset/stop/error, line offsets, FE1/2/4 and disabled/fallback profiles.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','changed_files','tests_started')})


if __name__=='__main__':
    main()
