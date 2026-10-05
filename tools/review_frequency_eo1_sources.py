"""Archive the complete EO1 source and handshake review; no HDL/EDA tests."""
import difflib
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT
from prepare_prf_precompare_and_store_imm12 import verify_parent
from prepare_stable_mmio_and_registered_hit import stable_core
from prepare_registered_cache_hit_reply import core as held_core, cache as held_cache
from review_frequency_dx_sources import blocks


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    root=Path('E:/Verilog_cpu')
    ap=root/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=read(ap)
    parent=ROOT/'EL1_cache_response_match_before_select'
    en=ROOT/'EN1_mmio_narrow_stable_domains'
    eo=ROOT/'EO1_registered_cache_hit_reply'
    assert Path(active['candidate'])==parent and active['measurement_process_id'] is None
    assert active['status']=='WORKTREE_IMPLEMENTED_TIMING_ONLY_COMPLETE_PROGRAMS_NOT_RUN'
    for p in (parent,en,eo):
        verify_parent(p)
    pm,cm=read(parent/'candidate.json'),read(eo/'candidate.json')
    delta=[n for n,h in cm['source_sha256'].items() if h!=pm['source_sha256'][n]]
    assert delta==['rtl/cache/rv32_dcache_nonblocking.v','rtl/cpu_core.v']
    assert cm['new_declared_sequential_state_bits']==0 and len(cm['implemented_groups'])==18
    assert cm['parameter_overrides']==pm['parameter_overrides']==active['parameter_overrides']
    old_core=(parent/'rtl/cpu_core.v').read_text(encoding='utf-8')
    new_core=(eo/'rtl/cpu_core.v').read_text(encoding='utf-8')
    old_cache=(parent/delta[0]).read_text(encoding='utf-8')
    new_cache=(eo/delta[0]).read_text(encoding='utf-8')
    assert stable_core(old_core)==(en/'rtl/cpu_core.v').read_text(encoding='utf-8')
    assert held_core(stable_core(old_core))==new_core
    assert held_cache(old_cache)==new_cache
    for anchor in ("(memory_dreq_addr == 32'h80000000)","(memory_dreq_mask == 16'h000f)",
                   'if (mmio_exit_request && mem_d_req_ready)',
                   'mem_d_req_wdata[32+upper_word*16 +: 16]',
                   'mmio_exit_views[11+upper_word]', '.HIT_BYPASS(0)'):
        assert anchor in new_core,anchor
    for anchor in ('resp_slot_free = !resp_valid_reg || dcache_resp_ready_i;',
                   "resp_valid_reg <= !(bypass_load_hit && dcache_resp_ready_i);",
                   "resp_from_sram <= (TAG_SRAM == 0);",
                   'response_hit_capture && TAG_SRAM!=0,response_sram_capture',
                   'data_rdata,response_hit_word,',
                   'wire bypass_store_ack = (TAG_SRAM != 0) && request_fire &&'):
        assert anchor in old_cache and anchor in new_cache,anchor
    total=0
    patch=[]
    for n in cm['source_sha256']:
        if n.endswith('.v'):
            original=blocks((parent/n).read_text(encoding='utf-8'))
            assert original==blocks((eo/n).read_text(encoding='utf-8')),n
            total+=len(original)
        if n in delta:
            patch.extend(difflib.unified_diff((parent/n).read_text(encoding='utf-8').splitlines(True),
                         (eo/n).read_text(encoding='utf-8').splitlines(True),
                         fromfile=parent.name+'/'+n,tofile=eo.name+'/'+n))
    for n,h in active['source_sha256'].items():
        assert sha(root/n)==h,n
    run=Path(active['frozen_run'])
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    frozen=read(run/'source_manifest.json')
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    proof=Path('F:/CPU2026Proofs/EO1_source_review_20261005')
    proof.mkdir(exist_ok=False)
    full_patch=proof/'changes_vs_measured_EL1.patch'
    full_patch.write_text(''.join(patch),encoding='utf-8')
    saved=read('F:/CPU2026Proofs/EF_mapped_paths_20261005/saved_path_analysis.json')
    bypass_paths=[p['rank'] for p in saved['paths'] if any('response_output_tree.g_driver[0].invert_root' in s['instance'] for s in p['segments'])]
    assert bypass_paths==[2,3,4,5]
    data=dict(status='FINAL_COMBINATION_SOURCE_AND_HANDSHAKE_REVIEW_ONLY_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),candidate=str(eo),candidate_manifest_sha256=sha(eo/'candidate.json'),
        chain=[dict(candidate=str(p),manifest_sha256=sha(p/'candidate.json')) for p in (parent,en,eo)],
        changed_files_vs_EL1=delta,candidate_inputs_verified=len(cm['source_sha256']),
        EL1_worktree_inputs_verified=len(active['source_sha256']),EL1_frozen_inputs_verified=len(frozen['snapshot_sha256']),
        EL1_inputs_unchanged=True,ordinary_integer_pipeline_depth=10,new_declared_state_bits=0,
        compound_clocked_blocks_text_equal=total,clock_text_is_not_cycle_equivalence=True,
        current_mmio_control_domains=17,maximum_mmio_payload_bits_per_leaf=16,
        masked_upper96_data_intentionally_zero_during_MMIO=True,
        raw_masked_payload_not_bitwise_equal_to_original=True,
        mmio_manual_binary_reasoning=[
            'Original exit predicate still requires request-valid/store, address80000000 and mask000f. Every control-tree view equals that predicate; acknowledgement uses the original predicate/edge.',
            'Normal requests retain all128 data bits. MMIO retains low32 exactly and uses constantzero for upper96, preserving all bytes enabled by mask000f.',
            'The unchanged bridge selects word mask nibbles, sets write_word_present only for nonzero current_mask, and only then asserts AWVALID/WVALID. MMIO words1..3 have zero nibble masks and issue no AXI write; enabled_words remains1, acknowledgement and FIFO rules unchanged.',
            'Under MMIO backpressure, the existing request skid stage holds the low32 payload and all transaction fields; masked upper96 are constantzero even if normal cache data changes.',
            'Current cached profile emits normal wmaskffff or0000; bridge count is4 or0. MMIO emits000f, count1; the original enabled_words bit0 therefore equals MMIO predicate. Alias alone is not exclusive bridge ownership.'
        ],hit_manual_handshake_reasoning=[
            'With HIT_BYPASS0, no hit is published from live request fields. Original request_fire/static action captures the same complete hit metadata and data into existing owners; original resp_valid_reg equation becomes1 on every accepted hit.',
            'At the next cycle, valid and captured tag/address/line/word/error are aligned. The first empty-slot hit is intentionally one cycle later; no claim of cycle-equivalence or measured IPC bound.',
            'While ready0 and held valid1, original resp_slot_free0 prevents accepting another load hit, and existing registered payload is retained. Reset, waiters and miss-response arbitration remain original.',
            'When a held response is consumed and another hit is accepted on the same edge, old data is consumed and existing owners capture the next response. This preserves the source ability to accept consecutive hits; actual throughput/IPC is unmeasured.',
            'TAG_SRAM0 already had no load-hit bypass. Default HIT_BYPASS1 retains generic behavior; store-ack bypass and MMIO ack are unchanged.'
        ],saved_EF_paths_through_bypass_bit0=bypass_paths,
        EL1_slowest_two_gates_ns=[1.1544,0.7405],
        EL1_slowest_gate_loads=[165,47],
        architecture_triage=[
            'Actual EL1 root is the wide qualified MMIO selector; handle final consumers instead of changing bridge word counts or treating a retained alias as exclusive ownership.',
            'Use existing cache response registers to cut the entire old cache→LSQ bypass chain instead of only reducing individual field gate loads.',
            'EM widens the shared store ROB query packet, but current EL1 top paths do not justify it. Keep it separate.',
            'Per-row cache response classification remains a source idea, but registered hit output removes its demonstrated cross-module critical consumer. Do not add duplicated queries without new limiting evidence.',
            'Full CDB/extra response packet stages, port/window reduction and speculative wake require broader latency/recovery changes. No additional source transformation is sufficiently justified for this final batch.'
        ],caveats=['Source/hash/manual binary/handshake reasoning only; no HDL acceptance, formal, simulation, synthesis, STA or IPC run.',
            'Zero new declared state does not imply unchanged mapped sequential area.',
            'New mapped loads/global Fmax unknown; hit latency and IPC intentionally trade off. Original area/IPC range and Tier3 remain requirements.'],
        patch=str(full_patch),patch_sha256=sha(full_patch),new_test_started=False,adopted=False)
    review=proof/'source_review.json'
    review.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    report=root/'reports/frequency_EL1_background_research_2026-10-05.md'
    text=report.read_text(encoding='utf-8')
    text+='''\n## EL1 完成：266.88 MHz，真实限制变成宽 MMIO 选择\n\nEL1 单次 Windows 原生 timing-only 完成：266.875163 MHz、含 SRAM 49,613.040354 μm²；相对 EF 频率 -27.9646%、面积 +1.0100%，原面积基线 +7.1332%。没有 CPU 构建、IPC 或功能程序。不能把这次回归归因到某个单项改动；五条最慢路径现在都经过 enabled_words 别名所在的 165-load NOR4（1.1544 ns）及 47-load INV（0.7405 ns），原缓存四条不再是导出的最慢路径。\n\n只读新映射 JSON，得到函数 result[0] 的公共别名与 165 个真实消费者。当前缓存常规 mask 只有 ffff/0000，退出请求 mask000f，所以 count 低位与 MMIO 请求条件等价。此别名不能被误当成仅属于 bridge 的计数输出；修改 bridge 计数或只给它增加分发不会解决 CPU 宽 mux 的最终消费者。\n\n## EN1 与 EO1：已实现完整源码组合，尚未测试\n\nEN1 保留 MMIO 的完整地址/mask/valid/store 检测和原 acknowledgement 时钟块；低32位数据仍精确来自原请求，上96位在 MMIO 下固定零，普通请求保留完整128位。17个控制域让每个数据叶最多服务16位。桥仍只给非零 mask 的 word 发 AW/W；退出请求只有第0 word 启用，所以被清零的上96位不改变任何 AXI 写或返回码。上位固定零还确保MMIO回压时整个请求稳定。此前 EN/EO 草稿保留，但采用此稳定的 EN1/EO1 分支。\n\nEO1 复用 Dcache 已有完整 response metadata/data owners 和 resp_valid_reg，CPU 将新增默认1的 HIT_BYPASS 参数置0。接受 hit 后从已有寄存器返回，空响应槽的首次 hit 多一拍；普通整数流水线仍10级，零新增状态。保持原 request_fire/capture、响应槽回压、reset、store-ack bypass、miss/waiter 仲裁。已有 EF 第2–5条路径明确经过 response_output_tree.g_driver[0]，源码 bit0 就是 bypass_load_hit；这一修改切断整个 MSHR 仲裁→hit输出→LSQ选行/提取联系，而非只修一个门。\n\nEL1→EN1→EO1 的41个候选输入、69个复合时钟块已核对，除两个 RTL 的组合式/参数外其余源相同。时钟文本相同不等于周期行为相同：HIT_BYPASS0有意改变首次hit返回时刻；IPC尚未知。审查：`F:/CPU2026Proofs/EO1_source_review_20261005/source_review.json`。当前主工作区仍是测得266.88MHz的EL1；没有新测量。\n\nEM 的共享 ROB 查询预解码与逐行缓存响应分类思路仍分开保存：当前实际路径不支持混入前者，EO1 已将后者的已证跨模块关键消费者移到现有寄存器边界。暂未找到另一个依据充分、应继续混入这批的结构变换。最终冻结后先汇报，再只测整体频率/面积一次；不得测中间草稿或用 EF/EL1 指标替代 EO1 指标。\n'''
    report.write_text(text,encoding='utf-8')
    records=[]
    for p in (ROOT/'EN_mmio_narrow_request_domains',ROOT/'EO_registered_cache_hit_reply',en,eo):
        record=dict(candidate=str(p),manifest_sha256=sha(p/'candidate.json'),tests_started=False,adopted=False,
            role=('Final combined stable-MMIO/register-hit source candidate' if p==eo else 'Source intermediate/draft preserved; no separate measurement'))
        if p==eo:
            record.update(review=str(review),review_sha256=sha(review))
        records.append(record)
    active['prepared_unmeasured_alternatives'].extend(records)
    active['post_dispatch_source_research'].update(report_sha256=sha(report),latest_review=records[-1],
        role='EL1 completed regression; EO1 final source review complete, no further measurement started')
    active['pending_source_research']=dict(next='Freeze reviewed EO1 and report final scope before one overall timing-only measurement.',
        candidate=str(eo),adopted=False,tests_started=False)
    active['source_research_decision']='Address actual 165-load qualified MMIO mux and use existing registered cache reply boundary; EM and cache classification stay separate. Report before the next combined timing-only job.'
    ap.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(review=str(review),candidate_manifest_sha256=data['candidate_manifest_sha256'],
        clocked_blocks_text_equal=total,EL1_inputs_unchanged=True,new_tests_started=False)))


if __name__=='__main__':
    main()
