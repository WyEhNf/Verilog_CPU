"""Single official Pi follow-up after a source-proven insufficient watchdog."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
import sys

from manage_frozen_baseline_programs import ROOT, read, sha, write, optional
from manage_er1_a109_closing import check as check_original, OUT as ORIGINAL
from manage_er1_a109_measurement import RUN, live

OUT = Path('F:/CPU2026CourseRuns/ER1_A109_pi_budget_20261006')
PLAN = OUT/'followup_plan.json'
REPORT = ROOT/'reports/ER1_A109_pi_cycle_budget_pretest_2026-10-06.md'
STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'


def check():
    check_original()
    plan = read(PLAN)
    for name,digest in plan['frozen_sha256'].items():
        assert sha(Path(name)) == digest, name
    assert plan['max_cycles'] == 48000000 and plan['latency'] == 10
    return plan


def prepare():
    original = check_original()
    assert not OUT.exists() and not REPORT.exists()
    text = (ORIGINAL/'official_stdout.log').read_text(encoding='utf-8')
    block = re.search(r'^\[correctness_pi\]\s*(.*?)^\[correctness_qsort\]',text,re.MULTILINE|re.DOTALL)
    assert block and 'PASS' not in block.group(1)
    error = (ORIGINAL/'official_stderr.log').read_text(encoding='utf-8')
    assert 'FAIL: timeout or finish before exit write response; cycles=10000000' in error
    course = RUN/'source/.deps/RISC-V-CPU-2026'
    case = course/'testcases/correctness_pi'
    image = case/'program.data'
    asm = case/'program.S'
    mdu = RUN/'source/rtl/rv32m_mdu_iterative.v'
    wrapper = RUN/'source/rtl/backend/rv32m_mdu_reservation_station.v'
    source = mdu.read_text(encoding='utf-8')
    assert "if (step == 6'd31)" in source and "step <= 6'b0" in source
    assert 'busy <= 1\'b1' in source and '!busy && !finishing' in source
    assert 'MUL_IMPL' in wrapper.read_text(encoding='utf-8')
    assert read(RUN/'source_manifest.json')['parameter_overrides']['MUL_IMPL'] == 2
    memory = {}
    address = 0
    for line in image.read_text(encoding='utf-8').splitlines():
        for token in line.split('//')[0].split('#')[0].split():
            if token.startswith('@'):
                address = int(token[1:],16)
            else:
                value = int(token,16)
                assert 0 <= value <= 255
                memory[address] = value
                address += 1
    instructions = {int(pc,16):int(word,16) for pc,word in re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s',asm.read_text(encoding='utf-8'),re.MULTILINE)}
    for pc,word in instructions.items():
        assert sum(memory[pc+i]<<(8*i) for i in range(4)) == word, hex(pc)
    immediate = lambda word: ((word>>20)+2048)%4096-2048
    base = instructions[0xb4]&0xfffff000
    outer_initial = base+immediate(instructions[0xc8])
    inner_initial = base+immediate(instructions[0xc0])
    outer_final = immediate(instructions[0xd4])
    outer_stride = immediate(instructions[0x124])
    inner_stride = immediate(instructions[0x128])
    assert (outer_initial,inner_initial,outer_final,outer_stride,inner_stride) == (5599,2799,-1,-28,-14)
    assert immediate(instructions[0x104]) == -1
    iterations = (outer_final-outer_initial)//outer_stride
    assert iterations == 200 and outer_initial+iterations*outer_stride == outer_final
    inner_total = sum(inner_initial+i*inner_stride for i in range(iterations))
    assert inner_total == 281200
    m_classes = {pc:(word>>12)&7 for pc,word in instructions.items() if word&127==0x33 and word>>25==1}
    assert m_classes == {0x68:7,0xe4:0,0xec:6,0xf0:4,0x100:0,0x108:0,0x110:6,0x118:4,0x130:4,0x140:6}
    counts = dict(MUL=2*inner_total+iterations,DIV=inner_total+2*iterations,REM=inner_total+2*iterations,REMU=1)
    total = sum(counts.values())
    minimum = total*32
    assert total == 1125801 and minimum == 36025632
    assert read(case/'metrics.json')['dynamic_instructions'] == 3117658
    assert (case/'expected.txt').read_text(encoding='utf-8').strip() == '112'
    readme = ROOT/'.deps/RISC-V-CPU-2026/README-ZH.md'
    assert 'make test MAX_CYCLES=5000000 LATENCY=10' in readme.read_text(encoding='utf-8')
    sim = course/'scripts/sim.cpp'
    assert 'while (!memory.done && memory.cycle < limit && !context.gotFinish()) tick();' in sim.read_text(encoding='utf-8')
    executable = Path(original['executable'])
    assert sha(executable) == original['executable_sha256']
    OUT.mkdir(parents=True)
    bound = dict(status='SOURCE_ANALYSIS_NO_NEW_CPU_TESTS',outer_iterations=iterations,
        inner_iterations_total=inner_total,m_instruction_counts=counts,total_m_instructions=total,
        serialized_mdu_iterations_per_operation=32,minimum_required_iteration_cycles=minimum,
        original_deadline=10000000,correctness_answer_not_yet_verified=True,
        analysis_scope='Correct architectural execution needs this many M operations; lower bound proves watchdog insufficiency, not absence of other bugs.',
        disassembly_words_checked_against_original_image=len(instructions))
    write(OUT/'cycle_bound_analysis.json',bound)
    result = read(RUN/'result/result.json')
    REPORT.write_text(f'''# A109 Pi 周期预算核算与单项补测前汇报

原三项同配置实测仍为IPC{result['ipc']:.12f}、含SRAM面积{result['area_um2']:.6f}um²、估算Fmax{result['fmax_mhz']:.6f}MHz。原19+4集中验证仍继续；Pi已在10,000,000周期报告timeout，旧结果与错误日志完整保留，不能据此宣布正确性通过或采用源码。

Pi原汇编与program.data逐条编码核对。外层s3从5599每次减28直到-1，共200次；内层a2从2799每次外循环减14，到最后13，总计281200次。内层每次MUL×2、DIV×1、REM×1；外层额外MUL×1、DIV×2、REM×2，退出hash再REMU×1。因此MUL562600、DIV281600、REM281600、REMU1，共1,125,801条M指令。

当前MUL_IMPL2使用单份共享迭代器，busy阻止下一操作替换，step0..31每周期一轮，finishing与结果发布另占边沿。仅必需迭代的下界是1,125,801×32=36,025,632周期，尚未包括发射、发布、访存、分支或错误路径工作。10M预算不可能让功能正确的此实现完成Pi。A16旧独立Wallace乘法器、radix4/归一化/商余缓存除法器可6277118周期完成，不能把它的预算直接套到新的面积取舍。这是本次测试预算遗漏，不等于已证明CPU没有其他问题。

课程README-ZH.md明确演示make test MAX_CYCLES=5000000 LATENCY=10，Makefile/testcase.py直接提供可配置周期上限；config.mk也给出100000000示例。MAX_CYCLES是本地watchdog参数，用户提供的评分要求没有固定10M正确性门槛。sim.cpp中它只用于终止循环，不参与DUT输入或内存调度；内存latency仍10，所有原程序、Golden答案和工具版本保持同一冻结身份。六perf的原1M上限和已有三项指标不变。

现只用课程原testcase.py --kind correctness --case correctness_pi --max-cycles48000000 --latency10 --sim原exe。预算在36.03M必需迭代下界上给发射、发布和其他开销留余量；只有实际完整退出112与原答案匹配才算通过。复用同一exe/source/config，不构建CPU或重新测三项，不重复已通过程序。补测可与原其余case独立执行，输出写入{OUT}；原原19+4任务保留。最终必须同时核对原其余18项、四边界及此次Pi，再采用当前已测41源。

可执行文件SHA256：{original['executable_sha256']}。补测前已在对话汇报该单项范围与预算原因。
''',encoding='utf-8')
    frozen = {str(path):sha(path) for path in [Path(__file__),REPORT,OUT/'cycle_bound_analysis.json',
        mdu,wrapper,image,asm,case/'metrics.json',case/'expected.txt',readme,sim,
        course/'scripts/testcase.py',course/'scripts/oj_io.py',executable,
        RUN/'source_manifest.json',RUN/'course_windows_config.json',RUN/'result/result.json']}
    command = [sys.executable,'-u',str(course/'scripts/testcase.py'),'--kind','correctness',
        '--case','correctness_pi','--testcases',str(course/'testcases'),'--sim',str(executable),
        '--max-cycles','48000000','--latency','10']
    plan = dict(status='PREPARED_NOT_RUN',prepared_at=datetime.now(timezone.utc).isoformat(),
        command=command,candidate=original['candidate'],candidate_sha256=original['candidate_sha256'],
        source_manifest_sha256=original['source_manifest_sha256'],config_sha256=original['config_sha256'],
        executable=str(executable),executable_sha256=original['executable_sha256'],
        original_result_sha256=original['original_result_sha256'],max_cycles=48000000,latency=10,
        working_directory=str(RUN/'source'),runtime_bin=original['runtime_bin'],build_bin=original['build_bin'],
        cycle_bound_analysis_sha256=sha(OUT/'cycle_bound_analysis.json'),frozen_sha256=frozen,
        new_cpu_builds=0,new_synth_runs=0,new_perf_runs=0,case='correctness_pi',expected_u32=112)
    write(PLAN,plan)
    print(dict(status=plan['status'],minimum_iteration_cycles=minimum,max_cycles=plan['max_cycles'],pretest_report=str(REPORT)))


def start():
    plan = check()
    assert not (OUT/'dispatch_identity.json').exists() and not (OUT/'phase.json').exists()
    with (OUT/'supervisor_stdout.log').open('w',encoding='utf-8') as stdout,(OUT/'supervisor_stderr.log').open('w',encoding='utf-8') as stderr:
        process = subprocess.Popen([sys.executable,'-u',str(Path(__file__).resolve()),'run'],cwd=ROOT,
            stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP)
    dispatch = dict(started_at=datetime.now(timezone.utc).isoformat(),process_id=process.pid,
        plan_sha256=sha(PLAN),manager_sha256=sha(Path(__file__)),initial_process_alive=process.poll() is None)
    write(OUT/'dispatch_identity.json',dispatch)
    state = read(STATE)
    state.update(status='A109_NUMERIC_PASS_ORIGINAL_PI_10M_WATCHDOG_INSUFFICIENT_SINGLE_CASE_48M_FOLLOWUP_STARTED',
        pi_budget_followup_run=str(OUT),pi_budget_followup_process_id=process.pid,
        pi_budget_followup_plan_sha256=sha(PLAN),pi_iteration_lower_bound=36025632,
        original_pi_timeout_cycles=10000000,pi_followup_completed=False,goal_complete=False,candidates_adopted=False)
    write(STATE,state)
    print(dispatch)


def run():
    plan = check()
    assert not (OUT/'phase.json').exists() and not (OUT/'followup_result.json').exists()
    phase = dict(status='PI_CORRECTNESS_IN_PROGRESS',supervisor_pid=os.getpid(),started_at=datetime.now(timezone.utc).isoformat(),plan_sha256=sha(PLAN))
    write(OUT/'phase.json',phase)
    env = dict(os.environ,PYTHONUNBUFFERED='1')
    env['PATH'] = ';'.join([plan['runtime_bin'],plan['build_bin'],env['PATH']])
    with (OUT/'official_stdout.log').open('w',encoding='utf-8') as stdout,(OUT/'official_stderr.log').open('w',encoding='utf-8') as stderr:
        result = subprocess.run(plan['command'],cwd=plan['working_directory'],env=env,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
    text = (OUT/'official_stdout.log').read_text(encoding='utf-8')
    cycles = re.findall(r'^PASS cycles=(\d+)$',text,re.MULTILINE)
    passed = result.returncode == 0 and re.findall(r'^\[(correctness_[^\]]+)\]$',text,re.MULTILINE) == ['correctness_pi'] and len(cycles)==1 and 'Results: 1 passed, 0 failed' in text
    passed = passed and 36025632 <= int(cycles[0]) <= plan['max_cycles']
    check()
    output = dict(status='PI_BUDGET_FOLLOWUP_COMPLETE',completed_at=datetime.now(timezone.utc).isoformat(),
        returncode=result.returncode,passed=passed,cycles=int(cycles[0]) if len(cycles)==1 else None,
        max_cycles=plan['max_cycles'],latency=10,expected_u32=112,plan_sha256=sha(PLAN),
        source_manifest_sha256=plan['source_manifest_sha256'],executable_sha256=plan['executable_sha256'],
        official_stdout_sha256=sha(OUT/'official_stdout.log'),official_stderr_sha256=sha(OUT/'official_stderr.log'),
        new_cpu_builds=0,new_synth_runs=0,new_perf_runs=0,goal_complete=False)
    write(OUT/'followup_result.json',output)
    phase.update(status=output['status'],passed=passed,result_sha256=sha(OUT/'followup_result.json'))
    write(OUT/'phase.json',phase)
    print(output,flush=True)
    if not passed: raise SystemExit(1)


def observe():
    check()
    dispatch = read(OUT/'dispatch_identity.json')
    print(dict(observed_at=datetime.now(timezone.utc).isoformat(),process_id=dispatch['process_id'],
        process_alive=live(dispatch['process_id']),phase=optional(OUT/'phase.json'),result=optional(OUT/'followup_result.json')))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','start','run','observe'])
    args=parser.parse_args()
    assert os.name=='nt'
    if args.action=='run':
        try: run()
        except Exception as error:
            write(OUT/'failure.json',dict(status='PI_FOLLOWUP_FAILED',error=repr(error),failed_at=datetime.now(timezone.utc).isoformat()))
            raise
    else: {'prepare':prepare,'start':start,'observe':observe}[args.action]()
