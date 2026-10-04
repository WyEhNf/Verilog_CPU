"""Review EB source during the immutable EA run; no HDL or EDA execution."""
import difflib
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT
from prepare_prf_precompare_and_store_imm12 import verify_parent
from review_frequency_dx_sources import blocks


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    root=Path('E:/Verilog_cpu')
    active_path=root/'build/cpu2026/active_frequency_implementation_20261004.json'
    a=json.loads(active_path.read_text(encoding='utf-8'))
    ea=ROOT/'EA_combined_control_locality'
    eb=ROOT/'EB_ea_registered_store_probe'
    assert Path(a['candidate'])==ea and a['tests_started'] is True
    verify_parent(ea)
    verify_parent(eb)
    for n,h in a['source_sha256'].items():
        assert sha(root/n)==h,n
    frozen=json.loads((Path(a['frozen_run'])/'source_manifest.json').read_text(encoding='utf-8'))
    assert sha(Path(a['frozen_run'])/'source_manifest.json')==a['frozen_manifest_sha256']
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(Path(a['frozen_run'])/'source'/n)==h,n
    ebm=json.loads((eb/'candidate.json').read_text(encoding='utf-8'))
    changes=ebm['changed_files_vs_parent']
    assert set(changes)=={'rtl/backend/rv32_backend_joint.v','rtl/backend/rv32_reservation_station.v'}
    for n in changes:
        assert blocks((ea/n).read_text(encoding='utf-8'))==blocks((eb/n).read_text(encoding='utf-8'))
    proof=Path('F:/CPU2026Proofs/EB_source_review_20261005')
    proof.mkdir(exist_ok=False)
    data=dict(status='SOURCE_ONLY_CONDITIONAL_FOLLOWUP_NOT_ADOPTED',created_at=datetime.now(timezone.utc).isoformat(),
        candidate=str(eb),candidate_manifest_sha256=sha(eb/'candidate.json'),
        no_hdl_compiler_simulation_synthesis_sta_or_formal_run=True,
        active_EA_input_identities_verified=len(a['source_sha256']),EA_frozen_inputs_verified=len(frozen['snapshot_sha256']),
        EA_frozen_manifest_sha256=a['frozen_manifest_sha256'],EA_inputs_unchanged=True,
        changed_files=changes,compound_clocked_blocks_text_equal_to_EA=True,
        new_declared_state_bits=0,ordinary_issue_bypass_unchanged=True,
        manual_reasoning=[
            'Only entry_base_ready/value, the read-only early-store probe view, changes from effective current-cycle wake state to existing src1 ready/value registers.',
            'The ordinary RS issue operands still use effective wake state; clocked operand capture, allocation, release and chronological order are unchanged.',
            'When current-cycle CDB wakes a previously not-ready base, early probe eligibility may be deferred. A same-cycle normal issue may take over address publication through the unchanged normal ALU path.',
            'A base already saved in RS remains available to the early probe. Full LSQ/ROB generation matching and stale-response rejection remain unchanged.' ],
        adoption_condition='Completed EA timing must identify same-cycle CDB wake -> early store probe as a material limiter. Review the actual store-address readiness/IPC tradeoff before using this candidate.',
        limitation='Not a measured improvement, syntax check, whole-parameter equivalence or correctness proof.')
    review=proof/'source_review.json'
    review.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=root/'reports/frequency_EA_background_research_2026-10-05.md'
    assert not report.exists()
    report.write_text('''# EA 后台测量期间的源码研究

EA 已作为八组完整组合冻结并后台测量。这里新增的 EB 仅为源码候选，不修改 EA 工作区或冻结输入，不启动另一轮测量。

EB 把 linked early-store probe 的 base ready/value 改为现有 RS 寄存器视图。普通发射仍用本周期 CDB 旁路，因此没有给正常整数路径增加周期或寄存器位。源级上可切断 CDB wake → store probe → 地址加法这条联系。

代价需要明确：如果 base 此周期刚被 CDB 唤醒，早期探测会推迟；若普通发射已消费此 store，则可能由原 ALU 地址更新路径先提供地址。这可能推迟 older-store 冲突释放，不能声称 IPC 不变。只有 EA 完成后仍显示该探测锥明显限制频率，才考虑采用，并在后续测试前先报告实际范围。

PRF 分银行、动态读端口与提前唤醒也已研究。动态端口需要结构冲突处理/重发；提前 ALU wakeup 需要保证回压条件下旁路数据按时可用。公开项目提供设计参考，不能直接证明本核换接口之后的周期或正确性。[BOOM register file/bypass](https://docs.boom-core.org/en/latest/sections/reg-file-bypass-network.html)，[BOOM issue/wakeup](https://docs.boom-core.org/en/latest/sections/issue-units.html)。

''' + f"EB candidate：`{eb}`。源码检查：`{review}`。EA 工作区 {len(a['source_sha256'])} 项与冻结 {len(frozen['snapshot_sha256'])} 项身份重新核对，保持不变。源码/时钟块文本检查不是 HDL 或功能验证。\n",encoding='utf-8')
    a['ongoing_research_report']=str(report)
    a['post_dispatch_source_research']=dict(report=str(report),report_sha256=sha(report),candidate=str(eb),
        review=str(review),review_sha256=sha(review),EA_inputs_unchanged=True,new_test_started=False)
    a['prepared_unmeasured_alternatives'].append(dict(candidate=str(eb),manifest_sha256=sha(eb/'candidate.json'),
        tests_started=False,adopted=False,role='Conditional registered-base early-store probe; wait for EA limiting-path evidence'))
    active_path.write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(report=str(report),EA_inputs_unchanged=True,new_test_started=False,
                         EB_adopted=False,EB_new_state_bits=0)))


if __name__=='__main__':main()
