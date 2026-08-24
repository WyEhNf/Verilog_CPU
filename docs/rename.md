# 重命名单元（B-02）

`rv32_rename_unit` 维护推测 RAT、已提交 RRAT 和非零物理寄存器 free list。输入 bundle
按 lane 顺序处理，只产生资源足够的连续前缀。组合阶段先复制 RAT 到临时工作映射；每个
写 rd 的 lane 从 free-list 头取一个物理寄存器，后续 lane 的源查询立即看到该新映射，因而
覆盖 bundle 内 RAW 和 WAW。

`rename_ready_i`、ROB/RS/LSQ free count 或 free-list 空间任一阻塞时，不接受后续 lane。x0 固定映射 P0，
对 x0 的写不消耗 free-list。时钟沿写入 RAT/free-list；commit 沿更新 RRAT 并把 old phys
放回 free-list。恢复沿以完整 RAT、free-list 内容、head/tail/count 快照替换推测状态，
优先于普通 rename/commit。

`rat_state_o`、`rrat_state_o` 和 `free_list_state_o` 是可用于 checkpoint/验证的扁平快照。
free-list 初始顺序为 P1 到 `P{PHYS_REGS-1}`，因此非二幂 `PHYS_REGS` 也能正确回绕。
`rename_new_phys_o` 与 `rename_rd_we_o` 同时驱动 PRF 的 allocation clear 端口。

验证命令：`make b02`，覆盖 `BE_WIDTH=1/2/4` 与 `PHYS_REGS=48/64/96`。
