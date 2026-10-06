# EP 完整组合：测试前汇报

源码已实现、完成源文件/握手审查、备份并冻结。**本报告落盘时尚未运行 EP 编译、仿真、综合、STA 或功能/IPC 程序。** 先在对话汇报本报告，再只对完整组合做一次 Windows 原生课程 timing-only。EN1、EO1、EP 没有分项测试。

## 已测参考与当前未知指标

|版本|课程 Fmax|最低周期|含 SRAM 总面积|IPC/功能|
|---|---:|---:|---:|---|
|历史 EF|370.477569 MHz|2.69921875 ns|49,116.955854 μm²|未测|
|上一主版本 EL1|266.875163 MHz|3.7470703125 ns|49,613.040354 μm²|未测|
|本轮 EP|未知|未知|未知|未测|

EL1 相比 EF 频率下降27.9646%、面积增加1.0100%；没有用历史 EF 频率代替 EL1，也不能把回归归因到某个未经单项测量的改动。EL1 总面积相对原46,309.693490基线 +7.1332%，在 ±10% 内，但 Tier3 的36,000面积目标仍未达到。上述指标全部只属于各自冻结版本。EP 的现时指标重置为未知。

## 三处新增优化及实际路径依据

|改动|要消除的限制|行为与代价|
|---|---|---|
|EN1：MMIO 最终消费者分域、只保留有效低32位，屏蔽上96位|EL1 五条最慢路径都穿过165输入负载 NOR4（1.1544ns）及47负载 INV（0.7405ns）；两个门占约1.895ns。当前缓存常规 mask=ffff/0000，退出请求=000f，bridge enabled_words bit0 与 MMIO选择等价；不能把公共别名误当仅属于bridge计数|原 MMIO valid/store/address80000000/mask000f 检测、ack时钟、地址/掩码/ID/低32数据/握手均保留。17个最终控制域，每个数据叶最多16位。MMIO上96位固定0，普通请求完整128位；原桥只有非零word mask发AW/W，所以上96位不参与任何退出AXI写，并保证MMIO回压时整个请求稳定。零新状态/周期；被屏蔽原始位有意不同|
|EO1：复用已有完整缓存回复寄存器，关闭当前CPU load-hit直通|历史 EF 第2–5条明确经过 response_output_tree bit0=bypass_load_hit；切断 MSHR响应仲裁→命中输出选择→LSQ行匹配/字节提取整条跨模块组合链|新增默认1的 HIT_BYPASS 参数，CPU设0；原 hit捕获条件、数据/metadata owners、响应槽回压、reset、miss/waiter仲裁、store-ack直通均保留。首次空槽hit返回有意多一拍，IPC未知；没有新增寄存器状态，普通整数流水线仍10级|
|EP：LSQ选择暂存字段按最多16位统一写入|EL1路径末尾 selection_write_tree 的地址叶控制32位hold mux、64输入负载、0.1189ns；原slot+两tag叶共38位|同一 selection_input_fire、同一posedge、同一完整输入字段，移到已有word-bank。当前110位、7叶；完整LSQ/ROB tag/generation不缩短。valid/flush/recovery/kill/done/转发hold时序保留，无LSQ新增周期。零新增声明状态不代表映射重复位合并或时序面积必然相同|

继承EL1的选择前并行store分配地址、既有RS寄存器共享probe、LSQ直接响应选行/偏移预解码/完整tag比较域、每MSHR地址先比较，以及EF之前的控制局部化。累计19组，相对EL1仅 LSQ、Dcache、CPU core 三个RTL文件变化；39项课程override和顶层队列/宽度/cache配置、库/工具/面积算法/约束均不改。

## 源码审查范围

候选41个输入、工作区40个输入、冻结157个输入均核对SHA256，EL1测量及备份保留。68个复合时钟块文本相同；1块只移除原payload写入，剩余valid/恢复逻辑文本相同。word-bank单语句时钟写另行核对相同边沿、写条件、字段宽度/顺序、hold和无reset行为。未使用HDL编译器、仿真器、综合、STA或形式工具；源码推理不是功能证明。

缓存首次hit延迟会变，不能因原resp_valid_reg语句文本相同就声称周期等价；后续必要IPC与功能测量必须对应EP完全相同冻结身份。MMIO上96原始位不同，只声称有效字节/AXI事务和完整请求稳定性保持。

## 已评估但不加入本批的方向

- EM共享store选择前ROB查询预解码已实现为单独备选；当前EL1最慢路径不支持扩大这条query包，保留不测。
- 逐MSHR响应类型先分类再选择可能缩短仲裁，但EO1已将其已证跨模块消费者移到原寄存器边界，先不追加重复逻辑。
- EH把全部load/MDU wake延后会影响普通依赖发射；既有EI仅调整共享probe。全CDB、完整probe/cache包再加级需额外状态、tag/valid对齐和恢复规则。
- PRF银行/动态端口、缩窗口/issue/CDB宽度、依赖队列、推测提前wake均涉及IPC、仲裁/重发/恢复；当前实际主路径不证明它们应混入本批。绝不删除正常ROB/LSQ权限检查。
- 普通ALU继续加级无法自动消除MMIO控制和缓存→LSQ组合链。全设计按负载排行加缓冲也可能扩大area或形成新的汇合宽控制；只改路径有证据的消费者。

上述取舍依据实际报告和源行为；BOOM [Issue Unit](https://docs.boom-core.org/en/latest/sections/issue-units.html)、[Register Files](https://docs.boom-core.org/en/latest/sections/reg-file-bypass-network.html)及[Palacharla等论文](https://ftp.cs.wisc.edu/sohi/papers/1997/isca.complexity.pdf)提供wake/端口/旁路复杂度背景，不是本CPU定量频率预测。

本轮已完成三个有实际路径依据的结构变化，暂未找到更多依据充分、适合继续加入这一组合的方案，达到一次整体测量的条件。不声称以后不会出现新主路径，也不把旧门延迟相减直接预测MHz。

## 唯一测量及后续条件

对话先汇报后调用 `tools/start_frequency_course_background.py --run F:/CPU2026CourseRuns/architecture_EP_20261005 --timing-only`。一次完整课程synth/ABC/OpenSTA周期搜索与面积计算；无子项测量、无CPU构建、无IPC/功能程序。后台测量期间继续源码研究，新备选另存，冻结输入不改。

全程Windows原生、禁止WSL。framework `54fc150ffc290f52aa024209ffb9a29d43856f6d`、testcases `29f980727f7d99a1842a58f34091c7579ba3fe85`，Yosys0.63/课程ABC/OpenSTA3.1/ASAP7 RVT TT/FakeRAM，latency10、原2ns映射约束及原输入输出/uncertainty保持。测得最低可行周期才给Fmax，2ns负slack不是300MHz未达标判据。

频率是本阶段主任务；原面积上限50,940.662839 μm²、IPC下限0.882115146585仍需控制，当前IPC未知。Tier3最终需area≤36,000含SRAM、IPC≥1.0985、Fmax≥300。350MHz只保留为昂贵IPC阶段工作门槛，不替代完整目标；有足够频率收益、面积可控后另行先报告必要IPC/功能阶段。不能以历史IPC或仅过300宣布整个目标完成。

## 冻结身份

- 候选：`F:\CPU2026Candidates\frequency_research_20261003\EP_lsq_selection_payload_word_owners`
- 候选manifest SHA256：`009b8aece4428210a0162c6e0866a814b9d8e58951e2cda8d7e0a56bd1f4a6f1`
- 冻结目录：`F:\CPU2026CourseRuns\architecture_EP_20261005`
- 冻结manifest SHA256：`2aaa5d09501f2d59dbdceb7a4d446c2312ba174dfb15f205f11457954e7a879c`
- EP源码审查：`F:\CPU2026Proofs\EP_source_review_20261005\source_review.json`
- EO1握手审查：`F:\CPU2026Proofs\EO1_source_review_20261005\source_review.json`
- 完整对EL1改动：`F:\CPU2026Proofs\EP_source_review_20261005\changes_vs_measured_EL1.patch`
- 原EL1工作区备份：`F:/CPU2026Candidates/pre_EP_worktree_20261005`
