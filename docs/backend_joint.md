# B-09 后端联合门

`rv32_backend_joint` 是 `BE_WIDTH=1/2/4` 参数化的多发射乱序后端闭环。输入和
`CommitRecord` 均为按 lane 压平的连续 bundle；D-Cache 侧直接复用 `rv32_lsq`
的请求、响应和 store ack 协议，不建立第二套内存字段。

## 数据路径

Rename 为每条 trace 分配 ROB tag 和物理目的寄存器。PRF 提供两个读口；当源
物理寄存器尚未写回时，联合门用 `phys_tag_mem` 保存其生产者 ROB tag，RS 在
CDB wakeup 后再发射。立即数、分支预测信息和访存属性按 ROB slot 保存，避免
trace 输入撤销后改变已分派指令。

RS 每周期按年龄选择最多 `BE_WIDTH` 条 ready 指令，每个 lane 有独立整数 ALU；
MUL/DIV 由一个共享 MDU 接受当拍最老的 M 类指令。ALU、MDU 和 LSQ load completion
统一进入 completion network，再同时驱动 PRF、ROB 和 RS wakeup。ROB 只在队首
产生最多 `BE_WIDTH` 条连续提交记录；store 必须成为 lane 0/实际 ROB head，并先通过
LSQ 的 commit/ack 握手才可提交。load response 的 error
按 ROB slot 保留到 completion，store ack 的 error 直接送入 ROB；两者都只在对应指令
精确提交时更新 `error_o`。

分支恢复由带有效 tag 的 ALU completion 触发。ROB 保留分支及更老条目、恢复
逐 lane 构造的 RAT checkpoint。RS、LSQ、completion FIFO 按 ROB 年龄杀死严格年轻项；
恢复同拍的老路径 completion/AGU 更新会被保留。长延迟 MDU 继续运行，输出用动态
slot+8-bit generation tag 校验，避免旧结果写入复用后的 ROB/物理寄存器。
free bitmap 则由恢复后的 RAT、分支自身映射和幸存 ROB old-phys 直接重建，不经过
空闲寄存器编号压缩或环形 free-list head/tail 恢复。

## 单元门

`tb/unit/rv32_backend_joint_tb.v` 覆盖 RAW/WAR/WAW、长延迟 DIV、MUL 与 load
同周期完成、store/load responder 往返、字节转发、checkpoint recovery、精确
load/store error 和 halt 返回值，并包含 100-cycle completion timeout 与
10,000-time-unit 全局 watchdog。`make b09` 保持单发射兼容性，`make join04` 验证
双/四发射代表配置，`make join05` 验证全部 9 组 FE/BE 宽度组合，并同时覆盖
`PHYS_REGS=48/64/96`、`ROB_ENTRIES=16/32/64`。

整机前端为每个 fetch lane 提供独立预测读口。当前实现复制小型 BHT/BTB 状态，并让
所有副本接收相同反馈以保持一致，避免 lane 1--3 中的分支被固定成 not-taken；fetch
frontend 仍以 bundle 中最早的 taken 预测截断后续指令。
