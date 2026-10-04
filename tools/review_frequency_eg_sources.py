"""Archive an isolated arithmetic/bypass source review; never execute HDL/EDA."""
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
    workspace = Path('E:/Verilog_cpu')
    active_path = workspace/'build/cpu2026/active_frequency_implementation_20261004.json'
    active = json.loads(active_path.read_text(encoding='utf-8'))
    ef = ROOT/'EF_rob_commit_packet_domains'
    eg = ROOT/'EG_prf_parallel_store_address'
    assert Path(active['candidate']) == ef
    for candidate in (ef, eg):
        verify_parent(candidate)
    assert sha(ef/'candidate.json') == active['candidate_manifest_sha256']
    for name, expected in active['source_sha256'].items():
        assert sha(workspace/name) == expected, name
    run = Path(active['frozen_run'])
    assert sha(run/'source_manifest.json') == active['frozen_manifest_sha256']
    frozen = json.loads((run/'source_manifest.json').read_text(encoding='utf-8'))
    for name, expected in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/name) == expected, name

    parent = json.loads((ef/'candidate.json').read_text(encoding='utf-8'))
    candidate = json.loads((eg/'candidate.json').read_text(encoding='utf-8'))
    changes = [name for name, h in candidate['source_sha256'].items()
               if h != parent['source_sha256'][name]]
    assert set(changes) == {'rtl/rv32_physical_register_file.v',
                           'rtl/backend/rv32_backend_joint.v', 'rtl/cpu_core.v'}
    total = 0
    records = []
    for name in candidate['source_sha256']:
        if not name.endswith('.v'):
            continue
        old = (ef/name).read_text(encoding='utf-8')
        new = (eg/name).read_text(encoding='utf-8')
        clocked = blocks(old)
        assert clocked == blocks(new), name
        total += len(clocked)
        records.append(dict(file=name,compound_clocked_blocks=len(clocked),
                            existing_clocked_text_equal=True))

    prf_name = 'rtl/rv32_physical_register_file.v'
    old = (ef/prf_name).read_text(encoding='utf-8')
    new = (eg/prf_name).read_text(encoding='utf-8')
    bypass_start = '            for(wl=0;wl<BE_WIDTH;wl=wl+1) begin:g_bypass'
    assert old.split(bypass_start,1)[1].split('            always @* begin',1)[0] == \
           new.split(bypass_start,1)[1].split('            if((rp%2)==0)',1)[0]
    original_parallel_read = old.split('            always @* begin',1)[1].split('    end else begin : g_original_read',1)[0]
    assert original_parallel_read == new.split('            always @* begin',1)[1].split('    end else begin : g_original_read',1)[0]
    legacy_start = '    // Reads are combinational.'
    assert old.split(legacy_start,1)[1] == new.split(legacy_start,1)[1]
    parallel_tree_start = '    localparam integer READ_ROWS='
    assert old.split(parallel_tree_start,1)[1].split(bypass_start,1)[0] == \
           new.split(parallel_tree_start,1)[1].split(bypass_start,1)[0]
    backend_name = 'rtl/backend/rv32_backend_joint.v'
    old_backend = (ef/backend_name).read_text(encoding='utf-8')
    new_backend = (eg/backend_name).read_text(encoding='utf-8')
    guard = '''                assign lsq_alloc_addr_valid[io_lane] = (EARLY_STORE_ADDRESS != 0) &&
                    d_valid[io_lane] && d_is_store[io_lane] && rs_src1_ready[io_lane];'''
    assert guard in old_backend and guard in new_backend
    ready_start = '            rs_src1_ready[source_lane] ='
    dependency_end = '    localparam integer PARALLEL_STORE_ADDRESS='
    old_dependency = old_backend.split(ready_start,1)[1].split('    rv32_physical_register_file #',1)[0]
    new_dependency = new_backend.split(ready_start,1)[1].split(dependency_end,1)[0]
    assert old_dependency == new_dependency
    top = (eg/'rtl/course/student_top.v').read_text(encoding='utf-8')
    assert 'parameter integer FE_WIDTH = 4, BE_WIDTH = 4,' in top
    assert 'parameter integer PRF_READ_MUX_IMPL = 1,' in top

    proof = Path('F:/CPU2026Proofs/EG_source_review_20261005')
    proof.mkdir(exist_ok=False)
    review = proof/'source_review.json'
    data = dict(status='SOURCE_REVIEW_ONLY_UNADOPTED_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),candidate=str(eg),
        candidate_manifest_sha256=sha(eg/'candidate.json'),parent_candidate=str(ef),
        parent_manifest_sha256=sha(ef/'candidate.json'),changed_files_vs_EF=changes,
        candidate_inputs_verified=len(candidate['source_sha256']),
        EF_worktree_inputs_verified=len(active['source_sha256']),
        EF_frozen_inputs_verified=len(frozen['snapshot_sha256']),EF_inputs_unchanged=True,
        compound_clocked_blocks_reviewed=total,source_records=records,
        original_prf_bypass_matches_and_priority_selector_text_equal=True,
        original_prf_parallel_read_data_and_ready_text_equal=True,
        original_prf_legacy_read_and_storage_suffix_text_equal=True,
        original_prf_stored_read_tree_text_equal=True,
        allocation_valid_guard_text_equal=True,same_bundle_dependency_and_ready_text_equal=True,
        current_materialized_BE_WIDTH=4,current_parallel_read_enabled=True,
        additional_declared_state_bits=0,ordinary_integer_pipeline_depth=10,
        allocation_adders=dict(formula='BE_WIDTH*(1+BE_WIDTH)',EG=20,EA=4,EF=0),
        manual_binary_algebra=[
            'No legal write match: fallback selects exactly the original stored_tree[1] plus the same signed-12 offset.',
            'One or more matches: original highest numbered write slot still wins; the new selector shifts every write event index by one and assigns fallback index zero only if no match exists.',
            'Addition modulo 2^32 commutes with the determined selection because every candidate uses the same offset.',
            'P0/padding read zero and bypass legal/range qualification remain original. New address validity still requires the original source-ready guard; normal ROB authority and same-bundle dependencies are retained.'
        ],
        estimated_extra_adder_area_vs_EA_um2=227.448,
        estimated_complete_allocation_adder_area_vs_EF_um2=284.310,
        area_evidence='F:/CPU2026Proofs/EF_parallel_address_plan_20261005/summary.json',
        review_scope='Source hashes, selected original combinational text, compound begin/end clocked text, and manual dataflow algebra. Not HDL parsing, simulation, formal proof, synthesis, timing or IPC.',
        caveats=[
            'Binary determined-control algebra only; no executable four-state or parameter proof.',
            'Clocked-text identity is not full architectural correctness.',
            'Additional selectors and write-data/offset load may offset timing gains; old mapped adder area does not predict new total area.',
            'Only the isolated candidate is changed; the EF job measures EF, never EG.'
        ],new_test_started=False,adopted=False,
        patch=str(eg/'changes_vs_parent.patch'),patch_sha256=sha(eg/'changes_vs_parent.patch'))
    review.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    report = workspace/'reports/frequency_EF_background_research_2026-10-05.md'
    text = report.read_text(encoding='utf-8')
    text = text.replace('这里记录一个新条件方向，尚未创建新 candidate，也没有改 EF 的任何工作区或冻结源。不会据此启动第二个综合。',
        '这里记录一个条件方向及其后续源码实现。独立 EG 备选已创建并完成源码关系审查，未采用、未测量。EF 工作区与冻结源保持一致，不据此启动第二个综合。')
    text = text.replace('若 EF 实测获得明显频率余量，可以先实现该独立备选并比较结构，再考虑一次完整组合测量。',
        'EG 已先作为独立备选实现并比较源码结构。应先结合 EF 的实际频率、面积与限制路径，再决定后续完整组合；任何新测量前先汇报。')
    text += f'''\n## EG 已实现，源码审查结果\n\nEG 位于 `{eg.as_posix()}`，仅 PRF、backend joint、CPU core 三个 RTL 与 EF 不同。新模式 2 在 PRF 内并行算旧存储值和各写回值的地址，之后复用原旁路匹配和最高槽优先级。模式 0 保留 EF，模式 1 保留原后加法器；不支持 parallel/signed-12 合同时回到原实现。\n\n核对候选 41 个源、主工作区 {len(active['source_sha256'])} 个源及冻结 EF {len(frozen['snapshot_sha256'])} 个源的哈希。{total} 个 begin/end 时钟块文本与 EF 相同；原 PRF 存储读树、旁路比较、数据/ready 输出、legacy 读写后缀，以及后端 ready/同批依赖段均保持原文本。普通整数流水线仍为 10 级，零新增状态。此项仅源码关系审查，不是 HDL、功能、等价或时序测试。\n\n当前课程顶层明确 `BE_WIDTH=4`、`PRF_READ_MUX_IMPL=1`；通用宏默认宽度为 1，不能用宏默认代替实际测量配置。新分配加法器共 20 个；未声称全局频率收益或面积达标。EF 的实测结果只能属于 EF。\n\n源码审查：`{review.as_posix()}`。候选 manifest SHA256：`{data['candidate_manifest_sha256']}`。\n'''
    report.write_text(text,encoding='utf-8')
    # Reload after the review; preserve any observer fields recorded meanwhile.
    active = json.loads(active_path.read_text(encoding='utf-8'))
    assert Path(active['candidate']) == ef
    alternatives = active.setdefault('prepared_unmeasured_alternatives',[])
    assert not any(Path(x['candidate']) == eg for x in alternatives)
    alternatives.append(dict(candidate=str(eg),manifest_sha256=data['candidate_manifest_sha256'],
        tests_started=False,adopted=False,review=str(review),review_sha256=sha(review),
        role='Isolated arithmetic-before-PRF-bypass allocation address; source-reviewed, no measurement scheduled'))
    active['post_dispatch_source_research'] = dict(report=str(report),report_sha256=sha(report),
        review=str(review),review_sha256=sha(review),EF_inputs_unchanged=True,new_test_started=False,
        role='EG parallel allocation store address implemented and source-reviewed; unadopted, unmeasured',
        prior_plan_review='F:/CPU2026Proofs/EF_parallel_address_plan_20261005/summary.json')
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(review=str(review),compound_clocked_blocks_reviewed=total,
        candidate_manifest_sha256=data['candidate_manifest_sha256'],EF_inputs_unchanged=True,
        report=str(report),new_test_started=False,adopted=False)))


if __name__ == '__main__':
    main()
