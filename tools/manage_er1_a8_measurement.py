"""Freeze/report, dispatch once, or observe one complete native A8 measurement."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from wait_frequency_directed_native import live

BASE=Path('F:/CPU2026CourseRuns/ER1_native_identifier_compat_20261005')
CANDIDATE=Path('F:/CPU2026Candidates/tier3_er1_20261005/A8_direct_issue_local_recovery')
RUN=Path('F:/CPU2026CourseRuns/ER1_A8_tier3_20261005')
REPORT=ROOT/'reports/ER1_A8_pretest_2026-10-05.md'
GOAL_RECORD=ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'


def check():
    plan=read(RUN/'measurement_plan.json')
    for path,key in [(RUN/'source_manifest.json','source_manifest_sha256'),
                     (RUN/'course_windows_config.json','config_sha256'),
                     (REPORT,'pretest_report_sha256'),(CANDIDATE/'candidate.json','candidate_sha256'),
                     (Path(__file__),'manager_sha256')]:
        assert sha(path)==plan[key],path
    manifest=read(RUN/'source_manifest.json')
    for name,digest in manifest['snapshot_sha256'].items():assert sha(RUN/'source'/name)==digest,name
    config=read(RUN/'course_windows_config.json')
    assert config['environment']=='WINDOWS_NATIVE' and config['wsl_allowed'] is False
    assert config['latency']==10
    assert sha(Path(config['tools_root'])/'toolchain_manifest.json')==plan['toolchain_manifest_sha256']
    return plan


def prepare():
    assert not RUN.exists() and not REPORT.exists()
    parent=read(BASE/'source_manifest.json');candidate=read(CANDIDATE/'candidate.json')
    for name,digest in parent['snapshot_sha256'].items():assert sha(BASE/'source'/name)==digest,name
    for name,digest in candidate['source_sha256'].items():assert sha(CANDIDATE/name)==digest,name
    active=read(ROOT/'build/cpu2026/active_frequency_implementation_20261004.json')
    for name,digest in active['source_sha256'].items():assert sha(ROOT/name)==digest,name
    # Validate the materialized top defaults rather than passing hidden overrides.
    top=(CANDIDATE/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key,value in candidate['parameter_overrides'].items():
        match=re.search(r'\b'+key+r'\s*=\s*(\d+)',top)
        assert match and int(match.group(1))==value,key
    names=sorted(set(parent['snapshot_sha256'])|set(candidate['source_sha256']))
    for name in names:
        src=CANDIDATE/name if name in candidate['source_sha256'] else BASE/'source'/name
        dest=RUN/'source'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    source=RUN/'source';framework=source/'.deps/RISC-V-CPU-2026'
    perf=sorted(p.name for p in (framework/'testcases').glob('perf_*') if p.is_dir())
    correctness=sorted(p.name for p in (framework/'testcases').glob('correctness_*') if p.is_dir())
    assert len(perf)==6 and len(correctness)==19
    untouched=[name for name in names if name.startswith('.deps/')]
    for name in untouched:assert sha(source/name)==parent['snapshot_sha256'][name],name
    frozen=dict(format='er1-tier3-native-source-v1',status='FROZEN_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),source_root=str(source),
        reference_manifest_sha256=sha(BASE/'source_manifest.json'),candidate=str(CANDIDATE),
        candidate_manifest_sha256=sha(CANDIDATE/'candidate.json'),
        framework_commit=candidate['framework_commit'],testcases_commit=candidate['testcases_commit'],
        parameter_overrides=candidate['parameter_overrides'],materialized_top_defaults=True,
        snapshot_sha256={name:sha(source/name) for name in names},tests_started=False)
    write(RUN/'source_manifest.json',frozen)
    config=read(BASE/'course_windows_config.json')
    config.update(source=str(source),source_manifest=str(RUN/'source_manifest.json'),
        out=str(RUN/'result'),native_build_path=str(RUN/'native_build'),native_ipc_path=str(RUN/'native_ipc'))
    write(RUN/'course_windows_config.json',config)
    REPORT.write_text('''# ER1 A8 完整组合测试前汇报

目标仍为 Fmax>300MHz、六个官方perf动态IPC几何平均≥1.1、含SRAM总面积≤36,000μm²。
ER1 已测基线：IPC0.76303979、371.41820820MHz、49,638.890694μm²。需IPC+44.1602%、面积−27.4762%。

本次只测一个完整组合A8，不测A1—A7中间版本，不扫描参数。修改已实现并完成源码审查：

|修改|可观收益的源码依据|待测限制|
|---|---|---|
|ready-base load分配时写LSQ地址，并免去RS/AGU重复发射|复用20个原有分配地址加法器，每个符合条件的load少占一个RS/AGU操作|实际符合条件的动态比例未知；缺基址load保持普通AGU|
|恢复已有D-cache HIT_BYPASS|空响应槽、可接受hit少等一个边沿|命中回传组合路径变长|
|RS直接发射至原有带结果寄存器的ALU|普通依赖链少一个队列边沿；不实例化四个两项缓冲，声明容量1,984位|wake/select/ALU合并路径可能低于300MHz|
|保留LOCAL_EXEC_RECOVERY=1|ALU/MDU/LSQ仍有原有年龄取消与唤醒保护|完整分支恢复正确性待测|
|ROB32/PRF56/RS8/D-cache512行|减少队列/PRF/比较读写网络与真实SRAM；保持四路整数发射、CDB3、LSQ16、I/D MSHR8/4|资源缩减及cache miss可能抵消IPC收益|
|轻量ROB及匹配的窄读包|ROB32省去4,224位不用的PC/指令/地址/mask/普通value载荷；退休包197→65位，分配选择包86→22位|实际映射面积未测；保持MMIO数据、完整tag、ready/error和顺序退休|

理想普通load命中路径（以LSQ分配边沿t0计，无老store阻塞、转发、miss、背压和恢复）：
ER1在t1捕获issue队列、t2捕获AGU、t3写LSQ地址、t4捕获LSQ选择、t5查询SRAM、t6缓存响应寄存、t7捕获LSQ结果、t8写PRF。
A8在t0同时写地址、t1捕获LSQ选择、t2查询SRAM、t3旁路响应捕获LSQ结果、t4写PRF。
因此这类路径明确省去4个等待边沿；整体IPC不能据此直接推算，尚未宣称达到1.1。

课程FakeRAM公式与预期宏形状给出SRAM从7,825.666854降至约4,299.816954μm²（−3,525.849900）。
这只是形状预算，正式报告须确认宏数量/深度/宽度；不得把寄存器声明位数换算为最终逻辑面积。
仍需要逻辑面积明显下降。32行ROB、窄载荷和去队列共同针对该差额，不保证总面积已达36,000。

宽度/生命周期检查：ROB槽5位、generation8位、tag16位；LSQ槽4位、generation9位、tag16位；PRF地址6位。
56个PRF的八位空闲组共7组；64叶读树中56—63号行输出0。RS8为3位索引。
D-cache两路、256set、8位index、20位tag；保持128位line、按字节写及四个tag读镜像。
省略RS的load仍被保守地预留RS信用，不增加容量承诺；LSQ/ROB/PRF目标原子分配和完整代际判断保持。
课程顶层明确LEGACY_SENTINEL_HALT=0，普通ROB value只到未连接退休输出；如启用旧HALT，自动恢复value存储。
MMIO退出所用store_data始终保留，AXI地址/WDATA/WSTRB由原LSQ路径输出。

本轮暂未追加：共享load地址探测器的寄存器基址晚于当前周期RS唤醒旁路，收益主要限于争用；
更激进容量缩减缺乏动态压力证据；全局删除keep仅有约804μm²保守不可观察面积证据且可能破坏时序分布。
这些不足以支持继续堆入本次组合。先统一测量当前已具备明确结构收益的完整实现。

测量范围：原生Windows固定课程Yosys0.63/ABC/OpenSTA3.1/Verilator5.020，官方脚本与sim.cpp不变；不使用WSL。
一次CPU构建、一次六perf、一次19correctness、一次综合/STA（含FakeRAM面积和完整边界）。两阶段可并行。
latency10，分子用原metrics动态指令数，综合请求2ns；其余课程约束、ASAP7 RVT TT/FakeRAM计价不变。
报告生成和冻结时尚未启动任何候选测试；对话汇报后才一次调度。保留EU工作树和所有ER1原结果。
最终必须由同一冻结版本证明严格IPC≥1.1、Fmax>300和总面积≤36,000，以及全部25个程序答案。
任何功能失败或指标未达标都保留记录并继续优化，不据源码检查、旧IPC或旧频率宣布完成。
''',encoding='utf-8')
    plan=dict(status='PREPARED_NOT_STARTED',candidate=str(CANDIDATE),
        candidate_sha256=sha(CANDIDATE/'candidate.json'),source_manifest_sha256=sha(RUN/'source_manifest.json'),
        config_sha256=sha(RUN/'course_windows_config.json'),pretest_report=str(REPORT),
        pretest_report_sha256=sha(REPORT),toolchain_manifest_sha256=sha(Path(config['tools_root'])/'toolchain_manifest.json'),
        manager_sha256=sha(Path(__file__)),perf_cases=perf,correctness_cases=correctness,
        unchanged_course_dependency_files=len(untouched),source_files=len(names),
        scope='One complete A8 CPU build + six perf +19correctness + one synth/STA; no intermediate or directed cases.',
        target=dict(ipc=1.1,total_area_um2=36000,strict_minimum_fmax_mhz=300))
    write(RUN/'measurement_plan.json',plan)
    goal=read(GOAL_RECORD)
    goal.update(status='A8_SOURCE_READY_FROZEN_PRETEST_REPORTED_NOT_STARTED',current_prepared_candidate=CANDIDATE.name,
        candidate_manifest_sha256=plan['candidate_sha256'],candidate_tests_started=False,candidates_adopted=False,
        prepared_run=str(RUN),prepared_source_manifest_sha256=plan['source_manifest_sha256'],
        candidate_pretest_report=str(REPORT),candidate_pretest_report_sha256=sha(REPORT),
        last_goal_turn_classification='PROGRESS_SOURCE_IMPLEMENTATION_AND_FREEZE',
        candidate_ipc=None,candidate_fmax_mhz=None,candidate_area_um2=None,
        next_work=['Deliver concrete pretest scope before one complete measurement.',
                   'Continue independent optimization while the immutable measurement runs.',
                   'Audit exact A8 IPC/area/Fmax/full25program answers against the full objective.'])
    write(GOAL_RECORD,goal)
    check()
    print({k:plan[k] for k in ('status','candidate','source_files','unchanged_course_dependency_files','pretest_report','source_manifest_sha256')})


def start():
    plan=check()
    assert plan['status']=='PREPARED_NOT_STARTED'
    assert not (RUN/'dispatch_identity.json').exists() and not (RUN/'result').exists()
    command=[sys.executable,'-u',str(ROOT/'tools/run_course_standard_windows.py'),
             '--config',str(RUN/'course_windows_config.json'),'--correctness']
    with (RUN/'driver_stdout.log').open('w',encoding='utf-8') as stdout,(RUN/'driver_stderr.log').open('w',encoding='utf-8') as stderr:
        process=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)
    dispatch=dict(status='BACKGROUND_DISPATCHED',process_id=process.pid,
        started_at=datetime.now(timezone.utc).isoformat(),command=command,
        source_manifest_sha256=plan['source_manifest_sha256'],pretest_report_sha256=plan['pretest_report_sha256'],
        initial_process_alive=process.poll() is None,environment='WINDOWS_NATIVE')
    write(RUN/'dispatch_identity.json',dispatch)
    goal=read(GOAL_RECORD);goal.update(status='A8_IMMUTABLE_MEASUREMENT_IN_PROGRESS',
        candidate_tests_started=True,measurement_run=str(RUN),measurement_process_id=process.pid)
    write(GOAL_RECORD,goal)
    print(dispatch)


def observe():
    plan=check();dispatch=read(RUN/'dispatch_identity.json')
    observation=dict(run=str(RUN),process_id=dispatch['process_id'],
        process_alive=live(dispatch['process_id']),observed_at=datetime.now(timezone.utc).isoformat(),
        result=optional(RUN/'result/result.json'),failure=optional(RUN/'result/failure.json'))
    if observation['result']:
        result=observation['result']
        observation['objective_numeric_met']=(result['ipc']>=1.1 and result['fmax_mhz']>300 and result['area_um2']<=36000)
    for name in ('driver_stdout.log','driver_stderr.log'):
        path=RUN/name
        observation[name]=[line[:250] for line in path.read_text(errors='replace').splitlines()[-4:]] if path.exists() else []
    print({k:v for k,v in observation.items() if k not in ('result',)})


def main():
    assert os.name=='nt','Native Windows only'
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','start','observe'))
    args=parser.parse_args()
    {'prepare':prepare,'start':start,'observe':observe}[args.action]()


if __name__=='__main__':main()
