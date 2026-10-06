"""Repair one SystemVerilog reserved identifier in the untested region cache."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A33_resolved_store_alloc_load_bypass'
TARGET=BASE/'A34_region_query_native_compat'


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    name='rtl/cache/rv32_icache_nonblocking.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    assert len(re.findall(r'\bmatches\b',original))==3
    text=re.sub(r'\bmatches\b','region_query_matches',original)
    assert text.replace('region_query_matches','matches')==original
    for source_name in parent['source_sha256']:
        dest=TARGET/source_name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/source_name,dest)
    (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=[name],source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Alpha-rename three region-query uses of SystemVerilog reserved identifier matches to region_query_matches; no logic or behavior changes.'
    ]
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_ALPHA_RENAME_NATIVE_COMPATIBILITY_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),changed_files=[name],
        renamed_tokens=3,reverse_alpha_rename_text_exact=True,
        new_state_bits=0,added_pipeline_cycles=0,tests_started=False,adopted=False,
        source_arguments=[
            'matches is a SystemVerilog keyword. The declaration, fanout output and row part-select share the same alpha-renamed local signal.',
            'Reverse alpha-renaming reproduces the parent source exactly. Every other candidate source hash matches the parent.',
            'This preparation performs no HDL build, lint, simulation, synthesis, STA, CPU/perf or unit tests. No metric improvement is claimed.'
        ])
    write(BASE/'A34_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':main()
