"""Archive EH/EI source relationships only; never invoke HDL or measurements."""
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
    for name,expected in active['source_sha256'].items():
        assert sha(workspace/name)==expected,name
    run=Path(active['frozen_run'])
    frozen=json.loads((run/'source_manifest.json').read_text(encoding='utf-8'))
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    for name,expected in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/name)==expected,name
    eg=ROOT/'EG_prf_parallel_store_address'
    verify_parent(eg)
    parent=json.loads((eg/'candidate.json').read_text(encoding='utf-8'))
    reviews=[]
    for short,name in [('EH','EH_rs_fast_slow_wake'),('EI','EI_eg_registered_shared_store_probe')]:
        candidate=ROOT/name
        verify_parent(candidate)
        manifest=json.loads((candidate/'candidate.json').read_text(encoding='utf-8'))
        changes=[n for n,h in manifest['source_sha256'].items() if h!=parent['source_sha256'][n]]
        expected={'rtl/backend/rv32_backend_joint.v','rtl/backend/rv32_reservation_station.v'}
        if short=='EH':
            expected.add('rtl/cpu_core.v')
        assert set(changes)==expected
        total=0
        for n in manifest['source_sha256']:
            if n.endswith('.v'):
                old_blocks=blocks((eg/n).read_text(encoding='utf-8'))
                assert old_blocks==blocks((candidate/n).read_text(encoding='utf-8')),n
                total+=len(old_blocks)
        rs_name='rtl/backend/rv32_reservation_station.v'
        old=(eg/rs_name).read_text(encoding='utf-8')
        new=(candidate/rs_name).read_text(encoding='utf-8')
        backend_name='rtl/backend/rv32_backend_joint.v'
        old_backend=(eg/backend_name).read_text(encoding='utf-8')
        new_backend=(candidate/backend_name).read_text(encoding='utf-8')
        wake_start='    // A locally owned ALU/MDU result loses valid'
        assert old_backend.split(wake_start,1)[1]==new_backend.split(wake_start,1)[1]
        if short=='EH':
            owner_start='    genvar owner_row, owner_lane;'
            owner_end='    // Allocate a contiguous prefix'
            assert old.split(owner_start,1)[1].split(owner_end,1)[0] == new.split(owner_start,1)[1].split(owner_end,1)[0]
            comparisons='            for (wl = 0; wl < WAKE_WIDTH; wl = wl + 1) begin : g_lane'
            old_match=old.split(comparisons,1)[1].split('            rv32_frequency_event_select #',1)[0]
            new_match=new.split(comparisons,1)[1].split('            if(SAME_CYCLE_WAKE_PORTS>',1)[0]
            assert old_match==new_match
            algebra=[
                'Original first grants G are partitioned into low prefix F and suffix S; OR(G[i]&V[i]) equals OR(F[i]&V[i]) | OR(S[i]&V[i]) for binary inputs, including multi-grant cases.',
                'Original first and last matching logic is unchanged. Sequential value recombines both first partitions for unique-owner alias; generic last selector remains original.',
                'Fast prefix has no dependence on higher-index slow matches: original lowest-lane priority only checks lower indices. If any fast match exists, original first winner is also in the fast prefix; otherwise effective operand waits for saved ready/value.',
                'All original all-port row wake/ready updates and producer validity/cancellation remain; slow held result broadcasts are still captured without requiring CDB acceptance.'
            ]
            tradeoff='Slow MDU/LSQ issue/base-probe becomes available through existing row state; can cost a dependent issue opportunity cycle. Ordinary ALU same-cycle wake retained.'
        else:
            # All normal operand/issue and clocked storage source after the base
            # observation block is byte-for-byte equal, not just clocked text.
            issue_start='    wire [WAKE_WIDTH-1:0] wake1_match'
            assert old.split(issue_start,1)[1]==new.split(issue_start,1)[1]
            algebra=[
                'Probe readiness uses original valid & target_live & saved src1_ready & !flush, and probe value uses original saved src1_value.',
                'Normal effective operands, all-port wake priority, issue selection, all payload owners and clocked updates after the base observation block are source-text identical.',
                'Only STORE_RS_LINKS enables registered probe. Ordinary ALU address updates, original shared probe owner matching and full identity guards remain unchanged.'
            ]
            tradeoff='A newly woken shared-store base waits for existing row registers; ordinary load/MDU issue bypass retains current-cycle behavior. Address conflicts may release later.'
        proof=Path(f'F:/CPU2026Proofs/{short}_source_review_20261005')
        proof.mkdir(exist_ok=False)
        review=proof/'source_review.json'
        data=dict(status='SOURCE_REVIEW_ONLY_UNADOPTED_UNTESTED',created_at=datetime.now(timezone.utc).isoformat(),
            candidate=str(candidate),candidate_manifest_sha256=sha(candidate/'candidate.json'),
            parent=str(eg),parent_manifest_sha256=sha(eg/'candidate.json'),changed_files_vs_EG=changes,
            candidate_inputs_verified=len(manifest['source_sha256']),compound_clocked_blocks_text_equal=total,
            original_producer_wake_identity_and_cancel_text_equal=True,
            EF_worktree_inputs_verified=len(active['source_sha256']),EF_frozen_inputs_verified=len(frozen['snapshot_sha256']),
            EF_inputs_unchanged=True,new_declared_state_bits=0,ordinary_integer_pipeline_depth=10,
            manual_binary_algebra=algebra,cycle_tradeoff=tradeoff,new_test_started=False,adopted=False,
            measured_reference_run=str(run),measured_reference_fmax_mhz=active['current_measured_fmax_mhz'],
            limiting_path_evidence='F:/CPU2026Proofs/EF_mapped_paths_20261005/saved_path_analysis.json',
            patch=str(candidate/'changes_vs_parent.patch'),patch_sha256=sha(candidate/'changes_vs_parent.patch'),
            review_scope='Source hash/selected text correspondence and manual binary dataflow algebra. Not HDL parsing, simulation, formal equivalence, synthesis, STA or IPC.')
        review.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        reviews.append(dict(candidate=str(candidate),manifest_sha256=data['candidate_manifest_sha256'],
            tests_started=False,adopted=False,review=str(review),review_sha256=sha(review),
            role=tradeoff+' Source-reviewed; no measurement scheduled.'))
    report=workspace/'reports/frequency_EF_background_research_2026-10-05.md'
    text=report.read_text(encoding='utf-8').replace('EF 已冻结并在 Windows 原生后台做一次 timing-only 测量。',
        'EF 已完成一次 Windows 原生 timing-only 测量，370.477569 MHz、含 SRAM 49,116.955854 μm²；IPC/功能未测。')
    text+='''\n## EH 与 EI：两种通知/共享探测边界备选\n\nEH 将 RS 当拍旁路分为低编号四个 ALU 快速端口与 MDU/LSQ 慢端口。慢端口仍按原式写入现有行寄存器；同拍发射的 readiness 和数据都只来自快速分区。原 first-grant 向量分区后 OR 合并，保留原顺序写值；没有新状态。它可能增加 load/MDU 直接依赖的一次发射等待，IPC 未知。默认 SAME_CYCLE_WAKE_PORTS=WAKE_WIDTH 保留通用行为。\n\nEI 是更窄的平行备选，继承 EG 并行分配地址。只有共享 store 基址探测读取已有 src1 ready/value 寄存器，普通 issue 的所有 wake、优先级、操作数和选择文本保持原样。EF 第一条慢路径明确经过当前拍 LSQ wake -> shared probe，因此 EI 有直接路径依据。新醒来的共享基址可能晚于 EF 可用，正常 ALU 地址更新仍可先完成；不声称 IPC 已保住。\n\n两者各核对 41 个候选输入、69 个 begin/end 时钟块；EF 主源 40 个、冻结输入 157 个保持原哈希。两者均未采用、未运行 HDL/仿真/综合/STA，不能使用 EF 的 370.48 MHz 作为其测量值。\n\nBOOM 将 ALU 快速通知与 load/variable-latency 慢通知分开：[Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)。这里的 EH 仍用现有已有效的 ALU held-result 通知，没有提前预告未来结果，亦未引入 speculative issue/replay。EI 则只对共享 store 探测作窄范围边界调整。\n\nEH 审查：`F:/CPU2026Proofs/EH_source_review_20261005/source_review.json`。EI 审查：`F:/CPU2026Proofs/EI_source_review_20261005/source_review.json`。\n'''
    report.write_text(text,encoding='utf-8')
    active=json.loads(active_path.read_text(encoding='utf-8'))
    alternatives=active.setdefault('prepared_unmeasured_alternatives',[])
    for review in reviews:
        assert not any(Path(x['candidate'])==Path(review['candidate']) for x in alternatives)
        alternatives.append(review)
    active['post_dispatch_source_research'].update(report_sha256=sha(report),
        additional_reviews=reviews,role='EG, EH and EI source-reviewed alternatives; EF completed, no further measurement started')
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(reviews=reviews,EF_inputs_unchanged=True,new_tests_started=False)))


if __name__=='__main__':
    main()
