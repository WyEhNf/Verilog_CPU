"""Rebase the narrow registered probe onto EG; source preparation only."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta
from prepare_store_registered_probe import registered_probe, backend


def main():
    parent=ROOT/'EG_prf_parallel_store_address'
    verify_parent(parent)
    out=prepare('EI_eg_registered_shared_store_probe',parent,
        {'rtl/backend/rv32_reservation_station.v':registered_probe,
         'rtl/backend/rv32_backend_joint.v':backend},
        'Narrow alternative to EH: linked shared store probe uses original registered RS base state; ordinary issue retains all same-cycle wake ports. Inherits EG allocation-address restoration. No new FF/cycles in ordinary pipeline. Source-only, unadopted/unmeasured.')
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    record_delta(out,parent,groups+['registered_existing_rs_base_for_shared_store_probe'])
    path=out/'candidate.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        declared_additional_state_bits_vs_parent=0,new_declared_sequential_state_bits=0,
        measured_parent_run=None,measured_reference_run='F:/CPU2026CourseRuns/architecture_EF_20261005',
        behavior='Original normal issue, all wake/ready updates and operand bypass preserved. Only linked read-only shared-store probe uses existing src1 ready/value registers. Allocation early address restored via inherited EG parallel address calculation.',
        timing_tradeoff='Cuts measured EF path 1 through current-cycle LSQ wake -> shared probe. Shared address of newly-woken base can become available later; normal AGU may win. No extra ordinary load/MDU dependent issue cycle as in EH. IPC/area/timing unmeasured.',
        limiting_path_evidence='F:/CPU2026Proofs/EF_mapped_paths_20261005/saved_path_analysis.json',
        existing_clocked_payload_refactor='No clocked change; original RS effective operands retained for issue.',
        adoption_condition='Analyze the nearly equal cache-response paths too; report complete selected combination before any new measurement.')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        adopted=False,tests_started=False,new_declared_state_bits=0)))


if __name__=='__main__':
    main()
