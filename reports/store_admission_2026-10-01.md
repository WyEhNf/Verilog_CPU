# LSQ已提交store同拍接收实验

新增参数 `LSQ_STORE_ADMISSION_BYPASS=0`，经过student_top/cpu_core/backend传到LSQ的 `STORE_ADMISSION_BYPASS`。默认0完整保留旧行为，未将实验设为默认。

模式1仅在 `store_commit_valid && store_commit_ready` 且无reset/flush/recovery时，让**已获ROB架构接收授权**、完整generation-tag匹配的store同拍参加现有单请求端口的最老eligible仲裁。并非投机store提前写入。cache-ready低时，授权先登记为committed，随后稳定等待；真实cache握手才登记sent/response_wait，ACK、MMIO等待、恢复保留规则不变。

## 验证

`tools/test_lsq_store_admission.ps1` 完成30组：BE1/2/4×接收模式0/1的6组LSQ测试，加上完成模式0/2×store-retire0/1的24组backend整合测试，全部通过。证据 `D:/CPU2026Tests/store_admission_20261001`，入口日志 `build/lsq_store_admission_matrix_20261001.log`。

LSQ新增17次store覆盖槽位与generation复用、错误ROB tag拒绝、正确tag授权前不发送、MMIO字地址与完整字掩码、交替立即ready/持续背压、授权边沿恰好一次请求、恢复边沿不发新请求而保留committed store、ACK完整身份及不重复发送。原有半字/字节forward、未知store依赖、年轻load取消和恢复边沿已收到响应的测试保留。

实际课程AXI构建 `D:/CPU2026Builds/store_admit_fifo_tagbanks_i128_r32p48rs8_20261001`，显式参数TAG1/I128/PRF48/RS8/LSQ_STORE_ADMISSION_BYPASS1，完成FIFO模式0、ROB32/LSQ8/四发射/D1024。benchmark6/6、basic5/5、simulator17/17和256MiB末地址脏回写边界通过，pi冻结；原版共享32-bit AXI、20cycle/word、B握手退出未改。

## 实测结果：未选用

| benchmark | 原FIFO/接收模式0周期 | 接收模式1周期 | 退休数 |
|---|---:|---:|---:|
| median | 10906 | 10781 | 7062 |
| multiply | 12170 | 12181 | 27637 |
| qsort | 169012 | 170936 | 139606 |
| rsort | 224250 | 225170 | 289966 |
| towers | 5731 | 5919 | 3803 |
| vvadd | 6185 | 6443 | 4525 |

新模式总周期431430、退休472599，六项IPC GEOMEAN **0.9434785396017451**，低于旧模式0.9558133327368818。单次store省去一拍并不保证整机获益；仲裁/访存时序变化影响全机行为，未宣称已归因具体负收益原因。保留为显式可测试选项，不作为最终性能候选。本模式未做独立完整面积/频率，不用其它配置PPA推算。

各suite原始报告 `build/cpu2026/store_admit_fifo_tagbanks_i128_r32p48rs8_{benchmark,basic,simulator,boundary}_20261001.json`。此冻结构建先于后续预测器源码改动；不能宣称它等于修改后的当前全部源码。
