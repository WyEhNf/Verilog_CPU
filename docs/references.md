# 面积优化与乱序设计参考论文及资源清单

> 说明：外部论文 PDF 即使下载到本机也属于只读研究资料，由 `.gitignore` 排除；仓库只
> 提交本清单和由实现、综合结果验证过的结论。

## 第一梯队：经典乱序微架构（最权威，教科书级）

- **Alpha 21264 微处理器架构**（原题：The Alpha 21264 Microprocessor Architecture；R. E. Kessler, IEEE Micro 1999）
  - 现代乱序核的事实标准：统一物理寄存器文件 + 重命名 + 空闲列表 + 乱序执行 + 存储队列。
  - 你要的 PRF、空闲列表、重命名和精确异常结构，这篇全讲透。
  - 开放 PDF：https://www.cs.tufts.edu/comp/150PAT/arch/alpha/ev6chip.pdf

- **MIPS R10000**（K. C. Yeager, IEEE Micro 1996）
  - 你建议里“R10K + 不保存操作数数据的 RS”的来源：发射时 RS 只存标记和就绪状态，操作数后读；按序提交 + 精确异常。
  - 讲义（开放 PDF）：https://pages.cs.wisc.edu/~karu/courses/cs752/fall2016/project/pdf/Handout36.pdf

- **BOOM v2：开源乱序 RISC-V 核**（原题：BOOM v2: An Open-Source Out-of-Order RISC-V Core；Celio 等，Berkeley EECS-2017-157）
  - 开源乱序 RISC-V 标杆，PRF、重命名、空闲列表、ROB、RS、SQ 全有对应实现。
  - PDF：https://www2.eecs.berkeley.edu/Pubs/TechRpts/2017/EECS-2017-157.pdf
  - 源码：https://github.com/riscv-boom/riscv-boom

## 第二梯队：面积/能耗导向的乱序优化（顶会 ISCA/MICRO）

- **加载切片核微架构**（原题：The Load Slice Core Microarchitecture；Carlson, Heirman, Allam, Kaxiras, Eeckhout; MICRO 2015）
  - “用更小面积获得乱序执行的访存级并行性（MLP）”：大部分指令走顺序执行切片，只有缓存未命中的依赖链进入乱序执行。**面积/能效最优化的代表工作**。
  - https://ieeexplore.ieee.org/document/7284072（IEEE 付费，可在作者页/谷歌学术找开放版）

- **NoSQ：无需存储队列的存储到加载通信**（原题：NoSQ: Store-Load Communication without a Store Queue；Sha, Martin, Roth; IEEE Micro 2007）
  - 直接对应你“干掉高消耗 CAM / NLQ / Store-Set”的建议：不用存储队列也能做存储到加载通信。
  - https://doi.org/10.1109/MM.2007.17（IEEE Micro 付费）

- **通过存储队列索引预测实现可扩展的存储到加载转发**（原题：Scalable Store-Load Forwarding via Store Queue Index Prediction；Sha, Martin, Roth; MICRO 2005）
  - 上面的前作，提高存储队列匹配的可扩展性。
  - https://www.semanticscholar.org/paper/31d03f85dc8e10eec9a47fe502afc821c1959b3d

- **访存依赖预测**（原题：Memory Dependence Prediction；Moshovos 等，ISCA 1997）
  - 存储到加载依赖预测的开山之作（可选读）。

- **SonicBOOM：第三代伯克利乱序处理器**（原题：SonicBOOM: The 3rd Generation Berkeley Out-of-Order Machine；HOT CHIPS / CARRV 2020）
  - 不保存操作数数据的 RS（发射后再读 PRF）的落地实现。
  - 幻灯片：https://carrv.github.io/2020/slides/CARRV2020_slides_15_Zhao.pdf

## 技术 → 论文映射

| 你的建议 | 权威论文 |
|---|---|
| 不保存操作数数据的 RS / 发射后读 PRF | MIPS R10000、SonicBOOM |
| PRF / 空闲列表 / 重命名 | Alpha 21264、BOOM v2 |
| NoSQ / Store-Set 省 CAM | NoSQ (IEEE Micro 2007)、Sha MICRO 2005 |
| 单套 RAT + 撤销日志 / 精确恢复 | R10000、Alpha 21264（检查点/撤销） |
| 面积/能耗高效的乱序执行 | Load Slice Core (MICRO 2015) |

## 备注

- 顶会论文（MICRO/ISCA）的正式 PDF 多为 IEEE/ACM 付费墙；校园网或作者主页通常有开放版，也可用 Google Scholar 的 "[PDF]" 直达。
- 建议优先精读 **Alpha 21264**（结构）和 **Load Slice Core**（面积思想），再按你想压的模块读 NoSQ / R10000。
