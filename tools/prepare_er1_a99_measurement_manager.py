"""Create a fresh, PPA-gated A95-A99 native course characterization manager."""
from manage_frozen_baseline_programs import ROOT, sha


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old,new)


def main():
    source = ROOT/'tools/manage_er1_a94_measurement.py'
    target = ROOT/'tools/manage_er1_a99_measurement.py'
    assert not target.exists()
    assert sha(source) == '3ccf5bd5c115ce9cec842b5962f890c765940308b0978533577280c7006e744d'
    text = source.read_text(encoding='utf-8')
    for old,new in [
        ('Windows A84-A94 characterization.','Windows A95-A99 PPA-gated characterization.'),
        ('from manage_er1_a83_measurement import check as check_a83','from manage_er1_a94_measurement import check as check_a94'),
        ("REFERENCE=Path('F:/CPU2026CourseRuns/ER1_A83_tier3_20261006')","REFERENCE=Path('F:/CPU2026CourseRuns/ER1_A94_tier3_20261006')"),
        ("CANDIDATE=Path('F:/CPU2026Candidates/tier3_er1_20261005/A94_localparam_dependency_order')","CANDIDATE=Path('F:/CPU2026Candidates/tier3_er1_20261005/A99_balanced_saved_identity')"),
        ("RUN=Path('F:/CPU2026CourseRuns/ER1_A94_tier3_20261006')","RUN=Path('F:/CPU2026CourseRuns/ER1_A99_tier3_20261006')"),
        ("REPORT=ROOT/'reports/ER1_A94_pretest_2026-10-06.md'","REPORT=ROOT/'reports/ER1_A99_pretest_2026-10-06.md'"),
        ('    check_a83()','    check_a94()'),
        ("terminal=read(ROOT/'build/cpu2026/er1_a83_complete_result_20261006.json')['metrics']","terminal=read(ROOT/'build/cpu2026/er1_a94_complete_result_20261006.json')['metrics']"),
        ("assert terminal['candidate']=='A83_fast_store_identity_preselect'","assert terminal['candidate']=='A94_localparam_dependency_order'"),
        ("previous=Path('F:/CPU2026Candidates/tier3_er1_20261005/A83_fast_store_identity_preselect')","previous=Path('F:/CPU2026Candidates/tier3_er1_20261005/A94_localparam_dependency_order')"),
        ('for number in range(84,95):','for number in range(95,100):'),
        ("        'FAST_STORE_WB_DATA'):","        'FAST_STORE_WB_DATA','FAST_STORE_CLASS_COMPARE','FAST_STORE_BATCH','RS_ELASTIC_SKIP_CAPACITY',\n        'LSQ_SAVED_IDENTITY_WORD_MASK','LSQ_SAVED_IDENTITY_BALANCED_MERGE'):"),
        ("status='A94_FROZEN_SERIAL_PRETEST_NOT_STARTED'","status='A99_FROZEN_PPA_GATED_PRETEST_NOT_STARTED'"),
        ("'PROGRESS_A84_A94_CORRECTED_CUMULATIVE_NATIVE_PRETEST_FROZEN'","'PROGRESS_A95_A99_A94_CYCLE_FREQUENCY_NATIVE_PRETEST_FROZEN'"),
        ("status='A94_SERIAL_CHARACTERIZATION_IN_PROGRESS'","status='A99_PPA_GATED_CHARACTERIZATION_IN_PROGRESS'"),
        ("'PROGRESS_A94_CORRECTED_CUMULATIVE_PRETEST_REPORTED_NATIVE_SERIAL_DISPATCH'","'PROGRESS_A99_PRETEST_REPORTED_PPA_GATED_NATIVE_SERIAL_DISPATCH'"),
    ]:
        text = once(text,old,new)
    text = text.replace('a83_reference.json','a94_reference.json')
    begin = text.index('PREPARERS={')
    end = text.index('\n\n',begin)
    text = text[:begin]+'''PREPARERS={
    95:'prepare_er1_store_class_compare.py',
    96:'prepare_er1_fast_store_batch.py',
    97:'prepare_er1_rs_elastic_skip_capacity.py',
    98:'prepare_er1_saved_identity_word_mask.py',
    99:'prepare_er1_balanced_saved_identity.py',
}'''+text[end:]
    begin = text.index('    for proof_name in [')
    end = text.index("        p=ROOT/'build/cpu2026'/proof_name",begin)
    text = text[:begin]+'''    for proof_name in ['er1_a94_complete_result_20261006.json',
        'er1_a95_background_progress_20261006.json',
        'er1_a96_background_progress_20261006.json',
        'er1_a94_ppa_a97_a98_progress_20261006.json',
        'er1_a99_source_progress_20261006.json']:
'''+text[end:]
    text = once(text,"    tool_paths=[Path(config[key])", "    assert effective['FAST_STORE_BATCH']==0 and effective['RS_ELASTIC_SKIP_CAPACITY']==1\n    assert effective['LSQ_SAVED_IDENTITY_WORD_MASK']==effective['LSQ_SAVED_IDENTITY_BALANCED_MERGE']==1\n    tool_paths=[Path(config[key])")
    text = once(text,'new_synth_runs_planned=1,perf_max_cycles=1000000,',
        'new_synth_runs_planned=1,perf_max_cycles=1000000,\n        performance_only_after_fmax_above300_and_total_area_at_most36000=True,')
    text = once(text,"        measurement_pretest_report=str(REPORT),measurement_pretest_report_sha256=sha(REPORT),",
        "        candidate_ipc=None,candidate_fmax_mhz=None,candidate_area_um2=None,\n        active_measurement_partial_ppa=None,measurement_last_observation=None,\n        measurement_pretest_report=str(REPORT),measurement_pretest_report_sha256=sha(REPORT),")
    text = once(text,"            record.update(status='SERIAL_PERFORMANCE_IN_PROGRESS',timing_report_sha256=sha(RUN/'result/timing_only.json'))",'''            if not (timing['fmax_mhz']>300 and timing['area_um2']<=36000):
                record.update(status='SERIAL_TIMING_COMPLETE_PERFORMANCE_DEFERRED',
                    timing_report_sha256=sha(RUN/'result/timing_only.json'),
                    performance_deferred_reason='Measured frequency/area gate did not pass; preserve source evidence without an unnecessary CPU build or performance simulation.',
                    fmax_mhz=timing['fmax_mhz'],area_um2=timing['area_um2'])
                write(RUN/'serial_phase_identity.json',record)
                print('DONE SERIAL timing; performance deferred by measured PPA gate',flush=True)
                return
            record.update(status='SERIAL_PERFORMANCE_IN_PROGRESS',timing_report_sha256=sha(RUN/'result/timing_only.json'))''')
    begin = text.index("    REPORT.write_text(f'''")
    end = text.index('    assert effective[',begin)
    report = """    REPORT.write_text(f'''# A99：保持 A94 周期行为的频率批次，测量前汇报

目标仍为Fmax严格>300MHz、课程六性能IPC几何平均≥1.1、含SRAM总面积≤36000μm²；完整RV32IM、OoO、顺序提交、MMIO和参数化保留。

## 参考与改动

原A94监督PID84416已结束，timing/performance返回0/0，完整身份及原课程程序已核对。参考IPC{original['ipc']:.9f}、Fmax{original['fmax_mhz']:.6f}MHz、总面积{original['area_um2']:.6f}μm²；六性能答案通过、19正确性未跑。周期3.4453125ns，需要缩短超过111.979167ps；面积余量201.027322μm²。A99未测，不能借用参考指标。

| 源码修改 | 作用与状态 |
|---|---|
| A95 | 用原低12位carry与高位prefix精确推导保存地址RAM类别，保留原sum/实际地址/对齐和WB优先级。 |
| A96 | 可选并行快存储功能保留；本次课程profile关闭FAST_STORE_BATCH，保持A94单身份和至多一条快存储，控制组合面积。 |
| A97 | 保存D需求与free+k提前计算，晚load/store跳过资格只选布尔容量，保持原实际RS需求、原子admit与信用。 |
| A98 | 保存报告grant分布到最多16位一组；每位仍为原grant & identity。 |
| A99 | 保留每个二叉OR为独立组合层，原每节点left|right、所有query/包/填充位保持。 |

无新增声明FF、SRAM、流水边沿或端口容量，FE4/BE2/整数2/CDB2、ROB32/PRF56/RS8/LSQ16/BTB16、缓存/预测表与完整GEN位数不改。这些布尔重写预计二值输入下周期行为与A94相同，但新IPC及完整正确性仍需实测。

## 可观收益依据和剩余风险

A94关键路径：LSQ边界/held资格0.6385ns→hold分布0.7101ns→saved身份query1.593ns→ROB live1.811ns→完成选择2.185ns→分配控制约3.004ns→GEN3.247ns→FF3.385ns。报告相关_223268_为61负载/30.94fF，单门373.5ps，后继INV167.7ps；后段另有40负载NAND耗220.5ps。当前周期只需减少约112ps。

A98限制报告grant叶掩码负载；A99阻止原名义4层OR被跨层因式合成为约十级交替AOI/OAI；A97同时移走晚ready后计数/减法/容量比较。三项覆盖同链不同串行因素，有依据支持一次集中PPA判断。门到源变量的部分归属为推断，不能把单门耗时直接相加当预测节省。额外缓冲、OR层、映射变化及新瓶颈可能使面积/频率不达标；201μm²余量很小。

源码推导逐项核对原mask/OR递推、query位域、包格式、held/head/grant优先级、GEN/取消/恢复、实际fire/信用以及保存地址carry/sign/RAM分类。仅源码阅读、哈希与既有证据；本报告生成时未运行HDL/lint/形式/仿真/综合/STA/单元测试。

额外流水沿会改变同周期唤醒和原子入队，当前IPC余量仅1.37%；扩容和更复杂预测器没有当前性能瓶颈证据且面积受限。第三份held/normal ROB资格会复制GEN/live逻辑，在已有掩码/OR负载问题尚未判断前净收益依据较弱。当前已完成能直接支撑收益的同路径修改，之后继续以新结果探索其他路径，不把这批当穷尽长期方案。

## 集中测量规范

新任务目录{RUN}；冻结{len(names)}文件，{len(dependencies)}课程依赖逐字匹配成功A94。Windows原生、无WSL，框架54fc150ffc290f52aa024209ffb9a29d43856f6d，测试29f980727f7d99a1842a58f34091c7579ba3fe85，Yosys0.63/ABC/OpenSTA3.1/Verilator5.020，原ASAP7 RVT TT/FakeRAM、latency10、clock2ns映射和原I/O/uncertainty/load不改。

对话汇报后只启动一次综合/STA。只有实测Fmax>300MHz且含SRAM面积≤36000μm²，才复用同一PPA、同manifest/config工具，构建一次原课程CPU并运行六项perf（各1000000周期、原分子/答案/几何平均）。PPA不达标则终止该批并记录，无CPU构建/性能仿真、无自动重试，不借用A94IPC。数值三目标改善确认后，采用前集中验证完整19正确性及M/GEN/恢复/MMIO/参数覆盖。

旧成功生成器/管理器/证明/报告、A94结果和测量源保持冻结。A99每一步源码审阅与准备脚本、五份源进度证据、全部依赖及本管理器哈希绑定。主E EU40源保持，无采用。

候选SHA256：{sha(CANDIDATE/'candidate.json')}

源manifest SHA256：{sha(RUN/'source_manifest.json')}
''',encoding='utf-8')
"""
    text = text[:begin]+report+text[end:]
    text = once(text,"ROOT/'tools/verilator_windows_time_zero.cpp',Path(__file__)]",
        "ROOT/'tools/verilator_windows_time_zero.cpp',ROOT/'tools/prepare_er1_a99_measurement_manager.py',Path(__file__)]")
    assert 'check_a83' not in text and 'a83_reference' not in text
    target.write_text(text,encoding='utf-8')
    print(dict(manager=str(target),manager_sha256=sha(target),source_manager_sha256=sha(source),tests_started=False))


if __name__ == '__main__':
    main()
