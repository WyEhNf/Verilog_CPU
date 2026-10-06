"""Record DK file identities and measured history; never invoke HDL tools."""
from datetime import datetime, timezone
import difflib
import json
from pathlib import Path
from summarize_course_frequency_native import read, sha

ROOT = Path('E:/Verilog_cpu')
ACTIVE = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
DF1 = Path('F:/CPU2026CourseRuns/architecture_DF1_20261005')
EXPECTED = [
    'rtl/backend/rv32_backend_joint.v',
    'rtl/backend/rv32_lsq.v',
    'rtl/backend/rv32_store_address_select.v',
    'rtl/cache/rv32_dcache_nonblocking.v',
    'rtl/common/rv32_asap7_fanout.v',
]


def main():
    active = read(ACTIVE)
    candidate, run = Path(active['candidate']), Path(active['frozen_run'])
    assert candidate.name == 'DK_store_address_prefix' and not active['tests_started']
    assert sha(run/'source_manifest.json') == active['frozen_manifest_sha256']
    frozen, old_frozen = read(run/'source_manifest.json'), read(DF1/'source_manifest.json')
    for name, expected in active['source_sha256'].items():
        assert sha(ROOT/name) == expected, 'Worktree:'+name
    for source_run, manifest in ((run, frozen), (DF1, old_frozen)):
        for name, expected in manifest['snapshot_sha256'].items():
            assert sha(source_run/'source'/name) == expected, str(source_run)+':'+name
    assert frozen['parameter_overrides'] == old_frozen['parameter_overrides']
    changed = [name for name in active['source_sha256']
               if name.endswith('.v') and sha(ROOT/name) != sha(DF1/'source'/name)]
    assert changed == EXPECTED, changed
    previous = read(Path(active['backup'])/'backup.json')['previous_identity']
    assert Path(previous['frozen_run']) == DF1 and previous['measurement_process_id'] is None
    measured = dict(active['previous_measurement'])
    for key in ('current_correctness_suite_passed', 'completed_ipc_report',
                'directed_result_report', 'limited_directed_cases_passed', 'limited_directed_checks'):
        measured[key] = previous.get(key)
    measured.update(source_manifest_sha256=sha(DF1/'source_manifest.json'),
                    measurement_process_id=None,
                    status='MEASUREMENT_COMPLETE_FULL_CORRECTNESS_NOT_RUN')
    active['previous_measurement'] = measured
    active['last_observed_measurement'] = measured
    history = list(previous.get('background_measurements', []))
    history.append(measured)
    active['background_measurements'] = history
    for key in ('completed_ipc_report', 'directed_result_report',
                'limited_directed_cases_passed', 'limited_directed_checks',
                'measurement_progress_recorded_at', 'metrics_recorded_at'):
        active.pop(key, None)
    report = str(ROOT/'reports/frequency_batch_DK_pretest_2026-10-05.md')
    active.update(implementation_report=report, pretest_report=report)
    review = dict(status='SOURCE_IDENTITIES_AND_MANUAL_REASONING_ONLY_NO_HDL_TEST',
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        active_source_files=len(active['source_sha256']),
        frozen_input_files=len(frozen['snapshot_sha256']),
        changed_rtl_vs_measured_DF1=changed,
        parameter_override_count=len(frozen['parameter_overrides']),
        ordinary_integer_pipeline_stages=10,
        lsq_report_packet_bits_before=74, lsq_report_packet_bits_after=75,
        lsq_report_selection_leaves_before=5, lsq_report_selection_leaves_after=5,
        store_selection_packet_bits_before=38, store_selection_packet_bits_after=46,
        store_selection_leaves_before=3, store_selection_leaves_after=3,
        tests_started=False,
        limitations='No HDL syntax, functionality, mapped fanout, area, IPC, timing, or formal proof; state/cycle preservation inferred by manual source review.')
    active['source_identity_review'] = review
    patch = ''.join(''.join(difflib.unified_diff(
        (DF1/'source'/name).read_text(encoding='utf-8').splitlines(True),
        (run/'source'/name).read_text(encoding='utf-8').splitlines(True),
        fromfile='measured_DF1/'+name, tofile='untested_DK/'+name)) for name in changed)
    (run/'changes_vs_DF1.patch').write_text(patch, encoding='utf-8')
    preparation = [ROOT/'tools'/name for name in (
        'prepare_dcache_merge_controls.py', 'prepare_lsq_report_cancel.py',
        'prepare_store_address_onehot.py', 'prepare_store_address_prefix.py')]
    artifact = dict(review, source_manifest_sha256=sha(run/'source_manifest.json'),
        patch_sha256=sha(run/'changes_vs_DF1.patch'),
        preparation_scripts_sha256={str(p):sha(p) for p in preparation},
        source_sha256={name:sha(run/'source'/name) for name in changed})
    (run/'implementation_review.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(review,source_manifest_sha256=artifact['source_manifest_sha256']),ensure_ascii=False))


if __name__ == '__main__':
    main()
