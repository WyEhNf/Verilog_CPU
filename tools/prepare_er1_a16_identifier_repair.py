"""Rename one SV-reserved local in an immutable, otherwise identical A16 child."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
from manage_frozen_baseline_programs import ROOT, read, sha, write
from wait_frequency_directed_native import live

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A16_shared_barrel_elastic_dispatch'
TARGET = BASE/'A16R1_shared_barrel_elastic_dispatch'
FAILED_RUN = Path('F:/CPU2026CourseRuns/ER1_A16_tier3_20261005')


def main():
    assert not TARGET.exists()
    assert not live(read(FAILED_RUN/'dispatch_identity.json')['process_id'])
    failure_log = FAILED_RUN/'native_build/build.log'
    assert 'syntax error, unexpected matches' in failure_log.read_text(encoding='utf-8')
    parent = read(PARENT/'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
        destination = TARGET/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT/name, destination)
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_bytes()
    edits = [(b'wire [BE_WIDTH-1:0] matches;', b'wire [BE_WIDTH-1:0] load_address_matches;'),
             (b'assign matches[address_lane]', b'assign load_address_matches[address_lane]'),
             (b'.events_i(matches),.values_i(addr_update_i)', b'.events_i(load_address_matches),.values_i(addr_update_i)')]
    corrected = original
    for before, after in edits:
        assert corrected.count(before) == 1, before
        corrected = corrected.replace(before, after)
    reversed_text = corrected
    for before, after in edits:
        assert reversed_text.count(after) == 1, after
        reversed_text = reversed_text.replace(after, before)
    assert reversed_text == original
    (TARGET/name).write_bytes(corrected)
    record = dict(parent)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=[name],
        source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),
        compatibility_repair='Only three occurrences of local SV-reserved matches renamed to load_address_matches; exact reverse-byte equality.')
    record['implemented_changes'] = list(parent['implemented_changes']) + [record['compatibility_repair']]
    write(TARGET/'candidate.json',record)
    unchanged = [n for n in parent['source_sha256'] if n != name]
    assert all(sha(TARGET/n) == parent['source_sha256'][n] for n in unchanged)
    proof = dict(status='IDENTIFIER_ONLY_REPAIR_SOURCE_REVERSE_BYTE_IDENTITY',
        candidate=str(TARGET), candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=sha(PARENT/'candidate.json'), changed_files=[name],
        unchanged_source_hash_entries=len(unchanged), identifier_occurrences_changed=3,
        reversed_source_exact_parent_bytes=True, original_sha256=sha(PARENT/name), corrected_sha256=sha(TARGET/name),
        failed_build_log_sha256=sha(failure_log), failed_run=str(FAILED_RUN),
        termination_identity_sha256=sha(FAILED_RUN/'termination_identity.json'),
        tests_started=False, adopted=False, new_architecture_change=False,
        all_a16_gain_and_risk_arguments_unchanged=True)
    write(BASE/'A16R1_source_review.json',proof)
    # Separate single-use manager: preserve the dispatched A16 manager/report/plan.
    old_manager = ROOT/'tools/manage_er1_a16_measurement.py'
    new_manager = ROOT/'tools/manage_er1_a16r1_measurement.py'
    assert not new_manager.exists()
    text = old_manager.read_text(encoding='utf-8').replace('A16','A16R1').replace('a16','a16r1')
    anchor = '冻结和本报告生成时未启动本候选任何CPU/EDA测试；'
    assert text.count(anchor) == 1
    text = text.replace(anchor,
        '修正版只将局部保留字matches的三处代码出现改名为load_address_matches；反向替换后文件字节与A16完全相同，其余40个源码hash项不变。A16编译语法失败日志和已停止的未完成综合保留，尚无A16仿真结果。\n'+anchor)
    old = "source_reviews_sha256={f'A{i}_source_review.json':sha(CANDIDATE.parent/f'A{i}_source_review.json') for i in range(9,17)},"
    assert text.count(old) == 1
    text = text.replace(old, old+"\n        identifier_repair_proof_sha256=sha(CANDIDATE.parent/'A16R1_source_review.json'),")
    new_manager.write_text(text,encoding='utf-8')
    print({key:proof[key] for key in ('status','candidate','candidate_sha256','unchanged_source_hash_entries','identifier_occurrences_changed')})


if __name__ == '__main__':
    main()
