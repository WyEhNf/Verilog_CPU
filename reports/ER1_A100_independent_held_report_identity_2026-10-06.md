# A100：普通、暂停保持和队首报告独立核对身份

记录时A99原监督PID48248仍存在；原157文件快照、候选/工具/准备脚本/报告和源证据通过冻结检查。A100仅在独立F盘41源码目录生成，未改变原A99运行或主E EU40文件。没有启动新的HDL/lint/形式/仿真/综合/STA/单元测试。

A94已测IPC1.115262692、含SRAM面积35798.972678μm²、频率290.249433MHz；A99尚未产生新指标。A100不借用这些指标。

## 结构改动

原资格路径先用较晚的held-live在16行grant之间切换，再掩码/合并28位ROB身份和query，之后读取当前ROB valid与完整8bit GEN。新模式普通报告的28位身份树只依赖原普通priority；held身份则用保存的完整LSQ票据中的slot提前读取原rob_tag_mem，并产生原低/高bank query；队首身份保持。三份当前ROB valid/GEN独立核对，原held/head选择只控制一个live资格位。

不新增完整85位数据包副本，不改原public报告包、query、valid、held捕获、range/GEN/complete检查、回收/入队、错误/恢复和顺序提交。声明FF、SRAM和流水边沿增量均为0；新增一份9位ROB live读取（课程ROB32）和28位普通身份树（LSQ16），组合面积可能增加。FAST_STORE_BATCH仍0，ISA/GEN/队列/cache/预测容量不减。

## 等价推导

H=held-live。H=0时原saved_grant逐行等于普通priority P，新normal树每位采用同P&identity与相同OR递推，因此candidate0与原tag/query一致。队首候选与选择保持。

H=1时至少一个原held_match为真。原函数要求tag有效、当前LSQvalid、slot相同且完整LSQGEN相同，所有不同真实行的slot值不同，故至多一行匹配，其行号严格为保存held_tag中的slot。原held树因此输出该行rob_tag_mem及其原bank解码；新held_reader读取同一保存行、直接解码同位域，因此第三候选身份一致。这个证明不移除原range/live/complete/reported或全GEN门槛，也不依赖假设某条不可达路径。

后端所有候选保留tag[0]、ROBslot范围、当前ROBvalid及全部8GEN比较；仅由原H/head在各自结果之间选择。实际load事件/reset/flush/recovery/cancel/CDB暂停条件仍原代码。未被选的私有query可不同，不能凭它创建完成事件。原public query之后的整个LSQ后缀（含状态更新和helper）逐字不变。

## 收益判断与后续

A94从held资格0.6385/0.7101ns经过saved query1.593ns、ROBlive1.811ns、完成选择2.185ns到分配GEN/FF3.385ns。A100把held选择从宽身份/ROB查询之前移动到bool结果之后，有直接串行依赖收益依据；但普通priority路径、新读取扇出、额外面积或其他路径可能主导。面积余量201μm²很小，不宣称必然达标。

A99已预报后启动当前集中PPA；只有其Fmax>300且总面积≤36000才会构建CPU和测六项IPC。A100是等待期间独立准备的下一方案，不并行启动测量、不修改已冻结运行；先用原A99结果判断新瓶颈与净面积余量。若需要新批，先汇报，采用前仍集中验证完整19正确性及M/GEN/恢复/MMIO/参数覆盖。目标仍严格>300MHz/IPC≥1.1/含SRAM≤36000μm²，未达成。
