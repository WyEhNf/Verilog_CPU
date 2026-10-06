# 可参数化 XOR D-cache 索引

## 已验证结果

仍未达到任何评分档位。XOR 索引是在现有缓存容量不变时改善 IPC 的可选实现，默认 `DCACHE_INDEX_HASH=0`，设为 1 开启。不能把 2 KiB 配置的 IPC 配上 1 KiB 的面积、频率声称达标。

固定 CPU：FE2/BE2、PHYS48、ROB16、RS4、LSQ8、ISSUE2/CDB2、I-MSHR8、D-MSHR4、完成队列 8、FETCH_QUEUE16、CHECKPOINT_IMPL=0。主存统一、延迟 20 周期，I/D 在途数 16/8。每组均运行六项 CPU-2026 基准，无 pi。

| D-cache | 索引 | 总周期 | IPC | 完整层级面积 µm² | 预布局 Fmax MHz |
|---|---|---:|---:|---:|---:|
| 1 KiB | 普通，上一轮审计基线 | 990,475 | 0.477137737 | 36,406.230840 | 201.64 |
| 1 KiB | XOR，当前完整审计 | 873,950 | 0.540755192 | 36,550.922760 | 207.42 |
| 2 KiB | XOR，当前性能实验 | 752,534 | 0.628002190 | 未重算 | 未重算 |

1 KiB XOR 比基线 IPC 提高约 13.33%，完整层级面积增加 144.691920 µm²（约 0.40%）。频率改善是这次映射的实测结果，不表示 XOR 索引必然改善所有配置的关键路径。

| 基准 | 1 KiB 普通周期 | 1 KiB XOR 周期 | 2 KiB XOR 周期 |
|---|---:|---:|---:|
| median | 13,574 | 17,436 | 13,950 |
| multiply | 18,892 | 19,380 | 19,170 |
| qsort | 310,235 | 244,978 | 224,949 |
| rsort | 633,846 | 579,731 | 481,954 |
| towers | 6,751 | 5,353 | 5,353 |
| vvadd | 7,177 | 7,072 | 7,158 |

所有配置均退休 472,593 条指令。聚合 IPC 用总退休数除以总周期，不是六项 IPC 的算术平均。median 和 multiply 变慢，所以不全局默认开启；仍需结合最终配置选择。

## 完整面积与时序口径

XOR 1 KiB 层级网表共 340,810 个单元，独立 Liberty 求和与 Yosys 一致。顺序单元面积 14,637.445200 µm² 未变化，新增成本来自组合逻辑。

展平清理后基础面积 32,733.907920 µm²，23,084 个 BUFx8 增加 4,038.776640 µm²，时序网表总面积 **36,772.684560 µm²**，共 325,044 个单元。所有内部存储展开，零存储黑盒、零未计价单元。外部主存不在综合顶层，未计入面积。

STA：最小周期 4821.20 ps，Fmax 207.42 MHz，WNS −1487.87 ps，TNS −12649836 ps。时钟周期 3333.333333 ps、不确定度 100 ps、输出负载 1 fF。理想连线及数据扇出缓冲，不含布局布线、寄生和时钟树，不是物理签核。

## 实现与正确性边界

设缓存有 2^k 行、每行 16 字节：索引由地址的 `[k+3:4]` 与其上方 k 位做 XOR，tag 仍保存完整高地址部分。给定保存的 tag 和物理槽号可以反推出原始行地址。写回必须使用这个反变换，不能直接拼接 tag 与散列槽号，否则会写错主存位置。

请求、预取、MSHR 槽位冲突检查及全部回填分支统一调用 `cache_index()`；脏行写回使用 `victim_line_address()`。数据阵列容量、tag 宽度、MSHR 数、访存接口及流水级均未改变。

`tools/test_dcache_hash.ps1` 八组通过：普通/XOR × 16/64 行 × 无/有预取。每组包含 1000 个随机 32 位地址的索引反变换检查、非零 tag 脏行碰撞写回、500 组随机掩码写入与读取、最后对整个 4096 字节测试内存的 1024 个 word 再读验证。参考字节数组独立于 DUT 和内存模型；使用真实三周期测试内存。测试脚本检查 PASS，拒绝 ERROR/FAIL/FATAL，不依赖 `$finish` 的进程退出码。

六项整机性能实验另使用 20 周期主存，并检查 LSQ 不变量。本次没有新增 LH/LHU/SH 功能，未测试 pi。XOR 1/2 KiB 测试通过不等价于已验证全部缓存容量和所有乱序参数组合。

## 参数与流程

- RTL：`cpu_core.DCACHE_INDEX_HASH` → 非阻塞 D-cache 的 `INDEX_HASH`，有效值 0/1。
- 构建：`tools/build_join02_verilator.ps1 -DcacheIndexHash 1`。
- 完整综合：`tools/run_full_area.py --dcache-index-hash 1`，manifest 和面积报告记录该参数。
- Makefile 与三个综合脚本传递此参数；Makefile 的 Verilator 构建入口也补齐已支持的 CPU/缓存/主存延迟参数传递，避免设置变量后仍使用脚本默认值。dry-run 验证参数存在；当前性能数据来自直接调用构建脚本。
- 旧黑盒面积流程只保持参数兼容，不作为评分面积。

## 证据

- `build/synth/p2_p48_r16_d1k_hash_full/`：当前源码指纹、配置、网表、完整及独立面积。
- `build/timing/p2_p48_r16_d1k_hash_full/`：完整时序与含缓冲面积；展平 JSON 以 `cpu_core_flat.json.zip` 保存，已验证解压内容 SHA-256，复算前解压。
- `build/cpu2026/report_p2_hash_final_l20.json`、`report_p2_hash_d128_l20.json`：1/2 KiB XOR 性能。
- `build/cpu2026/dcache_hash_tests.log`：八组专项测试。
- 当前源码与综合 manifest 的全部源文件哈希一致。
- 普通索引 1/2/4 KiB 已用当前源码重新构建并跑完六项：`report_p2_hash0_d64_l20.json`、`report_p2_hash0_d128_l20.json`、`report_p2_hash0_d256_l20.json`，周期与旧记录一致。统一的参数实验表见 `parameter_sensitivity.md`，架构报告草稿见 `architecture_exploration.md`。

为释放空间，上一轮更名前的重复综合目录已归档为 `build/synth/p2_p48_r16_d1k_reclaim_full.zip`，逐文件校验 SHA-256 后移除原目录；当前基线 `reclaim_v2_full` 仍保留。删除的编译 `.gch` 缓存可重新生成，可执行文件和结果均保留。

后续必须继续处理频率及乱序窗口/存储延迟瓶颈，完成其余参数敏感度实验。2 KiB XOR 的 IPC 超过 0.6，但其面积未达到 10,000 µm² 的证据缺失，频率也未达标，不能认定获得第一阶段分数。
