"""Review the isolated ED alternative; preserve the still-live EA inputs."""
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
    root=Path('E:/Verilog_cpu')
    active_path=root/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=json.loads(active_path.read_text(encoding='utf-8'))
    ea=ROOT/'EA_combined_control_locality'
    ed=ROOT/'ED_ea_shared_only_store_address'
    assert Path(active['candidate'])==ea and active['tests_started'] is True
    verify_parent(ea)
    verify_parent(ed)
    for name,expected in active['source_sha256'].items():
        assert sha(root/name)==expected,name
    run=Path(active['frozen_run'])
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    frozen=json.loads((run/'source_manifest.json').read_text(encoding='utf-8'))
    for name,expected in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/name)==expected,name
    cm=json.loads((ed/'candidate.json').read_text(encoding='utf-8'))
    pm=json.loads((ea/'candidate.json').read_text(encoding='utf-8'))
    changes=[name for name,expected in cm['source_sha256'].items() if expected!=pm['source_sha256'][name]]
    assert set(changes)=={'rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v'}
    for name in changes:
        assert blocks((ea/name).read_text(encoding='utf-8'))==blocks((ed/name).read_text(encoding='utf-8'))
    source=(ed/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    assert "assign lsq_alloc_addr_valid[io_lane]=1'b0;" in source
    assert "assign lsq_alloc_addr[io_lane*32 +: 32]=32'b0;" in source
    probe_a=(ea/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    def shared(t):
        start=t.index('    generate if (EARLY_STORE_ADDRESS == 2) begin : g_shared_store_address')
        return t[start:t.index('    wire rob_pred_taken_mem',start)]
    assert shared(probe_a)==shared(source)
    proof=Path('F:/CPU2026Proofs/ED_source_review_20261005')
    proof.mkdir(exist_ok=False)
    review=proof/'source_review.json'
    data=dict(status='SOURCE_ONLY_CONDITIONAL_FOLLOWUP_NOT_ADOPTED',created_at=datetime.now(timezone.utc).isoformat(),
        candidate=str(ed),candidate_manifest_sha256=sha(ed/'candidate.json'),
        source_review_scope='Source hashes, compound clocked-block text and manual dataflow reasoning. No HDL compiler, simulation, synthesis, STA or formal execution.',
        active_EA_input_identities_verified=len(active['source_sha256']),EA_frozen_inputs_verified=len(frozen['snapshot_sha256']),
        EA_inputs_unchanged=True,EA_frozen_manifest_sha256=active['frozen_manifest_sha256'],
        changed_files=changes,existing_compound_clocked_blocks_text_equal_to_EA=True,
        shared_store_address_source_text_equal_to_EA=True,declared_new_state_bits=0,
        ordinary_integer_pipeline_depth=10,
        manual_reasoning=[
            'New default-on backend option preserves the original allocation address path for standalone clients. The CPU candidate explicitly disables it.',
            'The disabled branch supplies zero for both valid and payload. No address addition is instantiated in that branch; the original PRF-to-allocation-address arithmetic dependency is absent from the source graph.',
            'LSQ allocation leaves addr_ready zero. Unready address payload is not used to authorize a request; older stores with unknown addresses still block conflicting younger loads conservatively.',
            'The original linked shared store selector can publish a pending store address from the existing RS operands on a later edge. Ordinary ALU address/data updates and complete identity checks remain available.',
            'Single shared probe throughput is one store per cycle, versus up to four allocated stores. Publication delay is workload and contention dependent; no fixed one-cycle bound or IPC-loss bound is claimed.',
            'This does not remove the ordinary PRF-to-RS allocation boundary and does not affect issue width, queue depth, or cache capacity.' ],
        adoption_condition=cm['adoption_condition'],
        limitation='Unmeasured architectural tradeoff; source text is not HDL acceptance, equivalence, timing, area or correctness proof.')
    review.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=root/'reports/frequency_EA_background_research_2026-10-05.md'
    text=report.read_text(encoding='utf-8')
    old='这个方案尚未制作 candidate、没有改 EA，也没有测试。它预计零新增状态，普通流水线 10 级保持，'
    new='该方案现已另存为 ED 源码 candidate，没有改 EA，也没有启动测试。它声明零新增状态，普通流水线 10 级保持，'
    assert text.count(old)==1
    text=text.replace(old,new,1)
    text+=f'\nED candidate：`{ed}`。源码检查：`{review}`。其两个改动文件的既有 begin/end 时钟块及共享探测源文本与 EA 相同；默认参数为 1，CPU 候选显式置 0。仅源码检查，未测收益或 IPC。\n'
    report.write_text(text,encoding='utf-8')
    item=dict(candidate=str(ed),manifest_sha256=sha(ed/'candidate.json'),tests_started=False,adopted=False,
        role='Conditional removal of allocation-edge early address arithmetic; preserve shared probe and ordinary AGU',
        review=str(review),review_sha256=sha(review))
    active['prepared_unmeasured_alternatives'].append(item)
    active['post_dispatch_source_research'].update(report_sha256=sha(report),ED_candidate=str(ed),
        ED_source_review=str(review),ED_review_sha256=sha(review),EA_inputs_unchanged=True,new_test_started=False,
        additional_source_plan='Conditional allocation-edge store-address removal implemented as isolated ED; wait for completed EA mapped endpoint evidence.')
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(ED_candidate=str(ed),source_review=str(review),EA_inputs_unchanged=True,
                         new_test_started=False,ED_adopted=False)))


if __name__=='__main__':
    main()
