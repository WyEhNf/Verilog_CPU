"""Journal independent ACK query/head-reclaim work while original A83 runs."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a83_measurement import check, live, RUN

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT/'build/cpu2026/er1_a85_a86_background_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A85_A86_ack_query_and_head_release_2026-10-06.md'
ITEMS = [
    ('A85_store_ack_source_query','prepare_er1_store_ack_source_query.py','caa8c4e38683a7aff619c7d08623bd16ab3759db0a7f7b0baab2b3236330dc8d'),
    ('A86_head_store_ack_bypass','prepare_er1_head_store_ack_bypass.py','a118f5381b22dcf0b10fdb2e22777a29e6532a8c43a4f7858a24ee67c4e0cacd'),
]


def main():
    assert not PROOF.exists() and not REPORT.exists()
    state = read(STATE)
    assert state['current_source_candidate'] == 'A84_rob_store_prefix_admission'
    assert state['active_measurement_candidate'] == 'A83_fast_store_identity_preselect'
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    assert dispatch['process_id'] == state['measurement_process_id'] == 82452
    original_alive = live(82452)
    assert original_alive
    assert dispatch['source_manifest_sha256'] == plan['source_manifest_sha256'] == state['active_measurement_source_manifest_sha256']
    assert sha(RUN/'dispatch_identity.json') == state['measurement_dispatch_sha256']
    phases = read(RUN/'serial_phase_identity.json')
    assert phases['supervisor_pid'] == 82452
    previous_proof = Path(state['last_source_progress_proof'])
    assert sha(previous_proof) == state['last_source_progress_proof_sha256'] == '2cb97c13423189294dfe2d4e36f8e48397443ebed5cfb5e147aa232a9a7e96f6'
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == read(previous_proof)['main_active_manifest_sha256']
    for name,digest in read(active)['source_sha256'].items():
        assert sha(ROOT/name) == digest,name
    previous = BASE/'A84_rob_store_prefix_admission'
    records = []
    for name,script,expected in ITEMS:
        candidate_root = BASE/name
        candidate = read(candidate_root/'candidate.json')
        assert sha(candidate_root/'candidate.json') == expected
        assert Path(candidate['parent_candidate']).resolve() == previous.resolve()
        assert sha(previous/'candidate.json') == candidate['parent_candidate_sha256']
        assert sha(ROOT/'tools'/script) == candidate['preparation_script_sha256']
        for file,digest in candidate['source_sha256'].items():
            assert sha(candidate_root/file) == digest,(name,file)
        assert len(candidate['source_sha256']) == 41
        changed = sorted(file for file in candidate['source_sha256'] if (candidate_root/file).read_bytes() != (previous/file).read_bytes())
        assert changed == sorted(candidate['changed_from_parent_files'])
        review = Path(candidate['source_review'])
        assert read(review)['candidate_sha256'] == expected
        assert not candidate['tests_started'] and not candidate['adopted']
        assert candidate['candidate_ipc'] is candidate['candidate_area_um2'] is candidate['candidate_frequency_mhz'] is None
        records.append(dict(candidate=name,candidate_sha256=expected,parent_candidate_sha256=candidate['parent_candidate_sha256'],
            source_file_count=41,source_hashes_valid=True,changed_files=changed,preparation_script_sha256=sha(ROOT/'tools'/script),
            review=str(review),review_sha256=sha(review),tests_started=False,metrics=None,adopted=False))
        previous = candidate_root
    candidate = read(previous/'candidate.json')
    top = (previous/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key in ['ROB_STORE_PREFIX_ADMISSION','LSQ_STORE_ACK_SOURCE_QUERY','LSQ_HEAD_STORE_ACK_BYPASS']:
        assert candidate['parameter_overrides'][key] == 1
        match = re.search(r'\b'+key+r'\s*=\s*(\d+)',top)
        assert match and int(match[1]) == 1,key
    for name in ['rtl/backend/rv32_rob.v','rtl/rv32i_alu.v','rtl/backend/rv32_completion_network.v',
                 'rtl/backend/rv32_reservation_station.v','rtl/rv32_rename_unit.v']:
        assert (previous/name).read_bytes() == (BASE/'A84_rob_store_prefix_admission'/name).read_bytes(),name
    classification = 'PROGRESS_A83_LIVE_A85_PARALLEL_ACK_IDENTITIES_A86_HEAD_ACK_REPORT_RECLAIM_RTL_NO_NEW_JOBS'
    REPORT.write_text('''# A85–A86：确认身份前移与队首存储回收

目标仍为频率严格大于300MHz、IPC几何平均至少1.1、含SRAM面积不超过36000μm²，完整RV32IM、乱序执行、顺序提交、MMIO和参数化保留。原A83测量PID82452在记录时確認存活；其157文件、管理器、库/约束与预报文件均通过冻结哈希检查，未修改、未重启。本轮未启动新HDL/lint/形式/仿真/综合/STA/单元作业。

当前待测源码已推进至独立A86，继承A84提交前缀存储授权重叠。新增两项：

| 候选 | 修改 | 依据和限制 |
|---|---|---|
| A85 | 私有缓存ACK候选标签用已注册ack_valid选择保存结果/当前请求；缓存和已保存MMIO标签并行核对LSQ全身份，再用原有效与缓存优先级门控真正事件。 | 原缓存确认含当拍旁路，不能直接当注册结果。前移身份查询避免晚旁路与缓存/MMIO标签选择后再串全GEN检查；额外并行比较耗门，面积/时序未知。未省流水边沿。 |
| A86 | 非空LSQ已提交队首存储收到合法当前ACK时，当拍发布原确认结果，并仅在原ACK-ready接受时释放队首。暂停仍用原确认/错误捕获，其他行保持原保存路径。 | 省一拍队首确认到正式上报/回收等待，没有新增保持FF/SRAM。ROBACK私有身份也提前读原队首完整标签，真正valid和全部8ROBGEN检查保留。 |

缓存候选标签的有效期推导：公开ACK-valid=ack_valid_reg OR bypass_store_ack，而旁路必须ack_valid_reg为0。保存ACK有效时，其公开和私有标签均为ack_lsq_reg；保存ACK无效但当拍旁路有效时，两者均为core_req_lsq_tag。公开valid/tag/error与所有捕获、消费规则未改变，私有无效候选不代表结果。

原core确认优先级保持：

| 缓存有效 | MMIO待确认 | 真正事件与身份 |
|---|---|---|
| 0 | 0 | 没有ACK |
| 0 | 1 | 已保存MMIO标签 |
| 1 | 0 | 缓存有效候选标签 |
| 1 | 1 | 缓存优先，MMIO继续原暂停保存规则 |

逐LSQ行将“先选标签再核对”分配为两个独立的tag_matches_slot查询和实际优先级事件门控。原当前valid、row、全部LSQGEN、request_sent和response_wait检查均保留；课程TAG16/LSQ16意味着LSQ9位GEN，ROB仍8位GEN。元数据ACK捕获结果与原core公共接口逐有效事件一致，错误仍采用原统一错误输入。选项0忽略私有输入并保留原查询表达式；blocking cache私有候选等于其公开标签。不声称相互矛盾的额外组件查询输入与公共输入等价。

A86只对未已有确认、已提交且非加载的实际队首启用旁路，要求非空、有效、完整当前身份/已发出且等待响应，以及无reset/flush/恢复apply。输出仍含原ROB/LSQ完整标签和真实错误。ACK-ready为0时，本拍不释放，原队首捕获ACK/error后仍占用原行，下一拍以相同身份、相同错误继续保存报告；不需要独立结果缓存。ACK-ready为1时，原捕获后pop清理优先级同时清队首，真实接收者在该边沿消费原数据。第二项加载前缀回收和head/count/行清理继续同一原pop_count，满队列仍不能使用本边沿刚释放行同时分配。

任何有效LSQ存储确认都属于当前队首，故提前读取其原rob_tag_mem与公开ACK包的ROB标签在有效事件上完全相同。实际ROBACK-valid仍来自原报告，当前ROB全valid/row/8GEN核对与错误/等待/终止状态优先级不变；私有空闲标签不是确认。MMIO确认仍在原真实总线完成后才能进入该路径，不会提前写内存或越过未提交指令。

本批A84–A86没有新增FF/SRAM/流水边沿/端口容量；A85增加并行身份比较、A86增加私有队首标签读与晚确认/错误到ROB和计数路径。公开未用字段能否被映射裁掉、累积面积是否仍在341μm²余量内，以及新增路径是否超过3.333ns，都需要以后集中STA判断；不预报三项达标。源码收益是一条实际队首回收等待边沿和A84连续就绪存储授权吞吐机会，不是已测IPC百分点。

未来集中覆盖：缓存保存/当拍旁路/MMIO/双有效优先级、队首/非队首/暂停/重复/旧GEN/错误确认、已提交存储跨恢复、reset/flush、满/绕回队列与第二加载回收、分配/退休/确认碰撞、MMIO退出、blocking/nonblocking缓存、TAG_SRAM模式、width1/2/4、LSQ1/2/4/8/16/32和全部默认回退。完整19正确性与M/恢复/参数专项仍须在采用前证明。A83任何后续测量值只属于其冻结源码，不能赋给A86。

当前最新完成结果仍A75：IPC1.05188539、Fmax299.24021MHz、面积35658.77140μm²。频率/面积达标的已测综合最优仍A55R2：1.01714182/306.86245MHz/35480.53090μm²。两者六项性能通过、完整19正确性未完成；目标尚未达成。
''',encoding='utf-8')
    proof = dict(status=classification,recorded_at=datetime.now(timezone.utc).isoformat(),new_tests_started=False,
        previous_goal_turn_classified_progress=True,
        original_measurement=dict(candidate='A83_fast_store_identity_preselect',run=str(RUN),process_id=82452,
            process_alive=True,phase=phases['status'],source_manifest_sha256=plan['source_manifest_sha256'],
            pretest_report_sha256=plan['pretest_report_sha256'],dispatch_sha256=sha(RUN/'dispatch_identity.json'),source_files_verified=157),
        candidates=records,pending_candidate=str(previous),pending_candidate_sha256=sha(previous/'candidate.json'),pending_metrics=None,
        main_active_manifest_sha256=sha(active),main_source_file_count=len(read(active)['source_sha256']),main_source_unchanged=True,
        previous_source_progress_proof=str(previous_proof),previous_source_progress_proof_sha256=sha(previous_proof),
        report=str(REPORT),report_sha256=sha(REPORT),adopted=False,goal_complete=False)
    write(PROOF,proof)
    state.update(status='ER1_A83_MEASUREMENT_WITH_A86_INDEPENDENT_SOURCE_PROGRESS',current_prepared_candidate=previous.name,
        current_source_candidate=previous.name,candidate_manifest_sha256=sha(previous/'candidate.json'),
        pending_source_candidate=str(previous),pending_source_candidate_sha256=sha(previous/'candidate.json'),
        candidate_tests_started=False,pending_source_candidate_tests_started=False,candidate_ipc=None,candidate_fmax_mhz=None,
        candidate_area_um2=None,candidate_metrics_belong_to=None,candidate_correctness_not_run=True,
        candidate_correctness_passed=False,candidate_correctness_finished=False,prepared_run=None,prepared_source_manifest_sha256=None,
        candidate_pretest_report=None,candidate_pretest_report_sha256=None,
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,
        previous_source_progress_proof=str(previous_proof),previous_source_progress_proof_sha256=sha(previous_proof),
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),measurement_process_alive=True,
        candidates_adopted=False,goal_complete=False,
        next_work='Keep original A83 serial PID82452/source frozen; continue coherent A84-A86 IPC/area/timing ownership work without new per-edit tests; report before any later batch.')
    write(STATE,state)
    print(dict(status=classification,active_pid=82452,phase=phases['status'],pending=previous.name,new_tests_started=False,
        proof=str(PROOF),proof_sha256=sha(PROOF),report=str(REPORT),goal_complete=False))


if __name__ == '__main__':
    main()
