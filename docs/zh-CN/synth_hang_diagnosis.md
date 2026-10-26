# Yosys+ASAP7 面积综合"卡死"诊断与修复记录

日期：2026-09-04。范围：`make synth`（register 上界流程 `synth/synth.tcl`，
FE=BE=1, PHYS_REGS=64, ROB_ENTRIES=32，ASAP7 7.5T RVT TT）。

## 1. 症状与最初误判

- 第一次全设计综合（14:32–14:34）写日志 2.9 MB 后 2.3 分钟内无进展，被判定"卡死"并终止；
  日志停在第 `27. Executing PROC pass`（`proc` 阶段）。
- 逐模块扫描（`synth/per_module_scan.tcl`，`_per_module.log`）显示每个模块单独 `procs`
  只要几秒，但日志在 `rv32_lsq.v` 之后中断 → 怀疑 LSQ。
- 同时 Yosys 报出少量 `Warning: Latch inferred`（PRF `bypass_lane`、rename `free_index`、
  ROB `commit_lane` 等）→ 最初怀疑隐式 latch 导致（本记录确认了方向：**组合逻辑里
  缺默认赋值**，但真正的爆炸点不是这些 latch 本身）。

## 2. 真正的根因：LSQ 组合逻辑让 proc 的 decoder 构造爆炸

- 单独跑 `rv32_lsq.v; proc`（verbose）能看到进度计数
  `N/23901: ...`（"Creating decoders for process ..."），即 `proc_mux` 要为该进程构造
  **23901 个 decoder 信号**，且每信号的条件树都很大；实测速率低至 ~1.4 个/s
  （>240 s 跑不完，quiet 模式同样慢 → 与日志打印无关）。
- 制造 23901 的代码是 store-forwarding 的**逐字节条件写**：

  ```verilog
  for (byte_index = 0; byte_index < 16; byte_index = byte_index + 1)
      if (mask_mem[i][byte_index] && target_mask[byte_index]) begin
          fwd_mask[byte_index] = 1'b1;
          fwd_data[(byte_index*8) +: 8] = data_mem[i][(byte_index*8) +: 8];
      end
  ```

  每个 fwd 位都带独立的嵌套条件 → proc 按位分裂 decoder；`blocked/target_mask/fwd_mask/
  fwd_data` 又只在深层 `if` 内被写（无默认赋值）→ dlatch 候选把 $mem2bits 读口也拖进来。
- 修复（`rtl/backend/rv32_lsq.v`，功能等价，回归周期数逐位一致）：
  1. 组合块顶部给 `blocked/target_mask/fwd_mask/fwd_data/overlap/alloc_slot/older_age`
     无条件默认值（符合 plan.md H-00 "组合块必须有默认赋值"）；
  2. 逐字节写改成**整字合并**（每 store 一个统一条件，保持 youngest-wins 语义）：

  ```verilog
  overlap = mask_mem[i] & target_mask;
  fwd_data = (data_mem[i] & expand_bytes(overlap)) |
             (fwd_data & ~expand_bytes(overlap));
  fwd_mask = fwd_mask | overlap;
  ```

  3. `expand_bytes()`：16-bit mask → 128-bit 逐字节复制函数（无过程化条件）。
- 结果：LSQ 单独 `proc` 从 >240 s 降到 ~48 s；整设计 `proc` 正常通过。

## 3. 隐式 latch 的清理（plan.md H-00 风格）

全设计只推断出 19 条 latch 告警，全部是**整数循环/跨块变量**（无功能影响但会生成
$dlatch 进 ABC，可能参与 ABC 崩溃）。按"组合块顶部默认赋值"原则清理：

| 文件 | 变量 | 说明 |
| --- | --- | --- |
| rtl/rv32_physical_register_file.v | `bypass_lane` | 读口旁路循环变量（generate 内） |
| rtl/rv32_rename_unit.v | `free_index` | rename 分配循环变量 |
| rtl/backend/rv32_rob.v | `commit_lane` | 提交循环变量（仅在 `!recovery_found` 下进入） |
| rtl/backend/rv32_lsq.v | `alloc_slot`, `older_age` | 见上 |
| rtl/backend/rv32_backend_joint.v | `recovery_rs_index`, `recovery_completion_index`, `producer_recovery_index` | 恢复扫描循环变量 |

所有改动只加默认赋值，不改变任何条件分支语义；Icarus 整机 smoke（naive/gcd/expr/
multiarray/array_test2）返回值与 cycle 数均与改动前完全一致。

## 4. 后续综合运行记录

- run2/run3：`proc` 阶段通过（run3 到达 `34. Executing ABC pass`），
  **ABC 报错 `return code -2`**（`&nf` 映射步骤内崩溃，见下）。
- run4（latch 清理后）：`proc/opt/fsm/memory_dff/techmap` 全通过，ABC 仍在
  `&nf` 崩溃（与 latch 无关）。
- 映射器排查：
  - 默认映射器 `&nf` 对 ASAP7 正确（`if -g` 报 "Library with only 2 cell classes
    cannot be used"、`if` 只映射成通用门不落库），但 `&nf` 在本设计上稳定崩溃。
  - 尝试最小脚本 `+strash;&get -n;&dch -f;&nf;&put`（跳过 fraig/scorr/dc2/dretime）
    规避崩溃 → run5，结果待补。

## 4b. 功能回归结论（LSQ 重写后）

- B-08 LSQ 单测 BE_WIDTH=1/2：PASS。
- Icarus 整机冒烟（naive/gcd/expr/multiarray/array_test2）：PASS，周期数逐位一致。
- Verilator 18 项全量回归：**18/18 PASS**，所有用例周期数与改动前完全一致
  （含 pi：548,099,190 cycles / 101,560,724 instret；qsort/tak/superloop/queens/
  magic/hanoi/bulgarian 等长测试亦逐周期一致）。
  结论：LSQ 逐字节→整字合并重写功能完全等价。

## 5. ABC 崩溃的最终解法：自建 genlib + 经典 map

- 判定：Yosys 0.68+120 自带 ABC 的 liberty→genlib 转换无法处理 ASAP7 NLDM 库
  （`&nf` 连 ALU 单模块都崩溃；`map`/`if -g` 只见 "only 2 cell classes"；genlib
  临时文件里只剩 12 个通用原语、没有 ASAP7 单元）。
- 解法：`tools/liberty2genlib.py` 直接把 ASAP7 组合单元（INVBUF/SIMPLE/AO/OA）解析成
  SIS genlib（排除 CKINVDC/HB 时钟树单元、FA/HA 多输出单元、TIE 常量单元；常量门
  ZERO/ONE 用 CONST0/CONST1 无 PIN 行写法），`tools/filter_asap7_lib.py` 先剥掉
  `pg_pin` 块。流程改为：
  ```
  abc -genlib _asap7_lib_filtered/asap7_comb.genlib -script "+strash;scorr;dc2;dretime;strash;map"
  dfflibmap -liberty .../asap7sc7p5t_SEQ_RVT_TT_nldm_201020.lib
  ```
  `map` 用 genlib 整型面积成本（×10000）做优化，最终 `stat -liberty` 读原库真实面积。

## 6. 面积结果（FE=1 BE=1, PHYS_REGS=64, ROB_ENTRIES=32, ASAP7 7.5T RVT TT）

- **主指标（Cache data/tag 阵列按 SRAM 黑盒，其余全部展开为触发器）**：
  `synth/synth.tcl`（memory_dff）**≈ 28,497 µm²**。Cache 阵列因同步读，memory_dff
  不会展开（仍为 $mem，约 48 kb），需再用 ASAP7 SRAM 宏库补面积。
- **全黑盒口径（所有 `reg` 阵列都留作 $mem）**：`synth/synth_bb.tcl`（memory -nomap）
  **≈ 27,942 µm²**（ROB/LSQ/PRF/rename 阵列也黑盒，口径比计划更宽，仅参考）。
- 两口径差异 554 µm² ≈ 小型寄存器阵列（ROB/LSQ/PRF/rename）展开成触发器带来的增量。
- 分模块（主指标口径，µm²，局部面积）：
  backend_joint 9530 / lsq 6781 / rob 3881 / prf 2257 / multiplier 1578 / dcache(控制)
  1085 / cache_stats 772 / alu 594 / rs 557 / icache(控制) 275 / divider 239 / rename
  198 / branch_predictor 186 / fetch_frontend 177 / memory_bridge 130 / completion 119 /
  cpu_core(glue) 65 / mdu_rs 43 / decoder 31。
- 待补：① Cache SRAM 宏面积（`third_party/asap7/sram_0p0` 宏库尚未拉取）；② 真正的
  寄存器面积上界（把 Cache 阵列也强制展开成触发器，需 memory_map/改异步读）。

## 7. 遗留问题

- Verilator 子 make（verilated.mk 归档步骤）在本环境反复报
  `0 was unexpected at this time.`（cmd 解析错误），绕开方式：对象编译完后手工
  `ar rcs` + `g++` 链接（与 make 等价）。已记录在 `.dsh/skills/long-running-tests`。
- `make synth` 依赖 `environment.bat` 更新 gdk-pixbuf cache（临时文件+改名），在 DSH
  文件沙箱下被拒；绕开方式：不调 environment.bat，直接设 `YOSYSHQ_ROOT/PATH/SSL_CERT_FILE`
  后运行 yosys（见 skill）。
