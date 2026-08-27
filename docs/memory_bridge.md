# A-06 主存桥与 Cache 统计

`rv32_memory_bridge` 位于 I/D Cache 和双端口 line memory 之间。I、D 两侧各有一个独立的
单事务缓冲，因此两个端口可以在同一周期接受请求并分别等待响应。Cache 请求只在
`cache_*_req_valid && cache_*_req_ready` 时被锁存；此后 line 地址、128-bit 写数据、
16-bit byte enable、读写属性和 8-bit transaction ID 保持不变，直到主存完成事务。

桥不会把 testbench 的 byte array 直接暴露给 Cache。合法请求在
`mem_*_req_valid && mem_*_req_ready` 握手后等待原端口响应；响应反压期间，返回地址、
数据、ID 和 error 全部稳定。主存响应的地址或 ID 与已接受事务不匹配时，桥仍然消费该
响应，但向 Cache 返回原事务的地址/ID 和确定的 error，避免 tag 串线或死锁。

line 地址必须 16-byte 对齐并落在 `MEMORY_SIZE` 范围内。未对齐或越界请求不发送到主存，
而是在对应 Cache 端口产生保留原 ID 的本地 error 响应和全零数据。D 写请求完整转发
128-bit data 与 16-bit mask；写入可见时刻仍由 H-03 主存模型的响应握手定义。

`rv32_cache_stats` 在复位时清零，之后只消费已定义的单周期事件。I/D request、hit、miss、
refill、writeback 和 stall 来自 Cache；I memory request、D memory read/write 来自主存桥
真实请求握手。flush 不清除历史统计，也不会伪造一次请求或响应事件。

验证入口 `make a06` 覆盖真实 50-cycle I/D 并发、请求 payload 锁存、响应反压稳定、D 写
mask/小端序、原 transaction ID 返回、本地异常终止、精确主存握手事件和全部统计计数器
的复位及逐沿计数，并执行 Verilator 与 Yosys 检查。
