"""Record isolated EC source review and unchanged live EA inputs; no HDL/EDA."""
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
    ea=ROOT/'EA_combined_control_locality'
    ec=ROOT/'EC_ea_narrow_store_probe_packet'
    assert Path(active['candidate'])==ea and active['tests_started'] is True
    verify_parent(ea)
    verify_parent(ec)
    for name,expected in active['source_sha256'].items():
        assert sha(workspace/name)==expected,name
    run=Path(active['frozen_run'])
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    frozen=json.loads((run/'source_manifest.json').read_text(encoding='utf-8'))
    for name,expected in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/name)==expected,name
    cm=json.loads((ec/'candidate.json').read_text(encoding='utf-8'))
    pm=json.loads((ea/'candidate.json').read_text(encoding='utf-8'))
    changes=[n for n,h in cm['source_sha256'].items() if h!=pm['source_sha256'][n]]
    assert changes==['rtl/backend/rv32_backend_joint.v']
    name=changes[0]
    old=blocks((ea/name).read_text(encoding='utf-8'))
    new=blocks((ec/name).read_text(encoding='utf-8'))
    added=[b for b in new if b not in old]
    assert len(new)==len(old)+1 and len(added)==1
    assert [b for b in new if b not in added]==old
    assert 'saved_valid<=' in added[0]
    tag_width=3+6+8
    assert tag_width==17 and 2*tag_width+32+12+1==cm['new_declared_sequential_state_bits']==79
    proof=Path('F:/CPU2026Proofs/EC_source_review_20261005')
    proof.mkdir(exist_ok=False)
    data=dict(status='SOURCE_ONLY_CONDITIONAL_FOLLOWUP_NOT_ADOPTED',created_at=datetime.now(timezone.utc).isoformat(),
        candidate=str(ec),candidate_manifest_sha256=sha(ec/'candidate.json'),
        source_review_scope='Source hashes, compound clocked-block text and manual dataflow/identity reasoning. No HDL compiler, simulation, synthesis, STA or formal execution.',
        active_EA_input_identities_verified=len(active['source_sha256']),EA_frozen_inputs_verified=len(frozen['snapshot_sha256']),
        EA_frozen_manifest_sha256=active['frozen_manifest_sha256'],EA_inputs_unchanged=True,
        changed_files=changes,all_existing_compound_clocked_blocks_text_equal_to_EA=True,
        new_compound_clocked_blocks=1,additional_current_declared_state_bits=79,
        added_packet_bits=78,added_valid_bits=1,ordinary_integer_pipeline_depth=10,
        source_manual_reasoning=[
            'The selected full ROB tag, full LSQ tag, base and immediate are captured together before same-edge RS release; downstream addition consumes only that saved packet.',
            'The saved valid bit and packet write have matching reset/flush/branch hold suppression. An inactive payload is unreset, with publication suppressed by valid.',
            'Publication reads current ROB valid/generation using saved ROB slot, and retains the complete tag generation comparison. LSQ still checks its own current valid/generation and pending store address flags.',
            'Normal ALU address updates retain the original priority over early probe publication; no store data or commit authority is supplied by this probe.',
            'Each pending LSQ row excludes only the matching full identity of the previous saved packet, permitting distinct back-to-back store selections.',
            'STORE_ALLOC_IMM12 retains 12 offset bits consumed by signed-12-bit adder. Generic standalone mode retains 32 bits. Unlinked mode bypasses the new registers.',
            'The ordinary RS effective wake/issue and allocation-time store adder remain unchanged. This candidate does not cut an allocation-only PRF-to-store-adder critical path.' ],
        adoption_condition=cm['adoption_condition'],
        limitation='Unmeasured source candidate; added publication cycle may delay older-store conflict release. No timing, IPC, synthesis FF count, correctness or parameter proof.')
    review=proof/'source_review.json'
    review.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=workspace/'reports/frequency_EA_background_research_2026-10-05.md'
    report_text=report.read_text(encoding='utf-8')
    assert '## EC：' not in report_text
    report_text+='''
## EC：保存选中操作数，再执行共享存储 AGU

EC 是与 EB 并列的 EA 源码备选，二者尚未组合或采用。EB 使用现有 RS 寄存视图，零新增状态，但会错过刚被 CDB 唤醒的早期探测。EC 保留现有同周期 CDB wake/issue，在选出完整 store packet 后加寄存边界，再进行地址加法和当前 ROB 身份检查。

当前 packet 保存 ROB tag 17 位、LSQ tag 17 位、base 32 位、S 型 offset 12 位，共 78 位，加 valid 1 位，共 79 个新增状态位。原通用立即数构想为 99 位；这里少保存 20 位，只依据 CPU decoder 的 signed-12 合同。通用独立配置仍保存 32 位。真实 FF 数量、缓冲和面积尚未综合。

选中 packet 在 RS 同边沿正常释放前捕获；发布时重新读当前 ROB valid/generation，LSQ 仍验证自身完整 generation。当前待发布 owner 按完整 LSQ tag 从下一轮 pending 中排除，减少重复选择。正常 ALU 地址更新和 store commit 授权保留。普通整数流水线仍 10 级，只有 opportunistic early-store probe 增加一拍，可能延迟旧 store 冲突释放。

EC 仅对“共享探测选择/旁路 → AGU → 发布”的组合链建立边界，不切断分配时的 PRF → store 加法器。因此不能凭旧 DM1 的疑似分配端点就声称 EC 会解决最慢路径。只有 EA 新路径明确指向共享探测锥，才比较 EB 与 EC 的代价后选择；测试前另报完整范围。此时没有启动 EC 编译、仿真、综合或 STA。

'''+f'EC candidate：`{ec}`。源码检查：`{review}`。EA 工作区 {len(active["source_sha256"])} 项与冻结 {len(frozen["snapshot_sha256"])} 项身份再次保持不变；全部既有 begin/end 时钟块文本保持，仅新增 valid 块和 packet word-bank 状态。检查不是 HDL 或功能证明。\n'
    report.write_text(report_text,encoding='utf-8')
    item=dict(candidate=str(ec),manifest_sha256=sha(ec/'candidate.json'),tests_started=False,adopted=False,
        role='Conditional saved narrow packet before shared store AGU; compare with EB only after EA critical paths',
        review=str(review),review_sha256=sha(review))
    active['prepared_unmeasured_alternatives'].append(item)
    research=active['post_dispatch_source_research']
    research.update(report_sha256=sha(report),EC_candidate=str(ec),EC_source_review=str(review),
        EC_review_sha256=sha(review),EA_inputs_unchanged=True,new_test_started=False)
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(report=str(report),EC_review=str(review),EA_inputs_unchanged=True,
                         new_test_started=False,EC_adopted=False,EC_declared_new_state_bits=79)))


if __name__=='__main__':
    main()
