# RV32IM 可视化实验台

在项目根目录运行：

```powershell
python tools/cpu_gui.py
```

或运行 `make gui`。服务默认监听 `http://127.0.0.1:8765/` 并自动打开浏览器。

GUI 支持面积优先、乱序单发射、双发射和四发射预设，也可编辑 `cpu_core`
的全部实现参数。运行时会展示取指、译码、后端、ALU/MDU、访存与提交活动；
串行后端显示八阶段状态机和操作数，乱序后端显示 ROB/RS/LSQ/完成队列占用、
空闲物理寄存器和 dispatch/issue/CDB 信号。寄存器表由退休记录实时更新。

核心演示包含 `accumulate`、`vvadd`、`vmul` 和 `m_isa_smoke`，展开“全部测试”
可运行已有程序镜像。Pi 和 LH/LHU/SH 链路按当前项目约束保持冻结。
