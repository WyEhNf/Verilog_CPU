"""Remove live AGU data from the empty LSQ selection shortcut, without HDL tests."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A47_recovery_apply_older_issue'
TARGET = BASE / 'A48_lsq_registered_address_bypass'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not (BASE / 'A48_source_review.json').exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer EMPTY_SELECTION_BYPASS = 0,',
        '''    // 0: registered selection; 1: empty fallthrough with AGU lookthrough;
    // 2: empty fallthrough from registered addresses only (shorter timing path).
    parameter integer EMPTY_SELECTION_BYPASS = 0,''')
    text = once(text, '''    // Selection is still registered: this folds address ownership and
    // selection capture into one edge without a bypass to the D-cache.''',
        '''    // Modes0/1 retain the live AGU address view. Mode2 deliberately uses
    // only saved addresses: an unknown-address load waits for its original
    // address owner, then can fall through an empty selection slot. This cuts
    // AGU data out of request eligibility, oldest selection and SRAM address.''')
    text = once(text, '        if(LOAD_ADDRESS_LOOKTHROUGH!=0 && REQUEST_PIPELINE!=0) begin:g_enabled',
        '        if(LOAD_ADDRESS_LOOKTHROUGH!=0 && REQUEST_PIPELINE!=0 && EMPTY_SELECTION_BYPASS!=2) begin:g_enabled')
    # Everything after the address view (age/hazards/pick/forwarding/ticket
    # backpressure/lifecycle) is exactly the existing A47 implementation.
    marker = '    wire [LSQ_ENTRIES-1:0] request_eligible;'
    assert text[text.index(marker):] == original[original.index(marker):]
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer LSQ_EMPTY_SELECTION_BYPASS = 1,',
        '    parameter integer LSQ_EMPTY_SELECTION_BYPASS = 2,')
    changes[name] = text
    for name in parent['source_sha256']:
        dst = TARGET / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, dst)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT / 'candidate.json'),
        changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), tests_started=False, adopted=False)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], LSQ_EMPTY_SELECTION_BYPASS=2)
    record['enabled_profile'] = dict(parent['enabled_profile'], LOAD_ADDRESS_LOOKTHROUGH=0,
        lsq_empty_bypass_uses_registered_address=True,
        lsq_live_agu_to_cache_data_path_removed=True,
        lsq_registered_address_bypass_added_ff_bits=0,
        lsq_registered_address_bypass_added_sram_bits=0,
        lsq_registered_address_bypass_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Course EMPTY_SELECTION_BYPASS2 prunes the current AGU load-address lookthrough and uses stored LSQ address/ready state throughout eligibility, oldest pick and direct cache offer. Retain mode1 for the prior shortcut and mode0 for the original selection stage. Original AGU address owner, tag checks and forwarding remain unchanged.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        live_agu_data_to_direct_cache_address_structurally_removed=True,
        known_queued_load_can_skip_selection_wait=True,
        newly_agu_resolved_load_empty_ready_port_latency_equal_a41_source_timeline=True,
        lsq_registered_address_bypass_mapped_area_and_frequency_unknown=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_LSQ_REGISTERED_ADDRESS_BYPASS_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False, added_ff_bits=0, added_sram_bits=0, added_pipeline_edges=0,
        source_arguments=[
            'The mode2 generate branch assigns request_addr=addr_mem and request_addr_ready=addr_ready_mem for every row. All live AGU address payload selectors and their per-row full-tag update matches are pruned from request selection; the original sequential full-tag AGU address owner remains. Store hazards and youngest-per-byte forwarding already use saved store address/data/mask.',
            'A newly resolved load with empty selection and a ready cache crosses its AGU address ownership edge, then offers directly during the following cycle. A41 instead captures the live address in its selection owner on that edge and offers next cycle. Under those stated conditions the nominal request edge is the same; this is a source timeline argument, not a measured latency result. Occupied tickets, allocation fastpaths and cache stalls can have different schedules.',
            'For a previously allocated load whose address is already registered when the selection owner becomes empty, mode2 can offer and complete without a separate selection capture edge. Original full LSQ generation, ROB identity, oldest eligible pick, unknown-store blockers, full/partial byte forwarding and stall snapshots remain exact A47 source.',
            'Ready0 captures the identical existing ticket and forwarding snapshot; ready1 consumes once without recapture. Newly allocated rows and stores keep their original selection rules. Recovery/reset/flush gates and original request/response state writers are unchanged.',
            'Mode0 and mode1 have the same address-view elaboration as A47. REQUEST_PIPELINE0 still uses saved addresses, and standalone/core defaults remain0. The course top changes only LSQ_EMPTY_SELECTION_BYPASS1 to2. No MDU/ALU/predictor/frontend/cache/ROB source changes are made in this candidate.',
            'This removes the newly joined live-AGU-to-cache DATA path, but the registered-address hazard/pick/forward/cache control path still needs future timing measurement. Area may fall from pruning address selectors, but neither totalarea nor Fmax is inferred from source counts. The308MHz metric remains A41-only.',
            'No HDL/lint/simulation/synthesis/STA/unit execution. Later meaningful coverage includes AGU address becoming valid with empty/occupied ticket and stalled cache, registered queued loads with older unresolved/overlapping stores, exact byte forwarding, allocation/reclaim collisions, recovery and mode0/1/2 fallback.'
        ])
    write(BASE / 'A48_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'changed_files', 'tests_started')})


if __name__ == '__main__':
    main()
