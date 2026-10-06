# A96：同批普通RAM存储独立准备完成

记录时A94原监督PID84416仍存在、在原串行课程测量阶段；原快照157文件/配置/工具/报告/准备脚本和审阅通过冻结检查。A96仅在F盘独立源码目录生成，未跑HDL/lint/形式/仿真/综合/STA/单元测试，未改测量源、旧脚本、结果或主E EU40文件。

## 要解决的问题

A83为缩短晚ready之后的宽标签选择，提前选最低potential store身份。A95沿用此策略：前面的潜在存储未就绪时，后面已具备原LSQ真实地址/数据的存储仍不能走快完成；同批两条都就绪，也只能省一条RS/AGU工作。A96让各条普通RAM存储的完整保存ROB身份直接并行核对，晚ready只门控对应合法事件，不选择或复用一条宽标签。支持已有BE_WIDTH1/2/4；课程宽度2可让两条合格存储都跳过重复RS/ALU准备。

各lane保留原完整资格：D真实valid/store且非load，canonical immediate，保存基址ready且无匹配当前base-WB，数据保存ready或合法WB-ready，原RAM与对齐/类型/size判断，explicit-data为0。actual fast valid继续要求相应LSQ真实alloc_fire、原reset/flush/branch guard。地址/数据继续原LSQ/PRF（包括最高WB优先级），MMIO/异常类型/未就绪继续原RS，不扩大内存请求带宽。

## 容量判断与时序结构

令B为原d_valid中除去load_without_AGU的数量，F为全部合格fast store数量。fast store是B中的非load有效存储，0≤F≤B；真实RS需求仍由原d_rs_need计数，严格等于B−F。

提前计算room[k]=(B≤free+k)，k=0..BE_WIDTH，free先扩展17bit再加常数。晚资格只检查是否存在合格存储子集S、k=|S|，使room[k]为真。存在这样的S与B−F≤free等价：正向k≤F；反向取全部fast集合（F=0则room0）。固定mask/count在展开时决定，没有晚popcount/减法/比较链。

课程BE=2退化为：room0 OR ((f0 OR f1) AND room1) OR (f0 AND f1 AND room2)。BE=1/2/4分别有1/3/15个非空固定mask，不借同边沿RS回收。原D整包admit/reset/flush/busy/LSQroom、实际RS/LSQ需求与fire、全部valid保守替换信用/FIFO语义保持。A90稀疏分配计划证明仍成立：实际admit时全部原内存需求满足原free，所以任何实际LSQfire下plan等于完整fire向量。

## ROB与提交不变量

批模式不再把事件压到一个预选标签；每lane原d_tag提前送给原ROB全valid/row/8GEN/store/no-rd/no-branch/no-halt比较，晚实际valid门控。ROB只把FAST_STORE_OWNER_LANES从1恢复BE，原所有逐行比较/OR及ready更新、CDB完成处理、错误、allocate/retire优先级、sent/ACK、恢复及存储提交主体逐字不变。不同真实D存储对应不同完整ROB身份，多个行可在同一边沿独立完成准备。只更新原ready，不提前授权内存副作用。

参考：[BOOM LSU](https://docs.boom-core.org/en/latest/sections/load-store-unit.html)将存储地址/数据准备与committed后按程序序排出分开；[BOOM ROB](https://docs.boom-core.org/en/latest/sections/reorder-buffer.html)说明存储只有commit后才可发往内存，LSU接收可commit存储数量。此处借鉴该分离原则，保留本CPU原单授权口、顺序LSQ排出、缓冲退休和MMIO条件。外部文档是架构参考，不是本RTL正确性或频率/IPC证明。

## 收益与限制

同输入下A95快集合是A96快集合子集，原fast机会不会因更早潜在lane而丢失，可减少第二条或更后就绪存储的重复RS/ALU准备。聚合IPC仍未测，内存排出仍最多原单请求/边沿；不把快集合扩大当所有程序必然加速。

新增每lane完整身份比较和容量组合逻辑，不新增声明FF/SRAM/普通流水沿/端口容量，不减ROB/PRF/队列、GEN或ISA。更多比较/资格扇出可能增加面积或降低Fmax；面积余量有限，需下一次有依据的整批映射判断。FAST_STORE_BATCH默认core/backend/ROB0、课程top1，仅在保存快存储profile激活；关闭时保留A95原单potential身份/至多一条策略。

A95直接地址类别推导原样继承。A96无实测三指标、无采用，A94结果不能借给它。下一步继续读取原A94任务终态与新瓶颈，开展有证据的源码改动；新批测量先报告，采用前仍须完整19正确性及M/GEN/恢复/MMIO/参数覆盖。目标严格>300MHz/IPC≥1.1/含SRAM≤36000μm²仍未达成。
