"""Create an independent A75 serial manager without running HDL tools."""
from pathlib import Path

from manage_frozen_baseline_programs import ROOT, sha


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    source = ROOT / 'tools/manage_er1_a69_measurement.py'
    target = ROOT / 'tools/manage_er1_a75_measurement.py'
    assert not target.exists()
    text = source.read_text(encoding='utf-8')
    text = once(text, 'Windows A56-A69 characterization.', 'Windows A70-A75 characterization.')
    text = once(text, 'from manage_er1_a55_serial_measurement import check as check_a55r2,memory_status',
        'from manage_er1_a55_serial_measurement import memory_status\nfrom manage_er1_a69_measurement import check as check_a69')
    text = once(text, "REFERENCE=Path('F:/CPU2026CourseRuns/ER1_A55R2_tier3_20261005')",
        "REFERENCE=Path('F:/CPU2026CourseRuns/ER1_A69_tier3_20261006')")
    text = once(text, "CANDIDATE=Path('F:/CPU2026Candidates/tier3_er1_20261005/A69_same_edge_redirect_fetch')",
        "CANDIDATE=Path('F:/CPU2026Candidates/tier3_er1_20261005/A75_branch_capture_phase_valid')")
    text = once(text, "RUN=Path('F:/CPU2026CourseRuns/ER1_A69_tier3_20261006')",
        "RUN=Path('F:/CPU2026CourseRuns/ER1_A75_tier3_20261006')")
    text = once(text, "REPORT=ROOT/'reports/ER1_A69_pretest_2026-10-06.md'",
        "REPORT=ROOT/'reports/ER1_A75_pretest_2026-10-06.md'")
    text = text.replace("'a55r2_reference.json'", "'a69_reference.json'")
    text = once(text, '    check_a55r2()', '    check_a69()')
    text = once(text, "    previous=Path('F:/CPU2026Candidates/tier3_er1_20261005/A55_predictor_bank_local_prefix_history')",
        "    previous=Path('F:/CPU2026Candidates/tier3_er1_20261005/A69_same_edge_redirect_fetch')")
    text = once(text, '    for number in range(56,70):', '    for number in range(70,76):')
    a = text.index("    progress[str(ROOT/'build/cpu2026/er1_a64_a67_source_progress_20261006.json')]")
    b = text.index("    active_path=", a)
    text = text[:a] + '''    for proof_name in ['er1_a70_source_progress_20261006.json',
        'er1_a69_partial_ppa_a71_a72_source_progress_20261006.json',
        'er1_a69_complete_result_20261006.json']:
        p=ROOT/'build/cpu2026'/proof_name
        progress[str(p)]=sha(p)
''' + text[b:]
    text = once(text, "'RENAME_RETAIN_FREE_POOL','FRONTEND_REDIRECT_REQUEST','RAS_REPEAT_COMPRESSION','RAS_REPEAT_COUNTER_BITS'):",
        "'RENAME_RETAIN_FREE_POOL','FRONTEND_REDIRECT_REQUEST','RAS_REPEAT_COMPRESSION','RAS_REPEAT_COUNTER_BITS',\n        'RECOVERY_ROB_CREDIT','LSQ_SECOND_REPORT_RECLAIM','BRANCH_CAPTURE_REDIRECT_READY',\n        'RAS_REPEAT_MATCH_PREDECODE','FRONTEND_RAS_PARALLEL_CONTROL','BRANCH_CAPTURE_PHASE_VALID'):")
    a = text.index("    REPORT.write_text(f'''")
    b = text.index('    tool_paths=', a)
    text = text[:a] + '''    REPORT.write_text(f\'''# ER1 A75：A70–A75 集中测量前汇报

目标保持频率严格大于300MHz、六项IPC几何平均至少1.1、含SRAM总面积至多36000μm²，并保留完整RV32IM、OoO、严格顺序提交、MMIO和参数化要求。

当前频率/面积符合目标的已测综合最优仍是A55R2：IPC1.01714182，Fmax306.86245MHz，总面积35480.53090μm²。最近完成的A69为IPC{original['ipc']:.8f}、Fmax{original['fmax_mhz']:.5f}MHz、总面积{original['area_um2']:.5f}μm²；六项性能程序通过，但频率低于目标，未采用。完整19正确性及相关专项覆盖仍未完成。以A69为基准，IPC还需相对提高{(1.1/original['ipc']-1)*100:.4f}%。

本批累计六项源码改动，没有逐项执行HDL/lint/形式/仿真/综合/STA/单元测试：

1. A70在充分限定的直接恢复apply边沿，把现有ROB信用寄存器写成min(BE_WIDTH,ROB_ENTRIES-1-branch_age)，减少旧占用数的保守滞后。实际分配容量、GEN和其他信用保护不变。
2. A71在原来两项前缀回收机制中，允许第二项已完成加载通过当拍原始单报告端口握手满足上报条件；没有新增完成端口，存储仍遵守原始队首确认顺序。
3. A72在valid+redirect+!pending条件下，通用ALU ready等于现有重定向优先规则。捕获改用这个等价表达式，实际ALU ready/消费不变，切断普通完成队列ready对捕获的结构依赖。
4. A73在取指位置尚未被最终调用选择时就计算返回PC是否匹配RAS栈顶。FE1/2/4共享PC高位及高位+1比较，最终只选择一位相等结果；调用返回、计数、溢出和原地址写入规则不变。
5. A74用并行首事件掩码表达原RAS循环，字边界改为常数比较，响应接受置于最终局部门控。先前调用/返回/预测跳转终止前缀的语义保留。
6. A75只在直接恢复且A72启用时，让捕获查询ALU取消前的已保存有效位。捕获必须pending=0，而直接ROB apply唯一来源是pending=1，因此捕获相位cancel恒为0；所有真实执行、完成、唤醒、消费和8位GEN检查保持原样。其他配置退回原输入。

主要收益依据来自已经测量的A69最慢路径，而不是泛化经验或位数估算。五条最慢路径共享主干：注册pending tag→ROB完整GEN资格→MDU取消/普通完成ready→重定向相关Icache响应→预测器→RAS。最长数据到达4.293ns。A72与A75在源图上删除普通完成ready和恢复apply到新分支捕获的反馈依赖；A73/A74缩短RAS末端晚到控制传播。A69中RAS地址选择控制到达约3.578ns，后续约0.715ns，但不能把整个区间当作可保存延迟。当前三项针对已测严重退化的结构性依赖已完成，值得集中重新表征；实际改善大小和是否恢复到300MHz以上未知。

这六项没有新增声明的FF/SRAM/普通或恢复流水边沿。新增信用/回收组合门、早期地址比较和电气扇出仍会改变面积；A69面积余量仅{36000-original['area_um2']:.3f}μm²，不能承诺面积达标。原SRAM、缓存容量、MSHR数量、预测表、ROB/PRF/RS/LSQ深度、FE4/BE2/双整数/CDB2及8位ROB代数保持相同。

源码审查范围包含直接恢复容量0/1/2/满/绕回、LSQ队首及第二项报告握手/停顿/恢复、全部取指位置和PC高位进位/全32位绕回、RAS空/满/计数溢出、先前调用/返回/taken事件、恢复相位与新捕获互斥、旧GEN/重复重定向、width1/2/4和选项0回退。当前是布尔/算术/相位与哈希论证，不是形式或动态等价证明。本批没有加入false-path、忽略恢复或减少标签代数位。

剩余想法已评估：

- 扩PRF：六项925条与实际镜像绑定的反汇编中，只有rsort写过的架构寄存器种类使静态物理容量可能先于ROB32受限；其他程序缺乏扩容收益依据。free-pool滞后不等同物理容量不足，因此先不花面积扩PRF。
- 精确RAS修复：恢复指针仍不能保证被错路径覆盖的地址/重复计数正确。增加逐分支完整检查点会显著增加面积；缺乏当前动态返回错误分布，暂不实现没有成本收益依据的修复。
- 提前到原始RS/ALU输入解决分支：会把load wake、RS rank、分支比较、GEN检查和取指串在同拍，需要额外预测/撤销或转发协议；不能简单移走结果寄存器。
- 扩ROB/LSQ/cache/预测表或引入loop/TAGE：需要当前动态容量/命中/方向错误分布支持。A36旧记录不能充当A75动态瓶颈，也不能把互相重叠的停顿相加。
- 已有ALU/MDU/LSQ直唤醒和原始存储地址早发机制，重复加入旁路没有依据。六项perf没有M指令，仍必须保留完整M扩展功能。
- 给恢复到取指路径增加普通等待拍可能恢复时序，却可能放弃A69已测IPC收益；先表征这批删除无效串行依赖的改写。

目前没有剩余基于这组已测最慢路径、能直接落地并解释正确性与成本的修改。先集中测量A70–A75，再按真实新瓶颈继续推进；长期架构选项没有被宣称穷尽，IPC1.1也没有被缩减为当前较低结果。

测试只用Windows原生课程标准链：框架54fc150ffc290f52aa024209ffb9a29d43856f6d、测试29f980727f7d99a1842a58f34091c7579ba3fe85、Yosys0.63、OpenSTA3.1、Verilator5.020、课程ASAP7 RVT TT及FakeRAM模型，latency10；映射clock2ns和原STA约束保持相同，SRAM计入总面积，不用WSL。冻结{len(names)}文件，{len(dependencies)}课程依赖与A69逐字节一致。

原监督模式串行执行一次--timing-only，再用同一源码manifest/config/工具/报告身份执行一次--reuse-synth；只构建一个CPU并运行六项官方perf，各1000000周期及原始答案。无并行大型工具前端、逐改测试、自动重试或失败覆盖。完整19正确性与M/恢复/代际/缓存/参数专项仍须在采用前完成，待数值明确改善后集中验证。

报告生成时没有HDL/构建/仿真/综合/STA作业启动。先在对话汇报后才调度；运行中保持本快照不变，在独立候选继续优化IPC及面积。主E工作区EU RTL不改动。PID查询超时不能用于重启原作业。

候选SHA256：{sha(CANDIDATE/'candidate.json')}

源码manifest SHA256：{sha(RUN/'source_manifest.json')}

全部源码、库、工具、主机脚本、六份审阅和源级/实测证据绑定在measurement_plan.json。
\''',encoding='utf-8')
''' + text[b:]
    text = text.replace("'A69_FROZEN_SERIAL_PRETEST_NOT_STARTED'", "'A75_FROZEN_SERIAL_PRETEST_NOT_STARTED'")
    text = text.replace("'PROGRESS_A56_A69_COHERENT_RECOVERY_OWNERSHIP_AUDIT_AND_NATIVE_PRETEST_FROZEN'",
        "'PROGRESS_A70_A75_CRITICAL_PATH_PHASE_AUDIT_AND_NATIVE_PRETEST_FROZEN'")
    text = text.replace("'A69_SERIAL_CHARACTERIZATION_IN_PROGRESS'", "'A75_SERIAL_CHARACTERIZATION_IN_PROGRESS'")
    text = text.replace("'PROGRESS_A69_CUMULATIVE_PRETEST_REPORTED_NATIVE_SERIAL_DISPATCH'",
        "'PROGRESS_A75_CUMULATIVE_PRETEST_REPORTED_NATIVE_SERIAL_DISPATCH'")
    target.write_text(text, encoding='utf-8')
    print(dict(status='A75_NEW_SERIAL_MANAGER_CREATED_NO_HDL_EXECUTION', manager=str(target),
        manager_sha256=sha(target), template_sha256=sha(source)))


if __name__ == '__main__':
    main()
