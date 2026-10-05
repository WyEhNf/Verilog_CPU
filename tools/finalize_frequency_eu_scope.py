"""Finalize reviewed EU scope from immutable source evidence, without tests."""
from datetime import datetime, timezone
import json
from pathlib import Path
from start_reused_frequency_programs_background import ROOT, ACTIVE, read, sha


def main():
    active=read(ACTIVE)
    source_review=Path('F:/CPU2026Proofs/EU_source_review_20261005/source_review.json')
    review=read(source_review)
    assert active['measurement_process_id'] is None
    assert active['status']=='WORKTREE_IMPLEMENTED_TIMING_ONLY_COMPLETE_PROGRAMS_NOT_RUN'
    assert review['candidate_manifest_sha256']==sha(Path(review['candidate'])/'candidate.json')
    assert not review['tests_started'] and not review['adopted']
    for n,h in active['source_sha256'].items():
        assert sha(ROOT/n)==h,n
    run=Path(active['frozen_run'])
    manifest=read(run/'source_manifest.json')
    for n,h in manifest['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    path=source_review.with_name('final_scope_review.json')
    assert not path.exists()
    final=dict(review)
    final.update(finalized_at=datetime.now(timezone.utc).isoformat(),
        immutable_source_review=str(source_review),immutable_source_review_sha256=sha(source_review),
        new_test_started=False,scope_finalized=True,
        architecture_triage=[
            'ER1 exported five paths are all LSQ report/full ROB authority/direct CDB/source value to early store addition. ET moves arithmetic before that source mask, including zero/default and branch-link/current-offset identities; this is the main new structural cut.',
            'ES retains the exact old winner/default as parallel circular prefix packet. It is a previously measured request-bottleneck backstop after the current chain is shortened, not asserted to appear in ER1 top5. Its code and proof compose into EU unchanged.',
            'Registering LSQ load report or delaying every load/MDU wake could cut the whole chain but adds a dependent opportunity cycle to unknown IPC; not included. Normal ROB live/generation and committed-store permissions must remain. No optimistic load/replay or authority deletion.',
            'Further ROB live before row selection needs replicated full-generation lookups and area/source identity review; currently conditional rather than an implementation justified for this batch. Shrinking windows/ports/caches would change IPC and is not mixed into the frequency-focused batch.',
            'All justified source changes in the complete EU batch are implemented and source-reviewed. No additional source change is currently justified for this batch. Freeze the whole identity and deliver a concrete pretest report before one native background timing-only; no intermediate or program tests.'])
    path.write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    active['measurement_plan']['historical_best_reference_mhz']=max(
        row['current_measured_fmax_mhz'] for row in active['timing_only_measurement_history'])
    active['pending_source_research']=[]
    active['source_research_decision']=final['architecture_triage'][-1]
    active['EU_final_source_scope_review']=str(path)
    active['EU_final_source_scope_review_sha256']=sha(path)
    ACTIVE.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(review=str(path),review_sha256=sha(path),
        candidate=final['candidate'],source_groups=final['source_groups'],new_test_started=False)))


if __name__=='__main__':
    main()
