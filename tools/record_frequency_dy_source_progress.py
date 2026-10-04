"""Record adopted DY source and a pretest report; never start measurement."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha(p):
    with Path(p).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def main():
    root=Path('E:/Verilog_cpu')
    active_path=root/'build/cpu2026/active_frequency_implementation_20261004.json'
    active=read(active_path)
    run=Path('F:/CPU2026CourseRuns/architecture_DY_20261005')
    candidate=Path('F:/CPU2026Candidates/frequency_research_20261003/DY_dm1_locality_and_store_simm12')
    backup=read('F:/CPU2026Candidates/pre_DY_worktree_20261005/backup.json')
    prior=backup['previous_identity']
    frozen=read(run/'source_manifest.json')
    review_path=Path('F:/CPU2026Proofs/DY_source_review_20261005/source_review.json')
    review=read(review_path)
    assert Path(active['candidate'])==candidate and Path(active['frozen_run'])==run
    assert active['tests_started'] is False and review['no_compiler_lint_simulation_synthesis_sta_or_formal_run']
    assert sha(candidate/'candidate.json')==review['candidate_manifest_sha256']==frozen['candidate_manifest_sha256']
    assert sha(run/'source_manifest.json')==active['frozen_manifest_sha256']
    for n,h in active['source_sha256'].items():
        assert sha(root/n)==h,n
    for n,h in frozen['snapshot_sha256'].items():
        assert sha(run/'source'/n)==h,n
    dm1=read('F:/CPU2026Candidates/pre_DT_worktree_20261005/backup.json')['previous_identity']
    assert frozen['parameter_overrides']==dm1['parameter_overrides']
    config=read(run/'course_windows_config.json')
    assert config['environment']=='WINDOWS_NATIVE' and config['wsl_allowed'] is False
    for name in ('result','dispatch_identity.json','native_build','native_ipc','driver_stdout.log','driver_stderr.log'):
        assert not (run/name).exists(),name
    report=root/'reports/frequency_batch_DY_pretest_2026-10-05.md'
    text=f'''# DY 频率优化源码进度与测试前报告（2026-10-05）

**当前工作区是 DY，未测。** 本轮只读取历史报告、修改源码、检查文件身份及 clocked block 文本并冻结快照，没有运行 HDL 编译、仿真、综合、STA 或形式验证。本报告不表示新版本频率已提升，也不自动触发测试；仍需完成剩余优化方向的考虑后，在实际启动前再次明确汇报。

## 已知测量结果与选择父版本的理由

|版本|频率 MHz|周期 ns|总面积 μm²（含 SRAM）|IPC|此次用途|
|---|---:|---:|---:|---:|---|
|DM1|302.1540|3.3095703125|51,130.6726|0.7823728642|DY 的有数据父版本|
|DT|272.2680|3.6728515625|51,371.6362|未测|保留回退结果及源码，不作为 DY 的父版本|
|DY|未测|未测|未测|未测|目前工作区源码|

DT 相对 DM1 频率下降 9.8910%。其最慢五条路径都经过 LSQ 请求锥；NAND5 的 220 个直接负载导致 1.3177 ns 单门延迟，后续 INV 又耗时 0.9104 ns，两者约占最慢数据到达时间的 61.6%。扁平化后的 `bus.enabled_words` 别名不等同于已证明字数函数是独立根因。DT 的 completion/PRF 组合影响整体映射，当前数据不足以把回退单独归因于某一组。

DM1 的旧最慢链则经过 LSQ 完成选择、ROB 存活/代际查询、completion 和 PRF 操作数旁路，随后还有一段较长组合后缀。因此 DY 同时针对请求锥、完成查询与控制分发，保留 DM1 的 completion 和 PRF 源码。历史 DM1 的 IPC/面积及有限功能结果只属于 DM1，不能作为 DY 的通过记录。

## 已完成并组合到工作区的五项改动

|改动|源级实现|为什么可能提高频率|代价与待验证事项|
|---|---|---|---|
|全核分发树极性重构|根节点一次反相、内部节点保持负极性、每个独立叶节点一次反相恢复正极性；内部仍最多四个子门负载|对 LEAVES>1，每条源至叶路径少两个串联 INV；去掉重复的中间驱动|不能把门数直接换算 MHz。入口负载与 slew 改变，需在实际映射后确认|
|LSQ 请求与转发构造局部化|在独立 combinational owner 中计算资格；掩码、完整标签、数据、转发临时值按最多 16 位分组门控|避免共同资格直接驱动宽字段和移位网络，针对这次 220 负载的慢锥|保留请求无效时的零字段及转发临时值门控；新增小树可能带来局部面积开销|
|LSQ 完成查询提前解码|每个存储行在报告选择前把 ROB slot 解成低/高两组 one-hot，连同完整报告传送|把 late selection 后的编码解码搬到并行早期计算，减少后串行查询逻辑|完成 packet 从 75 到 91 位，新增 16 位是组合线。仍读原 ROB valid 和完整 generation；报告无效时的状态读差异须维持有效位约束|
|分配时存储地址专用加法|低 12 位相加；高 20 位只需根据低位进位和立即数符号做 −1/0/+1|不再把通用 32 位操作数贯穿完整加法器|CPU decoder 的 store imm 是有符号 12 位；独立 trace 后端默认仍用通用加法|
|共享存储 AGU 专用加法|同一专用结构也用于既有共享 store address probe|消除另一处存储地址的通用 32 位加法后缀|只在 CPU 开启的同一 signed-12-bit 合同下启用；不增加探测/握手周期|

四个文件与 DM1 不同：`rtl/backend/rv32_backend_joint.v`、`rtl/backend/rv32_lsq.v`、`rtl/common/rv32_asap7_fanout.v`、`rtl/cpu_core.v`。普通整数路径仍是原有 10 级设计；未添加 clocked block 或声明的时序状态。只读文本对比检查了 **69 个**时钟块，其更新源码与 DM1 相同。这不是语法接受或功能等价证明。

旧 DM1 的既有 elaborated JSON 只读统计表明：原控制树的 RTL INV 实例为 119,936 个，极性方案对同一实例结构为 73,979 个，少 45,957 个（38.32%）。这是常量/死逻辑裁剪及映射之前的源实例数量，不能作为 DY 的实际标准单元、面积或延迟收益；DY 另外改了若干树实例。

## 请求代数及正确性边界

令 A 为 `!flush && !recovery && candidate_found && !candidate_wait`，F=A&&selected_load，M 为 access_mask，B 为原有 holding/tree 转发 mask。新请求有效位 V=`A && (!selected_load || ((B & M) != M))`，与旧嵌套请求判断的布尔函数一致。F 保持旧 target mask、fwd mask、fwd data 的资格；V 保持请求完整标签、size、mask 与 data 的资格；fire=V&&ready。先插入 raw forwarding data 再用 V 门控可行，因为 V&&selected_load 蕴含 F。地址继续保持旧的无有效位门控输出。

ROB 正常 valid/generation 检查、恢复取消、完整 LSQ/ROB tag、就绪/回压和 in-order commit 均保留。没有使用省略代际检查、约束放宽、库替换、黑盒或不计 SRAM 等方法。源码手工推导只针对实际二值硬件/合法 decoder 输入；没有完整四值或全参数形式等价结论。

## 已考虑的其他方向与后续待办

|方向|本轮判断|
|---|---|
|DT 的预比较、双 eligibility grant、融合 PRF 路由等组合|保留独立候选与实测记录。回退后的最慢锥变成请求资格，缺少单组收益证据，当前 DY 采用已有较好结果的 DM1 基础|
|只在 AXI enabled_words 周围加 buffer|公共网名不足以定位独立根因，且多个上游等价资格会重合；已经选择改整个 LSQ 请求/转发构造|
|继续机械增加流水级|已经是 10 级，当前巨大延迟集中在门的实际负载；单独加流水级不会自动修复这一负载结构|
|寄存 PRF 读与提前唤醒、分银行操作数路由|仍可考虑，但会改变依赖指令时序/端口冲突；先梳理可维持吞吐的具体结构，不能直接宣称 IPC 不变|
|复制局部 ROB 存活表/缓存查询结果|仍可考虑；须明确与分配、提交、恢复、槽重用的同步关系及面积，不能用过期授权代替实际 generation 检查|
|更多宽字段和掩码的局部负载拆分|后续读取既有网表做更广的负载清单，寻找五条最慢路径之外能直接实施的共享条件；这不需要启动新的 EDA|
|改变课程库/版本、时序约束或以 WSL 构建|不采用；继续 Windows 原生固定课程版本|

还有明确的源级研究方向，因此**此刻不启动新测试**。下一步是把可直接实施的剩余方向与已经完成的五组改动比较，必要时继续合并实现；在确定下一批范围后先向用户报告，再决定是否启动一次完整组合的后台 timing-only 测量。

若以后启动：先只调用原生课程综合/STA，并读取含 SRAM 面积；不单测中间候选、不构建 Verilator、不跑 CPU 程序。只有频率显示实质增益且面积评估可接受后再复用同一个综合结果测 IPC/正确性。350 MHz 是判断是否值得启动昂贵第二阶段的工作阈值，原始 300 MHz、面积±10%、IPC±10% 和最终 Tier3 要求没有被改写。350 MHz 不是本次已实现或已预测的结果。

## 快照与身份

'''
    text+=f"- 当前 candidate：`{candidate}`\n- Candidate manifest SHA256：`{sha(candidate/'candidate.json')}`\n- 冻结目录：`{run}`\n- 冻结 manifest SHA256：`{sha(run/'source_manifest.json')}`\n- 源码输入：工作区 {len(active['source_sha256'])} 项，冻结 {len(frozen['snapshot_sha256'])} 项，课程参数 override {len(frozen['parameter_overrides'])} 项（与 DM1 一致）。\n- 修改差异：`{candidate/'changes_vs_measured_DM1.patch'}`\n- 源码检查：`{review_path}`\n- 改动前 DT 备份：`F:/CPU2026Candidates/pre_DY_worktree_20261005`\n- DT 结果报告：`E:/Verilog_cpu/reports/frequency_DT_measurement_2026-10-05.md`\n"
    if report.exists():
        assert report.read_text(encoding='utf-8')==text,'Preserve a differing report'
    else:
        report.write_text(text,encoding='utf-8')
    active['previous_measurement']=dict(prior['last_timing_only_measurement'])
    active['last_observed_measurement']=dict(prior['last_timing_only_measurement'])
    for key in ('completed_timing_only_report','current_timing_result_report','measurement_report',
                'completed_build_identity','completed_ipc_report','directed_result_report',
                'measurement_observation','measurement_progress_recorded_at','limited_directed_checks',
                'limited_directed_cases_passed','measurement_started_at'):
        active.pop(key,None)
    active.update(status='WORKTREE_IMPLEMENTED_UNTESTED_RESEARCH_CONTINUES',measurement_process_id=None,
        tests_started=False,source_identity_review={**review,'review_path':str(review_path),'review_sha256':sha(review_path)},
        last_complete_course_standard_result=dm1['last_complete_course_standard_result'],
        implementation_report=str(report),pretest_report=str(report),pretest_report_sha256=sha(report),
        ongoing_research_report=str(report),research_status='FIVE_COMBINATIONAL_GROUPS_IMPLEMENTED_MORE_SOURCE_RESEARCH_PENDING',
        test_start_condition='Finish considering remaining concrete source optimization directions, then deliver final measurement-scope report before any dispatch. Current pretest report does not authorize automatic dispatch.',
        frequency_requirement_verified=dict(status='CURRENT_SOURCE_UNMEASURED',source_manifest_sha256=active['frozen_manifest_sha256'],
            previous_verified_report=prior['last_verified_frequency_requirement']['report']),
        completion_audit=dict(observed_at=datetime.now(timezone.utc).isoformat(),frequency_300_met=None,
            area_within_10_percent=None,ipc_within_10_percent=None,tier3_area_met=None,tier3_ipc_met=None,
            full_correctness_proven=False,overall_goal_complete=False,
            remaining='Current DY unmeasured. DM1 reached 302.154 MHz but area/IPC/full correctness targets remain unmet. DT timing regressed and programs were not run.'),
        pending_source_research=['Wider read-only mapped-load census outside published top-five paths',
            'Concrete PRF read/wakeup banking alternatives with dependency throughput analysis',
            'Local ROB status duplication/caching with exact allocation/retire/recovery authority rules'])
    active['measurement_plan']['ready_for_dispatch']=False
    active['measurement_plan']['cpu_build_started']=False
    active['measurement_plan']['simulation_started']=False
    active['measurement_plan']['frequency_reference_mhz']=dm1['current_measured_fmax_mhz']
    seen={entry['candidate'] for entry in active['prepared_unmeasured_alternatives']}
    for name in ('DU_lsq_report_rob_predecode','DV_negative_polarity_distribution','DW_predecode_and_polarity',
                 'DX_dm1_request_locality_and_predecode'):
        p=candidate.parent/name
        if str(p) not in seen:
            active['prepared_unmeasured_alternatives'].append(dict(candidate=str(p),manifest_sha256=sha(p/'candidate.json'),
                tests_started=False,adopted=False,role='Source-only alternative/intermediate retained; no individual measurement planned'))
    active_path.write_text(json.dumps(active,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=active['status'],report=str(report),frozen_manifest_sha256=active['frozen_manifest_sha256'],
                         active_inputs=len(active['source_sha256']),frozen_inputs=len(frozen['snapshot_sha256']),
                         tests_started=False,measurement_process_id=None)))


if __name__=='__main__':main()
