"""Archive the complete EL1 source review; no HDL or EDA execution."""
import difflib
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from prepare_prf_precompare_and_store_imm12 import verify_parent
from prepare_staged_frequency_candidate import ROOT
from prepare_cache_response_match_before_select import cache
from review_frequency_dx_sources import blocks


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    workspace=Path('E:/Verilog_cpu')
    active_path=workspace/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=read(active_path)
    names=['EF_rob_commit_packet_domains','EG_prf_parallel_store_address',
           'EI_eg_registered_shared_store_probe','EJ_lsq_response_query_predecode',
           'EK_lsq_response_match_domains','EL1_cache_response_match_before_select']
    chain=[ROOT/name for name in names]
    ef,parent,candidate=chain[0],chain[-2],chain[-1]
    assert Path(active['candidate'])==ef and active['measurement_process_id'] is None
    assert active['status']=='WORKTREE_IMPLEMENTED_TIMING_ONLY_COMPLETE_PROGRAMS_NOT_RUN'
    for path in chain:
        verify_parent(path)
    cm,pm,em=read(candidate/'candidate.json'),read(parent/'candidate.json'),read(ef/'candidate.json')
    delta=[n for n,h in cm['source_sha256'].items() if h!=pm['source_sha256'][n]]
    assert delta==['rtl/cache/rv32_dcache_nonblocking.v']
    dcache=delta[0]
    old=(parent/dcache).read_text(encoding='utf-8')
    new=(candidate/dcache).read_text(encoding='utf-8')
    assert cache(old)==new
    assert "mshr_valid[response_index] && mshr_sent[response_index]" in new
    assert "{mshr_addr[match_mshr][31:4],4'b0}" in new
    assert 'mem_resp_line_addr_i==mshr_victim_addr[match_mshr]' in new
    assert '.index_i(mem_resp_id_i)' in new
    assert cm['new_declared_sequential_state_bits']==0 and len(cm['implemented_groups'])==16
    assert cm['parameter_overrides']==em['parameter_overrides']==active['parameter_overrides']
    total=0
    changed=[]
    diff=[]
    for n,h in cm['source_sha256'].items():
        if h!=em['source_sha256'][n]:
            changed.append(n)
            diff.extend(difflib.unified_diff((ef/n).read_text(encoding='utf-8').splitlines(True),
                        (candidate/n).read_text(encoding='utf-8').splitlines(True),
                        fromfile=names[0]+'/'+n,tofile=names[-1]+'/'+n))
        if n.endswith('.v'):
            original=blocks((ef/n).read_text(encoding='utf-8'))
            assert original==blocks((candidate/n).read_text(encoding='utf-8')),n
            total+=len(original)
    assert changed==['rtl/backend/rv32_backend_joint.v','rtl/backend/rv32_lsq.v',
                     'rtl/backend/rv32_reservation_station.v','rtl/cache/rv32_dcache_nonblocking.v',
                     'rtl/cpu_core.v','rtl/rv32_physical_register_file.v']
    reviews=[]
    for name in ('EG','EI','EJ','EK'):
        p=Path('F:/CPU2026Proofs')/(name+'_source_review_20261005')/'source_review.json'
        record=read(p)
        assert sha(Path(record['candidate'])/'candidate.json')==record['candidate_manifest_sha256']
        reviews.append(dict(path=str(p),sha256=sha(p),candidate_manifest_sha256=record['candidate_manifest_sha256']))
    for n,h in active['source_sha256'].items():
        assert sha(workspace/n)==h,n
    run=Path(active['frozen_run'])
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    frozen=read(run/'source_manifest.json')
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    proof=Path('F:/CPU2026Proofs/EL1_source_review_20261005')
    proof.mkdir(exist_ok=False)
    patch=proof/'changes_vs_measured_EF.patch'
    patch.write_text(''.join(diff),encoding='utf-8')
    data=dict(status='FINAL_COMBINATION_SOURCE_REVIEW_ONLY_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),candidate=str(candidate),
        candidate_manifest_sha256=sha(candidate/'candidate.json'),
        chain=[dict(candidate=str(p),manifest_sha256=sha(p/'candidate.json')) for p in chain],
        component_reviews=reviews,changed_files_vs_EK=delta,changed_files_vs_EF=changed,
        candidate_inputs_verified=len(cm['source_sha256']),EF_worktree_inputs_verified=len(active['source_sha256']),
        EF_frozen_inputs_verified=len(frozen['snapshot_sha256']),EF_inputs_unchanged=True,
        ordinary_integer_pipeline_depth=10,new_declared_state_bits=0,
        compound_clocked_blocks_text_equal_to_EF=total,original_dcache_response_authority_text_equal=True,
        dcache_change_is_exact_original_expression_transposition=True,
        manual_binary_algebra=[
            'For an in-range response row r, selecting (writeback[r] ? victim[r] : {demand[r][31:4],0}) and then comparing with the return line is equal to selecting the row Boolean (writeback[r] & line==victim[r]) | (!writeback[r] & line==aligned_demand[r]).',
            'The original response_found range/valid/sent predicate still qualifies this result. Out-of-range and invalid rows cannot authorize a response. Full victim address and aligned demand address remain distinct.',
            'EG parallel arithmetic selects the same priority-winning base plus signed-12 offset; the original PRF ready, read data, allocation-valid and same-bundle dependencies remain.',
            'EI delays only a newly woken opportunistic shared probe until existing RS row state. Ordinary issue wake and operand bypass remain unchanged. Allocation early-address behavior is restored by EG.',
            'EJ/EK retain complete generation/tag/valid/response_wait predicates, original last-row/default priority, forwarding and extraction semantics, as recorded in component reviews.'
        ],source_evidence=[
            'F:/CPU2026Proofs/EF_selected_path_loads_20261005/summary.json',
            'F:/CPU2026Proofs/EF_selected_gate_inputs_20261005/summary.json',
            'F:/CPU2026Proofs/EF_mshr_flag_input_cones_20261005/summary.json'],
        private_flag_identity_scope='Source/dataflow inference from all four D cones reaching dirty_victim bit14 and the writeback state equation; not formal private-net field equivalence.',
        patch=str(patch),patch_sha256=sha(patch),
        architecture_triage=dict(
            included='Parallelize arithmetic/comparison before late selection; narrow existing-register probe boundary; direct response row/byte selection; local full identity comparison.',
            retained_but_excluded=[
                'EH defers ordinary MDU/load same-cycle issue: extra dependent issue opportunity with broader IPC risk than EI for this actual probe path.',
                'EC saved shared-probe packet: 79 added state bits and extra stage, whereas EI cuts the current path with existing state.',
                'Register all CDB/cache responses or add full pipeline stages: ready/valid alignment, recovery and dependent latency changes; current late links can be cut without global stages.',
                'Reduce width/windows or dynamically bank PRF ports: arbitration, allocation/replay and IPC consequences; not demonstrated as the current primary limiting cone.',
                'Speculative early wake or cached ROB authority: must add replay or full recovery/invalidation lifecycle. Existing normal valid/generation authority is retained.',
                'Add buffers to every high-fanout bit or alter tool/library/constraints: does not remove current long serial links; course setup is fixed.',
                'Restructure AXI enable or other unsampled cones: saved loads alone do not establish a current timing limit or safe protocol transformation.'
            ],conclusion='Current saved critical paths have no additional sufficiently justified source transformation to include before measuring this complete combination. Future limiting paths may require new designs.'),
        caveats=['Source/hash/manual binary algebra only; no HDL acceptance, simulation, formal, synthesis, STA or IPC test.',
                 '69 compound clocked blocks are a text check, not a complete HDL equivalence proof.',
                 'New comparator/adders/routing loads and global frequency/area are unknown; EI shared-probe timing intentionally differs.',
                 'Course area includes SRAM; original area/IPC range and final Tier3 remain requirements.'],
        tests_started=False,adopted=False)
    review=proof/'source_review.json'
    review.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=workspace/'reports/frequency_EF_background_research_2026-10-05.md'
    text=report.read_text(encoding='utf-8')
    text+='''\n## EL1：地址先比较再选择，最终组合源码审查\n\n继续只读 EF 保存的 JSON。此前查询极性方向未得到别名，不据此认定字段；这次追溯四个所选寄存器的 D 输入，各锥均到达 MSHR lifecycle 的 dirty_victim 第 14 位。与源码中 writeback <= dirty_victim 的状态更新相符，形成 writeback 字段的强数据流推断；仍不是私有网形式等价证明。\n\nEL1 继承 EG→EI→EJ→EK，只改 Dcache：每行将返回地址与完整 victim 地址及低四位清零的 demand 地址分别比较，以该行 writeback 选择匹配结果，再按返回 ID 选择一位 Boolean。原 response_found 的范围、valid、sent 条件及所有消费者/时钟块保留。当前 4 MSHR，因此源码包含 8 个 32 位比较，新增输入负载及面积未知。这样去掉晚到的选后 writeback 驱动 32 位地址 mux 再比较的串行联系，不声称已消除整个 50-load 门或测得收益。\n\n最终源码链 EF→EG→EI→EJ→EK→EL1 共核对 41 个候选输入；69 个复合时钟块与 EF 相同，普通整数流水线 10 级、零新增状态。更广的慢 wake、额外 probe/响应流水级、减少端口和推测 wake 逐项取舍，采用能对应当前实际路径的窄边界与选择前并行方案。本批暂未找到另一个依据充分、值得继续混入的结构变换；并不排除未来新瓶颈下的方案。\n\n源码审查及对实测 EF 的完整 diff：`F:/CPU2026Proofs/EL1_source_review_20261005/`。失败的 EL 准备目录（原锚点格式不匹配）保留，无 manifest、未采用、未测试；EL1 使用原完整地址对齐表达式。当前主工作区仍是实测 EF。最终冻结后先向用户完整汇报，再只对整体测一次课程频率/面积，不分别测 EG/EI/EJ/EK/EL1 中间改动。\n'''
    report.write_text(text,encoding='utf-8')
    record=dict(candidate=str(candidate),manifest_sha256=data['candidate_manifest_sha256'],
        tests_started=False,adopted=False,review=str(review),review_sha256=sha(review),
        role='Final 16-group combination: EG/EI/EJ/EK and per-row cache response address matching; source review only')
    active.setdefault('prepared_unmeasured_alternatives',[]).append(record)
    active['post_dispatch_source_research'].update(report_sha256=sha(report),latest_review=record,
        mshr_flag_d_cone_evidence=data['source_evidence'][-1],
        role='EL1 combined source review complete; no new measurement started')
    active['pending_source_research']=dict(next='Freeze reviewed EL1 and publish complete pretest scope before one combined timing-only dispatch.',
        candidate=str(candidate),adopted=False,tests_started=False)
    active['source_research_decision']=data['architecture_triage']['conclusion']
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(review=str(review),candidate_manifest_sha256=data['candidate_manifest_sha256'],
        clocked_blocks_text_equal=total,changed_files_vs_EF=changed,new_tests_started=False)))


if __name__=='__main__':
    main()
