"""Repair two MSHR named ports and audit primary-body signal-only renaming."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
from manage_frozen_baseline_programs import ROOT, read, sha, write
from wait_frequency_directed_native import live
from prepare_er1_instruction_line_buffer import interface

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A16R1_shared_barrel_elastic_dispatch'
TARGET = BASE/'A16R2_shared_barrel_elastic_dispatch'
FAILED_RUN = Path('F:/CPU2026CourseRuns/ER1_A16R1_tier3_20261005')


def main():
    assert not TARGET.exists()
    assert not live(read(FAILED_RUN/'dispatch_identity.json')['process_id'])
    failure_log = FAILED_RUN/'native_build/build.log'
    log = failure_log.read_text(encoding='utf-8')
    assert log.count('%Error-PINNOTFOUND') == 2
    parent = read(PARENT/'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
        destination = TARGET/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT/name, destination)
    name = 'rtl/cache/rv32_icache_nonblocking.v'
    original = (PARENT/name).read_bytes()
    edits = [(b'.primary_if_req_pc(lookup_req_pc)', b'.if_req_pc_i(lookup_req_pc)'),
             (b'.primary_if_req_epoch(lookup_req_epoch)', b'.if_req_epoch_i(lookup_req_epoch)')]
    corrected = original
    for before, after in edits:
        assert corrected.count(before) == 1, before
        corrected = corrected.replace(before, after)
    assert all(before not in corrected for before, _ in edits)
    (TARGET/name).write_bytes(corrected)
    # Stronger than the old A12 inverse test: do not transform named ports.
    ancestor = BASE/'A11_compact_direct_cdb'/name
    original_cache = ancestor.read_text(encoding='utf-8')
    child_cache = (TARGET/name).read_text(encoding='utf-8')
    marker = '    wire lookup_req_valid,lookup_req_ready;'
    def body(text):
        start = text.index(marker)
        return text[start:text.index('\nendmodule',start)]
    mapping, _ = interface()
    pattern = re.compile(r'(?<!\.)\b('+'|'.join(map(re.escape,mapping))+r')\b')
    expected = pattern.sub(lambda m:mapping[m[0]],body(original_cache))
    assert body(child_cache) == expected
    ports = lambda text:re.findall(r'\.([A-Za-z_]\w*)\s*\(',text)
    assert ports(body(child_cache)) == ports(body(original_cache))
    record = dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=[name],source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),
        compatibility_repair='Retain A16R1 local identifier repair; restore exactly two original MSHR named-port labels. Primary body exactly equals A11 after signal-only renaming; named labels preserved.')
    record['implemented_changes'] = list(parent['implemented_changes']) + [record['compatibility_repair']]
    write(TARGET/'candidate.json',record)
    proof = dict(status='MSHR_PORT_REPAIR_PRIMARY_BODY_AND_NAMED_PORT_IDENTITY',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_files=[name],named_port_labels_restored=2,
        primary_body_exact_a11_after_signal_only_renaming=True,all_primary_named_port_labels_exact_a11=True,
        old_a12_inverse_rename_argument_was_insufficient_to_verify_named_ports=True,
        unchanged_source_hash_entries_relative_parent=40,
        failed_build_log_sha256=sha(failure_log),failed_run=str(FAILED_RUN),
        termination_identity_sha256=sha(FAILED_RUN/'termination_identity.json'),
        tests_started=False,adopted=False,new_architecture_change=False)
    assert all(sha(TARGET/n)==parent['source_sha256'][n] for n in parent['source_sha256'] if n!=name)
    write(BASE/'A16R2_source_review.json',proof)
    old_manager = ROOT/'tools/manage_er1_a16r1_measurement.py'
    new_manager = ROOT/'tools/manage_er1_a16r2_measurement.py'
    assert not new_manager.exists()
    text = old_manager.read_text(encoding='utf-8').replace('A16R1','A16R2').replace('a16r1','a16r2')
    old = '修正版只将局部保留字matches的三处代码出现改名为load_address_matches；反向替换后文件字节与A16完全相同，其余40个源码hash项不变。A16编译语法失败日志和已停止的未完成综合保留，尚无A16仿真结果。'
    assert text.count(old) == 1
    text = text.replace(old,
        '修正版保留三处局部保留字matches→load_address_matches改名，并恢复两处MSHR命名端口if_req_pc_i/if_req_epoch_i；相对A16共两个文件改变、39个源码hash项不变。主Icache主体与A11在仅重命名信号后完全一致，所有主缓存子模块命名端口标签与A11相同。旧A12反向改名检查未区分端口标签，因此不足以证明可构建，已补上标签保留检查并修复准备脚本。A16/A16R1失败构建及停止的未完成综合日志全部保留，均没有仿真结果。')
    new_manager.write_text(text,encoding='utf-8')
    print({key:proof[key] for key in ('status','candidate','candidate_sha256','named_port_labels_restored','primary_body_exact_a11_after_signal_only_renaming')})


if __name__ == '__main__':
    main()
