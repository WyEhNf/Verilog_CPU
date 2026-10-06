# A106：恢复年龄判定改为等价环形位置比较

A105原监督PID96096继续单独使用冻结源、原课程工具和原日志，未重启、未改测量脚本。此记录附带当前原进程观察，A106指标不继承任何旧版IPC/面积/频率。上一报告轮只核对了同一原进程仍活跃，分类为verified wait；本轮新增独立源快照与源级推导，分类为progress。

令W=原ROB_SLOT_WIDTH，M=2^W。原unsigned W-bit age=(slot-head) mod M：slot>=head时age=slot-head，slot<head时age=M+slot-head。Wrapped组的年龄全部晚于unwrapped组；同组只需普通slot比较。因此age>branch_age完全等价于(slot_wrap&&!branch_wrap)||((slot_wrap==branch_wrap)&&(slot>branch_slot))，无候选年龄减法。

年龄>=occupancy等价于unwrapped_position>=head+occupancy。共享端点E以max(W,COUNT_WIDTH)+1位无符号加法保留任何原二值count，不截断溢出。E=q*M+e；q=0时outside=slot_wrap||slot>=e，q=1时outside=slot_wrap&&slot>=e，q>=2时outside=false。每个候选只有W位slot>=e比较。端点加法、turn和branch_wrap可先行并共享，而非放在选中候选之后。这包括occupancy0、M及大于M，故不借用可达状态；非2幂ROB仍按原2^W回绕而非改为ROB_ENTRIES回绕。entries1使用原W>=1定义，也成立。

仅三文件增加flag及替换私有LSQ报告恢复classifier：core/backend默认0保留A103原年龄式，course profile1启用新式。原candidate完整GEN/currentlive/range、head/可选held布尔选择、actual recovery apply、producer_valid、producer targetlive更新、CDB/PRF/RS/LSQ/ROB所有状态后缀保持。backend从候选live_state声明至原末尾逐字相同。新增FF/SRAM/流水边沿均0，原ISA/窗口/提交/MMIO/全GEN/参数维度不缩减。

A99关键链包含恢复资格经CDB/PRF旁路回到LSQ分配，其最高到达3.414ns，PPA周期3.474609375ns，距300MHz需至少141.276ps。A106移除已提前到各候选的减法再比较链，提供下一个不改变周期行为的结构方向；组合面积可能增加或减小，且是否仍为A105瓶颈尚未知，因此本轮不开始测试。

准备器、41源码、审阅和本记录冻结。未运行HDL/lint/形式/仿真/综合/STA/单元测试或CPU构建；主E EU40源不变。继续原A105，结果出现后按实测路径决定A106及其余有依据的修改是否组成下一批。新测量前先汇报；仍仅在PPA>300MHz且含SRAM面积<=36000后测六perf，全部三项与19原正确性+4冻结边界程序及参数/架构审阅完成后才能采用。
