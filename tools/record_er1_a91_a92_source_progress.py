"""Journal full load packet/source preparation before a coherent measurement."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a83_measurement import check, live, RUN

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT/'build/cpu2026/er1_a91_a92_source_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A91_A92_load_packet_and_source_queries_2026-10-06.md'
ITEMS = [
    ('A91_head_load_packet_preselect','prepare_er1_head_load_packet_preselect.py','a8e25ceb8c851e50f5f176c5a9e2513794ed9d871f1ed792dacc573c3a44ee43'),
    ('A92_load_response_source_query','prepare_er1_load_response_source_query.py','113a0b3d696a4884a5dff09c94604dfbd48f4e3273c7a35b83380e1d6e0e56c2'),
]


def main():
    assert not PROOF.exists() and not REPORT.exists()
    state = read(STATE)
    assert state['current_source_candidate'] == 'A90_lsq_allocation_slot_preselect'
    assert state['active_measurement_candidate'] is None and state['active_measurement_process_ids'] == []
    previous_proof = Path(state['last_source_progress_proof'])
    assert sha(previous_proof) == state['last_source_progress_proof_sha256'] == 'fb67bda05d80257fb7d0859164eae6a2a080330806e672345686220c3f9e9000'
    terminal = Path(state['measurement_terminal_proof'])
    assert sha(terminal) == state['measurement_terminal_proof_sha256'] == '152bf20caac6b9440872f336deba4373cfc92f71772adc8a8f518f0b8d92d2c1'
    plan = check()
    phases = read(RUN/'serial_phase_identity.json')
    assert phases['status'] == 'SERIAL_CHARACTERIZATION_COMPLETE' and not live(82452)
    assert phases['supervisor_pid'] == 82452 and all(p['returncode'] == 0 for p in phases['phases'])
    completed = read(terminal)
    for path,digest in completed['artifacts_sha256'].items():
        assert sha(Path(path)) == digest, path
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == completed['main_active_manifest_sha256']
    for path,digest in read(active)['source_sha256'].items():
        assert sha(ROOT/path) == digest, path
    previous = BASE/'A90_lsq_allocation_slot_preselect'
    records = []
    for name,script,expected in ITEMS:
        root = BASE/name
        candidate = read(root/'candidate.json')
        assert sha(root/'candidate.json') == expected
        assert Path(candidate['parent_candidate']).resolve() == previous.resolve()
        assert sha(previous/'candidate.json') == candidate['parent_candidate_sha256']
        assert sha(ROOT/'tools'/script) == candidate['preparation_script_sha256']
        assert len(candidate['source_sha256']) == 41
        for path,digest in candidate['source_sha256'].items():
            assert sha(root/path) == digest, (name,path)
        changed = sorted(path for path in candidate['source_sha256'] if (root/path).read_bytes() != (previous/path).read_bytes())
        assert changed == sorted(candidate['changed_from_parent_files'])
        review = Path(candidate['source_review'])
        assert read(review)['candidate_sha256'] == expected
        assert not candidate['tests_started'] and not candidate['adopted']
        assert candidate['candidate_ipc'] is candidate['candidate_area_um2'] is candidate['candidate_frequency_mhz'] is None
        records.append(dict(candidate=name,candidate_sha256=expected,parent_candidate_sha256=candidate['parent_candidate_sha256'],
            changed_files=changed,source_file_count=41,source_hashes_valid=True,script=str(ROOT/'tools'/script),
            script_sha256=sha(ROOT/'tools'/script),review=str(review),review_sha256=sha(review),tests_started=False,metrics=None,adopted=False))
        previous = root
    current = read(previous/'candidate.json')
    top = (previous/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key in ['FAST_STORE_SAVED_OPERANDS','LSQ_SAVED_REPORT_PRIORITY','LSQ_HEAD_LOAD_IDENTITY_QUERY',
                'LSQ_ALLOC_SLOT_PRESELECT','LSQ_HEAD_LOAD_PACKET_PRESELECT','LSQ_RESPONSE_SOURCE_QUERY']:
        assert current['parameter_overrides'][key] == 1
        match = re.search(r'\b'+key+r'\s*=\s*(\d+)',top)
        assert match and int(match[1]) == 1, key
    lsq = (previous/'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8')
    core = (previous/'rtl/cpu_core.v').read_text(encoding='utf-8')
    cache = (previous/'rtl/cache/rv32_dcache_nonblocking.v').read_text(encoding='utf-8')
    assert 'REPORT_WIDTH : ROB_TAG_WIDTH+REPORT_ROB_QUERY_WIDTH;' in lsq
    assert 'SAVED_IDENTITY_QUERY_LSB=(HEAD_LOAD_PACKET_ACTIVE!=0) ? REPORT_BASE_WIDTH : ROB_TAG_WIDTH;' in lsq
    assert 'head_packet_metadata[TAG_WIDTH +: PHYS_ADDR_WIDTH]' in lsq
    assert 'assign prepared_report_payload=load_report_identity_head_o ?' in lsq
    assert 'assign dcache_resp_query_valid_o={bypass_load_hit,resp_valid_reg && !bypass_load_hit};' in cache
    assert 'assign dcache_resp_query_tags_o={core_req_lsq_tag,resp_lsq_reg};' in cache
    assert core.count("assign dcache_resp_query_valid={1'b0,dcache_resp_valid};") == 2
    assert '.dcache_resp_query_valid_i(dcache_resp_query_valid)' in core
    for path in ['rtl/backend/rv32_rob.v','rtl/backend/rv32_reservation_station.v','rtl/backend/rv32_completion_network.v',
                 'rtl/rv32_rename_unit.v','rtl/rv32i_alu.v']:
        assert (previous/path).read_bytes() == (BASE/'A90_lsq_allocation_slot_preselect'/path).read_bytes(), path
    classification = 'PROGRESS_A91_PRESELECTED_FULL_LOAD_PACKET_A92_PARALLEL_CACHE_RESPONSE_IDENTITIES_RTL_NO_TESTS'
    REPORT.write_text('''# A91–A92：加载报告包和缓存响应身份前移

上一轮A87–A90已经完成源码修改。本轮新增A91/A92，当前独立候选A92，全部仍未测试、未采用，没有重启已结束A83。A83原PID82452缺失、两阶段rc0，冻结157文件/依赖/库/工具/结果/二进制与终态证明保持一致；主E EU40源码不变，工作在F盘，不用WSL。

目标保持频率严格>300MHz、IPC≥1.1、含SRAM面积≤36000μm²以及完整RV32IM、OoO、顺序提交、MMIO和参数化。最新实测A83 IPC1.074413717/Fmax244.683393MHz/面积35647.034498μm²；六项性能答案通过，19正确性未运行。A92不能继承这些数值。

| 候选 | 修改 | 保留和代价 |
|---|---|---|
| A91 | 保存/held报告完整包和query提前选择；队首LSQ全票据、物理目的、unretired/cancel提前读取，复用原队首ROB标签。真实队首返回只选准备好的包及原响应值/错误。 | 资格/实际valid/held优先级/slot/捕获/接受/回收/全GEN保持。保存身份树课程28→85bits，并新增24bit队首元数据读，原晚包树可能裁掉；组合成本未知。无新状态/等待边沿。 |
| A92 | 保存缓存响应与命中旁路候选完整LSQ票据各自核对当前行，再用原真实源有效位门控匹配。 | 原public valid=保存valid OR旁路，ticket=旁路?请求tag:保存tag。新增互斥事件{旁路,保存valid&&!旁路}等价，原数据/error/address/握手/状态不变。每行双全GEN比较/查询分发可能耗门；blocking/uncached单候选精确回退，serial仍原接口。 |

A91三种实际报告情况：live-held选保存原包；没有held而fast-head存在选队首原元数据+当前原格式值/error；均无时选原保存优先级包。正常/held选中行已complete，所以原row_fast_response为0，其原包等于新保存包；head-fast原快响应为1，新队首tuple逐字段相同。查询位置随完整保存包布局改为REPORT_BASE_WIDTH，低ROB标签位置保持0。没有有效报告时，head选择和保存grant都0，原无效包/query仍0，不再增加晚宽valid掩码。全GEN核对和原hold状态没有提前假设。

A92只在有效事件上分配源候选：旁路有效时选择原core_req_lsq_tag；旁路无效且保存valid时选原resp_lsq_reg；都无效时没有事件。原两个完整票据分别使用tag_matches_slot和response_wait。输出response_match_rows与原公开选择后核对相同，故原head快完成、wake、scalar response slot、回复格式、捕获/错误/恢复继续同一事件。可选独立组件接口要求查询候选与公开包一致；参数0忽略新输入，不声称相互矛盾输入等价。

本批A84–A92九项已落盘：存储授权/确认少等待的A84/A86、确认身份前移A85，以及围绕A83真实4.032ns链的A87保存源/两容量分支、A88保存排序、A89两身份资格、A90提前分配槽、A91完整包准备、A92缓存候选身份。它们没有新增声明FF/SRAM/常规流水边沿/端口容量；组合面积、覆盖与时序未知。当前A83距300MHz需周期缩短超过0.753581ns，面积仅余352.966μm²。多个原串行依赖已前移，但不能将报告区间相加为保证节省。

当前直接针对这条已测慢链、且身份/状态/成本有明确源码依据的修改已经完成。剩余扩队列/缓存/PRF、混合新预测器、部分D入队、任意行更激进返回/存储授权或再增流水级，会改变容量或协议/状态，现有同版本数据不能量化收益与面积，暂不盲加。缓存回复格式/存储前递等仍可能成为新瓶颈，需本批映射报告定位；不声称穷尽全部长期架构方案。

因此下一步准备一次集中课程测量：原生Windows串行STA/含SRAM面积，然后同一源/工具/约束复用综合结果，只构建一次CPU并跑六项原性能程序。先在对话汇报具体批次与收益依据再启动；不逐改测试、不覆盖/重跑旧任务。完整19正确性及M/恢复/全GEN/MMIO/参数profile集中验证仍须在数值明显改善、采用前完成。本文件不是测试报告。
''',encoding='utf-8')
    proof = dict(status=classification,recorded_at=datetime.now(timezone.utc).isoformat(),classification='PROGRESS',
        new_tests_started=False,original_a83_terminal=True,original_pid_absent=True,frozen_a83_source_file_count=157,
        a83_completed_result_proof=str(terminal),a83_completed_result_proof_sha256=sha(terminal),
        a83_frozen_source_manifest_sha256=plan['source_manifest_sha256'],previous_source_progress_proof=str(previous_proof),
        previous_source_progress_proof_sha256=sha(previous_proof),main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,
        candidates=records,pending_candidate=str(previous),pending_candidate_sha256=sha(previous/'candidate.json'),
        metrics=None,adopted_to_main=False,declared_added_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        report=str(REPORT),report_sha256=sha(REPORT),material_batch_ready_for_pretest_reporting=True,goal_complete=False)
    write(PROOF,proof)
    state.update(status='ER1_A91_A92_SOURCE_BATCH_READY_FOR_PRETEST_REPORT',current_source_candidate=previous.name,
        current_prepared_candidate=previous.name,candidate_manifest_sha256=sha(previous/'candidate.json'),
        pending_source_candidate=str(previous),pending_source_candidate_sha256=sha(previous/'candidate.json'),
        pending_source_candidate_tests_started=False,candidate_ipc=None,candidate_fmax_mhz=None,candidate_area_um2=None,
        candidate_metrics_belong_to=None,candidate_tests_started=False,candidate_correctness_passed=False,
        candidate_correctness_finished=False,candidate_correctness_not_run=True,
        prepared_run=None,prepared_source_manifest_sha256=None,candidate_pretest_report=None,candidate_pretest_report_sha256=None,
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,
        candidates_adopted=False,goal_complete=False,
        next_work='Freeze/report one material A84-A92 course-native serial measurement, then characterize timing/area and six-case IPC. Keep old terminal tasks/main RTL immutable; no per-edit tests.')
    write(STATE,state)
    print(dict(status=classification,pending=previous.name,proof=str(PROOF),proof_sha256=sha(PROOF),
        a83_terminal=True,new_tests_started=False,main_eu_unchanged=True,goal_complete=False))


if __name__ == '__main__':
    main()
