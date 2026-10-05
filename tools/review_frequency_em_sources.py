"""Archive conditional EM source review while EL1 runs; never launch tests."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT
from prepare_prf_precompare_and_store_imm12 import verify_parent
from prepare_shared_store_rob_query_predecode import selector, backend, core
from review_frequency_dx_sources import blocks


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    workspace=Path('E:/Verilog_cpu')
    active_path=workspace/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=read(active_path)
    parent=ROOT/'EL1_cache_response_match_before_select'
    candidate=ROOT/'EM_shared_store_rob_query_predecode'
    assert Path(active['candidate'])==parent
    assert Path(active['frozen_run'])==Path('F:/CPU2026CourseRuns/architecture_EL1_20261005')
    verify_parent(parent)
    verify_parent(candidate)
    pm,cm=read(parent/'candidate.json'),read(candidate/'candidate.json')
    transforms={'rtl/backend/rv32_backend_joint.v':backend,
                'rtl/backend/rv32_store_address_select.v':selector,'rtl/cpu_core.v':core}
    delta=[n for n,h in cm['source_sha256'].items() if h!=pm['source_sha256'][n]]
    assert delta==list(transforms)
    total=0
    for n in cm['source_sha256']:
        if n.endswith('.v'):
            original=blocks((parent/n).read_text(encoding='utf-8'))
            assert original==blocks((candidate/n).read_text(encoding='utf-8')),n
            total+=len(original)
    for n,transform in transforms.items():
        assert transform((parent/n).read_text(encoding='utf-8'))==(candidate/n).read_text(encoding='utf-8'),n
    n='rtl/backend/rv32_backend_joint.v'
    old,new=(parent/n).read_text(encoding='utf-8'),(candidate/n).read_text(encoding='utf-8')
    guard='        assign shared_store_addr_valid = selected &&'
    end='    end else begin : g_no_shared_store_address'
    assert old.split(guard,1)[1].split(end,1)[0]==new.split(guard,1)[1].split(end,1)[0]
    n='rtl/backend/rv32_store_address_select.v'
    old,new=(parent/n).read_text(encoding='utf-8'),(candidate/n).read_text(encoding='utf-8')
    start='        for(row=0;row<LSQ_ENTRIES;row=row+1) begin:g_store'
    assert old.split(start,1)[1].split('            assign row_packets',1)[0]==new.split(start,1)[1].split('            wire [STORE_BASE_WIDTH',1)[0]
    assert old.split('    initial begin',1)[1]==new.split('    initial begin',1)[1]
    for n,h in active['source_sha256'].items():
        assert sha(workspace/n)==h,n
    run=Path(active['frozen_run'])
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    frozen=read(run/'source_manifest.json')
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    assert sha(active['pretest_report'])==active['pretest_report_sha256']
    proof=Path('F:/CPU2026Proofs/EM_source_review_20261005')
    proof.mkdir(exist_ok=False)
    review=proof/'source_review.json'
    data=dict(status='CONDITIONAL_SOURCE_REVIEW_ONLY_UNADOPTED_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),candidate=str(candidate),
        candidate_manifest_sha256=sha(candidate/'candidate.json'),parent=str(parent),
        parent_manifest_sha256=sha(parent/'candidate.json'),changed_files_vs_EL1=delta,
        candidate_inputs_verified=len(cm['source_sha256']),compound_clocked_blocks_text_equal=total,
        original_probe_priority_link_readiness_and_release_equations_text_equal=True,
        original_full_ROB_valid_generation_guard_and_all_address_arithmetic_text_equal=True,
        EL1_worktree_inputs_verified=len(active['source_sha256']),EL1_frozen_inputs_verified=len(frozen['snapshot_sha256']),
        EL1_pretest_report_unchanged=True,EL1_inputs_unchanged=True,
        new_declared_state_bits=0,ordinary_integer_pipeline_depth=10,
        current_packet_width_before=46,current_packet_width_after=62,current_query_width=16,
        manual_binary_algebra=[
            'Original circular priority emits at most one first-row grant for binary inputs. The original base packet positions and values stay unchanged.',
            'For selected row r, query masks decode exactly the same ROB-slot bits as selected_rob_tag. The existing bank-mask array reader returns the same valid/full-generation row as the original encoded-index reader, including zero for out-of-range slots.',
            'With no selected row, mask-query returns zero rather than original default row0. selected_live is used only in shared_store_addr_valid already qualified by selected=0; externally observed valid and address/tag outputs remain unchanged.',
            'No eligibility authority is moved into the priority decision; a stale oldest tag still suppresses shared-valid exactly as before, rather than silently choosing a later row.',
            'Generic default ROB_QUERY_PREDECODE=0 retains the original packet and encoded-index query. HIGH_BITS=0 has one constant high-bank mask; no zero-width part-select is generated.'
        ],caveats=['Source/hash/manual binary reasoning only; no HDL, formal, simulation, synthesis, STA or IPC run.',
            'Larger packet and static tag decode can increase loading. No measured frequency/area benefit.',
            'Current RS_ISSUE_METADATA=1 already supplies immediate from RS rows; this candidate targets only the normal ROB-live query suffix, not ROB immediate reads.',
            'Source-only alternative; use only if completed EL1 paths justify this suffix, then report before a later combined measurement.'],
        patch=str(candidate/'changes_vs_parent.patch'),patch_sha256=sha(candidate/'changes_vs_parent.patch'),
        adopted=False,new_additional_test_started=False,parent_measurement_already_running=True)
    review.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=workspace/'reports/frequency_EL1_background_research_2026-10-05.md'
    assert not report.exists()
    report.write_text('''# EL1 后台期间的后续源码研究

EL1 已先向用户汇报完整范围，再启动一次 Windows 原生 timing-only 测量；没有启动 Verilator/IPC/功能程序。本文件不是新的测试计划，也不改变正在测量的源。

## EM：共享探测的正常 ROB 槽号先解码，条件备选

继续读 EL1 源码及 EF 保存路径。共享 probe 原 suffix 是选出完整 ROB tag 后，再解码其槽号查询正常 valid/full generation；EF 的旧路径确实经过这一后缀。当前 EL1 已切断前面的 LSQ wake 联系，新结果尚未说明这个后缀是否仍限制全局频率。

EM 把每行保存的 ROB slot 先解码成低/高银行掩码，随同原 full tag、LSQ tag、RS one-hot 按原 oldest/lowest 优先级选择。既有 bank-mask reader 查询相同 ROB 行；后端正常 valid、完整 generation、reset/flush/branch-busy 全部保留。零新增状态和周期，普通整数流水线仍为 10 级。当前 query 16 位、选择包 46→62 位；多出的选择负载和静态译码可能抵消收益，未测频率/面积。

没有 eligible 行时，新 mask 为零，内部 selected_live 会从原默认 ROB 行0改为零。但这个内部值只有 shared-valid 一个消费者，而该表达式已经被 selected=0 禁用；输出 address、tag 和其他选择 payload 保持原来。没有将 ROB 授权加入优先级筛选，因此 stale oldest 仍抑制 shared-valid，不改成选择后续行。

当前 RS_ISSUE_METADATA=1，immediate 已从 RS 选出。EM 不声称优化 ROB immediate 动态读；实际只处理正常 live 查询。通用默认参数为 0，原 packet/read 保留；零宽 high bank 单独处理。

已核对候选 41 个输入、69 个复合时钟块与 EL1 相同，原 store selector 的 eligible/upper/first 和 link lifecycle 文本相同，原后端完整 valid/generation guard 与所有地址加法文本相同。仅源码/二值关系检查，不是功能或形式等价测试。EL1 主输入40、冻结157及不可变测试前报告哈希仍一致。

候选：`F:/CPU2026Candidates/frequency_research_20261003/EM_shared_store_rob_query_predecode`。审查：`F:/CPU2026Proofs/EM_source_review_20261005/source_review.json`。没有采用 EM，没有单项测量。只有完成的 EL1 路径仍显示该 suffix 是主要瓶颈时，才考虑组合它；下一测量前仍需先汇报。
''',encoding='utf-8')
    record=dict(candidate=str(candidate),manifest_sha256=data['candidate_manifest_sha256'],
        tests_started=False,adopted=False,review=str(review),review_sha256=sha(review),
        role='Conditional predecoded normal ROB query after shared store selection; await completed EL1 paths, no measurement scheduled')
    active=read(active_path)
    active.setdefault('prepared_unmeasured_alternatives',[]).append(record)
    active['ongoing_research_report']=str(report)
    active['post_dispatch_source_research']=dict(report=str(report),report_sha256=sha(report),
        review=str(review),review_sha256=sha(review),candidate=str(candidate),
        EL1_inputs_unchanged=True,new_additional_test_started=False,
        role='Conditional EM source work during the one reported EL1 timing-only job')
    active['pending_source_research']=dict(next='Read completed EL1 metrics and mapped limiting paths; only then decide on EM or another structural direction.',
        candidate=str(candidate),adopted=False,tests_started=False)
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(review=str(review),clocked_blocks_text_equal=total,
        EL1_inputs_unchanged=True,new_additional_tests_started=False,adopted=False)))


if __name__=='__main__':
    main()
