# 重命名单元（B-02）

`rv32_rename_unit` 维护推测 RAT、已提交 RRAT 和非零物理寄存器 free bitmap。输入 bundle
按 lane 顺序处理，只产生资源足够的连续前缀。组合阶段先复制 RAT 到临时工作映射；每个
写 rd 的 lane 通过分层优先选择取一个空闲物理寄存器，并在 bundle 工作位图中清除；后续
lane 的源查询立即看到该新映射，因而
覆盖 bundle 内 RAW 和 WAW。

`rename_ready_i`、ROB/RS/LSQ free count 或 free bitmap 空间任一阻塞时，不接受后续 lane。x0 固定映射 P0，
对 x0 的写不消耗空闲项。时钟沿写入 RAT 并清除已分配 bit；commit 沿更新 RRAT 并置回
old phys bit。恢复沿以完整 RAT、free bitmap 和 count 替换推测状态，
优先于普通 rename/commit。

`rat_state_o`、`rrat_state_o` 和 `free_bitmap_state_o` 是可用于恢复/验证的扁平状态。
位图初始时 P1 到 `P{PHYS_REGS-1}` 为 1，P0 恒为 0，因此无需非二幂环形指针。
`rename_new_phys_o` 与 `rename_rd_we_o` 同时驱动 PRF 的 allocation clear 端口。

分支 checkpoint 仍只保存 RAT。恢复时 backend 从 checkpoint RAT、分支自身映射和幸存
ROB 项的 old phys 构造 reserved bitmap，取反后直接恢复 free bitmap；不再把空闲寄存器
动态压缩成宽 free-list 总线。

验证命令：`make b02`，覆盖 `BE_WIDTH=1/2/4` 与 `PHYS_REGS=48/64/96`。
