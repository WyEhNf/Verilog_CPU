"""Save EI/EJ source/dataflow correspondence; no HDL or measurement execution."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT
from prepare_prf_precompare_and_store_imm12 import verify_parent
from review_frequency_dx_sources import blocks


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    workspace=Path('E:/Verilog_cpu')
    active_path=workspace/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=json.loads(active_path.read_text(encoding='utf-8'))
    assert Path(active['candidate'])==ROOT/'EF_rob_commit_packet_domains'
    assert active['measurement_process_id'] is None
    parent=ROOT/'EI_eg_registered_shared_store_probe'
    candidate=ROOT/'EJ_lsq_response_query_predecode'
    for p in (parent,candidate):
        verify_parent(p)
    old_manifest=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))
    manifest=json.loads((candidate/'candidate.json').read_text(encoding='utf-8'))
    changes=[n for n,h in manifest['source_sha256'].items() if h!=old_manifest['source_sha256'][n]]
    assert set(changes)=={'rtl/backend/rv32_lsq.v','rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v'}
    total=0
    for n in manifest['source_sha256']:
        if n.endswith('.v'):
            old_blocks=blocks((parent/n).read_text(encoding='utf-8'))
            assert old_blocks==blocks((candidate/n).read_text(encoding='utf-8')),n
            total+=len(old_blocks)
    n='rtl/backend/rv32_lsq.v'
    old=(parent/n).read_text(encoding='utf-8')
    new=(candidate/n).read_text(encoding='utf-8')
    # Only the response query/extract declarations are changed after this
    # point; matching, ownership and response result writers retain text.
    suffix='    wire [1:0] response_line_views;'
    assert old.split(suffix,1)[1]==new.split(suffix,1)[1]
    old_predicate='if (dcache_resp_valid_i && tag_matches_slot(dcache_resp_lsq_tag_i, i) && response_wait_mem[i]) begin'
    assert old_predicate in old and old_predicate in new
    assert 'assign matches[query_row]=dcache_resp_valid_i &&\n                tag_matches_slot(dcache_resp_lsq_tag_i,query_row) && response_wait_mem[query_row];' in new
    for n,expected in active['source_sha256'].items():
        assert sha(workspace/n)==expected,n
    run=Path(active['frozen_run'])
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    frozen=json.loads((run/'source_manifest.json').read_text(encoding='utf-8'))
    for n,expected in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==expected,n
    proof=Path('F:/CPU2026Proofs/EJ_source_review_20261005')
    proof.mkdir(exist_ok=False)
    review=proof/'source_review.json'
    data=dict(status='SOURCE_REVIEW_ONLY_UNADOPTED_UNTESTED',created_at=datetime.now(timezone.utc).isoformat(),
        candidate=str(candidate),candidate_manifest_sha256=sha(candidate/'candidate.json'),
        parent=str(parent),parent_manifest_sha256=sha(parent/'candidate.json'),changed_files_vs_EI=changes,
        candidate_inputs_verified=len(manifest['source_sha256']),compound_clocked_blocks_text_equal=total,
        original_response_match_slot_fire_predicate_text_retained=True,
        original_line_valid_mux_forwarding_formatting_result_owners_and_metadata_suffix_text_equal=True,
        EF_worktree_inputs_verified=len(active['source_sha256']),EF_frozen_inputs_verified=len(frozen['snapshot_sha256']),
        EF_inputs_unchanged=True,new_declared_state_bits=0,ordinary_integer_pipeline_depth=10,
        manual_binary_algebra=[
            'The old row walk initializes slot zero, then last matching row wins. New events are M[i] for i>0 and M[0] OR !any(M) for row zero; highest-event priority therefore returns the identical selected row for every binary match vector, including none and multiple.',
            'Each selected row offset o has exactly one true bit in the new offset==0..15 code. Original full-word extraction with size=2 and unsigned=1 is low32(line >> (8*o)); each fixed window uses exactly line[8*o+b] or zero beyond bit127.',
            'No alignment assumption is needed for this byte-window identity, including offsets13..15 and zero padding at line end.',
            'Query ROB tag, forwarding data/mask, size and unsigned remain fields of the same selected row. Original line-valid word selection, forwarding merge and final size/sign formatting consume the same raw word.',
            'Original response_fire, slot owner, generation/valid/response_wait checks, recovery filtering and all clocked writers are untouched.'
        ],current_response_query_width=72,extra_combinational_query_bits_per_row=12,
        caveats=['No HDL parser, simulation, formal, synthesis, STA or IPC run for EJ.',
                 'Manual algebra applies to determined binary inputs; no four-state equivalence claim.',
                 'Wider query and fixed-window OR routing may increase control/data loads and area; global gain is unmeasured.',
                 'EJ inherits EG arithmetic replication and EI registered-probe availability tradeoff.'],
        measured_reference_run=str(run),limiting_path_evidence='F:/CPU2026Proofs/EF_mapped_paths_20261005/saved_path_analysis.json',
        patch=str(candidate/'changes_vs_parent.patch'),patch_sha256=sha(candidate/'changes_vs_parent.patch'),
        new_test_started=False,adopted=False)
    review.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=workspace/'reports/frequency_EF_background_research_2026-10-05.md'
    text=report.read_text(encoding='utf-8')
    text+='''\n## EJ：响应行直接选择与字节偏移预解码，已实现\n\nEJ 继承 EI。响应匹配继续用原 `dcache_resp_valid && tag_matches_slot && response_wait`，保留原 valid/generation 权限；payload 直接按相同最高匹配行优先级选择，不再经过 `response_slot` 编码后解码。无匹配时选择原默认行 0，即使出现多个匹配也保留原最后行优先级。原 response_match/slot/fire 控制段保持原文本。\n\n每行保存的 4 位地址偏移在行选择前变为 16 位 one-hot 组合码；当前 query 从 60 位变为 72 位，零新增状态。原 line extractor 的四个串行 byte-offset 路由改为同一偏移的固定 32 位 byte-window 选择，越过 128 位行末的部分填零。按位等同 `low32(line >> (8*offset))`，不依赖自然对齐假设。原 line-valid 选择、转发合并、LB/LH 符号扩展/无符号扩展、LW、恢复过滤和写入事件均保持原文本。\n\n新增选择器及宽查询可能改变负载、面积和全局频率。EJ 没有任何编译、仿真、综合、STA 或 IPC 结果；源码审查只核对 41 个输入、69 个时钟块及以上二值关系。没有用当前 EF 370.48 MHz 作为 EJ 结果。\n\nEJ 审查：`F:/CPU2026Proofs/EJ_source_review_20261005/source_review.json`。先继续定位 EF 缓存响应的 50 负载慢门，再明确最终组合，测试前另行汇报；当前不启动任何新测试。\n'''
    report.write_text(text,encoding='utf-8')
    active=json.loads(active_path.read_text(encoding='utf-8'))
    alternatives=active.setdefault('prepared_unmeasured_alternatives',[])
    assert not any(Path(x['candidate'])==candidate for x in alternatives)
    record=dict(candidate=str(candidate),manifest_sha256=data['candidate_manifest_sha256'],tests_started=False,adopted=False,
        review=str(review),review_sha256=sha(review),role='Combined EG arithmetic, EI narrow probe and direct/predecoded response query; source-only alternative, no measurement scheduled')
    alternatives.append(record)
    active['post_dispatch_source_research'].update(report_sha256=sha(report),
        latest_review=record,role='EG/EH/EI/EJ source-reviewed; EF timing completed, no further test started')
    active['pending_source_research']=dict(next='Identify the actual 50-load Dcache response mapped Boolean/consumers, then finalize source combination and pretest report.',
        candidate=str(candidate),adopted=False,tests_started=False)
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(review=str(review),clocked_blocks_text_equal=total,EF_inputs_unchanged=True,
        candidate_manifest_sha256=data['candidate_manifest_sha256'],new_tests_started=False)))


if __name__=='__main__':
    main()
