"""Record the six-part DM1 source batch and retain independent DF1 measurements."""
from pathlib import Path
from datetime import datetime,timezone
import json,difflib
from summarize_course_frequency_native import read,sha

ROOT=Path('E:/Verilog_cpu')
ACTIVE=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
DF1=Path('F:/CPU2026CourseRuns/architecture_DF1_20261005')
DK=Path('F:/CPU2026CourseRuns/architecture_DK_20261005')
EXPECTED=[
    'rtl/backend/rv32_backend_joint.v',
    'rtl/backend/rv32_lsq.v',
    'rtl/backend/rv32_reservation_station.v',
    'rtl/backend/rv32_store_address_select.v',
    'rtl/cache/rv32_dcache_nonblocking.v',
    'rtl/common/rv32_asap7_fanout.v',
]


def main():
    active=read(ACTIVE)
    run,candidate=Path(active['frozen_run']),Path(active['candidate'])
    assert candidate.name=='DM1_lsq_report_bound_widths' and not active['tests_started']
    frozen,df1,dk=read(run/'source_manifest.json'),read(DF1/'source_manifest.json'),read(DK/'source_manifest.json')
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    for source_run,manifest in ((run,frozen),(DF1,df1),(DK,dk)):
        for name,expected in manifest['snapshot_sha256'].items():
            assert sha(source_run/'source'/name)==expected,str(source_run)+':'+name
    for name,expected in active['source_sha256'].items():
        assert sha(ROOT/name)==expected,'Worktree:'+name
    assert frozen['parameter_overrides']==df1['parameter_overrides']==dk['parameter_overrides']
    changed=[n for n in active['source_sha256'] if n.endswith('.v') and sha(ROOT/n)!=sha(DF1/'source'/n)]
    assert changed==EXPECTED,changed
    changed_dk=[n for n in changed if sha(ROOT/n)!=sha(DK/'source'/n)]
    assert changed_dk==EXPECTED[:4],changed_dk
    previous=read(Path(active['backup'])/'backup.json')['previous_identity']
    assert Path(previous['frozen_run'])==DK and previous['tests_started'] is False
    active['previous_implementation_identity']=dict(candidate=previous['candidate'],frozen_run=str(DK),
        source_manifest_sha256=sha(DK/'source_manifest.json'),tests_started=False)
    active['previous_measurement']=previous['last_observed_measurement']
    active['last_observed_measurement']=previous['last_observed_measurement']
    for key in ('completed_ipc_report','directed_result_report','limited_directed_cases_passed',
                'limited_directed_checks','measurement_progress_recorded_at','metrics_recorded_at',
                'pretest_report_sha256'):
        active.pop(key,None)
    report=str(ROOT/'reports/frequency_batch_DM1_pretest_2026-10-05.md')
    active.update(implementation_report=report,pretest_report=report,
        research_status='SIX_COMBINED_SOURCE_RESTRUCTURINGS_IMPLEMENTED_REMAINING_DIRECTIONS_EVALUATED',
        test_start_condition='Deliver the final DM1 pretest report before one native background course measurement; no per-edit tests.')
    review=dict(status='SOURCE_IDENTITIES_AND_MANUAL_REASONING_ONLY_NO_HDL_TEST',
        reviewed_at=datetime.now(timezone.utc).isoformat(),active_source_files=len(active['source_sha256']),
        frozen_input_files=len(frozen['snapshot_sha256']),changed_rtl_vs_measured_DF1=changed,
        changed_rtl_vs_untested_DK=changed_dk,parameter_override_count=len(frozen['parameter_overrides']),
        ordinary_integer_pipeline_stages=10,combined_implementation_groups=6,
        new_declared_link_state_bits=80,store_association_full_tag_pairs_before=192,
        store_association_full_tag_pairs_after=0,linked_rs_slot_bits=4,
        store_ready_distribution_bits_before=216,store_ready_distribution_bits_after=12,
        report_end_bits=6,report_end_domains=4,report_packet_bits=75,report_selection_leaves=5,
        tests_started=False,
        limitations='Manual ownership/algebra reasoning and file identities only; not HDL syntax, functional/parametric proof, mapped cell count, area, IPC, fanout, or timing evidence.')
    active['source_identity_review']=review
    scripts=[ROOT/'tools'/n for n in ('prepare_dcache_merge_controls.py','prepare_lsq_report_cancel.py',
        'prepare_store_address_onehot.py','prepare_store_address_prefix.py','prepare_store_rs_links.py',
        'prepare_store_rs_link_domains.py','prepare_lsq_report_bounds.py','prepare_lsq_report_bound_widths.py')]
    patch=''.join(''.join(difflib.unified_diff((DF1/'source'/n).read_text(encoding='utf-8').splitlines(True),
        (run/'source'/n).read_text(encoding='utf-8').splitlines(True),fromfile='measured_DF1/'+n,
        tofile='untested_DM1/'+n)) for n in changed)
    (run/'changes_vs_DF1.patch').write_text(patch,encoding='utf-8')
    artifact=dict(review,source_manifest_sha256=sha(run/'source_manifest.json'),
        patch_sha256=sha(run/'changes_vs_DF1.patch'),preparation_scripts_sha256={str(p):sha(p) for p in scripts},
        source_sha256={n:sha(run/'source'/n) for n in changed})
    (run/'implementation_review.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(review,source_manifest_sha256=artifact['source_manifest_sha256']),ensure_ascii=False))


if __name__=='__main__':main()
