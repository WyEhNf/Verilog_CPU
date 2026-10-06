"""Freeze A96 multi-store preparation while keeping original A94 running."""
from datetime import datetime, timezone
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a94_measurement import check, live, RUN

STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A96_fast_store_batch')
PROOF = ROOT/'build/cpu2026/er1_a96_background_progress_20261006.json'
REPORT = ROOT/'reports/ER1_A96_parallel_ready_store_preparation_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    state = read(STATE)
    plan = check()
    dispatch = read(RUN/'dispatch_identity.json')
    phase = read(RUN/'serial_phase_identity.json')
    assert dispatch['process_id'] == phase['supervisor_pid'] == state['measurement_process_id'] == 84416
    assert live(84416) and phase['status'] in ['SERIAL_TIMING_IN_PROGRESS','SERIAL_PERFORMANCE_IN_PROGRESS']
    assert state['active_measurement_candidate'] == 'A94_localparam_dependency_order'
    assert state['current_source_candidate'] == 'A95_store_class_compare'
    assert sha(CANDIDATE/'candidate.json') == 'b8184faf6b03a70682edd2b3ffef97ec336acf531f9388640a1df756c9f39175'
    candidate = read(CANDIDATE/'candidate.json')
    parent = Path(candidate['parent_candidate'])
    assert parent.name == 'A95_store_class_compare'
    assert sha(parent/'candidate.json') == candidate['parent_candidate_sha256'] == state['pending_source_candidate_sha256']
    preparer = ROOT/'tools/prepare_er1_fast_store_batch.py'
    assert sha(preparer) == candidate['preparation_script_sha256']
    for path,digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE/path) == digest, path
    changed = sorted(path for path in candidate['source_sha256'] if (CANDIDATE/path).read_bytes() != (parent/path).read_bytes())
    assert changed == sorted(candidate['changed_from_parent_files']) and len(changed) == 4
    assert not candidate['tests_started'] and not candidate['adopted']
    assert candidate['candidate_ipc'] is candidate['candidate_area_um2'] is candidate['candidate_frequency_mhz'] is None
    review = Path(candidate['source_review'])
    assert read(review)['candidate_sha256'] == sha(CANDIDATE/'candidate.json')
    active = ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'
    assert sha(active) == plan['main_active_manifest_sha256']
    for path,digest in read(active)['source_sha256'].items():
        assert sha(ROOT/path) == digest, path
    backend = (CANDIDATE/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    assert backend.index('FAST_STORE_SAVED_ACTIVE=') < backend.index('FAST_STORE_BATCH_ACTIVE=')
    assert backend.index('function integer fast_store_subset_count;') < backend.index('localparam integer CREDIT=fast_store_subset_count(')
    assert 'rob_fast_store_publish_tag=((FAST_STORE_IDENTITY_PRESELECT!=0) && !FAST_STORE_BATCH_ACTIVE)' in backend
    assert '((store_without_agu & MASK)==MASK) && room[CREDIT];' in backend
    name = 'rtl/backend/rv32_rob.v'
    original = (parent/name).read_text(encoding='utf-8')
    new = (CANDIDATE/name).read_text(encoding='utf-8')
    marker = '    localparam integer FAST_STORE_DOMAINS='
    assert new[new.index(marker):] == original[original.index(marker):]
    previous = Path(state['last_source_progress_proof'])
    assert sha(previous) == state['last_source_progress_proof_sha256']
    REPORT.write_text('''# A96：同批普通RAM存储独立准备完成

记录时A94原监督PID84416仍存在、在原串行课程测量阶段；原快照157文件/配置/工具/报告/准备脚本和审阅通过冻结检查。A96仅在F盘独立源码目录生成，未跑HDL/lint/形式/仿真/综合/STA/单元测试，未改测量源、旧脚本、结果或主E EU40文件。

## 要解决的问题

A83为缩短晚ready之后的宽标签选择，提前选最低potential store身份。A95沿用此策略：前面的潜在存储未就绪时，后面已具备原LSQ真实地址/数据的存储仍不能走快完成；同批两条都就绪，也只能省一条RS/AGU工作。A96让各条普通RAM存储的完整保存ROB身份直接并行核对，晚ready只门控对应合法事件，不选择或复用一条宽标签。支持已有BE_WIDTH1/2/4；课程宽度2可让两条合格存储都跳过重复RS/ALU准备。

各lane保留原完整资格：D真实valid/store且非load，canonical immediate，保存基址ready且无匹配当前base-WB，数据保存ready或合法WB-ready，原RAM与对齐/类型/size判断，explicit-data为0。actual fast valid继续要求相应LSQ真实alloc_fire、原reset/flush/branch guard。地址/数据继续原LSQ/PRF（包括最高WB优先级），MMIO/异常类型/未就绪继续原RS，不扩大内存请求带宽。

## 容量判断与时序结构

令B为原d_valid中除去load_without_AGU的数量，F为全部合格fast store数量。fast store是B中的非load有效存储，0≤F≤B；真实RS需求仍由原d_rs_need计数，严格等于B−F。

提前计算room[k]=(B≤free+k)，k=0..BE_WIDTH，free先扩展17bit再加常数。晚资格只检查是否存在合格存储子集S、k=|S|，使room[k]为真。存在这样的S与B−F≤free等价：正向k≤F；反向取全部fast集合（F=0则room0）。固定mask/count在展开时决定，没有晚popcount/减法/比较链。

课程BE=2退化为：room0 OR ((f0 OR f1) AND room1) OR (f0 AND f1 AND room2)。BE=1/2/4分别有1/3/15个非空固定mask，不借同边沿RS回收。原D整包admit/reset/flush/busy/LSQroom、实际RS/LSQ需求与fire、全部valid保守替换信用/FIFO语义保持。A90稀疏分配计划证明仍成立：实际admit时全部原内存需求满足原free，所以任何实际LSQfire下plan等于完整fire向量。

## ROB与提交不变量

批模式不再把事件压到一个预选标签；每lane原d_tag提前送给原ROB全valid/row/8GEN/store/no-rd/no-branch/no-halt比较，晚实际valid门控。ROB只把FAST_STORE_OWNER_LANES从1恢复BE，原所有逐行比较/OR及ready更新、CDB完成处理、错误、allocate/retire优先级、sent/ACK、恢复及存储提交主体逐字不变。不同真实D存储对应不同完整ROB身份，多个行可在同一边沿独立完成准备。只更新原ready，不提前授权内存副作用。

参考：[BOOM LSU](https://docs.boom-core.org/en/latest/sections/load-store-unit.html)将存储地址/数据准备与committed后按程序序排出分开；[BOOM ROB](https://docs.boom-core.org/en/latest/sections/reorder-buffer.html)说明存储只有commit后才可发往内存，LSU接收可commit存储数量。此处借鉴该分离原则，保留本CPU原单授权口、顺序LSQ排出、缓冲退休和MMIO条件。外部文档是架构参考，不是本RTL正确性或频率/IPC证明。

## 收益与限制

同输入下A95快集合是A96快集合子集，原fast机会不会因更早潜在lane而丢失，可减少第二条或更后就绪存储的重复RS/ALU准备。聚合IPC仍未测，内存排出仍最多原单请求/边沿；不把快集合扩大当所有程序必然加速。

新增每lane完整身份比较和容量组合逻辑，不新增声明FF/SRAM/普通流水沿/端口容量，不减ROB/PRF/队列、GEN或ISA。更多比较/资格扇出可能增加面积或降低Fmax；面积余量有限，需下一次有依据的整批映射判断。FAST_STORE_BATCH默认core/backend/ROB0、课程top1，仅在保存快存储profile激活；关闭时保留A95原单potential身份/至多一条策略。

A95直接地址类别推导原样继承。A96无实测三指标、无采用，A94结果不能借给它。下一步继续读取原A94任务终态与新瓶颈，开展有证据的源码改动；新批测量先报告，采用前仍须完整19正确性及M/GEN/恢复/MMIO/参数覆盖。目标严格>300MHz/IPC≥1.1/含SRAM≤36000μm²仍未达成。
''',encoding='utf-8')
    classification = 'PROGRESS_A94_ORIGINAL_LIVE_A96_ALL_READY_RAM_STORES_PARALLEL_IDENTITIES_PRECOMPUTED_CAPACITY_NO_TESTS'
    artifacts = [RUN/'measurement_plan.json',RUN/'source_manifest.json',RUN/'course_windows_config.json',
        RUN/'dispatch_identity.json',review,preparer,CANDIDATE/'candidate.json',REPORT]
    proof = dict(status=classification,classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        original_a94_pid=84416,original_a94_pid_alive_at_record=True,original_a94_phase_observed=phase['status'],
        original_a94_source_manifest_sha256=plan['source_manifest_sha256'],original_a94_frozen_source_check_passed=True,
        candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),source_file_count=41,
        candidate_source_hashes_valid=True,changed_files=changed,review_sha256=sha(review),preparation_script_sha256=sha(preparer),
        source_capacity_derivation='exist eligible subset S with B<=free+|S| iff B-F<=free; constant1/3/15 masks for BE1/2/4',
        original_rob_row_commands_byte_identical=True,additional_tests_started=False,candidate_metrics=None,
        artifacts_sha256={str(p):sha(p) for p in artifacts},main_active_manifest_sha256=sha(active),main_eu_source_unchanged=True,
        previous_source_progress_proof=str(previous),previous_source_progress_proof_sha256=sha(previous),
        pending_source_candidate=str(CANDIDATE),adopted_to_main=False,goal_complete=False)
    write(PROOF,proof)
    state.update(current_source_candidate=CANDIDATE.name,current_prepared_candidate=CANDIDATE.name,
        candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),
        pending_source_candidate=str(CANDIDATE),pending_source_candidate_sha256=sha(CANDIDATE/'candidate.json'),
        pending_source_candidate_tests_started=False,pending_source_candidate_has_measured_metrics=False,
        last_source_progress_proof=str(PROOF),last_source_progress_proof_sha256=sha(PROOF),
        last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        previous_goal_turn_classification=state['last_goal_turn_classification'],last_goal_turn_classification=classification,
        candidates_adopted=False,goal_complete=False,
        next_work='Continue exact original A94 PID84416 serial course measurement without edits/restarts. Pending A96 inherits A95 direct RAM predicate and adds all-ready-store preparation/per-lane full identity plus precomputed exact subset RS capacity; no additional tests. Inspect A94 terminal metrics/new path before another pre-reported coherent batch; full correctness and architecture coverage before adoption.')
    write(STATE,state)
    print(dict(status=classification,a94_original_pid_alive=True,a96_tests_started=False,proof=str(PROOF),
        proof_sha256=sha(PROOF),candidate_sha256=sha(CANDIDATE/'candidate.json'),goal_complete=False))


if __name__ == '__main__':
    main()
