# A101：在选择暂停报告行之前解码 ROB 查询

A99原监督PID48248记录时仍在原串行任务中运行；157文件快照、工具、候选、准备脚本、审阅及报告冻结检查通过。A101只在独立F盘41源码中改一份LSQ文件，无HDL/lint/形式/仿真/综合/STA/单元测试或CPU构建；原运行源、旧成功脚本和主E EU40源码不改。

A100已把普通/head/held身份独立核对，但held分支仍是保存LSQslot→读取16bit ROBtag→解码12bit bank query→读取9bit当前ROB live/GEN。A101把bank解码移到每个保存LSQ行，原held_reader直接选择28bit的{preparedquery,fulltag}。因此移除选中ROBslot编码后的解码层，标签的全部GEN/valid位保持，读选择仍使用原held票据的slot。

对任何合法LSQ索引r：原输出是tag[r]和decode(tag[r])；新row packet就是{decode(tag[r]),tag[r]}，原reader一热rowhit选择同r，输出相同。非法索引在原reader返回零tag，tag[0]=0保证该候选live为假；新preparedquery可以为零，但标签也为零，资格仍假。原H=true必须存在完整LSQtag匹配的真实行，因此非法私有值不能触发实际事件。H/head晚bool选择、完整8ROBGEN/9LSQGEN、range/live/complete/reported、cancel/reset/flush/recovery保持。

新增声明FF/SRAM/流水边沿/ROB查询数量均为0；沿用A100新增第三查询，本次只扩展其LSQ私有组合读取16→28bit。每组最多16bit掩码控制，可能额外增加12bit路由/OR和一个wordselect驱动。原普通身份query也按同保存ROBtag解码，综合可能共享这些等式，但不能当作面积已下降或时序已改善。A100 normal/head/private输出之后的整个LSQ后缀（含公共query/包与所有状态/helper）逐字不变；backend/core/top以及参数值不变。

当前无A99/A100/A101新指标。最新测量仍A94：IPC1.115262692、含SRAM总面积35798.972678μm²、Fmax290.249433MHz。需约112ps改善，面积余量仅201μm²；新结构有串行依赖依据但净收益待原A99结果判断。A99仅在PPA双门槛通过后测六项IPC。未并行或重复测量，未采用；目标严格>300MHz/IPC≥1.1/总面积含SRAM≤36000μm²及完整RV32IM/OoO/顺序提交/MMIO/参数化保持。采用前仍需集中19正确性与M/GEN/恢复/MMIO/参数覆盖。
