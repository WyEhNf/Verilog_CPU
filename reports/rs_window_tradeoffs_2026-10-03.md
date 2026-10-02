# RS容量与同源码IPC权衡

当前目标仍要求同一整机同时满足全部SRAM计价面积≤36000 µm²、六项IPC几何平均≥1.0985、含SRAM频率≥300 MHz。下列实验只测正确性和IPC，没有新面积/频率成绩。

保持四发射、ROB64、PRF64、LSQ16、I128/D1024两路及当前全部控制/数据布局参数，仅改变RS_ENTRIES。测量采用原官方sim.cpp，只添加只读退休数打印；256MiB共享32-bit AXI4-Lite内存，20周期/word，MMIO在B握手退出。六项程序仍为median、multiply、qsort、rsort、towers、vvadd，Pi保持冻结。

| RS项数 | 29项正确性 | 六项IPC几何平均 | 六项总周期 | 六项退休数 | IPC门槛 |
|---|---|---:|---:|---:|---|
| 16 | 全通过 | 1.1213155347352615 | 372783 | 472599 | 通过 |
| 8 | 全通过 | 1.066078323919282 | 389317 | 472599 | 未通过 |
| 12 | 全通过 | 1.1232643380242247 | 369979 | 472599 | 通过 |

RS16→8使IPC下降4.9261%，超过当前配置约2.03%的余量，因此不选择RS8作为当前达标配置。RS16→12的IPC提高0.1738%，总周期减少2804、退休数不变，全部29项正确性通过；下一轮整机面积与频率优先测量RS12。容量缩小不能代替完整面积计价，也不把预计节省面积记成实测收益。

| 程序 | RS16周期 | RS8周期 | RS12周期 | RS16 IPC | RS8 IPC | RS12 IPC |
|---|---:|---:|---:|---:|---:|---:|
| median | 10166 | 10437 | 10167 | 0.694669 | 0.676631 | 0.694600 |
| multiply | 11871 | 12052 | 11931 | 2.328111 | 2.293146 | 2.316403 |
| qsort | 157540 | 160994 | 158408 | 0.886162 | 0.867150 | 0.881306 |
| rsort | 184317 | 196170 | 180587 | 1.573192 | 1.478136 | 1.605686 |
| towers | 4929 | 5019 | 4926 | 0.771556 | 0.757721 | 0.772026 |
| vvadd | 3960 | 4645 | 3960 | 1.142677 | 0.974166 | 1.142677 |

严格机器核验分别位于 `F:/CPU2026Integration/parallel_select_20261002/rs8_tradeoff_audit.json` 与 `rs12_tradeoff_audit.json`，工具为 `tools/compare_course_window_tradeoff.py`。所有43个编译来源、完整官方驱动、观察驱动、可执行文件、程序映像和内存约定逐项核验；两组各29项退出码和退休数全部相同，IPC逐程序独立重算，六项几何平均重新计算。

原始override表除了RS_ENTRIES，还显示COMPLETION_BYPASS从未显式指定变为0；核验器从同一冻结student_top源码提取全部参数默认值，确认原默认本来就是0。有效配置恰好只有RS_ENTRIES一个变化，不把override文本差异误称为额外硬件改动，也不忽略未经核实的默认值。

RS8输出：`F:/CPU2026Integration/r64p64rs8lsq16_cdbmode0_robr1w1_dc2i1m1_rswake1_ratread1_action1_20261002rs8tradeoff`。

RS12输出：`F:/CPU2026Integration/r64p64rs12lsq16_cdbmode0_robr1w1_dc2i1m1_rswake1_ratread1_action1_20261003rs12tradeoff`。

当前RS16完整整机综合继续运行，主树43个编译输入保持不变。RS静态分配与PRF并行读在独立源码目录接入，RS12完整原生构建和29项测试已全部通过；实际RS12静态分配完整模块等价证明10380点全部通过，冻结输入再次核验。独立核验 `F:/CPU2026Integration/parallel_select_20261002/staged_rs12_native_audit.json` 确认全部29项周期、退休数、退出码与RS12基线完全相同，IPC仍为1.1232643380242247；记录恰好五个RTL变化和两个新增开关，其它有效参数及原驱动、程序映像、内存约定一致。

独立接入源码：`F:/CPU2026Candidates/static_datapath_integration_20261003`；全部43个编译输入由staging_manifest逐项记录，正式CPU构建另保存实际RS12参数，源码未被年龄比较缓存原型覆盖。完整CPU输出将位于 `F:/CPU2026Integration/r64p64rs12lsq16_static_datapath_20261003staged1`。主树后续采用此实现时，必须逐字匹配这份实际测试和测量的源码。

同一build的全CPU面积与时序流程已启动，使用原五库/defaultABC/全SRAM。首次启动在RTL综合前因隔离目录没有官方框架Git元数据而失败；通过真实本地克隆及固定提交54fc150ffc290f52aa024209ffb9a29d43856f6d的detached checkout修复，Git工作区干净。43个编译输入及149个评测依赖逐字哈希验证保持不变，旧目录与失败日志保留，证据在独立源码的 `framework_checkout_repair.json`。重试输出为整机目录下 `area_v2`，已完成elaborate、进入prepare；面积及频率尚无新结果。
