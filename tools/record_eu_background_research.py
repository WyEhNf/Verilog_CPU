"""Record read-only EU background research and unchanged measurement identity."""
from datetime import datetime, timezone
import json
from pathlib import Path
from start_reused_frequency_programs_background import ROOT, ACTIVE, read, sha


def main():
    active=read(ACTIVE)
    run=Path(active['frozen_run'])
    assert run.name=='architecture_EU_20261005'
    manifest=read(run/'source_manifest.json')
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    for n,h in active['source_sha256'].items():
        assert sha(ROOT/n)==h,n
    for n,h in manifest['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    dispatch=read(run/'dispatch_identity.json')
    assert dispatch['timing_only_requested'] and not dispatch['cpu_build_and_simulation_requested']
    for n in ('native_build','native_ipc','program_dispatch_identity.json','result/ipc.json','result/result.json'):
        assert not (run/n).exists(),n
    report=ROOT/'reports/frequency_EU_background_research_2026-10-05.md'
    out=Path('F:/CPU2026Proofs/EU_background_research_20261005.json')
    assert not out.exists()
    proof=dict(created_at=datetime.now(timezone.utc).isoformat(),status='EU_BACKGROUND_SOURCE_RESEARCH_ONLY',
        report=str(report),report_sha256=sha(report),source_manifest_sha256=active['frozen_manifest_sha256'],
        worktree_inputs_unchanged=len(active['source_sha256']),frozen_inputs_unchanged=len(manifest['snapshot_sha256']),
        inspected_source_sha256={n:sha(ROOT/n) for n in ('rtl/backend/rv32_backend_joint.v',
            'rtl/rv32_physical_register_file.v','rtl/backend/rv32_reservation_station.v')},
        conditional_directions=['Full current ROB valid+generation query before LSQ report winner, with replication/default/recovery costs.',
            'Selective deferral of same-cycle WB-based store allocation address through existing registered RS/shared probe; IPC and lifecycle review required.'],
        new_candidate_created=False,new_hardware_change=False,new_additional_test_started=False,
        current_EU_timing_job_only=True,program_phase_started=False,
        limits='Source/owner and saved-path reading only; no HDL/formal/EDA/program run in this research recorder.')
    out.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    active.update(ongoing_research_report=str(report),last_background_source_research={
        **proof,'proof':str(out),'proof_sha256':sha(out)})
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:proof[k] for k in ('status','worktree_inputs_unchanged',
        'frozen_inputs_unchanged','new_candidate_created','new_hardware_change','new_additional_test_started')}))


if __name__=='__main__':
    main()
