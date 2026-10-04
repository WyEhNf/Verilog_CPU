"""Prepare an unadopted EA alternative during its frozen background run."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta
from prepare_store_registered_probe import registered_probe, backend


def main():
    parent=ROOT/'EA_combined_control_locality'
    verify_parent(parent)
    out=prepare('EB_ea_registered_store_probe',parent,
        {'rtl/backend/rv32_reservation_station.v':registered_probe,
         'rtl/backend/rv32_backend_joint.v':backend},
        'Conditional follow-up to frozen EA: linked early store-address probe uses existing registered RS base readiness/value, while ordinary issue still includes current-cycle CDB bypass. No extra state, no ordinary pipeline edge. May delay early store-address availability. Source-only, unadopted; select only if EA timing still proves this wake/probe cone is limiting.')
    record_delta(out,parent,['allocation_store_signed_12bit_adder','shared_store_signed_12bit_adder',
        'negative_polarity_distribution','local_lsq_request_and_forwarding_owner',
        'lsq_report_rob_slot_predecode','rat_recovery_architectural_domains',
        'icache_request_queue_word_owners','icache_promoted_response_metadata_domains',
        'registered_existing_rs_base_for_early_store_probe'])
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        declared_additional_state_bits_vs_parent=0,new_declared_sequential_state_bits=0,
        adoption_condition='First inspect completed EA mapped path evidence. Adopt only if current-cycle CDB wake -> early store probe remains material; report the store-address availability tradeoff before any measurement.',
        behavior='Early probe uses existing registered source state. Ordinary issue/wakeup, normal ALU address updates, complete tags, and in-order store commit are unchanged.',
        timing_tradeoff='Removes same-cycle wake dependence from the opportunistic probe; may defer store-conflict release by a cycle or allow normal ALU update to win. IPC benefit is not claimed.')
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256((out/'candidate.json').read_bytes()).hexdigest(),
                         tests_started=False,adopted=False)))


if __name__=='__main__':main()
