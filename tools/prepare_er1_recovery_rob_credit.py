"""Advertise exact ROB capacity after direct recovery; no HDL execution."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A69_same_edge_redirect_fetch'
TARGET = BASE / 'A70_recovery_rob_credit'
REVIEW = BASE / 'A70_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_backend_joint.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer RECOVERY_DIRECT_APPLY = 0,',
        '''    parameter integer RECOVERY_DIRECT_APPLY = 0,
    // Only the fully qualified direct apply can advertise its post-edge ROB
    // capacity. Ordinary allocation credits keep their original conservative rule.
    parameter integer RECOVERY_ROB_CREDIT = 0,''')
    text = once(text, '    integer credit_lane;\n    function [CREDIT_WIDTH-1:0] bounded_credit;',
        '''    integer credit_lane;
    wire [CREDIT_WIDTH-1:0] recovery_rob_credit;
    generate if(RECOVERY_ROB_CREDIT!=0 && RECOVERY_DIRECT_ACTIVE!=0) begin:g_recovery_rob_credit
        // Qualified apply holds head, blocks rename/commit, and leaves the
        // prefix through the pending branch: free'=ROB_ENTRIES-1-branch_age.
        // Decode only the small saturated credit classes, avoiding a late
        // free-count subtract/compare on the recovery qualification path.
        wire [BE_WIDTH-1:0] credit_events;
        wire [BE_WIDTH*CREDIT_WIDTH-1:0] credit_values;
        genvar credit_class;
        for(credit_class=1;credit_class<=BE_WIDTH;credit_class=credit_class+1) begin:g_class
            localparam integer AGE_BOUND=ROB_ENTRIES-1-credit_class;
            if(credit_class>ROB_ENTRIES-1) begin:g_impossible
                assign credit_events[credit_class-1]=1'b0;
            end else if(credit_class==BE_WIDTH) begin:g_saturated
                assign credit_events[credit_class-1]=
                    execution_branch_age<=ROB_SLOT_WIDTH'(AGE_BOUND);
            end else begin:g_exact
                assign credit_events[credit_class-1]=
                    execution_branch_age==ROB_SLOT_WIDTH'(AGE_BOUND);
            end
            assign credit_values[(credit_class-1)*CREDIT_WIDTH +: CREDIT_WIDTH]=CREDIT_WIDTH'(credit_class);
        end
        rv32_frequency_event_select #(.WIDTH(CREDIT_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) select_credit (
            .events_i(credit_events),.values_i(credit_values),.write_o(),.value_o(recovery_rob_credit));
    end else begin:g_original_recovery_credit
        assign recovery_rob_credit=0;
    end endgenerate
    function [CREDIT_WIDTH-1:0] bounded_credit;''')
    text = once(text, '            rob_credit<=bounded_credit(rob_free_count,used_rob_credit);',
        '''            if(RECOVERY_ROB_CREDIT!=0 && RECOVERY_DIRECT_ACTIVE!=0 && recovery_domains[7])
                rob_credit<=recovery_rob_credit;
            else rob_credit<=bounded_credit(rob_free_count,used_rob_credit);''')
    # The new credit affects the saved acceptance count only. All branch
    # generation qualification, actual ROB allocation and other credits stay exact.
    for marker in [
        'rs_credit<=reserved_credit(rs_free_count,d_reserved_rs,used_rs_credit);',
        'lsq_credit<=reserved_credit(lsq_free_count,d_reserved_lsq,used_lsq_credit);',
        'branch_pending_tag[3 +: ROB_SLOT_WIDTH]-recovery_descriptor_head;',
        'assign recovery_descriptor_head=rob_head_views[0 +: ROB_SLOT_WIDTH];',
        'assign recovery_descriptor_valid=branch_pending && rob_recovery_preview;',
        '.rename_ready_i(!halted_o && !flush_i && !branch_busy_domains[1] && dispatch_packet_ready)',
        'assign rob_alloc_valid = dispatch_valid;',
    ]:
        assert marker in text, marker
    tail = '    wire [BE_WIDTH-1:0] completion_valid_r, completion_done_r, completion_error_r;'
    assert text[text.index(tail):] == original[original.index(tail):]
    changes[name] = text
    for name, default in [('rtl/cpu_core.v', 0), ('rtl/course/student_top.v', 1)]:
        text = (PARENT / name).read_text(encoding='utf-8')
        text = once(text, f'    parameter integer RECOVERY_DIRECT_APPLY = {default},',
            f'    parameter integer RECOVERY_DIRECT_APPLY = {default},\n    parameter integer RECOVERY_ROB_CREDIT = {default},')
        text = once(text, '.RECOVERY_DIRECT_APPLY(RECOVERY_DIRECT_APPLY),',
            '.RECOVERY_DIRECT_APPLY(RECOVERY_DIRECT_APPLY), .RECOVERY_ROB_CREDIT(RECOVERY_ROB_CREDIT),')
        changes[name] = text
    rob = (PARENT / 'rtl/backend/rv32_rob.v').read_text(encoding='utf-8')
    for marker in [
        'occupancy_reg <= branch_age + 1;',
        'branch_age = apply_age;',
        'wire [SLOT_WIDTH-1:0] apply_age = STAGED_RECOVERY ? recovery_saved_age : chosen_age;',
        'wire recovery_apply = STAGED_RECOVERY ?',
        '(recovery_apply_i && recovery_saved_valid) : recovery_found;',
        'if (!recovery_domains[5] && !recovery_hold && !halted_o && !error_o)',
    ]:
        assert marker in rob, marker
    for name in parent['source_sha256']:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, destination)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_DIRECT_RECOVERY_ROB_CREDIT_UNTESTED', source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(), parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), source_review=str(REVIEW),
        tests_started=False, synthesis_started=False, timing_started=False, adopted=False,
        candidate_ipc=None, candidate_area_um2=None, candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], RECOVERY_ROB_CREDIT=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], recovery_post_edge_rob_credit=True,
        recovery_rob_credit_new_ff_bits=0, recovery_rob_credit_new_sram_bits=0,
        recovery_rob_credit_actual_allocation_guard_unchanged=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'At fully qualified direct recovery apply, record min(BE_WIDTH, ROB_ENTRIES-1-pending_branch_age) into the existing ROB credit register. Disjoint constant credit classes reuse the saved branch/head age. This exposes exact post-edge capacity without waiting for the old occupancy to catch up; reset/flush, other recovery modes, ordinary credit transitions, actual ROB allocation and RS/LSQ admission stay unchanged.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        direct_recovery_post_edge_capacity_source_argument=True,
        recovery_rob_credit_old_occupancy_wait_removed=True,
        recovery_rob_credit_limit='Only useful when old advertised credit is insufficient and target/pool/dispatch readiness is sufficient. A36 ROB-full observations are opportunity evidence, not A70 measured saved cycles. New qualified-apply to credit-register path needs future STA.')
    write(TARGET / 'candidate.json', record)
    proof = dict(status=record['status'], candidate=str(TARGET), candidate_sha256=sha(TARGET / 'candidate.json'),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, new_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0,
        source_arguments=[
            'Backend supplies only lane0 pending recovery tag. Original ROB accepts it only with valid-bit, current-slot, full eight-generation-bit membership and age below occupancy. This event already drives recovery_domains[7]. No raw branch prediction/result bypass can write the new credit.',
            'Enabled path additionally requires RECOVERY_DIRECT_ACTIVE. Then descriptor head is current pre-edge ROB head, and execution_branch_age is the same slot-distance as chosen_age. ROB holds head on apply, applies occupancy=branch_age+1, and blocks commit. Backend branch_pending blocks rename and therefore dispatch_valid/ROB allocation. Thus post-edge free slots equal ROB_ENTRIES-1-branch_age exactly.',
            'For credit k below BE_WIDTH, exactly age=ROB_ENTRIES-1-k selects k. The saturated class selects BE_WIDTH for age<=ROB_ENTRIES-1-BE_WIDTH. When k exceeds ROB_ENTRIES-1 the class is constant zero. These classes are disjoint, zero is default, and the result is min(BE_WIDTH, actual post-apply free slots), including BE_WIDTH1/2/4 and small ROB2. Supported ROB depths remain the original required power of two.',
            'Credit register reset/flush priority stays original. Ordinary transition still omits same-edge retirement releases, so remains conservative. On apply the exact recovery credit is written into the existing register; next-cycle actual ROB free count also reflects the same capacity. Original ROB allocation still checks occupancy and accepts only a prefix. RS/LSQ saved credits, elastic packet admission and physical pool count are untouched.',
            'No state, SRAM or ordinary/recovery pipeline edge is added. Disjoint constant classes replace a variable-width arithmetic dependency on this new path. Shared pending age fanout and qualified-apply to credit D/enable can affect Fmax; exact mapped cost, Fmax and IPC remain unknown. Option0 or non-direct profile preserves original saved credit behavior.',
            'Source/hash/manual reasoning only, no HDL execution or equivalence claim. Future coherent batch must cover old-full ROB with middle/head/tail branch, near-tail capacity0/1/2, wrapped head, no killed suffix, consecutive recovery, stale generation/invalid slot, reset/flush priority, retained/empty pool, delayed target response, blocked elastic packet, widths1/2/4 and option0/non-direct fallbacks.'
        ], goal_complete=False)
    write(REVIEW, proof)
    print({key: proof[key] for key in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
