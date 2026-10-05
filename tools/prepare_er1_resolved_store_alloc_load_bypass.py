"""Permit existing resolved-store forwarding on early allocated-load selection."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A32_region_owned_icache_tags'
TARGET=BASE/'A33_resolved_store_alloc_load_bypass'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():assert sha(PARENT/name)==digest,name
    name='rtl/backend/rv32_lsq.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'''    // This conservative shortcut never passes an existing store or a store
    // in an earlier lane of the same allocated bundle.''','''    // Unresolved stores still block this shortcut. Fully resolved stores,
    // including earlier accepted lanes, use the existing next-cycle youngest
    // byte forwarding/hazard machinery after full LSQ row ownership exists.''')
    assert text.count('allocation_older_stores')==3
    text=text.replace('allocation_older_stores','allocation_unresolved_stores')
    assert text.count('allocation_prior_store')==5
    text=text.replace('allocation_prior_store','allocation_prior_unresolved_store')
    text=once(text,'            assign allocation_unresolved_stores[early_row]=valid_mem[early_row] && store_mem[early_row];','''            assign allocation_unresolved_stores[early_row]=valid_mem[early_row] && store_mem[early_row] &&
                (!addr_ready_mem[early_row] || !data_ready_mem[early_row]);''')
    text=once(text,'''                    (alloc_fire_o[early_lane-1] && alloc_is_store_i[early_lane-1]);''','''                    (alloc_fire_o[early_lane-1] && alloc_is_store_i[early_lane-1] &&
                     (!alloc_addr_valid_i[early_lane-1] || !alloc_data_valid_i[early_lane-1]));''')
    marker='    wire forwarding_hold_write='
    assert text[text.index(marker):]==original[original.index(marker):]
    for name2 in parent['source_sha256']:
        dest=TARGET/name2;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name2,dest)
    (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=[name],source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['enabled_profile']=dict(parent['enabled_profile'],allocation_load_bypass_allows_resolved_stores=True,
        allocation_load_bypass_allows_resolved_prior_lane_stores=True,
        allocation_load_bypass_added_address_comparisons=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Allow ready allocated load selection behind fully resolved existing/earlier-lane stores; retain conservative blocking of every unknown-address/data store and use unchanged next-cycle youngest-byte forwarding.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        allocation_load_old_guard_rejected_all_stores=True,
        allocation_load_new_guard_rejects_unresolved_stores=True,
        allocation_load_added_address_comparisons=0,
        allocation_load_resolved_store_trigger_rate_and_ppa_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_READY_LOAD_SELECTION_RESOLVED_STORE_FORWARDING_REUSED_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),changed_files=[name],tests_started=False,
        source_arguments=[
            'A28 rejected any existing or earlier-lane store, even when address/data were ready. New guard rejects every valid store with unknown address OR unknown data; it remains more conservative than original normal eligibility for nonoverlapping unknown-data stores.',
            'Earlier accepted store lanes likewise must have both allocation address/data valid. Their original full payload/mask/generation/valid capture occurs on the same edge as load selection, so they are present as older stores when selected load forwarding executes.',
            'No request or forwarding executes on allocation edge. Existing full LSQ generation/valid selection_live check and next-cycle byte window/tournament use selected load address/mask and circular head age. Youngest older overlapping store wins each byte, fully covered loads complete without a cache request, partial forward is retained over backpressure.',
            'Resolved existing store address/data readiness is monotonic during its lifetime. A retired/freed slot is absent or younger after reuse; original circular age and full selection tag keep it from becoming an older false forward owner. Recovery still kills a younger load if its earlier speculative store is killed.',
            'Normal older eligible operation retains absolute priority; same selected slot exclusion, capture acceptance, held packet, cache ready, generation/discard/reset/recovery and all clocked LSQ source remain unchanged.',
            'Only two guarded registered ready flags per existing row and two allocation-valid flags per prior lane are added. No32/28-bit store/load address comparison, new state, register boundary or cache port is introduced.',
            'Material opportunity is the original one saved wait edge now available behind pending-but-resolved stores, including forwarding cases. Actual trigger rate and IPC/area/Fmax remain unknown.',
            'No HDL build, lint, simulation, synthesis, STA, CPU/perf or unit tests. Relevant later coverage needs overlapping/partial byte forwards, multiple old stores, sparse store-before-load lanes, unknown address/data stalls, wrap/reuse/recovery and MMIO order.'
        ])
    write(BASE/'A33_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':main()
