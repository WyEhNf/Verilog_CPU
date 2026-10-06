"""Publish the frozen EL1 scope before one timing-only dispatch; no tests."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    root=Path('E:/Verilog_cpu')
    active_path=root/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=read(active_path)
    candidate=Path('F:/CPU2026Candidates/frequency_research_20261003/EL1_cache_response_match_before_select')
    run=Path('F:/CPU2026CourseRuns/architecture_EL1_20261005')
    prior=read('F:/CPU2026Candidates/pre_EL1_worktree_20261005/backup.json')['previous_identity']
    frozen=read(run/'source_manifest.json')
    cm=read(candidate/'candidate.json')
    review_path=Path('F:/CPU2026Proofs/EL1_source_review_20261005/source_review.json')
    review=read(review_path)
    assert Path(active['candidate'])==candidate and Path(active['frozen_run'])==run
    assert not active['tests_started']
    assert sha(candidate/'candidate.json')==review['candidate_manifest_sha256']==frozen['candidate_manifest_sha256']
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    assert len(cm['implemented_groups'])==16 and cm['new_declared_sequential_state_bits']==0
    assert frozen['parameter_overrides']==prior['parameter_overrides']
    assert prior['current_measured_fmax_mhz']==370.4775687409551
    for name,expected in active['source_sha256'].items():
        assert sha(root/name)==expected,name
    for name,expected in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/name)==expected,name
    config=read(run/'course_windows_config.json')
    assert config['environment']=='WINDOWS_NATIVE' and config['wsl_allowed'] is False
    for name in ('result','native_build','native_ipc','dispatch_identity.json','driver_stdout.log','driver_stderr.log'):
        assert not (run/name).exists(),name
    report=root/'reports/frequency_batch_EL1_pretest_2026-10-05.md'
    assert not report.exists()
    text='''# EL1 完整组合及测试前汇报

完整组合已实现、备份并冻结，**尚未启动 EL1 的 HDL 编译、仿真、综合或 STA**。先在对话汇报本报告，再只对完整组合做一次 Windows 原生课程综合/STA。EG、EI、EJ、EK、EL1 均未单项测试；本阶段不构建 Verilator、不跑 IPC 或功能程序。

## 已测参考与当前身份

实测参考 EF：370.477569 MHz，最低周期 2.69921875 ns，总面积 49,116.955854 μm²，其中 SRAM 7,825.666854 μm²；原面积基线以上 6.0619%，仍在 ±10% 内。EF 的 IPC、功能均未测，Tier3 面积 36,000 未满足。上述数字只属于 EF，**当前 EL1 的所有指标均未知**。原 EF 已完整备份，原冻结结果保留。

EF 五条最慢路径：第一条 2.6398 ns，另外四条 2.6327 ns。第一条为 LSQ report → direct report grant → RS wake → shared store base probe → store packet → normal ROB live 查询 → LSQ mask owner；不是普通 ALU 地址加法路径。另外四条为 Dcache response read/lifecycle/output select → LSQ response row 查询 → byte offset → line extraction。不能继续只在 ALU 上加流水级期待这些联系自动消失。

## 五类新结构，普通整数流水线保持 10 级

|改动|解决的串行联系|代价与边界|
|---|---|---|
|EG：PRF 旁路前并行计算分配 store 地址|旧存储值和每个原写回值各先加 signed-12 offset，复用原旁路匹配与最高槽优先级选地址；恢复 EF 取消的分配提前地址机会|当前 BE=4，共 20 个分配加法器；零新增状态。原数据/ready/同批依赖与 normal ROB 权限保留。增加面积和源数据负载，未声称新频率收益|
|EI：共享 store probe 使用现有 RS ready/value 寄存器|切断当前拍 LSQ report/wake → shared probe 的实际最长链|只延后刚被唤醒的机会性共享探测，普通 issue 的全部 wake/操作数旁路保持。普通 AGU 和 EG 分配地址仍可先完成；共享多 store 竞争时的 IPC 代价未知|
|EJ：LSQ 响应直接选行，偏移先解码|省掉 payload 上的行号编码再解码；地址偏移在行选择前变为 one-hot，直接选固定 32 位 byte window|当前 query 60→72 位，零新增状态。保留原完整匹配、最后行/默认行 0 优先级、所有偏移的末尾填零、转发合并和 LB/LH 符号扩展|
|EK：完整返回 tag/valid 按四行分域比较|分散 Dcache 输出 tag 到 16 行 XNOR 比较的负载|当前四域，每叶最多四行比较；原 valid、slot、完整 generation、response_wait 全保留。多一段组合分发，收益待测|
|EL1：Dcache 地址每行先比较，再选择匹配位|移除晚到 selected writeback → 32 位地址 mux → 比较的联系|当前 4 MSHR、8 个 32 位比较，返回 line 地址负载增加。保留完整 victim 地址、demand 低四位清零，以及原索引范围/valid/sent 授权与全部消费者|

EF 的 ROB commit payload 分组、LSQ direct report、forwarding hold 分组、共享 signed-12 AGU、负极性分发、请求 owner、normal ROB 查询预解码、RAT 恢复及 Icache 分组继续保留。源码记录共 16 组，是一次组合测量；相对 EF 改动六个 RTL 文件：backend joint、RS、LSQ、Dcache、CPU core、PRF。没有改变课程顶层队列、发射宽度、cache 配置、39 项 override 或约束。

## 私有慢门证据及源码审查范围

读取 EF 已生成的映射 JSON，以库 cell 类型、公共输入端口、实际负载数及相邻 INV 拓扑对应私有名字。0.1909 ns AOI21 有 18 个直接连接，其中 16 个 XNOR2，支持接收端全 tag 比较负载的来源。0.2913 ns AOI221 有 50 个直接连接；四个所选 FF 的 D 输入均追溯到 lifecycle dirty_victim 位 14，与 writeback <= dirty_victim 相符。因此 EL1 针对该标志宽地址 mux 的可见消费者改写。**这是来源数据流推断，不是私有 net 的形式等价证明；也不声称整个 50-load 门已被消除。**

EF→EG→EI→EJ→EK→EL1 六份 manifest 和已有组件审查已核对。当前候选 41 个输入，主工作区 40 个输入，冻结 157 个输入；69 个 begin/end 复合时钟块与 EF 文本相同，零新增声明状态，普通整数流水线保持 10 级。EL1 只有原比较式的逐行/选择顺序转置，其余 Dcache 文本与 EK 相同。对于合法二值索引 r，先选地址再比较与先逐行比较再选 r 等价；原 response_found 仍必须为真。上述不是 HDL 接受、四态全参数形式等价、功能或 IPC 证明，EI 的 probe 可用时刻有意改变。

失败的 EL 准备目录因旧锚点格式不匹配而中止，未生成 candidate manifest、未改主工作区、未测试；保留失败记录，实际冻结使用已审查的 EL1。

## 其他方向的取舍

- EH 全部慢 load/MDU wake 延后到现有寄存器会影响普通依赖发射。本轮最长路径仅经过共享 probe，选更窄 EI。
- EC 保存整个 probe packet 需 79 位额外状态和阶段；当前路径可以用既有 RS 状态切断，未加入 EC。
- 全 CDB/cache 响应加寄存器或继续加整核流水级，需要重新对齐握手、恢复和依赖延迟。先采用本批两条链上已有边界和选择前并行计算。
- PRF 动态端口/分银行、减少宽度和窗口、依赖链分队列都可能有收益，但涉及仲裁、重发或 IPC 改变，且目前未证明它们是剩余主要限制链。
- 推测提前唤醒需要保存未决指令和失败重发；ROB 授权缓存需完整失效与恢复规则。本批保留所有正常 valid/generation 检查。
- 更改库、工具、课程约束，或只按高扇出排行统一加缓冲，不能代替消除当前长串行链。AXI 等未出现在最慢路径的锥，保留研究记录，不因单独负载排行盲改协议。

BOOM 的 fast/slow wake 设计及动态 PRF 读端口的重发代价见 [Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)、[Register Files](https://docs.boom-core.org/en/latest/sections/reg-file-bypass-network.html)。[Palacharla 等 ISCA 1997 论文](https://ftp.cs.wisc.edu/sohi/papers/1997/isca.complexity.pdf)研究 wake/select/bypass 复杂度和依赖队列；论文不是本 CPU 的定量时序预测。这里的取舍依据当前实际路径，属于设计判断。

本批已覆盖现有最慢两类路径的可见串行联系和宽控制负载；暂未找到另一个依据充分、应继续混入本批的结构方案。没有声称以后不可能发现新方案。整个组合的结构变化足以值得测一次，不将单个旧门延迟直接相减换算成预计 MHz。

## 唯一下一测量及后续条件

先把本报告在对话中汇报，再启动：`python tools/start_frequency_course_background.py --run F:/CPU2026CourseRuns/architecture_EL1_20261005 --timing-only`。一份完整组合调用一次课程 synth（包含原有 ABC 映射、周期搜索和报告），测 Fmax 与含 SRAM 总面积。无中间候选测量，无 CPU/程序测试。后台测量期间继续阅读源码和资料；新备选另存，冻结输入保持。

全程 Windows 原生，禁止 WSL。课程 framework `54fc150ffc290f52aa024209ffb9a29d43856f6d`、testcases `29f980727f7d99a1842a58f34091c7579ba3fe85`，固定 Yosys 0.63 / 课程 ABC / OpenSTA 3.1 / ASAP7 RVT TT / FakeRAM，原 latency=10、库、工具、面积算法和约束保持。

最初面积 ±10% 上限 50,940.662839 μm²，IPC 下限 0.882115146585；Tier3 最终需面积 ≤36,000、IPC ≥1.0985、频率 ≥300。频率仍是本阶段主目标；已测 EF 370.48 已过 300，但当前 EL1 未测。新组合有更大频率收益且面积可控后，另行先报告，复用完全相同的综合结果测必要 IPC/功能。350 MHz 只是第二阶段工作门槛，不替代原完整目标。

## 冻结与恢复身份

'''
    text+=f"- Candidate：`{candidate}`\n- Manifest SHA256：`{sha(candidate/'candidate.json')}`\n- 冻结目录：`{run}`\n- 冻结 manifest SHA256：`{sha(run/'source_manifest.json')}`\n- 源码审查：`{review_path}`\n- 对实测 EF 的完整改动：`F:/CPU2026Proofs/EL1_source_review_20261005/changes_vs_measured_EF.patch`\n- EF 备份：`F:/CPU2026Candidates/pre_EL1_worktree_20261005`\n- EF 实测报告：`E:/Verilog_cpu/reports/frequency_EF_measurement_2026-10-05.md`\n"
    report.write_text(text,encoding='utf-8')
    for key in ('measurement_report','current_timing_result_report','completed_timing_only_report',
                'measurement_observation','measurement_progress_recorded_at','measurement_started_at',
                'completed_build_identity','directed_result_report','completed_ipc_report',
                'limited_directed_checks','limited_directed_cases_passed'):
        active.pop(key,None)
    if 'post_dispatch_source_research' in active:
        active['last_background_source_research']=active.pop('post_dispatch_source_research')
    active.update(status='WORKTREE_IMPLEMENTED_UNTESTED_PRETEST_REPORTED',tests_started=False,
        measurement_process_id=None,current_measured_fmax_mhz=None,current_measured_ipc=None,current_measured_area_um2=None,
        measured_metrics_report=None,measured_frequency_belongs_to=None,
        implementation_report=str(report),pretest_report=str(report),pretest_report_sha256=sha(report),
        ongoing_research_report=str(report),research_status='FINAL_EL1_SIX_MANIFEST_COMBINATION_REPORTED',
        last_complete_course_standard_result=prior['last_complete_course_standard_result'],
        source_identity_review={**review,'review_path':str(review_path),'review_sha256':sha(review_path)},
        pending_source_research=[],source_research_decision=review['architecture_triage']['conclusion'],
        test_start_condition='Deliver the complete EL1 pretest scope in conversation before one native timing-only dispatch; no intermediate measurement or program test.',
        frequency_requirement_verified=dict(status='CURRENT_SOURCE_UNMEASURED',source_manifest_sha256=active['frozen_manifest_sha256'],
            previous_verified_report=active['last_verified_frequency_requirement']['report']),
        completion_audit=dict(observed_at=datetime.now(timezone.utc).isoformat(),frequency_300_met=None,
            area_within_10_percent=None,ipc_within_10_percent=None,tier3_area_met=None,tier3_ipc_met=None,
            full_correctness_proven=False,overall_goal_complete=False,
            remaining='EL1 unmeasured. Historical EF passes frequency and original area range; IPC/correctness and Tier3 remain unverified or unmet.'))
    active['measurement_plan'].update(ready_for_dispatch=True,initial_phase='TIMING_ONLY',cpu_build_started=False,
        simulation_started=False,official_course_synth_runs_planned=1,intermediate_candidate_tests_planned=0,
        measurement_scope_finalized=True,implemented_source_groups=16,frequency_reference_mhz=370.4775687409551)
    active['orchestration_source_sha256']={name:sha(root/name) for name in ('tools/run_course_standard_windows.py',
        'tools/start_frequency_course_background.py','tools/record_frequency_measurement_progress.py')}
    for item in active['prepared_unmeasured_alternatives']:
        if Path(item['candidate'])==candidate:
            item.update(adopted=True,tests_started=False,role='Adopted frozen EL1; intermediate components not separately measured')
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=active['status'],report=str(report),pretest_report_sha256=active['pretest_report_sha256'],
                         frozen_manifest_sha256=active['frozen_manifest_sha256'],
                         source_groups=16,tests_started=False,ready_for_one_timing_only=True)))


if __name__=='__main__':
    main()
