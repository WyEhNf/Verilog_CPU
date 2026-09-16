# 参考论文与资源清单（Area Optimization / OoO Design References）

> 说明：外部论文 PDF 即使下载到本机也属于只读研究资料，由 `.gitignore` 排除；仓库只
> 提交本清单和由实现、综合结果验证过的结论。

## 第一梯队：经典 OoO 微架构（最权威，教科书级）

- **The Alpha 21264 Microprocessor Architecture**（R. E. Kessler, IEEE Micro 1999）
  - 现代乱序核的事实标准：统一物理寄存器文件 + 重命名 + free list + 乱序执行 + store queue。
  - 你要的 PRF/free-list/rename/精确异常结构，这篇全讲透。
  - 开放 PDF：https://www.cs.tufts.edu/comp/150PAT/arch/alpha/ev6chip.pdf

- **MIPS R10000**（K. C. Yeager, IEEE Micro 1996）
  - 你建议里"R10K + Data-less RS"的来源：发射时 RS 只存 tag/ready，操作数后读；按序提交 + 精确异常。
  - 讲义（开放 PDF）：https://pages.cs.wisc.edu/~karu/courses/cs752/fall2016/project/pdf/Handout36.pdf

- **BOOM v2: An Open-Source Out-of-Order RISC-V Core**（Celio et al., Berkeley EECS-2017-157）
  - 开源 OoO RISC-V 标杆，PRF/rename/free-list/ROB/RS/SQ 全有对应实现。
  - PDF：https://www2.eecs.berkeley.edu/Pubs/TechRpts/2017/EECS-2017-157.pdf
  - 源码：https://github.com/riscv-boom/riscv-boom

## 第二梯队：面积/能耗导向的 OoO 优化（顶会 ISCA/MICRO）

- **The Load Slice Core Microarchitecture**（Carlson, Heirman, Allam, Kaxiras, Eeckhout; MICRO 2015）
  - "用更小面积拿到 OoO 的 MLP"：大部分指令走顺序 slice，只有 miss 依赖链进 OoO。**面积/能效最优化的代表工作**。
  - https://ieeexplore.ieee.org/document/7284072（IEEE 付费，可在作者页/谷歌学术找开放版）

- **NoSQ: Store-Load Communication without a Store Queue**（Sha, Martin, Roth; IEEE Micro 2007）
  - 直接对应你"干掉高消耗 CAM / NLQ / Store-Set"的建议：不用 store queue 也能做 store-load 通信。
  - https://doi.org/10.1109/MM.2007.17（IEEE Micro 付费）

- **Scalable Store-Load Forwarding via Store Queue Index Prediction**（Sha, Martin, Roth; MICRO 2005）
  - 上面的前作，store queue 匹配的 scalable 化。
  - https://www.semanticscholar.org/paper/31d03f85dc8e10eec9a47fe502afc821c1959b3d

- **Memory Dependence Prediction**（Moshovos et al., ISCA 1997）
  - store-load 依赖预测的开山之作（可选读）。

- **SonicBOOM: The 3rd Generation Berkeley Out-of-Order Machine**（HOT CHIPS / CARRV 2020）
  - data-less RS（发射后再读 PRF）的落地实现。
  - slides：https://carrv.github.io/2020/slides/CARRV2020_slides_15_Zhao.pdf

## 技术 → 论文映射

| 你的建议 | 权威论文 |
|---|---|
| Data-less RS / 发射后读 PRF | MIPS R10000、SonicBOOM |
| PRF / free-list / 重命名 | Alpha 21264、BOOM v2 |
| NoSQ / Store-Set 省 CAM | NoSQ (IEEE Micro 2007)、Sha MICRO 2005 |
| 单套 RAT + undo log / 精确恢复 | R10000、Alpha 21264（checkpoint/undo） |
| 面积/能耗高效 OoO | Load Slice Core (MICRO 2015) |

## 备注

- 顶会论文（MICRO/ISCA）的正式 PDF 多为 IEEE/ACM 付费墙；校园网或作者主页通常有开放版，也可用 Google Scholar 的 "[PDF]" 直达。
- 建议优先精读 **Alpha 21264**（结构）和 **Load Slice Core**（面积思想），再按你想压的模块读 NoSQ / R10000。
