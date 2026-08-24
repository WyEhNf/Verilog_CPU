# H-04/S-05 验证与回归契约

`tools/check_commit_trace.py` 是唯一的架构退休 trace 检查入口。输入为 JSON Lines，每条记录必须包含 `cycle`、`lane`、`valid`、`pc`、`inst`、`rd`、`rd_we`、`value`、`is_store`、`store_addr`、`store_mask` 和 `store_data`。只有真正提交的连续 lane 前缀可以有副作用；无效 lane、写 x0、空 store mask、倒退周期、旧 tag 结果和超过 watchdog 的无退休间隔都会被拒绝。

`tools/regression.py` 从 `tests/manifest` 加载全部 18 个外部 `.data` 镜像，检查名称唯一、期望返回值和每项的周期上限，并保留 `build/regression/manifest.json`。没有提供 `CPU_RUNNER` 时，执行回归会明确失败而不会把 manifest 校验伪装成 CPU 通过；`--validate-only` 只用于验证回归基础设施。

成功的整机案例必须满足 `halted=1 && error=0 && return_value==expected`，并且没有触发总周期或连续无退休 watchdog。失败时 runner 保存首个失败案例的 stdout/stderr 和 manifest 报告；波形路径由具体 CPU runner 追加到同一报告。
