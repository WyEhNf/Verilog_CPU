# 重排序缓冲（B-03）

`rtl/backend/rv32_rob.v` 是按程序顺序分配、按 head 连续提交的环形 ROB。每个 slot
保存 PC、原始指令、逻辑/物理寄存器信息、结果、store 元数据、HALT/error 标志和 branch
checkpoint。slot 的 generation 在复用时递增并跳过零；completion、store ack 和 recovery
都必须同时匹配 valid、slot 和 generation，旧响应不会写入新一代 entry。

store 到达 head 后先通过 `store_commit_valid_o` 请求 LSQ/Cache 提交许可，收到
`store_ack_valid_i` 后才产生 CommitRecord 并 pop；`store_ack_error_i` 会记录在匹配
entry 中，并与 completion error 一样仅在该 entry 提交时更新 `error_o`。普通结果只在
head 连续 ready 时提交。HALT、error 和返回值只在该精确提交沿更新。

branch recovery 以 distance-from-head 选择最老的 live request，恢复该 entry 的 opaque
checkpoint，保留 branch 及其以前的 entry，截断年轻 ROB 项并递增 epoch。恢复优先于普通
completion、commit 和 allocation。

Recovery tag 已包含 ROB slot，因此候选选择直接用 tag 中的 slot 索引 live generation，
再比较相对 head 的 age 以选择最老 recovery；不会再为每个 lane 扫描全部 ROB entry。
Completion 和 store-ack 的时序写回仍保留逐 entry 常量索引形式：当前小容量 FF-reference
综合证明 variable-index 写入会增加 decoder/mux 面积，不能只按 blackbox memory 推断结果
判断收益。

验证命令：`make b03`，覆盖 BE_WIDTH=1/2/4、generation stale completion、store ordering、
branch recovery、HALT、completion error 和 store-ack precise error。
