"""Archive conditional EQ source reasoning and correct the request-stage note."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT
from prepare_prf_precompare_and_store_imm12 import verify_parent
from prepare_lsq_mmio_classification import lsq, backend, core
from review_frequency_dx_sources import blocks


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    root=Path('E:/Verilog_cpu')
    ap=root/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=read(ap)
    parent=ROOT/'EP_lsq_selection_payload_word_owners'
    candidate=ROOT/'EQ_lsq_registered_mmio_classification'
    assert Path(active['candidate'])==parent and active['tests_started']
    assert active['measurement_plan']['initial_phase']=='TIMING_ONLY'
    verify_parent(parent)
    verify_parent(candidate)
    pm,cm=read(parent/'candidate.json'),read(candidate/'candidate.json')
    transforms={'rtl/backend/rv32_lsq.v':lsq,'rtl/backend/rv32_backend_joint.v':backend,'rtl/cpu_core.v':core}
    changed=[n for n,h in cm['source_sha256'].items() if h!=pm['source_sha256'][n]]
    assert set(changed)==set(transforms)
    assert cm['parameter_overrides']==pm['parameter_overrides']==active['parameter_overrides']
    assert cm['active_profile_additional_state_bits']==1 and len(cm['implemented_groups'])==20
    for n,f in transforms.items():
        assert f((parent/n).read_text(encoding='utf-8'))==(candidate/n).read_text(encoding='utf-8'),n
    total=0
    for n in cm['source_sha256']:
        if n.endswith('.v'):
            original=blocks((parent/n).read_text(encoding='utf-8'))
            assert original==blocks((candidate/n).read_text(encoding='utf-8')),n
            total+=len(original)
    assert total==69
    lsq_text=(candidate/'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8')
    core_text=(candidate/'rtl/cpu_core.v').read_text(encoding='utf-8')
    for anchor in ('wire request_valid=admitted && (!load_i || incomplete_forward);',
        'assign store_o=valid_views[1] && !load_views[3];',
        "wire [15:0] inserted_mask={12'b0,relative_mask} << address_i[3:0];",
        'assign mask_o={16{valid_views[2]}} & inserted_mask;',
        'assign dcache_req_mmio_exit_o=dcache_req_valid_o && selected_mmio_exit;'):
        assert anchor in lsq_text,anchor
    for anchor in ('wire mmio_exit_request = memory_dreq_valid && memory_dreq_mmio_exit;',
        'if (mmio_exit_request && mem_d_req_ready)',
        '.dcache_req_is_store_o(dcache_req_store), .dcache_req_mmio_exit_o(dcache_req_mmio_exit),',
        'assign dcache_req_mmio_exit=dcache_req_store &&',
        '.WIDTH(DREQ_PAYLOAD_WIDTH)'):
        assert anchor in core_text,anchor
    # The active top uses the LSQ request selection, not the optional extra
    # CPU skid register. Earlier EO1 prose accidentally assumed the latter.
    top=(parent/'rtl/course/student_top.v').read_text(encoding='utf-8')
    assert 'DCACHE_INDEX_HASH = 1, DCACHE_REQUEST_PIPELINE = 0,' in top
    assert pm['parameter_overrides'].get('DCACHE_REQUEST_PIPELINE',0)==0
    assert '.REQUEST_PIPELINE(1)' in (parent/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    run=Path(active['frozen_run'])
    frozen=read(run/'source_manifest.json')
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    assert sha(active['pretest_report'])==active['pretest_report_sha256']
    for n,h in active['source_sha256'].items():
        assert sha(root/n)==h,n
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    proof=Path('F:/CPU2026Proofs/EQ_source_review_20261005')
    proof.mkdir(exist_ok=False)
    data=dict(status='CONDITIONAL_SOURCE_REVIEW_ONLY_NOT_ADOPTED_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),candidate=str(candidate),
        candidate_manifest_sha256=sha(candidate/'candidate.json'),parent_candidate=str(parent),
        parent_manifest_sha256=sha(parent/'candidate.json'),changed_files=changed,
        source_groups=20,compound_clocked_blocks_text_equal=total,
        active_profile_additional_state_bits=1,active_profile_selection_payload_bits=111,
        optional_CPU_request_register_additional_state_bits=1,
        active_profile_CPU_request_register_enabled=False,ordinary_integer_pipeline_depth=10,
        extra_transaction_latency_cycles=0,existing_hit_extra_cycle_inherited=True,
        manual_binary_reasoning=[
            'Let V=request_valid, L=selected_load, A=selected_addr, M=selected_store_mask. Original exit is V && (V && !L) && A==80000000 && (V ? ({12zero,M} << A[3:0]) : 0)==000f.',
            'For V0, original and new exit both0. For L1, both0. For V1/L0/A!=80000000, both0. For V1/L0/A80000000, offset is0 and original mask equality holds iff M==f. Therefore original is V && (!L && A80000000 && Mf). No alignment/generation/queue invariant is assumed.',
            'Store classification C=!pick_load && pick_addr==80000000 && pick_store_mask==f is captured on exactly the existing selection_input_fire edge beside all fields. With REQUEST_PIPELINE1 its single bit matches the selected fields until replacement; with REQUEST_PIPELINE0 classifier and fields use the same current pick.',
            'New output V && C uses the unchanged V: full candidate/live LSQ generation, committed-store eligibility, wait/flush/recovery and forwarding/request admission. Classification alone never authorizes a request.',
            'CPU direct mode carries the new flag with the direct original fields and qualifies with memory_dreq_valid. CPU request-register mode prepends the flag to the same complete packet, so one existing skid acceptance/hold/reset edge aligns it; +1 payload bit there only if that mode is enabled.',
            'Legacy serial backend has no classifier port: CPU fallback computes the original full store/address/mask predicate before the optional packet register. On accepted packets all original fields are preserved; normal requests and MMIO active-byte/ack semantics remain inherited.',
            'Prepending the classifier leaves all old packed payload bits in their original low positions. LSQ bank110→111 stays7 leaves with only the final leaf growing14→15 bits. No old payload writer or valid/recovery block changes.',
            'The classification comparator now lies before the LSQ selection edge. It can worsen that earlier stage or gain nothing if MMIO is no longer critical; no frequency or area improvement is claimed without a new limiting path.'
        ],request_stage_documentation_erratum={
            'earlier_review':'F:/CPU2026Proofs/EO1_source_review_20261005/source_review.json',
            'incorrect_prose':'Existing CPU request skid stage holds the MMIO request in the current profile.',
            'actual_configuration':'student_top DCACHE_REQUEST_PIPELINE0 (not overridden), backend LSQ REQUEST_PIPELINE1.',
            'corrected_reasoning':'For a continuously asserted store request waiting for ready, the existing LSQ selection payload holds: request_fire0, selection_done0 for store, and selection_input_fire0 while selection_live1. The selected store fields remain captured until acceptance/discard/recovery. MMIO upper96 remain constant0. The optional CPU skid would additionally hold the whole packet only if DCACHE_REQUEST_PIPELINE1.',
            'scope':'Correction to source-review prose, no change to EP RTL, frozen inputs, constraints, immutable pretest report or dispatched measurement. Reset/recovery can withdraw valid according to unchanged original rules.'},
        source_identity=dict(worktree_inputs_verified=len(active['source_sha256']),
            EP_frozen_inputs_verified=len(frozen['snapshot_sha256']),EP_inputs_unchanged=True,
            EP_pretest_report_unchanged=True),
        adoption_condition=cm['adoption_condition'],
        caveats=['Source/hash/manual two-state reasoning only; no HDL acceptance/formal/simulation/EDA.',
            'Clock text equal is not full cycle-equivalence; one new payload state bit has been added inside word-bank.',
            'Existing EP load-hit extra cycle remains, IPC/area/Fmax unknown.'],
        tests_started=False,adopted=False,EP_background_measurement_restarted=False)
    review=proof/'source_review.json'
    review.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=root/'reports/frequency_EP_background_research_2026-10-05.md'
    assert not report.exists()
    text='''# EP 后台期间源码研究与文档更正

当前只有EP的一次原生 timing-only在后台，未启动CPU构建或程序。主工作区及157个冻结输入、测试前报告hash均保持。未启动EQ测试。

## 请求保持来源更正

EO1原审查将当前MMIO请求保持归因到CPU可选skid级，这句话不准确。当前student_top `DCACHE_REQUEST_PIPELINE=0`，39项override无改写；backend显式LSQ `REQUEST_PIPELINE=1`。持续valid的store等待ready时，既有LSQ选择payload保持；store的selection_done在request_fire=0时为0，selection_input_fire不能覆盖仍live的selection。reset/恢复可按原规则撤销valid；MMIO上96位固定0。CPU额外skid只在参数1时存在。原审查/预测试报告保存原hash，使用这份补充纠正文字；EP RTL和测量行为不变。

## 条件备选 EQ：将事务分类移到原LSQ选择边沿之前

若EP的完成报告仍显示MMIO检测/请求mask资格是限制，再考虑EQ。新增一个与原110位选择payload同拍存储的分类位：`!pick_load && pick_addr==80000000 && pick_store_mask==f`。当前变111位仍7写叶、仅多1状态位，不加LSQ阶段/事务延迟。最后必须与原request_valid相与；原live/full generation/committed-store/flush/recovery/wait资格全部保留。CPU直接模式沿用该标志；可选CPU寄存模式将其与全部原packet一起捕获；串行backend用完整原predicate fallback。

二值代数理由：原退出条件是valid、store、地址80000000和输出line mask000f。valid0或load1均不能退出；地址80000000低offset=0，store mask左移后等于000f恰好要求原store_mask=f。因此可在已有LSQ选择边沿前计算分类，保留实时完整valid资格，而省去资格后store/mask门与32位地址比较。并不缓存权限，也不依赖“已退休tag永远live”等不正确假设。

该方案将比較移到更早的LSQ选择阶段，可能使早级更慢；EP已经分散MMIO负载后，也可能完全不需要此变化。仅实现为独立条件备选，不能据源码预测MHz或自动加入EP。69个复合时钟块文本保持，单语句word-bank载荷增加1位人工核对。没有HDL编译、仿真、STA/综合或形式测试。

## 开源资料支持的边界

[BOOM Physical Realization](https://docs.boom-core.org/en/latest/sections/physical-realization.html)说明关闭前端flow-through可缩短fetch到dispatch联系，寄存branch resolution以一拍误预测代价换周期，并强调组合乘法后补延迟寄存器仍需retiming；这里将“已有边沿前做分类”作为设计推断，不能用其1GHz数字预测课程ASAP7结果。

[BOOM LSU](https://docs.boom-core.org/en/latest/sections/load-store-unit.html)保留store地址/数据资格并在commit后顺序发出；其乐观load/冲突后重放需要完整记忆序恢复，本CPU没有理由只删冲突/ROB权限来缩短链。[Ibex LSU](https://ibex-core.readthedocs.io/en/latest/03_reference/load_store_unit.html)说明请求等待grant与返回数据/error必须对齐；用于核对握手设计原则，并未照搬其in-order流水级或假设协议相同。

当前预先保存EM、EH与新EQ均有明确采纳条件。先读取EP新最慢路径，再选有证据的源方案；不得重启正在运行的测量，也不得为这些备选单项测试。

'''
    text+=f"- EQ候选：`{candidate}`\n- EQ manifest SHA256：`{sha(candidate/'candidate.json')}`\n- 源审查及更正：`{review}`\n- 原EP pretest SHA256：`{active['pretest_report_sha256']}`\n- 运行EP frozen SHA256：`{active['frozen_manifest_sha256']}`\n"
    report.write_text(text,encoding='utf-8')
    record=dict(candidate=str(candidate),manifest_sha256=sha(candidate/'candidate.json'),
        tests_started=False,adopted=False,review=str(review),review_sha256=sha(review),
        role='Conditional registered MMIO classification; adopt only if completed EP paths justify. Active+1 bit/no cycle.')
    active['prepared_unmeasured_alternatives'].append(record)
    active['post_dispatch_source_research']=dict(report=str(report),report_sha256=sha(report),
        review=str(review),review_sha256=sha(review),candidate=str(candidate),EP_inputs_unchanged=True,
        new_additional_test_started=False,role='Conditional source review during single EP timing-only job; request-stage prose corrected')
    active['ongoing_research_report']=str(report)
    active['pending_source_research']=dict(next='Observe original EP job, read limiting paths; consider EQ only if classifier still limits.',
        candidate=str(candidate),adopted=False,tests_started=False)
    ap.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(review=str(review),candidate_manifest_sha256=data['candidate_manifest_sha256'],
        compound_clocked_blocks_text_equal=total,additional_state_bits=1,EP_inputs_unchanged=True,
        report=str(report),new_tests_started=False)))


if __name__=='__main__':
    main()
