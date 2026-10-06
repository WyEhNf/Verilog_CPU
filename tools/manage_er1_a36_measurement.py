"""Freeze/report one A36 characterization, dispatch once, observe exact PID."""
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
from manage_er1_a21_measurement import check as check_a21
from wait_frequency_directed_native import live

BASE = Path('F:/CPU2026CourseRuns/ER1_A16R2_tier3_20261005')
CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A36_dcache_word_response')
RUN = Path('F:/CPU2026CourseRuns/ER1_A36_tier3_20261005')
REPORT = ROOT/'reports/ER1_A36_pretest_2026-10-05.md'
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
    check_a16r2(); check_a21()
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
    REPORT.write_text('''# ER1 A36 组合测量前汇报

目标保持同一冻结源码：IPC几何平均≥1.1、Fmax>300MHz、总面积（含SRAM）≤36,000μm²，完整RV32IM、OoO执行、顺序退休、MMIO退出及参数化要求不缩减。

当前完整课程答案已验证的最佳版本A16R2：IPC0.9463655946、总面积39,982.760814μm²、367.42016505MHz，6perf与19correctness全部PASS。最新实测A21：IPC0.9615883182、39,115.002954μm²、247.40275429MHz，6perf答案PASS，频率失败、19correctness未跑，未采用。两个原测量已终止，保持冻结，不重启、不覆盖。

上一轮仅核对指标，属于无源码进展；本轮重新核对终止结果并完成A34命名修复、A35 store数据提前捕获、A36 D-cache响应压缩。此前未集中记录的A29–A33源码也纳入本次组合。所有中间候选没有单独HDL/EDA测试。

## 已落实的结构变化及收益依据

|范围|具体变化/依据|成本与风险|
|---|---|---|
|A22 load返回|关闭A21正式完成直通，保留原LSQ结果寄存边界；新返回只提前唤醒RS|去掉A21返回→正式ROB完成组合跨越；cache→RS→ALU依然需要测时序，不能继承367MHz|
|A23分支恢复|同一已接收、完整ROB代际有效的分支捕获提前通知前端|省一拍取指等待；后台描述符、应用、epoch和物理回收原路不改|
|A24指令过滤缓存|16行保持容量，4×4×128同步课程SRAM；删除2,176位FF|同bank读写冲突等待，响应背压需每拍重读；SRAM组件85.996352μm²|
|A25总线读行|8行前三字放96-bit depth1 SRAM，最后字32-bit FF；删除768位FF|原AXI-Lite返回字序保证word3边沿读出prefix，发布周期不变；新增SRAM32.248632μm²|
|A26–27预测表示|保存JALR页内低12位、直接目标可重算；64项BTB58→39位|至少640位高目标位常量、删除1,216位BTB数据FF；全取指地址保留，跨页强制恢复，hash别名需完整目标校验|
|A28/33 load分配选择|已就绪load在分配拍进入原选择寄存器，允许已知地址/数据的旧store和前序lane store|省选择等待一拍；旧候选优先，未知store仍阻塞，下一拍原全LSQ代际/最年轻旧字节转发继续保护|
|A29分支反馈|两条已接受分支可以分别更新不同预测bank，冲突保留原第一条优先|补齐原先丢弃第二条训练；无新增表项/端口/流水级，新增bank选择成本待测|
|A30–31前端旁路|FQ为空时接受的响应首部直接进入原decode寄存器，余部仍入队|省一拍，首lane valid避开BHT方向和bundle-count加法；response→decode实际组合路径仍待测|
|A32主I-cache标签|128行、2way容量不变；每way共享完整高12位region，行保存低10位|净删除1,512位标签FF，三类高部比较从逐行共享到way/domain；region变化清除此way其他行，跨多个1MiB region可能增加miss|
|A34兼容性|把新增region-query信号的保留字matches改为region_query_matches|反向alpha rename逐字等于父版本，纯命名修复，无性能收益|
|A35 store分配数据|已就绪PRF src2在D分配拍写入原LSQ store-data owner|原早地址模式把allocation data-valid全置0；该改动提前使旧store可转发/不阻塞load，无新增FF或PRF口，仍保留store RS/ALU/ROB完成与顺序MMIO|
|A36 D-cache响应|每waiter存所需的对齐32位字，选择后只移低两位byte；held CPU数据160→32，发raw32且line_valid=0|删除896位数据FF、窄化waiter读和CPU返回并使LSQ全128位窗口选择无用；每waiter新增对齐字选择，实际面积/频率需测|

面积组件合计：显式删除6,568位数据FF，另有至少640位预测高部变为常量，合计7,208位。按既有映射DFF单价0.2916μm²，对应FF组件2,101.8528μm²；新增课程SRAM118.244984μm²，组件差1,983.607816μm²。保持mux/宽读写分发/标签比较减少是额外结构机会；新增hash、旁路、region失效、PRF数据输入、对齐字选择也可能增加逻辑。这是可观收益的源码与旧映射依据，不是新总面积，不足以宣称已达到36,000。

IPC机会集中在分支恢复/FQ空队列重填、load依赖唤醒、load候选选择、已就绪store转发与被丢弃的第二条训练。它们有明确可省边沿或原缺失事件，但发生频率和最终GEOMEAN未知，没有把各项收益相加当作预测IPC。

## 本轮源审阅边界

A24/A25遵守课程FakeRAM每拍默认Q=x、仅有效读产生Q的语义；保持响应时明确重读，不把idle Q当作保持寄存器。所有新SRAM按官方面积公式计入总面积，容量/读写掩码合法。

A32完整地址标签由共享高部+行低部重建，prefix变化的边沿同时清除该way其他行valid，新填充行优先保持valid。已有SRAM响应先复制/保持，原数据端口、MSHR、命中占用/复制/响应、错误和背压控制不改。它不是地址截断；六perf静态.text在同一region不等于动态全地址证明。

A26保存的跨页JALR方向强制不一致，完整实际目标执行检查仍在；mode0/2走原预测格式。A29只广播原branch_training_live全代际有效的accepted分支，bank冲突优先原首lane，无新执行ready反馈。A30/31 FQ空旁路接受N、直接消费K，原写行/尾指针前进N、头指针前进K、count=N-K；valid不依赖decode ready。epoch/错误/重定向/stop防护不变。

A33/A35新load候选只在原选择寄存器可接收、且无正常旧pick时写入。store数据只有已有PRF源ready才广告；同拍完成但尚未写PRF的源走旧wake路径。原RS/ALU完成不跳过，未增加store完成生产者。完整LSQ代际、行valid、年龄、逐byte最年轻旧store转发、请求owner和恢复继续原路。

A36使用课程要求的自然对齐：LB在对齐word任意byte、LH在0/2偏移、LW在0偏移，所有必要字节均在所存32位word。cache输出raw relative bytes，LSQ先覆盖forwarded bytes，再按原size/sign处理。cache128-bit SRAM、整行refill、victim/MSHR store合并与外部写回不动；即时hit、延后SRAM hit、demand return、MSHR forward、waiter、error各源的原接受/优先/保持/身份不改。WORD_RESPONSE默认关闭，核心只在OoO nonblocking-cache启用，serial/blocking路径保留原接口。

上述是源码审阅和哈希/投影证据，尚无HDL编译、仿真、综合、STA或整个核心等价证明。A36的IPC/面积/频率全部未知；A16/A21数据属于各自旧源码，不能混用。

## 其余方向筛选

RS独立store-data由课程trace常量零驱动，综合可能已剪除，删除声明不能重复计面积收益。纯删unused PC/元数据也须先看mapped owner，不能盲计FF。缩小D-cache曾使rsort倒退，暂不减少缓存容量。减少PRF端口或SRAM化PRF需处理同步读、多端口冲突和旁路，不支持直接替换后仍声称零额外周期。继续增深整数/唤醒流水线会直接延长依赖链；增加issue/ALU宽度超过2目前面积成本明显，尚无吞吐占用证据。gshare/loop predictor、early store source wake等更大协议改动需新增训练身份/恢复状态或数据更新仲裁，当前缺少收益足够覆盖成本的动态依据。

本轮可直接落实、且现有证据支持净收益的改动已整合为A36。继续累计未经测量的复杂结构将无法判定主次；本次只对这个组合取得实际IPC、面积、频率，不对A22–A35逐个回归或扫描参数。

## 单次测量范围及采用条件

在对话先汇报此报告后，执行一次Windows原生课程固定Verilator5.020构建、六perf、Yosys0.63/ABC/OpenSTA3.1综合/STA，不使用WSL。framework54fc150、tests29f9807、官方build.py/testcase.py/sim.cpp、程序/答案/metrics、ASAP7 RVT TT与FakeRAM计价保持冻结；perf latency10、MAX_CYCLES1,000,000、六项动态IPC GEOMEAN不改。综合2ns、课程I/O/uncertainty/load/reset/理想无寄生约束不改，以正式最小可行周期报告Fmax。

本次先不重复19correctness和M单元测试。只有取得相称实测收益且值得采用，才对同一冻结源码做19项课程正确性（官方支持的MAX_CYCLES10,000,000）及改动相关覆盖：全部8项M/符号边界/除零溢出/完成背压；分支恢复/错路径全代际；FQ部分消费、SRAM背压/填充冲突/错误；跨页间接和BTB hash别名；region更换；store allocation/byte forwarding/同束依赖；合并miss各word/offset的raw32返回和回收LSQ身份。六perf静态M指令为0，不能代替RV32IM验证。

EU主源码、旧候选与A16R2/A21结果保持冻结。本次构建/测量期间继续做已有网表路径和面积所有者分析及独立后续源码优化；不修改正在测量的A36快照。严格三指标及相应验证全部成立后才采用并将goal标为complete。
''',encoding='utf-8')
    tool_paths = [Path(config[key]) for key in ('yosys','abc','sta','verilator','verilator_build_driver')]
    tool_paths.append(Path(config['tools_root'])/'toolchain_manifest.json')
    tool_paths.extend(sorted(Path(config['asap7_lib']).glob('*.lib')))
    plan = dict(status='PREPARED_NOT_STARTED', candidate=str(CANDIDATE), candidate_sha256=sha(CANDIDATE/'candidate.json'),
        source_manifest_sha256=sha(RUN/'source_manifest.json'), config_sha256=sha(RUN/'course_windows_config.json'),
        pretest_report=str(REPORT), pretest_report_sha256=sha(REPORT),
        host_sha256={str(p):sha(p) for p in HOST_FILES}, tool_sha256={str(p):sha(p) for p in tool_paths},
        perf_cases=perf, correctness_cases=correctness, source_files=len(names), unchanged_course_dependency_files=len(untouched),
        source_reviews_sha256={f'A{i}_source_review.json':sha(CANDIDATE.parent/f'A{i}_source_review.json') for i in range(18,37)},
        shared_mdu_review_sha256=sha(CANDIDATE.parent/'A17R1_source_review.json'),
        static_isa_mix_proof_sha256=sha('F:/CPU2026Proofs/ER1_official_perf_static_instruction_mix_20261005.json'),
        perf_max_cycles=1000000, correctness_started_with_characterization=False,
        full_correctness_and_relevant_m_coverage_required_before_adoption=True,
        target=dict(ipc=1.1,total_area_um2=36000,strict_minimum_fmax_mhz=300),
        a16r2_reference_sha256=sha(RUN/'a16r2_reference.json'))
    write(RUN/'measurement_plan.json', plan)
    goal = read(GOAL_RECORD)
    goal.update(status='A36_FROZEN_PRETEST_NOT_STARTED',
        current_prepared_candidate=CANDIDATE.name, pending_source_candidate=str(CANDIDATE),
        pending_source_candidate_sha256=plan['candidate_sha256'], pending_source_candidate_tests_started=False,
        prepared_run=str(RUN), prepared_source_manifest_sha256=plan['source_manifest_sha256'],
        candidate_pretest_report=str(REPORT), candidate_pretest_report_sha256=plan['pretest_report_sha256'],
        last_goal_turn_classification='PROGRESS_A29_TO_A36_SOURCE_AND_FROZEN_PRETEST',
        previous_goal_turn_classification='NO_PROGRESS_METRICS_REPORT_REVALIDATED_TERMINAL_A16_A21',
        next_work=['Report A36 combined material-gain evidence before one native course characterization.',
                   'Continue independent source/netlist analysis while the exact A36 background process runs.',
                   'Require same-source strict metrics and relevant full correctness/M/recovery/cache/forwarding validation before adoption.'],
        goal_complete=False, candidates_adopted=False)
    # Historical metrics remain explicitly A21 until A36 results exist.
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
    goal.update(status='A36_IMMUTABLE_CHARACTERIZATION_IN_PROGRESS',
        active_measurement_candidate=CANDIDATE.name, measurement_run=str(RUN), measurement_process_id=process.pid,
        pending_source_candidate_tests_started=True, candidate_tests_started=True,
        previous_measurement_correctness_run=str(BASE), previous_measurement_correctness_process_id=read(BASE/'dispatch_identity.json')['process_id'])
    write(GOAL_RECORD,goal)
    print(dispatch)


def observe():
    check()
    dispatch = read(RUN/'dispatch_identity.json')
    result = optional(RUN/'result/result.json')
    metrics = ({key:result.get(key) for key in ('status','ipc','area_um2','fmax_mhz',
        'official_perf_expected_results_passed','official_correctness_suite_passed',
        'thread_objective_numeric_requirements_met')} if result else None)
    observation = dict(run=str(RUN),process_id=dispatch['process_id'],
        process_alive=live(dispatch['process_id']),observed_at=datetime.now(timezone.utc).isoformat(),
        result=metrics,failure=optional(RUN/'result/failure.json'))
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


