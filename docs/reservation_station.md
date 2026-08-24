# 保留站与发射选择（B-04）

`rv32_reservation_station` 保存一类执行端口的等待项；INT、MUL、DIV 通过参数化实例
分离。每项包含操作、PC、完整 ROB tag、目标物理寄存器、两个值/tag/ready 和 store data。

分配只接受连续有效前缀，RS 满时停止。CDB wakeup 在时钟沿更新，完整 valid+slot+generation
tag 匹配后置源 ready，因此 N 周期收到的唤醒最早在 N+1 选择。组合选择按 age 最小、再按
slot 最低的确定顺序输出最多 `BE_WIDTH` 项；执行端口未 ready 时，entry 保持不变。

flush 使用 entry kill mask 在一个沿清除严格年轻项；被清除项不能再次发射。只有 target-live
且两个源 ready 的项可选择，避免 ROB recovery 后旧项重新进入执行端。

验证命令：`make b04`，覆盖 BE_WIDTH=1/2/4、RAW wakeup、RS full、oldest 优先、backpressure、
flush 和 generation mismatch。
