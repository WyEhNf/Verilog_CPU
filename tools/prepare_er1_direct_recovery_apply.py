"""Prepare a direct recovery-apply candidate without executing HDL tools."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A64_ras_repeat_compression'
TARGET = BASE / 'A65_direct_recovery_apply'
REVIEW = BASE / 'A65_source_review.json'
PROFILE = Path('F:/CPU2026Proofs/ER1_A36_three_case_profile_20261005/result.json')


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
    text = once(original, '    parameter integer EARLY_FRONT_REDIRECT = 0,',
        '''    parameter integer EARLY_FRONT_REDIRECT = 0,
    // The branch result remains captured. Apply its full qualified recovery
    // on the next edge, using the original direct ROB recovery implementation.
    parameter integer RECOVERY_DIRECT_APPLY = 0,''')
    marker = '    reg recovery_descriptor_valid;'
    text = once(text, marker, '''    localparam integer RECOVERY_DIRECT_ACTIVE=(RECOVERY_DIRECT_APPLY!=0) &&
        (EARLY_FRONT_REDIRECT!=0) && (LOCAL_EXEC_RECOVERY!=0) &&
        (CHECKPOINT_IMPL!=0) && (RAT_RECOVERY_IMPL!=0);
    wire recovery_descriptor_valid;''')
    scalar_fields = {
        'recovery_descriptor_valid': '',
        'recovery_descriptor_reclaim_count': '[FREE_COUNT_WIDTH-1:0] ',
        'recovery_descriptor_head': '[ROB_SLOT_WIDTH-1:0] ',
        'recovery_descriptor_occupancy': '[ROB_COUNT_WIDTH-1:0] ',
        'recovery_descriptor_rs_kill': '[RS_ENTRIES-1:0] ',
    }
    for field, width in scalar_fields.items():
        if field != 'recovery_descriptor_valid':
            text = once(text, f'    reg {width}{field};', f'    wire {width}{field};')
    text = once(text,
        '''    wire recovery_preview_fire = branch_pending && rob_recovery_preview &&
        !recovery_descriptor_valid && !flush_i;''',
        '''    // Preview remains the same qualified branch event. In direct mode
    // it is also the apply edge; no descriptor-valid feedback drives preview.
    wire recovery_preview_fire = branch_pending && rob_recovery_preview &&
        ((RECOVERY_DIRECT_ACTIVE!=0) || !recovery_descriptor_valid) && !flush_i;''')
    text = once(text, '.STAGED_RECOVERY(1)', '.STAGED_RECOVERY(RECOVERY_DIRECT_ACTIVE==0)')
    start = '    rv32_frequency_word_bank #(.WIDTH(CHECK_RAT_WIDTH)) rat_descriptor_owner ('
    end = '    // Only accepted live redirects can acquire this packet.'
    a, b = original.index(start), original.index(end)
    old_owners = original[a:b].rstrip()
    saved_owners = old_owners
    for field in scalar_fields:
        saved_owners = saved_owners.replace(field, field + '_saved')
    declarations = '\n'.join(f'        reg {width}{field}_saved;' for field, width in scalar_fields.items())
    aliases = '\n'.join(f'        assign {field}={field}_saved;' for field in scalar_fields)
    replacement = '''    generate if(RECOVERY_DIRECT_ACTIVE!=0) begin:g_direct_recovery_descriptor
        // All consumers share the current pre-edge ROB prefix. No allocation
        // or commit occurs on this apply edge; full GEN authority stays in ROB.
        assign recovery_descriptor_valid=branch_pending && rob_recovery_preview;
        assign recovery_descriptor_rat=recovery_rat_state;
        assign recovery_descriptor_reclaim=rob_recovery_reclaim_bitmap;
        assign recovery_descriptor_reclaim_count=rob_recovery_reclaim_count;
        assign recovery_descriptor_head=rob_head_views[0 +: ROB_SLOT_WIDTH];
        assign recovery_descriptor_occupancy=rob_occupancy;
        assign recovery_descriptor_rs_kill=rs_preview_kill_mask;
    end else begin:g_staged_recovery_descriptor
''' + declarations + '\n' + aliases + '\n' + saved_owners + '\n    end endgenerate\n\n'
    text = once(text, original[a:b], replacement)
    # Everything after the descriptor block (including branch ownership and
    # history repair) is byte-exact. Disabled owners differ only in local names.
    assert text[text.index(end):] == original[original.index(end):]
    reverse = saved_owners
    for field in scalar_fields:
        reverse = reverse.replace(field + '_saved', field)
    assert reverse == old_owners
    changes[name] = text
    for name, default in [('rtl/cpu_core.v', 0), ('rtl/course/student_top.v', 1)]:
        original_wrapper = (PARENT / name).read_text(encoding='utf-8')
        text = once(original_wrapper, f'    parameter integer EARLY_FRONT_REDIRECT = {default},',
            f'    parameter integer EARLY_FRONT_REDIRECT = {default},\n    parameter integer RECOVERY_DIRECT_APPLY = {default},')
        text = once(text, '.EARLY_FRONT_REDIRECT(EARLY_FRONT_REDIRECT),',
            '.EARLY_FRONT_REDIRECT(EARLY_FRONT_REDIRECT), .RECOVERY_DIRECT_APPLY(RECOVERY_DIRECT_APPLY),')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, destination)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_DIRECT_RECOVERY_APPLY_UNTESTED', source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(), parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_from_parent_files=list(changes),
        source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), source_review=str(REVIEW),
        tests_started=False, synthesis_started=False, timing_started=False, adopted=False,
        candidate_ipc=None, candidate_area_um2=None, candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], RECOVERY_DIRECT_APPLY=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], direct_recovery_apply=True,
        branch_result_capture_preserved=True, recovery_descriptor_backend_ff_bits_removed=274,
        recovery_wait_edges_removed=1, full_rob_generation_width_unchanged=8)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Apply recovery on the first qualified preview edge after registered branch capture. Reuse existing ROB STAGED_RECOVERY=0, feed RAT/free-list/RS/LSQ/held execution/completion consumers the same current pre-edge prefix, and remove backend descriptor owners. Rename/allocation/commit remain excluded on apply, branch destination and full generation checks are retained. Staged fallback remains default outside the qualified profile.'
    ]
    reference = read(PROFILE)
    evidence = []
    for row in reference['results']:
        o = row['observations']
        evidence.append(dict(name=row['name'], reference='A36, not A55/A65', cycles=row['cycles'],
            observed_pending_edges=o['branch_pending'], observed_redirect_events=o['branch_pending_rising_events'],
            one_edge_per_event_reference_fraction=o['branch_pending_rising_events']/row['cycles'],
            scope='Reference opportunity scale only; overlapping bubbles, predictor differences, useful older issue and free-pool refill prevent treating it as measured or guaranteed saved cycles.'))
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        direct_recovery_reference_profile=evidence, direct_recovery_ipc_area_frequency_unknown=True,
        direct_recovery_remaining_free_pool_refill_edge=True,
        direct_recovery_limit='Remove one backend recovery wait edge, not every frontend or rename bubble. Restoring RAT and free bitmap directly can lengthen critical recovery paths; no proof of >300MHz or IPC1.1.')
    write(TARGET / 'candidate.json', record)
    review = dict(status='SOURCE_DIRECT_RECOVERY_APPLY_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'), changed_files=list(changes), tests_started=False, adopted=False,
        backend_descriptor_ff_bits_removed=274, new_ff_bits=0, new_sram_bits=0,
        branch_capture_edge_preserved=True, recovery_wait_edges_removed=1,
        rob_source_unchanged=True, rob_staged_zero_saved_payload_unconsumed_bits=43,
        reference_profile=str(PROFILE), reference_profile_sha256=sha(PROFILE), reference_opportunity=evidence,
        source_arguments=[
            'Capture c still selects the same accepted live redirect and stores tag/value/PC with full GEN qualification. Current ROB head/occupancy include any older commits or captured-edge allocations before recovery. First pending edge c+1 retains ROB full valid/GEN and age checks, applies the retained prefix and increments its sole epoch once; no raw ALU-to-restore shortcut is added.',
            'ROB preview depends on pending tag, current valid/generation and age/occupancy, not its apply input. STAGED_RECOVERY0 uses that qualified preview directly. Descriptor valid is its alias; recovery_preview_fire ignores descriptor-valid only in this mode. RAT recovery inputs are registered mappings/ROB payloads. These sources add no data feedback from restored outputs to qualification.',
            'On apply, backend branch_pending inhibits rename, dispatch admission and LSQ/RS allocation. ROB direct recovery inhibits commit and allocation. Thus all rollback consumers read the same pre-edge head/occupancy. The old scalar and wide descriptor owners remain byte-identical modulo local saved-signal names in default staged fallback.',
            'RAT undo retains the branch destination. Free-list restoration adds only current qualified younger destination reclaim bitmap/count. The registered free pool still clears on restore and must refill afterward; do not promise same-edge target rename or infer one useful cycle saved per redirect.',
            'RS kill mask, RS full-GEN issue qualification, ALU/MDU incoming and held cancellation, LSQ responses/retired-load exclusion, completion kills and D-stage selective recovery use current pre-edge head/occupancy on the same apply edge. Their source and interfaces are otherwise unchanged. Existing branch link-result injection and branch history capture/repair remain byte-exact.',
            'After apply branch_pending clears, so stale descriptor state cannot cause a second apply. ROB and frontend epochs retain their old qualified-redirect identities; only ROB application catches up one edge earlier. Reset and flush priorities remain in original owners.',
            'Course descriptor removal is192 RAT+56 reclaim+6 reclaim count+5 head+6 occupancy+8 RS kill+1 valid=274 logical FF bits. Existing direct ROB mode does not consume43 saved descriptor bits; actual mapped sequential/combinational/total area requires synthesis. No SRAM or architectural state is removed.',
            'Qualification requires early frontend redirect, local execution recovery and nonzero checkpoint/parallel RAT modes. Core/backend default0 and unsupported configurations preserve staging. Course top1 selects the existing intended profile. Source algebra and block identity only, not HDL equivalence or measured gain.',
            'Future coherent batch must cover full RV32IM correctness, same-edge older completion/LSQ response, branch link destination, head wrap/full ROB, killed MDU operations, late old LSQ response/GEN reuse, D-stage survivors, reset/flush, direct0/1 and fallback profiles, followed by official IPC/area/STA. No such execution started.'
        ],
        timing_risks=['Pending tag/head -> RAT undo selection -> rename mapping FF',
            'ROB younger destination bitmap/popcount -> free bitmap/count restore',
            'Full ROB live qualification -> apply control -> LSQ/execution cancellation and ready'],
        goal_complete=False)
    write(REVIEW, review)
    print({k:review[k] for k in ('status','candidate','candidate_sha256','changed_files','tests_started','backend_descriptor_ff_bits_removed')})


if __name__ == '__main__':
    main()
