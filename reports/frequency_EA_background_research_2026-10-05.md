# EA 后台测量期间的源码研究

EA 已作为八组完整组合冻结并后台测量。这里新增的 EB 仅为源码候选，不修改 EA 工作区或冻结输入，不启动另一轮测量。

EB 把 linked early-store probe 的 base ready/value 改为现有 RS 寄存器视图。普通发射仍用本周期 CDB 旁路，因此没有给正常整数路径增加周期或寄存器位。源级上可切断 CDB wake → store probe → 地址加法这条联系。

代价需要明确：如果 base 此周期刚被 CDB 唤醒，早期探测会推迟；若普通发射已消费此 store，则可能由原 ALU 地址更新路径先提供地址。这可能推迟 older-store 冲突释放，不能声称 IPC 不变。只有 EA 完成后仍显示该探测锥明显限制频率，才考虑采用，并在后续测试前先报告实际范围。

PRF 分银行、动态读端口与提前唤醒也已研究。动态端口需要结构冲突处理/重发；提前 ALU wakeup 需要保证回压条件下旁路数据按时可用。公开项目提供设计参考，不能直接证明本核换接口之后的周期或正确性。[BOOM register file/bypass](https://docs.boom-core.org/en/latest/sections/reg-file-bypass-network.html)，[BOOM issue/wakeup](https://docs.boom-core.org/en/latest/sections/issue-units.html)。

EB candidate：`F:\CPU2026Candidates\frequency_research_20261003\EB_ea_registered_store_probe`。源码检查：`F:\CPU2026Proofs\EB_source_review_20261005\source_review.json`。EA 工作区 40 项与冻结 157 项身份重新核对，保持不变。源码/时钟块文本检查不是 HDL 或功能验证。

## EC：保存选中操作数，再执行共享存储 AGU

EC 是与 EB 并列的 EA 源码备选，二者尚未组合或采用。EB 使用现有 RS 寄存视图，零新增状态，但会错过刚被 CDB 唤醒的早期探测。EC 保留现有同周期 CDB wake/issue，在选出完整 store packet 后加寄存边界，再进行地址加法和当前 ROB 身份检查。

当前 packet 保存 ROB tag 17 位、LSQ tag 17 位、base 32 位、S 型 offset 12 位，共 78 位，加 valid 1 位，共 79 个新增状态位。原通用立即数构想为 99 位；这里少保存 20 位，只依据 CPU decoder 的 signed-12 合同。通用独立配置仍保存 32 位。真实 FF 数量、缓冲和面积尚未综合。

选中 packet 在 RS 同边沿正常释放前捕获；发布时重新读当前 ROB valid/generation，LSQ 仍验证自身完整 generation。当前待发布 owner 按完整 LSQ tag 从下一轮 pending 中排除，减少重复选择。正常 ALU 地址更新和 store commit 授权保留。普通整数流水线仍 10 级，只有 opportunistic early-store probe 增加一拍，可能延迟旧 store 冲突释放。

EC 仅对“共享探测选择/旁路 → AGU → 发布”的组合链建立边界，不切断分配时的 PRF → store 加法器。因此不能凭旧 DM1 的疑似分配端点就声称 EC 会解决最慢路径。只有 EA 新路径明确指向共享探测锥，才比较 EB 与 EC 的代价后选择；测试前另报完整范围。此时没有启动 EC 编译、仿真、综合或 STA。

EC candidate：`F:\CPU2026Candidates\frequency_research_20261003\EC_ea_narrow_store_probe_packet`。源码检查：`F:\CPU2026Proofs\EC_source_review_20261005\source_review.json`。EA 工作区 40 项与冻结 157 项身份再次保持不变；全部既有 begin/end 时钟块文本保持，仅新增 valid 块和 packet word-bank 状态。检查不是 HDL 或功能证明。

## 分配当拍地址旁路：下一步的条件方案

EA backend 的 `g_backend_lane_io` 中，`rs_src1_value` 直接送四个分配 store 地址加法器，`lsq_alloc_addr_valid` 以 `rs_src1_ready` 为条件；LSQ 在分配时写入地址 payload 和 addr_ready。PRF 分配读取包含完成写回旁路。因此这里确实存在“完成授权/选择 → PRF 旁路 → 地址加法 → LSQ 分配写”的源码联系。旧 DM1 最慢路径的公共别名到 PRF port 6，末段可能对应分配加法，但此前并没有精确证明最终端点的字段；不能据此认定 EA 仍由它限制。

若 EA 新路径确认这一分配边界仍是限制器，可以增加默认开启的独立 `STORE_ALLOC_EARLY_ADDRESS` 参数，在 CPU 候选中关闭。关闭时令 `lsq_alloc_addr_valid=0`、`lsq_alloc_addr=0`，让综合裁去整个分配地址加法器及其下游数据联系；不只是令有效位为零而仍把宽地址写进 LSQ。共享早期地址探测保持开启，普通 ALU/AGU 的完整 LSQ tag 地址更新也保留，LSQ addr_ready 在实际地址更新前一直为零。

该方案现已另存为 ED 源码 candidate，没有改 EA，也没有启动测试。它声明零新增状态，普通流水线 10 级保持，但新分配的已知基址 store 不能在分配边沿就提供地址；单个共享探测器吞吐最多每拍一个，而分配宽度为四，故不能声称所有 store 都只多一拍，或 IPC 损失有确定上界。收益是切断完整组合链并删四个加法器，代价是旧 store 冲突释放可能更晚。普通取数/RS 分配路径仍存在，PRF 本身不会因这个选择消失。

下一批依据真实路径选择：分配地址链对应取消分配早期地址；共享探测链对应 EB 或 EC；请求资格共享大负载对应检查 EA owner 映射；若指向其他锥，则从新锥继续设计。当前所有备选均没有被当成实测收益，也不会各自启动一轮测试。

ED candidate：`F:\CPU2026Candidates\frequency_research_20261003\ED_ea_shared_only_store_address`。源码检查：`F:\CPU2026Proofs\ED_source_review_20261005\source_review.json`。其两个改动文件的既有 begin/end 时钟块及共享探测源文本与 EA 相同；默认参数为 1，CPU 候选显式置 0。仅源码检查，未测收益或 IPC。
