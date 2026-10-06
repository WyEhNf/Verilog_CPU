"""Create a fresh coherent A103-A105 PPA-gated manager; preserve old runs."""
from manage_frozen_baseline_programs import ROOT, sha


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    source=ROOT/'tools/manage_er1_a99_measurement.py'
    target=ROOT/'tools/manage_er1_a105_measurement.py'
    assert not target.exists()
    assert sha(source)=='2aad9628013a17d2cd69be96e79a704d7fe121399a79452f5662cdbe1e94248f'
    text=source.read_text(encoding='utf-8')
    for old,new in [
        ('Windows A95-A99 PPA-gated characterization.','Windows A95-A105 coherent PPA-gated characterization.'),
        ("CANDIDATE=Path('F:/CPU2026Candidates/tier3_er1_20261005/A99_balanced_saved_identity')","CANDIDATE=Path('F:/CPU2026Candidates/tier3_er1_20261005/A105_rob_recovery_row_live')"),
        ("RUN=Path('F:/CPU2026CourseRuns/ER1_A99_tier3_20261006')","RUN=Path('F:/CPU2026CourseRuns/ER1_A105_tier3_20261006')"),
        ("REPORT=ROOT/'reports/ER1_A99_pretest_2026-10-06.md'","REPORT=ROOT/'reports/ER1_A105_pretest_2026-10-06.md'"),
        ("ROOT/'tools/prepare_er1_a99_measurement_manager.py'","ROOT/'tools/prepare_er1_a105_measurement_manager.py'"),
        ('for number in range(95,100):','for number in range(95,106):'),
        ("    99:'prepare_er1_balanced_saved_identity.py',", "    99:'prepare_er1_balanced_saved_identity.py',\n"
         "    100:'prepare_er1_held_report_identity_query.py',\n"
         "    101:'prepare_er1_held_identity_row_query.py',\n"
         "    102:'prepare_er1_report_recovery_prequalification.py',\n"
         "    103:'prepare_er1_report_recovery_age_width.py',\n"
         "    104:'prepare_er1_lsq_alloc_fire_distribution.py',\n"
         "    105:'prepare_er1_rob_recovery_row_live.py',"),
        ("        'LSQ_SAVED_IDENTITY_WORD_MASK','LSQ_SAVED_IDENTITY_BALANCED_MERGE'):",
         "        'LSQ_SAVED_IDENTITY_WORD_MASK','LSQ_SAVED_IDENTITY_BALANCED_MERGE','LSQ_HELD_LOAD_IDENTITY_QUERY',\n"
         "        'LSQ_REPORT_RECOVERY_PREQUALIFY','LSQ_ALLOC_FIRE_DISTRIBUTE','ROB_RECOVERY_ROW_LIVE_QUALIFY'):"),
        ("        'er1_a99_source_progress_20261006.json']:",
         "        'er1_a99_source_progress_20261006.json',\n"
         "        'er1_a100_background_progress_20261006.json',\n"
         "        'er1_a101_background_progress_20261006.json',\n"
         "        'er1_minimal_closing_coverage_20261006.json',\n"
         "        'er1_a99_ppa_result_20261006.json',\n"
         "        'er1_a102_a104_source_progress_20261006.json',\n"
         "        'er1_a105_source_progress_20261006.json']:"),
        ("status='A99_FROZEN_PPA_GATED_PRETEST_NOT_STARTED'","status='A105_FROZEN_PPA_GATED_PRETEST_NOT_STARTED'"),
        ("'PROGRESS_A95_A99_A94_CYCLE_FREQUENCY_NATIVE_PRETEST_FROZEN'","'PROGRESS_A103_A105_RECOVERY_ROOT_MIDDLE_TAIL_NATIVE_PRETEST_FROZEN'"),
        ("status='A99_PPA_GATED_CHARACTERIZATION_IN_PROGRESS'","status='A105_PPA_GATED_CHARACTERIZATION_IN_PROGRESS'"),
        ("'PROGRESS_A99_PRETEST_REPORTED_PPA_GATED_NATIVE_SERIAL_DISPATCH'","'PROGRESS_A105_PRETEST_REPORTED_PPA_GATED_NATIVE_SERIAL_DISPATCH'"),
    ]:text=once(text,old,new)
    start=text.index("    REPORT.write_text(f'''");end=text.index('    assert effective[',start)
    report="""    REPORT.write_text(f'''# A105：恢复链起点/中段/末段结构批次，测量前汇报

目标严格>300MHz、六perf IPC几何平均≥1.1、含SRAM总面积≤36000μm²；完整RV32IM/OoO/顺序提交/MMIO与参数化保持。

## 原结果与新瓶颈

最新完整三指标参考A94：IPC{original['ipc']:.9f}、Fmax{original['fmax_mhz']:.6f}MHz、总面积{original['area_um2']:.6f}μm²，六perf答案通过、19正确性未跑。A99一次PPA为287.802136031478MHz、35915.75847799814μm²，原PID48248终态，门槛未过所以无CPU构建/IPC仿真。频率退化2.447297MHz、面积增加116.7858μm²；不把参考IPC借给A99或A105。当前周期还需缩短超过141.276ps，面积余量84.241522μm²。

新最慢五条均由branch_capture元数据开始，最长数据到达3.414ns：ROB恢复身份行选0.2935ns→recovery_preview0.6154ns→恢复分布0.7736ns→LSQ公开标签bit5（completiondata79）1.823ns→CDB选择2.202ns→PRF旁路2.499ns→分配资格2.982ns→LSQ行写3.253ns→FF。根段在选出9位currentGEN后比较；中段在晚报告选择后用公开tag算恢复资格；尾段分配事件驱动所有metadata/payload行。最长OAI21单门337ps/66负载/27.8877fF，晚分配NAND3约212ps/24.14fF。

## 已完成的整批源码

| 活跃修改 | 作用 |
|---|---|
| A103（修正A102类型后） | 保存/held与head完整候选分别前算原恢复kill资格，晚H/head只选bool；实际apply/producer-valid和全ROBGEN仍门控原target-live更新。 |
| A104 | 原真实LSQ alloc_fire通过功能控制树送到每组最多4行的metadata/payload匹配；公共分配/计数/票据、容量/槽位/GEN/写优先级保持。 |
| A105 | 当前ROB每行提前比较完整GEN与valid，再与槽位相等条件作bool OR；免去先读取9位valid/GEN再比较的串行层，原tagvalid/恢复选择/descriptor与状态保持。 |

A105在合法索引r下等价于tagvalid&&valid[r]&&fullGENmatch；非法索引无hit，两模式均false；tagvalid0两模式均false。因此不借用可达状态假设或删GEN/range。二叉1bitOR与query分发均实际映射/计价，非理想buffer。

A102准备时把age/branch_age误当signedINTEGER32；源声明复查发现实际是unsignedROB_SLOT_WIDTH regs，A103恢复原减法截断和unsigned比较。A102未测试/未采用，旧快照与错误审阅保持且被新证明明确替代。本批只测修正后末端A105。A100/A101第三held查询可选代码保留，课程flag0，保持A99两候选成本，不另测旧报告方向。FAST_STORE_BATCH仍0。A95/A97/A98/A99纯布尔/映射结构继承。

无新增声明FF、SRAM、流水边沿/端口容量；FE4/BE2/整数2/CDB2、ROB32/PRF56/RS8/LSQ16/BTB16、缓存/预测尺寸与完整8ROBGEN/9LSQGEN保持。预计二值输入下周期行为与A94一致，实际IPC仍重测。新增并行GEN比较有组合成本，移除9位读mux也有节省；84μm²余量很紧，不能以无FF或理论并行推定净面积/频率必过。

源级复查涵盖报告candidate/公共tag一致性、原unsigned年龄声明/减法/比较、完整GEN、apply/valid/held/head选择、非2幂/entries1/padding、实际alloc_fire控制等式/无creditloop，以及恢复/提交/数据/错误/状态。仅源码和哈希推导，无逐修改HDL/lint/形式/仿真/综合/STA/单元测试。

## 剩余方向与收益判断

三项针对同链root/middle/tail，可减少读取后的GEN比较、晚标签分类和高控制负载，直接覆盖多处数百ps区间，足以支持一次整批PPA判断；不能把各区间相加预测节省，新瓶颈和mapping可能抵消。再注册恢复/CDB/PRF会改变同周期唤醒/原子入队，IPC余量仅1.37%；扩窗口/大型预测器无本版瓶颈依据且面积紧；删GEN/取消/range不符合语义。CDB轮转/held仲裁进一步改写的净收益证据弱于已完成三项。当前没有额外能说明更明确可观净收益的同路径修改待完成，不宣称穷尽长期架构方案。

## 测量与最终验证范围

新目录{RUN}，冻结{len(names)}文件/其中{len(dependencies)}课程依赖与成功A94逐字一致。原生Windows、无WSL；框架54fc150ffc290f52aa024209ffb9a29d43856f6d，测试29f980727f7d99a1842a58f34091c7579ba3fe85，Yosys0.63/ABC/OpenSTA3.1/Verilator5.020，原ASAP7RVT TT/FakeRAM、latency10、clock2ns和原I/O/uncertainty/load保持。

对话汇报后一次综合/STA；只有Fmax>300且总面积≤36000，才复用同manifest/config/PPA构建一次原课程CPU、运行六perf各1000000周期并核对答案/原动态指令数/GEOMEAN。PPA不通过则终态性能阶段跳过，无构建/IPC，不重启旧任务或覆盖旧证据。

三项实测全部达标后另存正确性证据，复用同CPU一次原19官方正确性（上限10000000周期）及4份既有冻结补充程序（上限200000周期、latency10），不重综合/构建/六perf。四程序解释器共8762指令覆盖45类RV32IM、全部8M、除零/溢出/自然对齐/RAM边界/分支/JALR；补齐官方19没有DIVU/MULH/MULHSU/MULHU的缺口。冻结字节/期望不是当前CPU通过证明，有限测试不等于完整ISA形式证明；关键参数化仍源级审阅。

准备时未开始新测试；11份95至105准备脚本/审阅、完整参考和A99终态/newpath/类型修正/closingcoverage等证据、原工具与本管理器均绑定哈希。主E EU40文件不变，无采用。目标未达成。

候选SHA256：{sha(CANDIDATE/'candidate.json')}

源manifest SHA256：{sha(RUN/'source_manifest.json')}
''',encoding='utf-8')
"""
    text=text[:start]+report+text[end:]
    marker="    assert effective['LSQ_SAVED_IDENTITY_WORD_MASK']==effective['LSQ_SAVED_IDENTITY_BALANCED_MERGE']==1"
    text=once(text,marker,marker+"\n    assert effective['LSQ_HELD_LOAD_IDENTITY_QUERY']==0\n    assert effective['LSQ_REPORT_RECOVERY_PREQUALIFY']==effective['LSQ_ALLOC_FIRE_DISTRIBUTE']==effective['ROB_RECOVERY_ROW_LIVE_QUALIFY']==1")
    marker="    active_path=ROOT/'build/cpu2026/active_frequency_implementation_20261004.json'"
    text=once(text,marker,"    old_a99=Path('F:/CPU2026CourseRuns/ER1_A99_tier3_20261006')\n    assert not live(read(old_a99/'dispatch_identity.json')['process_id'])\n    assert read(old_a99/'serial_phase_identity.json')['status']=='SERIAL_TIMING_COMPLETE_PERFORMANCE_DEFERRED'\n"+marker)
    marker='        performance_only_after_fmax_above300_and_total_area_at_most36000=True,'
    text=once(text,marker,marker+"\n        intermediate_a102_signed_age_assumption_superseded_by_a103=True,\n        closing_coverage_plan=goal['closing_coverage_plan'],closing_coverage_plan_sha256=goal['closing_coverage_plan_sha256'],")
    target.write_text(text,encoding='utf-8')
    print(dict(manager=str(target),manager_sha256=sha(target),source_manager_sha256=sha(source),tests_started=False))


if __name__=='__main__':
    main()
