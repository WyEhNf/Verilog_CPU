# A110：先比较两份物理身份，再选择匹配结果

原A109独立课程运行源/157文件manifest/工具/脚本/报告已冻结检查，原PID103132当前观察附于JSON；未改源、未重启、未并行新测试。A110为独立41文件源候选，五文件改变，三项指标未知。

等待期间，继续对真实RS wake源码与BOOM原始文档核对。BOOM将ALU早唤醒和load/变延迟writeback唤醒分开，bypass位于register-read末端：[Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)、[Register Files and Bypass Network](https://docs.boom-core.org/en/latest/sections/reg-file-bypass-network.html)。这是架构思路，不能作为本CPU频率证据。

本设计原RS_DIRECT_WAKE已经把四rawproducer和独立cache-return送到RS；COMPLETION的source3 data72只是与LSQ public phys4和RS tagtree26共享的原载荷别名，不能据它的名称声称串行经过CDB仲裁。原路径的后续signal_i21是LSQ物理tag valid位（PAW6+valid1，column3从21开始），物理地址字段先晚mux，再执行phys!=0&&phys<56，随后RS等值比较与issue。因此早先CDB-tag选择后比较的表述被这次源级核对替代，数字/原节点证据不改。

A110导出原head_packet_metadata及saved_identity_tree中两份原物理地址，不新增存储/read port；backend分别执行原phys!=0&&phys<PHYS_REGS编码。各RS行的两个操作数分别提前比较这两份完整物理身份，再由同一个原head选择bool选匹配结果，仍与原实际local wake_valid相与。对任意h和tag：match(h?head:saved,t)=h?match(head,t):match(saved,t)，包含原tagvalid、src_tagvalid和range编码。公开报告packet不变，saved候选仍含原held选择，完整ROB/LSQGEN、unretired/localcancel/currentvalid实际门槛不改；无早唤醒/猜测事件。

只替换原LSQ rawproducer列的match，其他ALU/MDU/cache-return/legacyCDB列保留。原match向量逐bit等值，所以first/last duplicate priority、组合值旁路/时序捕获、issue选择/age矩阵、recover/kill/allocate和所有RS状态后缀逐字保持。默认flag0；实际启用还要求原headidentity、headpacket、directphysicalwake、parallelwakemux，其他配置保留原selectedtag比较。按四行域分布两份身份和原headbool，减少晚head值mux→物理valid编码→等值比较的串行深度。

RS8/两操作数使候选比较多16份，原selected-column比较和部分tag分发可能裁掉，但面积不保证减少；原wake_valid/值路由/issue链可能接替瓶颈。新增FF/SRAM/流水边沿0，目标窗口/cache/GEN/ISA/OoO/commit/MMIO/参数化不缩。未运行HDL/lint/形式/仿真/综合/STA/单元测试或CPU构建，不能借A94/A109指标。主E40源保持原状态。

先完成原A109同一个运行；按其原PPA/IPC/新路径判断是否需要A110或进一步结构工作。若A109三项达到目标，集中同CPU19课程+4冻结边界及参数/架构审阅后采用；若未达到，以实际数据组成下一批，先汇报再测，不能因为准备了A110就自动派发测试。
