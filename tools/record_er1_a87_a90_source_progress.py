"""Bind four untested timing changes to terminal A83 and immutable main RTL."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a83_measurement import check, live, RUN

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT/'build/cpu2026/er1_a87_a90_source_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A87_A90_timing_dependency_changes_2026-10-06.md'
ITEMS = [
    ('A87_saved_store_operands_parallel_admission','prepare_er1_saved_store_operands_parallel_admission.py','2b4c3d7b32192462f54273afff9f698cfa28873004ab7021e3a7c55c86e2826c'),
    ('A88_saved_load_report_priority','prepare_er1_saved_load_report_priority.py','9c78baed8b428a67a7abba80664842a0311595e8fce1e7410de422112f85095a'),
    ('A89_load_report_identity_prequalification','prepare_er1_load_report_identity_prequalification.py','21dbc81c8ef633380c321ef050af447fac7994712c4998ab5e10461405ba9bec'),
    ('A90_lsq_allocation_slot_preselect','prepare_er1_lsq_allocation_slot_preselect.py','48ab520879bc6dd259f481507e15cff5eacd75f29b6fdc7ce7a67fd0c8f4423d'),
]


def main():
    assert not PROOF.exists() and not REPORT.exists()
    state = read(STATE)
    assert state['current_source_candidate'] == 'A86_head_store_ack_bypass'
    assert state['active_measurement_candidate'] is None and state['active_measurement_process_ids'] == []
    terminal = Path(state['measurement_terminal_proof'])
    assert sha(terminal) == state['measurement_terminal_proof_sha256'] == '152bf20caac6b9440872f336deba4373cfc92f71772adc8a8f518f0b8d92d2c1'
    completed = read(terminal)
    assert completed['status'] == 'A83_ORIGINAL_COMPLETED_RESULT_BOUND'
    assert state['last_measured_result'] == completed['metrics']
    plan = check()
    phases = read(RUN/'serial_phase_identity.json')
    assert phases['status'] == 'SERIAL_CHARACTERIZATION_COMPLETE' and not live(82452)
    assert phases['supervisor_pid'] == 82452 and all(p['returncode'] == 0 for p in phases['phases'])
    for path,digest in completed['artifacts_sha256'].items():
        assert sha(Path(path)) == digest, path
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == completed['main_active_manifest_sha256']
    for path,digest in read(active)['source_sha256'].items():
        assert sha(ROOT/path) == digest, path
    previous_proof = Path(state['last_source_progress_proof'])
    assert sha(previous_proof) == state['last_source_progress_proof_sha256']
    previous = BASE/'A86_head_store_ack_bypass'
    assert sha(previous/'candidate.json') == 'a118f5381b22dcf0b10fdb2e22777a29e6532a8c43a4f7858a24ee67c4e0cacd'
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
    new_params = ['FAST_STORE_SAVED_OPERANDS','LSQ_SAVED_REPORT_PRIORITY','LSQ_HEAD_LOAD_IDENTITY_QUERY','LSQ_ALLOC_SLOT_PRESELECT']
    for key in new_params:
        assert current['parameter_overrides'][key] == 1
        match = re.search(r'\b'+key+r'\s*=\s*(\d+)',top)
        assert match and int(match[1]) == 1, key
    for path in ['rtl/backend/rv32_rob.v','rtl/backend/rv32_reservation_station.v','rtl/backend/rv32_completion_network.v',
                 'rtl/rv32_rename_unit.v','rtl/rv32i_alu.v']:
        assert (previous/path).read_bytes() == (BASE/'A86_head_store_ack_bypass'/path).read_bytes(), path
    backend = (previous/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    lsq = (previous/'rtl/backend/rv32_lsq.v').read_text(encoding='utf-8')
    assert '.alloc_plan_valid_i(d_lsq_need)' in backend and '.ALLOC_SLOT_PRESELECT(LSQ_ALLOC_SLOT_PRESELECT_ACTIVE)' in backend
    assert 'wire [BE_WIDTH-1:0] d_lsq_need=d_valid & (d_is_load | d_is_store);' in backend
    assert 'tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]==live_state[0 +: ROB_GENERATION_WIDTH]' in backend
    assert 'assign load_report_identity_head_o=fast_head_present && !report_hold_live;' in lsq
    metrics = completed['metrics']
    classification = 'PROGRESS_A87_A90_SAVED_STORE_ADMISSION_SAVED_REPORT_PARALLEL_IDENTITY_EARLY_LSQ_SLOTS_RTL_NO_TESTS'
    REPORT.write_text(f'''# A87–A90：拆开返回、身份和资源入队依赖

当前源码推进至独立A90；没有启动HDL/lint/形式/仿真/综合/STA/单元作业，也没有重启已结束A83。A83原PID82452已不存在，串行两阶段均返回0；157文件、工具/约束、结果/二进制和完成证明保持冻结。主E EU40文件与原manifest哈希一致。新候选仍在F盘，未采用；不使用WSL。

## 实测依据

A83：IPC {metrics['ipc']:.8f}、Fmax {metrics['fmax_mhz']:.5f}MHz、含SRAM面积 {metrics['area_um2']:.5f}μm²，六项性能答案通过，19正确性未运行。A83比A75 IPC提高2.1417%，但频率下降54.5568MHz。A90不能继承这些指标，也尚未证实优于A55R2（IPC1.01714182/306.86245MHz/35480.53090μm²）。目标仍为严格>300MHz、IPC≥1.1、含SRAM≤36000μm²，以及完整RV32IM/OoO/顺序提交/MMIO/参数化。

本次修改直接对应A83最慢4.032ns链：内存响应→缓存LSQ标签0.7946ns→LSQ匹配及wrap控制1.260ns→报告ROB查询1.597ns→当前ROB live读取1.785ns→完成选择2.091ns→PRF写回值2.292ns→存储地址高位分类2.755ns→D入队/tag-valid别名3.319ns→LSQ allocation lane1选择3.626ns→GEN写控制3.830ns→FF4.032ns。命名网可能是综合共享逻辑的别名；d_rob_value_tree.signal_i[0]在此也代表有效分配控制，不能按网名把所有时间归因于ROB标签数据本身。

## 已落盘修改

| 候选 | 改动 | 结构依据与代价 |
|---|---|---|
| A87 | 快速存储只用原保存的PRF操作数/地址分类；两源当前有匹配WB时走原RS。提前算RS普通容量和少一项容量。 | 移走WB值→地址加法/分类，以及晚快存储位→popcount/容量比较。新式B≤free OR(F AND B≤free+1)等于原B-F≤free；F至多1。保持原D替换信用，无新增D暂停。损失WB辅助存储的快速完成机会，IPC覆盖率未知。 |
| A88 | 仅队首旁路模式的通用报告排序使用已保存完成行。 | 有快队首时原head-fast已压过通用排序；有held时原held又压过它；没有快队首时两者资格相同。移走响应到未使用wrap/prefix仲裁的依赖，实际选中包不变。 |
| A89 | 保存/held候选与队首候选并行核对当前ROB全valid/全GEN，真实返回只选择资格位。 | 复用A86队首完整ROB标签读取。晚报告标签/地址不再串ROB查询/GEN比较后判LSQ生产者有效；新增普通候选标签/银行查询路由和两路live读取，组合面积/扇出未知。 |
| A90 | 根据保存D原始稀疏内存需求和LSQ tail提前计算分配槽，真实fire只门控原行写入。 | 弹性原子D：admit0时所有fire0；admit1时整包内存需求≤原保存空位，因此fire等于原始计划。槽位prefix/tail计算不再等待当拍入队事件；物理目的行使用同一提前槽。公开票据/fire/count、全GEN、所有状态写优先级保持原样。 |

四项无新增声明FF/SRAM/流水边沿/执行端口容量。A87原PRF读/写/实际LSQ地址数据、A88原报告valid/slot/hold、A89实际包与恢复年龄/cancel、A90实际fire和所有GEN/头尾/占用更新仍保留。所有选项有默认0或不适用profile回退。可选独立LSQ原子计划接口要求有真实分配时plan等于fire；课程后端从原整包资源条件保证，不能把相互矛盾的组件额外输入声称等价。

当前仅源码审查和冻结哈希核对，未证明RTL语法/功能/物理时序。A83面积余量仅352.966μm²；新组合网络是否可裁剪共享以及累计面积、IPC覆盖率和频率必须以后集中测量。不得把这些结构变化描述为已达300MHz。

## 下一项可发展方向

A89前移了有效身份核对，但当前公开报告物理目的/标签/值仍通过晚到的逐行report_first掩码。下一项将预选完整保存报告包，以及队首保存元数据（LSQ全票据/物理目的/unretired/cancel），真实队首返回只选择准备好的包并使用原响应格式值/错误。这样可进一步减少返回事件到CDB/PRF物理写标签的宽包选择，而不增加保持状态或等待边沿。需审查held优先级、无效输出、默认profile、完整字段/查询格式和队首读取门数，再决定是否实施；当前只是设计方向，不是已落盘A91。

仍有有据可发展的包预选方向，因此本轮不开始测试。后续形成完整批次时先向用户汇报，再在课程原生Windows链下集中测量；完整19正确性、M、恢复、代际、MMIO与参数profile覆盖仍欠缺。
''',encoding='utf-8')
    proof = dict(status=classification,recorded_at=datetime.now(timezone.utc).isoformat(),classification='PROGRESS',
        new_tests_started=False,original_a83_terminal=True,original_pid_absent=True,frozen_a83_source_file_count=157,
        a83_completed_result_proof=str(terminal),a83_completed_result_proof_sha256=sha(terminal),
        a83_frozen_source_manifest_sha256=plan['source_manifest_sha256'],previous_source_progress_proof=str(previous_proof),
        previous_source_progress_proof_sha256=sha(previous_proof),main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,
        candidates=records,pending_candidate=str(previous),pending_candidate_sha256=sha(previous/'candidate.json'),
        metrics=None,adopted_to_main=False,declared_added_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        report=str(REPORT),report_sha256=sha(REPORT),
        remaining_supported_direction='Preselect original saved load report packet and saved head metadata before actual response; preserve full actual packet and head/held priority.',
        goal_complete=False)
    write(PROOF,proof)
    state.update(status='ER1_A87_A90_SOURCE_PROGRESS_AFTER_A83_COMPLETE',current_source_candidate=previous.name,
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
        next_work='Develop saved/head load report packet metadata/value preselection after A89 live identity qualification; no per-edit tests or restarting terminal A83. Report before coherent later course-native batch.')
    write(STATE,state)
    print(dict(status=classification,pending=previous.name,proof=str(PROOF),proof_sha256=sha(PROOF),
        a83_terminal=True,new_tests_started=False,main_eu_unchanged=True,goal_complete=False))


if __name__ == '__main__':
    main()
