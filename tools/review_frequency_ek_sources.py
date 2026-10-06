"""Archive EK full-identity locality source review, without HDL/EDA tests."""
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
    parent=ROOT/'EJ_lsq_response_query_predecode'
    candidate=ROOT/'EK_lsq_response_match_domains'
    for p in (parent,candidate):
        verify_parent(p)
    old_manifest=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))
    manifest=json.loads((candidate/'candidate.json').read_text(encoding='utf-8'))
    changes=[n for n,h in manifest['source_sha256'].items() if h!=old_manifest['source_sha256'][n]]
    assert changes==['rtl/backend/rv32_lsq.v']
    total=0
    for n in manifest['source_sha256']:
        if n.endswith('.v'):
            old_blocks=blocks((parent/n).read_text(encoding='utf-8'))
            assert old_blocks==blocks((candidate/n).read_text(encoding='utf-8')),n
            total+=len(old_blocks)
    name='rtl/backend/rv32_lsq.v'
    old=(parent/name).read_text(encoding='utf-8')
    new=(candidate/name).read_text(encoding='utf-8')
    func='    function tag_matches_slot;'
    assert old.split(func,1)[1].split('    endfunction',1)[0]==new.split(func,1)[1].split('    endfunction',1)[0]
    suffix='    wire [LSQ_ENTRIES*SLOT_WIDTH-1:0] response_slot_views;'
    assert old.split(suffix,1)[1]==new.split(suffix,1)[1]
    assert "response_fire = dcache_resp_valid_i && response_match;" in new
    assert '            if (response_match_rows[i]) begin' in new
    assert '            assign matches[query_row]=response_match_rows[query_row];' in new
    for n,h in active['source_sha256'].items():
        assert sha(workspace/n)==h,n
    run=Path(active['frozen_run'])
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    frozen=json.loads((run/'source_manifest.json').read_text(encoding='utf-8'))
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    proof=Path('F:/CPU2026Proofs/EK_source_review_20261005')
    proof.mkdir(exist_ok=False)
    review=proof/'source_review.json'
    data=dict(status='SOURCE_REVIEW_ONLY_UNADOPTED_UNTESTED',created_at=datetime.now(timezone.utc).isoformat(),
        candidate=str(candidate),candidate_manifest_sha256=sha(candidate/'candidate.json'),
        parent=str(parent),parent_manifest_sha256=sha(parent/'candidate.json'),changed_files_vs_EJ=changes,
        candidate_inputs_verified=len(manifest['source_sha256']),compound_clocked_blocks_text_equal=total,
        original_full_tag_valid_generation_function_text_equal=True,
        original_query_byte_routing_forwarding_formatting_response_writers_suffix_text_equal=True,
        EF_worktree_inputs_verified=len(active['source_sha256']),EF_frozen_inputs_verified=len(frozen['snapshot_sha256']),
        EF_inputs_unchanged=True,new_declared_state_bits=0,ordinary_integer_pipeline_depth=10,
        manual_binary_algebra=[
            'Each control-tree view carries exactly the original complete response valid and LSQ tag. The original tag_matches_slot function retains tag-valid bit, exact row slot, row-valid and full generation checks.',
            'Every local response_match_rows[r] equals the former dc_resp_valid & tag_matches_slot(dc_resp_tag,r) & response_wait[r] predicate.',
            'Both scalar highest-row walk and EJ payload selection consume that identical shared predicate; response_match/slot/fire and default priority are unchanged for binary inputs.'
        ],current_response_match_domains=4,max_response_row_comparators_per_leaf=4,
        matched_existing_gate_load_evidence='F:/CPU2026Proofs/EF_selected_path_loads_20261005/summary.json',
        caveats=['Source/hash/manual algebra only, no HDL, simulation, formal, synthesis, STA or IPC run.',
            'Additional distribution stages may offset load reduction. New mapped pin loads and global Fmax are unmeasured.',
            'The separate 50-load AOI221 has no public output alias; exact selected field/Boolean function is still unresolved. Do not claim EK eliminates it.',
            'EK inherits EG arithmetic replication, EI shared-probe timing tradeoff and EJ wider query routing.'],
        patch=str(candidate/'changes_vs_parent.patch'),patch_sha256=sha(candidate/'changes_vs_parent.patch'),
        new_test_started=False,adopted=False)
    review.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=workspace/'reports/frequency_EF_background_research_2026-10-05.md'
    text=report.read_text(encoding='utf-8')
    text+='''\n## EK：返回完整身份的四行比较域，已实现\n\n只读取 EF 已生成的 design.json，按公开输入端口、库 cell 类型、STA 实际负载数及相邻 INV 拓扑交叉匹配 Verilog 与 JSON 私有门名。0.1909 ns 的 AOI21 输出有 18 个直接输入连接，其中 16 个为 XNOR2；其选择输入来自低 LSQ response-tag 输出分组。具体私有 tag 位未命名，不能仅凭后缀认定字段。EK 针对接收端全 tag 比较的可见宽负载，让每个返回 tag/valid 位通过四行域再比较；不删除 generation、有效位或 response_wait 条件。\n\n原 scalar 响应行遍历和 EJ direct query 复用相同的每行 match；返回匹配函数保持原文本。当前四个域，每叶至多四行比较；零新增状态/周期。额外分发深度可能抵消负载收益，未声称已提升新频率。\n\n另一个 0.2913 ns、50 负载 AOI221 及其 INV 已与 JSON 精确对应；它们从 response_read 的第 0/2 行低包分组取输入，输出没有公开别名。只凭此不能确定完整字段/布尔含义，不能声称已被 EK 消除。查询其三个私有输入的直接 INV 别名没有找到结果；保留这个未决项，不根据猜测改缓存状态权限。\n\nEK 审查：`F:/CPU2026Proofs/EK_source_review_20261005/source_review.json`。门及负载对应：`F:/CPU2026Proofs/EF_selected_path_loads_20261005/summary.json`。输入极性补查：`F:/CPU2026Proofs/EF_selected_field_polarity_20261005/summary.json`。没有执行新的综合、STA、仿真或程序。\n\n目前主工作区仍为实测 EF。EG/EH/EI/EJ/EK 均只是独立备选或源码组合，不能使用 EF 的实测指标。后续先处理上述剩余控制负载与最终组合取舍，再提供测试前完整汇报；不分别测量中间候选。\n'''
    report.write_text(text,encoding='utf-8')
    active=json.loads(active_path.read_text(encoding='utf-8'))
    alternatives=active.setdefault('prepared_unmeasured_alternatives',[])
    assert not any(Path(x['candidate'])==candidate for x in alternatives)
    record=dict(candidate=str(candidate),manifest_sha256=data['candidate_manifest_sha256'],tests_started=False,adopted=False,
        review=str(review),review_sha256=sha(review),role='EG+EI+EJ plus local full response match domains; source-reviewed complete candidate, unmeasured')
    alternatives.append(record)
    active['post_dispatch_source_research'].update(report_sha256=sha(report),latest_review=record,
        selected_load_analysis='F:/CPU2026Proofs/EF_selected_path_loads_20261005/summary.json',
        role='EG/EH/EI/EJ/EK source-reviewed; EF timing completed, no further measurement started')
    active['pending_source_research']=dict(next='Resolve or explicitly delimit the remaining 50-load cache response-read Boolean cone, then finalize the candidate scope and pretest report.',
        candidate=str(candidate),adopted=False,tests_started=False)
    active['source_research_decision']='Prefer narrow EI probe boundary over broad EH issue deferral for EF path 1; EJ/EK address response query and receiver load. All unmeasured; main remains EF at 370.48 MHz. Remaining 50-load cache cone must be reviewed before next measurement.'
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(review=str(review),clocked_blocks_text_equal=total,EF_inputs_unchanged=True,
        candidate_manifest_sha256=data['candidate_manifest_sha256'],new_tests_started=False)))


if __name__=='__main__':
    main()
