# B-09 后端联合门

`rv32_backend_joint` 是单发射后端闭环。输入是已经解码的 trace，输出只暴露
`CommitRecord` 字段；D-Cache 侧直接复用 `rv32_lsq` 的请求、响应和 store ack
协议，不建立第二套内存字段。

## 数据路径

Rename 为每条 trace 分配 ROB tag 和物理目的寄存器。PRF 提供两个读口；当源
物理寄存器尚未写回时，联合门用 `phys_tag_mem` 保存其生产者 ROB tag，RS 在
CDB wakeup 后再发射。立即数、分支预测信息和访存属性按 ROB slot 保存，避免
trace 输入撤销后改变已分派指令。

RS 的整数操作进入 ALU，MUL/DIV 进入 MDU。ALU、MDU 和 LSQ load completion
统一进入 completion network，再同时驱动 PRF、ROB 和 RS wakeup。ROB 只在队首
产生提交记录；store 先通过 LSQ 的 commit/ack 握手才可提交。load response 的 error
按 ROB slot 保留到 completion，store ack 的 error 直接送入 ROB；两者都只在对应指令
精确提交时更新 `error_o`。

分支恢复由带有效 tag 的 ALU completion 触发。ROB 保留分支及更老条目、恢复
checkpoint，并用一次性 `branch_pending` completion 使分支精确提交。

## 单元门

`tb/unit/rv32_backend_joint_tb.v` 覆盖 RAW/WAR/WAW、长延迟 DIV、MUL 与 load
同周期完成、store/load responder 往返、字节转发、checkpoint recovery、精确
load/store error 和 halt 返回值，并包含 100-cycle completion timeout 与
10,000-time-unit 全局 watchdog。运行 `make b09` 验证 `BE_WIDTH=1` 的单发射闭环；
PRF、rename、ROB、RS、LSQ 和 completion 的内部接口仍使用 B-01 至 B-08 定义的
flattened lane 协议，多发射 trace/CommitRecord 外壳留给 JOIN-04。
