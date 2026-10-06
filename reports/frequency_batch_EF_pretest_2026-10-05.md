# EF 完整组合与测试前汇报

EF 已实现并冻结，**尚未运行 EF 编译、仿真、综合或 STA**。本报告先明确完整范围；实际测试启动前再在对话中汇报。下一步仅做一次 Windows 原生课程综合/STA，测频率与含 SRAM 面积。ED、EE、ROB 单项均不分别测；不构建 Verilator，不跑 IPC 或功能程序。

## 实测参考与改动理由

EA 刚完成 328.205128 MHz、最低周期 3.046875 ns、总面积 49,279.056294 μm²。比 DM1 频率 +8.6218%、面积 -3.6213%；相对最初基线面积 +6.4120%，回到 ±10% 以内。EA 的 IPC/功能尚未测，Tier3 36,000 / 1.0985 尚未满足或证明。EF 的所有指标均未知，不能继承 EA 的测量结论。

EA 五条最慢路径约 2.986 ns，都明确经过 LSQ 报告 → ROB 正常 valid/generation 检查 → completion/PRF 旁路 → 第 2 发射槽的分配 store 加法器。PRF 输出 2.3777 ns，分配加法器 sum[30] 2.8773 ns，端点 2.9859 ns，PRF 后仍有约 0.6082 ns 的加法/写后缀。最大单门只有 0.1102 ns，因此下一步应切断串行阶段联系、消除编码再解码，继续给单门加缓冲不足以解决它。

## 四类新改动，继承 EA 其余优化

|改动|实现|周期、状态与代价|
|---|---|---|
|取消分配当拍提前 store 地址|新增默认开启的 backend 参数，CPU 候选置零；分配 valid 和地址 payload 都固定零，删除四个可选分配加法器及 PRF 到它们的联系|零新增状态，普通流水线保持 10 级。共享早期探测与普通 AGU 保留。已知基址 store 地址会晚于分配边沿可用；共享探测每拍最多一个，多 store 竞争时不能承诺只多一拍或 IPC 损失上界|
|LSQ 报告直接循环一位选择|先选首个未 wrap 的 eligible 行，若不存在则首个 eligible 行，直接门控原完整报告；原二进制 winner 仍供 metadata 使用|原 oldest 顺序、完整 tag、normal ROB 身份检查、报告握手不变；不新增寄存器/周期。省去宽报告路径上的锦标赛行号编码再解码|
|LSQ 转发暂存读写分组|原 4 mask + 32 data 的 36 个未复位 payload 位由既有 word-bank 同边沿写入；写及 saved/live 读选择分成 16/16/4 位|同一 write、data、valid/reset/recovery/回压逻辑。旧映射写叶 72 个 mux 输入连接，分组目标最多 16 个数据 mux（通常两个输入控制引脚）；实际映射待测|
|ROB 提交读银行包分组|相同 row_select 和相同字段顺序，经 PRIORITY=0 的既有分组选择器逐位 OR；银行旋转保持原式|当前包宽 197 位，叶服务最多 16 位。没有新增状态、提交周期或提交权限。逐位 masked OR 对多个选择位同时为 1 也保持原结果，不依赖 one-hot 假设|

与 EA 不同的四个 RTL 文件为 backend joint、CPU core、LSQ、ROB。EF 继承 EA 的全核负极性分发、请求 owner、LSQ 正常 ROB 查询预解码、共享 signed-12 AGU、RAT 恢复分组和 Icache 分组；分配 signed-12 加法器在 CPU 配置中被删除。按脚本保留的实现组记录共 12 组，非 12 次单项测量。

## 已有报告的补充检查及未采用方向

只读取 EA 已生成的映射 JSON，没有新增 STA。顶层 cell 404,724，至少 32 个输入连接的驱动 bit 2,130。181 负载 INV 输入确认为 reset bit 3，课程 case_analysis reset=0，此处不据负载排名盲目加缓冲。86/82 负载私有 NOR2 的输入可追溯到 ROB head 分发，可达 commit/retire 边界；源码中的宽提交包消费者因此被分组。逻辑可达不等于精确布尔身份或关键时序证明。

157 负载 INV 仍有 AXI enabled_words 的公共别名，可达 ready/request/写生命周期等控制边界；它未出现在 EA 最慢五条中。尚不能将该等价私有网单独定位为安全可替换的源码表达式，故没有根据名字改协议或削减授权。若它成为下一实测瓶颈，再按实际路径定位。72 负载的 forwarding hold 写叶则有明确的 36 位源码消费者，本次已处理。

EB 零状态注册 RS probe 和 EC 79 位保存 probe packet 针对共享探测器。当前最慢路径明确位于分配加法器，所以没有把两者混入 EF。额外全核流水线、PRF 读端口减少/分银行、提前 wakeup、复制或缓存 ROB 授权，也需要额外周期、重发或完整同步规则；本次保留原普通 issue、CDB 和 normal generation 检查。

目前根据新路径和已保存负载数据，可直接论证的本批改动已组合完成；暂未找到另一个值得在本批继续实施、且能明确保持接口/权限的结构改动。若下一结果给出新限制锥，继续沿它设计。不是声称所有未来方案已被排除。

## 源码检查范围

EA → ED → EE → EF 的四个源码 manifest 已核对。69 个 begin/end 时钟块已比较：除 forwarding hold 的两条 payload 写搬到已有 word-bank 外，其余时钟方程文本保持；搬移的 36 位 data/write/edge/unreset 条件单独对应。ROB 状态不搬移。LSQ 直接选择的手工推导是 tournament 最小键 (wrap,row) 与“首个未 wrap，否则首个 eligible”相同，对二值控制不依赖队列状态假设。

上述仅源码/手工数据流审查，不是 HDL 接受、四态/所有参数形式等价、功能或实测收益证明。取消分配提前地址本身有意改变微架构地址可用时间；不能用时钟块文本相同来宣称全核周期行为相同。

## 下一次后台测量范围

命令：`python tools/start_frequency_course_background.py --run F:/CPU2026CourseRuns/architecture_EF_20261005 --timing-only`。只对完整 EF 调用一次原课程 synth（含其既有 ABC 映射和周期搜索），没有中间候选测试，没有 IPC/CPU 程序。等待期间继续源码研究，新候选另存。

环境为 Windows 原生；课程 framework `54fc150ffc290f52aa024209ffb9a29d43856f6d`，testcases `29f980727f7d99a1842a58f34091c7579ba3fe85`，固定原生 Yosys 0.63 / 课程 ABC / OpenSTA 3.1 / ASAP7 RVT TT / FakeRAM 保持。39 项 override 与 EA 一致，未改课程约束、库或面积算法，禁止 WSL。

本批通过删除整个关键加法后缀及报告 encode/decode 联系，结构规模足以对完整组合测一次。不能直接把 0.6082 ns 换算成新 MHz：PRF-to-RS 等保留路径或其他锥可能成为下一限制器。若频率达到有意义的更大提升且面积可接受，再先报告并复用同一综合结果测 IPC/必要功能。350 MHz 是昂贵第二阶段的工作判断值，原标准仍为频率至少 300 MHz、原面积/IPC ±10%，并最终 Tier3 36,000 / 1.0985。EF 没有任何已经满足这些指标的实测证据。

## 身份与恢复

- 当前 candidate：`F:\CPU2026Candidates\frequency_research_20261003\EF_rob_commit_packet_domains`
- Candidate manifest SHA256：`45496708335aa098bdd98369018330afc591bcbc1e4c48960438708a722d3a59`
- 冻结目录：`F:\CPU2026CourseRuns\architecture_EF_20261005`
- 冻结 manifest SHA256：`3e90b25b005f6e8fc5b2dd625e38603d349c2c2027b7eaecf3efd4093c0651f2`
- 工作区输入 40；冻结输入 157；课程 override 39。
- 源码检查：`F:\CPU2026Proofs\EF_source_review_20261005\source_review.json`
- 对 EA 的完整 patch：`F:\CPU2026Candidates\frequency_research_20261003\EF_rob_commit_packet_domains\changes_vs_measured_EA.patch`
- EA 实测报告：`E:/Verilog_cpu/reports/frequency_EA_measurement_2026-10-05.md`
- EA 映射路径：`F:/CPU2026Proofs/EA_mapped_paths_20261005/saved_path_analysis.json`
- EA 负载/逻辑锥：`F:/CPU2026Proofs/EA_mapped_load_census_20261005.json`、`F:/CPU2026Proofs/EA_high_load_cones_20261005/summary.json`
- 改动前 EA 工作区备份：`F:/CPU2026Candidates/pre_EF_worktree_20261005`。EA 原始完整结果及所有候选保留。
