"""Freeze/report one A21 characterization, dispatch once, observe exact PID."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from manage_er1_a16r2_measurement import check as check_a16r2
from wait_frequency_directed_native import live

BASE = Path('F:/CPU2026CourseRuns/ER1_A16R2_tier3_20261005')
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A21_credit_guaranteed_dispatch_replace')
RUN = Path('F:/CPU2026CourseRuns/ER1_A21_tier3_20261005')
REPORT = ROOT/'reports/ER1_A21_pretest_2026-10-05.md'
GOAL_RECORD = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
HOST_FILES = [ROOT/'tools/run_course_standard_windows.py', ROOT/'tools/prebuild_course_windows.py',
              ROOT/'tools/verilator_windows_time_zero.cpp', Path(__file__)]


def check():
    plan = read(RUN/'measurement_plan.json')
    for path, key in [(RUN/'source_manifest.json','source_manifest_sha256'),
                      (RUN/'course_windows_config.json','config_sha256'),
                      (REPORT,'pretest_report_sha256'),
                      (CANDIDATE/'candidate.json','candidate_sha256')]:
        assert sha(path) == plan[key], path
    for path, digest in plan['host_sha256'].items():
        assert sha(path) == digest, path
    for path, digest in plan['tool_sha256'].items():
        assert sha(path) == digest, path
    for name, digest in read(RUN/'source_manifest.json')['snapshot_sha256'].items():
        assert sha(RUN/'source'/name) == digest, name
    config = read(RUN/'course_windows_config.json')
    assert config['environment'] == 'WINDOWS_NATIVE' and config['wsl_allowed'] is False
    assert config['latency'] == 10 and config['framework_revision'] == '54fc150ffc290f52aa024209ffb9a29d43856f6d'
    return plan


def prepare():
    assert not RUN.exists() and not REPORT.exists()
    check_a16r2()
    candidate = read(CANDIDATE/'candidate.json')
    assert candidate['tests_started'] is False and candidate['adopted'] is False
    parent = read(BASE/'source_manifest.json')
    for name, digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE/name) == digest, name
    active = read(ROOT/'build/cpu2026/active_frequency_implementation_20261004.json')
    for name, digest in active['source_sha256'].items():
        assert sha(ROOT/name) == digest, name
    top = (CANDIDATE/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key, value in candidate['parameter_overrides'].items():
        match = re.search(r'\b'+key+r'\s*=\s*(\d+)', top)
        assert match and int(match[1]) == value, key
    names = sorted(set(parent['snapshot_sha256']) | set(candidate['source_sha256']))
    for name in names:
        src = CANDIDATE/name if name in candidate['source_sha256'] else BASE/'source'/name
        assert src.exists(), name
        dest = RUN/'source'/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    source = RUN/'source'
    untouched = [name for name in names if name.startswith('.deps/')]
    for name in untouched:
        assert sha(source/name) == parent['snapshot_sha256'][name], name
    tests = source/'.deps/RISC-V-CPU-2026/testcases'
    perf = sorted(p.name for p in tests.glob('perf_*') if p.is_dir())
    correctness = sorted(p.name for p in tests.glob('correctness_*') if p.is_dir())
    assert len(perf) == 6 and len(correctness) == 19
    ipc = read(BASE/'result/ipc.json')
    ppa = read(BASE/'result/synth/opt/report.json')
    assert ipc['status'] == 'COMPLETE' and len(ipc['results']) == 6
    baseline_reference = dict(run=str(BASE), source_manifest_sha256=sha(BASE/'source_manifest.json'),
        ipc_report_sha256=sha(BASE/'result/ipc.json'), ppa_report_sha256=sha(BASE/'result/synth/opt/report.json'),
        ipc=ipc['geomean_ipc'], fmax_mhz=ppa['timing']['estimated_fmax_mhz'], area_um2=ppa['area']['area_um2'])
    write(RUN/'a16r2_reference.json', baseline_reference)
    frozen = dict(format='er1-tier3-native-source-v1', status='FROZEN_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(), source_root=str(source),
        reference_manifest_sha256=sha(BASE/'source_manifest.json'), candidate=str(CANDIDATE),
        candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),
        framework_commit=candidate['framework_commit'], testcases_commit=candidate['testcases_commit'],
        parameter_overrides=candidate['parameter_overrides'], materialized_top_defaults=True,
        snapshot_sha256={name:sha(source/name) for name in names}, tests_started=False)
    write(RUN/'source_manifest.json', frozen)
    config = read(BASE/'course_windows_config.json')
    config.update(source=str(source), source_manifest=str(RUN/'source_manifest.json'), out=str(RUN/'result'),
        native_build_path=str(RUN/'native_build'), native_ipc_path=str(RUN/'native_ipc'))
    write(RUN/'course_windows_config.json', config)
    REPORT.write_text('''# ER1 A21 组合测量前汇报

当前目标仍是同一版本动态IPC几何平均≥1.1、Fmax>300MHz、总面积包含SRAM≤36,000μm²，并满足完整RV32IM、乱序执行/顺序退休及课程退出答案要求。
A16R2实测IPC0.9463655946、367.420165MHz、39,982.760814μm²：还需IPC提高16.2341%、面积减少3,982.760814μm²。其六perf答案全部通过，19correctness原进程继续运行；本组合不修改它。

本轮只测A21一个组合，不测A17—A20中间候选、不扫描参数。新增源码已集中完成：

|修改|可定位的收益依据|代价与未验证部分|
|---|---|---|
|共享迭代RV32M|独立流水乘法器/除法器改为共用65位迭代状态与32位操作数；乘法/除法反馈前缀加法器由两套减为一套|M运算32步及额外完成边沿，M密集程序更慢；输入mux和mode分布增加逻辑。实际能否省够3,982.76μm²未知|
|迭代时序拆分|除法不再串联比较再减法，低字减法carry直接决定no-borrow；最终符号/异常修正在独立寄存边界之后|新增声明35状态位、M结果多一拍；不得继承A16R2频率|
|load返回直通|完整LSQ标签匹配的cache返回可在原返回边沿参与LSQ发布，省去原来等待结果存储的一拍；原每行捕获仍保留|新增17位完整tag保持状态及小mux。cache→LSQ→直接唤醒/ALU组合间隔变长，Fmax风险必须测量|
|满派发队列同拍替换|原count=2即停R，即使D同拍消费。保存的RS/LSQ容量能容纳整个旧头包时，允许同拍pop/push，省满队列后的接收气泡|新增小计数/容量比较；只使用旧头包分类与已注册占用，不接PRF/readiness/consume回R。无新增状态或流水边沿|

全八个M操作、符号高半部、除零/溢出、完整ROB/LSQ代际、物理目的、背压与本地恢复仍在；共享单元没有串行化整个OoO核心。I/D缓存容量与SRAM宏配置保持A16R2原值，不能靠忽略SRAM达到面积门槛。
六个官方perf最终.text静态M指令数全为零，且同时核对编码与助记符；perf_multiply为软件移位加法。这是保留普通指令吞吐、压缩M专用硬件的结构依据，不是动态IPC不变或完整ISA覆盖证明。
现有flattened面积报告把M逻辑合到顶层，无法从模块树单独分离其面积；没有把整个顶层面积或寄存位数当成M单元节省量。

协议源审阅：load返回始终按原格式存入旧行，直接接受设置同一行reported，拒收时保持完整LSQtag并从已存行重发；metadata slot也随保持身份选择。复位/flush/恢复禁止新返回直通，旧行失效或代际变化解除匹配。
MDU共同加法器在乘法模式严格使用原加法操作数/carry0，在除法模式使用原移位低字、取反除数/carry1；全部后续next-state和时钟逻辑与A19逐字相同。finishing阶段阻止新请求覆盖全tag/flags，包含在取消保护中。
满队列信用把所有valid lane都算作RS需求，必不小于真实需求；LSQ需求与真实需求相同。因此credit必推出d_admit/pop。满队列两指针相同，NBA让D接受旧值，然后旧头槽写新尾包；原先pop再push的valid写入顺序让push胜出，count保持2。恢复时normal为0，原完整tag/严格旧年龄重排逻辑不改。
源审阅不等于仿真、形式证明、实际时序或测得收益。

其他想法已筛选：分支预览期只发射更老指令最多消一拍，还需在唤醒→选择→发射上增加年龄判断，目前缺少动态错预测与老指令等待比例；缩小L0/ROB/PRF/LSQ/缓存或改相联度缺少容量冲突数据，可能倒退IPC；共享普通ALU全部加法器会延长高频依赖执行路径；删除全部keep会破坏已测控制分布；缓存fill-forward/完成字段继续投影预计小收益，暂不增加新状态协议。在当前证据下，本轮没有更多收益与时序风险相称的可落实修改。

下一步仅一次Windows原生固定课程Verilator5.020构建、六perf与Yosys0.63/ABC/OpenSTA3.1综合/STA；不使用WSL。framework54fc150、testcases29f9807、官方build.py/testcase.py/sim.cpp、所有程序/答案/metrics、ASAP7 RVT TT库与FakeRAM面积公式均保持冻结字节。
perf保持latency10、MAX_CYCLES=1,000,000、原动态指令分子及六项GEOMEAN。综合仍请求2ns并保留课程I/O/uncertainty/load/reset/理想无寄生约束，频率取正式报告的最小可行周期。
本次先取得实际IPC/面积/频率，不立即重复19correctness。只有出现相称实测收益且方案值得采用，才对同一冻结CPU执行19correctness及已有M算术/背压、必要局部恢复覆盖；正确性上限届时单独记录10,000,000（官方可配置MAX_CYCLES），不改变答案或perf预算。
六perf不覆盖M指令，单凭它们不能宣称RV32IM正确；未完成完整验证前不采用或宣布目标完成。

冻结/生成本报告时未启动本候选CPU/EDA测试，先在对话汇报后才开始单次测量。旧EU主工作树、所有旧候选、A16/A16R1失败构建日志及A16R2正在运行的测量保持不变。测量期间继续独立优化。
''',encoding='utf-8')
    tool_paths = [Path(config[key]) for key in ('yosys','abc','sta','verilator','verilator_build_driver')]
    tool_paths.append(Path(config['tools_root'])/'toolchain_manifest.json')
    tool_paths.extend(sorted(Path(config['asap7_lib']).glob('*.lib')))
    plan = dict(status='PREPARED_NOT_STARTED', candidate=str(CANDIDATE), candidate_sha256=sha(CANDIDATE/'candidate.json'),
        source_manifest_sha256=sha(RUN/'source_manifest.json'), config_sha256=sha(RUN/'course_windows_config.json'),
        pretest_report=str(REPORT), pretest_report_sha256=sha(REPORT),
        host_sha256={str(p):sha(p) for p in HOST_FILES}, tool_sha256={str(p):sha(p) for p in tool_paths},
        perf_cases=perf, correctness_cases=correctness, source_files=len(names), unchanged_course_dependency_files=len(untouched),
        source_reviews_sha256={f'A{i}_source_review.json':sha(CANDIDATE.parent/f'A{i}_source_review.json') for i in range(18,22)},
        shared_mdu_review_sha256=sha(CANDIDATE.parent/'A17R1_source_review.json'),
        static_isa_mix_proof_sha256=sha('F:/CPU2026Proofs/ER1_official_perf_static_instruction_mix_20261005.json'),
        perf_max_cycles=1000000, correctness_started_with_characterization=False,
        full_correctness_and_relevant_m_coverage_required_before_adoption=True,
        target=dict(ipc=1.1,total_area_um2=36000,strict_minimum_fmax_mhz=300),
        a16r2_reference_sha256=sha(RUN/'a16r2_reference.json'))
    write(RUN/'measurement_plan.json', plan)
    goal = read(GOAL_RECORD)
    goal.update(status='A21_FROZEN_PRETEST_NOT_STARTED_A16R2_CORRECTNESS_CONTINUES',
        current_prepared_candidate=CANDIDATE.name, pending_source_candidate=str(CANDIDATE),
        pending_source_candidate_sha256=plan['candidate_sha256'], pending_source_candidate_tests_started=False,
        prepared_run=str(RUN), prepared_source_manifest_sha256=plan['source_manifest_sha256'],
        candidate_pretest_report=str(REPORT), candidate_pretest_report_sha256=plan['pretest_report_sha256'],
        last_goal_turn_classification='PROGRESS_A20_SHARED_FEEDBACK_A21_CREDIT_GUARANTEED_FULL_DISPATCH_REPLACEMENT',
        goal_complete=False, candidates_adopted=False)
    # Metrics continue to belong explicitly to A16R2 until A21 results exist.
    write(GOAL_RECORD,goal)
    check()
    print({key:plan[key] for key in ('status','candidate','source_files','unchanged_course_dependency_files',
        'pretest_report','source_manifest_sha256','correctness_started_with_characterization')})


def start():
    plan = check()
    assert plan['status'] == 'PREPARED_NOT_STARTED'
    assert not (RUN/'dispatch_identity.json').exists() and not (RUN/'result').exists()
    command = [sys.executable,'-u',str(ROOT/'tools/run_course_standard_windows.py'),
               '--config',str(RUN/'course_windows_config.json')]
    with (RUN/'driver_stdout.log').open('w',encoding='utf-8') as stdout, (RUN/'driver_stderr.log').open('w',encoding='utf-8') as stderr:
        process = subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)
    dispatch = dict(status='BACKGROUND_DISPATCHED', process_id=process.pid,
        started_at=datetime.now(timezone.utc).isoformat(), command=command,
        source_manifest_sha256=plan['source_manifest_sha256'],pretest_report_sha256=plan['pretest_report_sha256'],
        host_sha256=plan['host_sha256'],initial_process_alive=process.poll() is None,environment='WINDOWS_NATIVE',
        full_correctness_started=False)
    write(RUN/'dispatch_identity.json',dispatch)
    goal = read(GOAL_RECORD)
    goal.update(status='A21_IMMUTABLE_CHARACTERIZATION_IN_PROGRESS',
        active_measurement_candidate=CANDIDATE.name, measurement_run=str(RUN), measurement_process_id=process.pid,
        pending_source_candidate_tests_started=True, candidate_tests_started=True,
        previous_measurement_correctness_run=str(BASE), previous_measurement_correctness_process_id=read(BASE/'dispatch_identity.json')['process_id'])
    write(GOAL_RECORD,goal)
    print(dispatch)


def observe():
    check()
    dispatch = read(RUN/'dispatch_identity.json')
    observation = dict(run=str(RUN),process_id=dispatch['process_id'],process_alive=live(dispatch['process_id']),
        observed_at=datetime.now(timezone.utc).isoformat(),result=optional(RUN/'result/result.json'),
        failure=optional(RUN/'result/failure.json'))
    for name in ('driver_stdout.log','driver_stderr.log'):
        path = RUN/name
        observation[name] = [line[:250] for line in path.read_text(errors='replace').splitlines()[-5:]] if path.exists() else []
    print(observation)


if __name__ == '__main__':
    assert os.name == 'nt', 'Native Windows only'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','start','observe'))
    args = parser.parse_args()
    {'prepare':prepare,'start':start,'observe':observe}[args.action]()
