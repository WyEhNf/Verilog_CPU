# 共享 AGU 接入前 RS 布局冻结版完整 PPA（2026-10-02）

本报告是冻结源码成绩，不是当前工作树成绩。最终目标仍为同一当前配置≤36,000µm²、IPC GEOMEAN≥1.0985、全 SRAM Fmax≥300MHz；Tier3 未达成。

## 同一冻结配置三项结果

四发射、ROB64/PRF64/RS16/LSQ16、RAT1、共享 AGU 地址2、Cache控制2、TAG1、I128/D1024、AXI读8/写4/word16、响应FIFO2；本次 RS metadata 接入前冻结。全部参数以目录中的 run_manifest 和 build_manifest 为准。

| 项目 | 结果 |
|---|---:|
| 组合标准单元面积 µm² | 40608.667980 |
| 时序标准单元面积 µm² | 12891.927600 |
| 全部实际片上 SRAM µm² | 7825.666854 |
| 完整总面积 µm² | **61326.262434** |
| 授权六项 benchmark IPC GEOMEAN | **1.1213155347352615** |
| 全 SRAM 估计 Fmax MHz | **18.100507309140404** |
| 最小周期 ns | 55.2470703125 |
| 实际计价叶实例 / SRAM宏 | 546526 / 37 |

原默认ABC、五份未改的 ASAP7 RVT TT 库、官方 SRAM/external-module 检查及完整展开；未计价叶、未展开内存和遗漏存储时序边界均0。频率使用 OpenSTA3.1、原课程约束、理想时钟与无线寄生，非布局布线实测；外部256MiB平台RAM不计面积。

完整证据目录：`F:/CPU2026AreaAudits/axi_response_fifo2_branch1_bus8w4q16_i128_r64p64rs16_lsq16_rat1_earlystore2_dcupdate2_standard_20261002sharedagu_os_nodfg`。面积和频率共同映射网表 SHA256：`e74768fd2e4db3f89263d41e7b2e7ae94b6840e42d0ffc54459065f4e5778567`。独立 Decimal 完整核价 VERIFIED；原自动 --require-current 核验已正确失败，失败记录保留，随后只按冻结版本核验并补齐时序，不冒称当前零差异。

## 原生结果与源码对齐核验

10:30重新逐项核验四份原生报告：各自 build_manifest 与本面积的完全相同；每个构建来源 SHA 与冻结面积源快照一致；测试驱动、可执行文件、程序镜像和非构建数据的 SHA 都与报告记录一致。6/5/17/边界共29项全部通过，原20cycle/word共享AXI、256MiB与B握手退出合同一致，Pi冻结。只将六项 benchmark 几何平均计分，不使用其它套件 IPC 或 aggregate 作为成绩。

报告位于 `build/cpu2026/axi_response_fifo2_branch1_bus8w4q16_i128_r64p64rs16_lsq16_rat1_earlystore2_dcupdate2_{benchmark,basic,simulator,boundary}_20261002sharedagu_os_nodfg.json`，其 SHA256 依次为：

- benchmark：`de4ae3d5fe528c46fc42347839384b4e72af97d5452dc8a1ca26a856872f5153`
- basic：`b1b8be2ff6eff651bdc559147a1108a395bd7b616e84333077ab4d92c91d287a`
- simulator：`4e1c072ccf84c273875185217e82151207fec2f770f00550292b38515b59f28c`
- boundary：`96bb416fb4be17d367d0158820a11607db61eb14e1430167c647aadb8757b814`

当前树与冻结源码不同的五个构建来源为 backend_joint、reservation_station、student_top、cpu_core 和 rv32i_alu。当前 RS metadata1 的两套 Cache0/2原生29项也已通过、IPC同为1.1213155347352615，但当前两套整机PPA仍在映射，不能沿用本报告面积与频率。
