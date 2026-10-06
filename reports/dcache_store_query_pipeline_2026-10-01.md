# 同步标签缓存：store确认与查询流水优化

## 实现与约束

本轮在已验证的one-hot取指读口基础上修改 `rtl/cache/rv32_dcache_nonblocking.v`，仅作用于TAG_SRAM=1；TAG0保留原行为，源码默认仍TAG0。课程真实同步1RW SRAM与20cycle/word共享AXI模型不变，pi冻结。

1. **同边沿store确认**：同步标签query已有受理的committed store。仅当内部request_fire为真、store确实能写入命中行或被MSHR接收、旧ACK寄存器空闲时，旁路输出ACK。LSQ接收ACK与SRAM写入/MSHR所有权转移发生在同一个上升沿；不是查询输入被接受时就提前ACK。下游不ready时，写入后将ACK保存在原寄存器，之后只交付一次。旧ACK占用时不旁路抢占它。TAG0不启用此旁路。
2. **标签查询与前一store的数据写重叠**：命中store不需要读取数据，下一store可在前一store写data bank的同边沿读取独立tag SRAM。load查询仍必须等待数据端口空闲，refill/local fill的tag写仍阻止新的tag读，不能将单端口伪造成多端口。
3. **metadata-only dirty miss补读**：若重叠查询实际miss且将淘汰脏行，其data_rdata可能是X，不能用于WB。新query_data_valid/query_data_from_sram将tag与data的有效期独立管理；必须等待数据写端口空闲，额外同步读取全部way，再受理该miss并捕获正确victim。held query的tag/data写转发继续保留，flush不丢此前已接收的committed store。

没有增加ISA功能，没有绕过ROB有序退休，没有改变外部RAM、程序镜像、计数口径或退出B握手。

## 实测性能（同为四发射、ROB32/PRF64/RS16/LSQ8、I128、TAG1）

| 版本 | 六项总周期 | 六项退休 | IPC GEOMEAN | 相对基线 |
|---|---:|---:|---:|---:|
| one-hot前端，原store管线 | 421340 | 472599 | 0.9596478218888492 | — |
| 仅同边沿ACK | 420907 | 472599 | 0.9634821054970533 | +0.399551% |
| ACK + tag/data-write重叠 | 420810 | 472599 | 0.9636108214058166 | +0.412964% |

最新逐项周期：median10856、multiply12111、qsort168469、rsort217492、towers5734、vvadd6148。各项退休数与基线一致。三组均同样正式共享32-bit AXI、20cycle/word、原sim.cpp仅一条只读instret输出，不能用累计退休/周期取代几何平均。

**结论**：单拍store所有权确认带来可测的约0.40%总体提升；再消除store tag/write冲突仅再贡献约0.01336%相对收益。这不是IPC低的主因，也未消除TAG1相对TAG0/I128基线1.0015073214787的退化。尚低于目标1.0985，不能宣称IPC问题已经解决。下一步需要检查同步lookup到MSHR/AXI读请求的额外启动拍、refill仲裁与实际缺失带宽，不能仅继续优化store确认。

## 验证与证据

- 最新完整真实AXI构建 `D:/CPU2026Builds/store_query_overlap_tagbanks_i128_20261001`：benchmark6/6、basic5/5（半字及M操作）、simulator17/17、256MiB末地址脏回写边界全部通过；四份报告 `build/cpu2026/store_query_overlap_tagbanks_i128_*_20261001.json`。
- 同边沿ACK单独版本同样四套回归通过，构建与报告前缀store_ack_bypass_tagbanks_i128；其SHA逐项验证的不可变RTL副本在该D盘构建的source_snapshot中，后续代码修改后仍可明确验证该中间版本，不冒称当前源码。
- `tools/test_dcache_sram.ps1`：TAG0/1×merge0/16/32×ways1/2共12组四态原版SRAM测试通过，日志 `build/dcache_store_query_overlap_protocol_20261001.log`。新增步骤14–18分别验证命中/miss的单拍ACK、ACK背压与flush持久性、只有实际写边沿才消费ACK、连续store一拍一个query、metadata-only dirty miss先补读再ACK、1/2way victim完整数据与WB背压/flush、refill后不再次ACK。
- 两个旧版负例均实际执行：原两拍ACK源码在新单拍断言失败；仅ACK旁路版在新连续query与data-write重叠断言失败。不是删除或放宽原测试来获取PASS。
- `tools/test_dcache_hash.ps1`：TAG0/1×hash0/1×lines16/64×ways1/2×prefetch0/1共32组通过，各组1000次可逆索引、500随机masked操作与1024位置walkback；日志 `build/dcache_store_query_overlap_hash_20261001.log`。
- `make lint unit matrix`通过，日志 `build/store_query_overlap_unit_matrix_20261001.log`。

## 面积与频率边界

该缓存管线的新完整面积/时序尚未完成。46,154.839314µm²/24.993287935369MHz是更早PRF48/RS8、旧取指/旧cache管线冻结版本，不能沿用。06:36上一轮one-hot/PRF48/RS8/旧cache版本已独立完成45,947.628354µm²、IPC0.9519069653774248、完整频率22.323472346363MHz；它相对工作树只有cache文件改变，不能将其面积/频率与本轮新store管线IPC拼接。PRF64/RS16 one-hot旧cache审计仍在运行。详见 `reports/latest_total_area_2026-09-30.md` 顶部。

本轮PRF48/RS8组合版本 `D:/CPU2026Builds/store_query_overlap_tagbanks_i128_r32p48rs8_20261001` 已编译完成并通过6/5/17/边界，六项总周期428254、退休472599，IPC **0.9558133327368818**；比同资源旧store管线的0.951906965有所改善，但不与PRF64/RS16的0.963610821混算。报告 `build/cpu2026/store_query_overlap_tagbanks_i128_r32p48rs8_*_20261001.json`。

07:01该新cache组合的完整默认ABC已经完成，面积 **45,928.134894 µm²** =组合27,589.413240 +时序10,513.054800 +全部实际SRAM7,825.666854。383,242个计价叶实例、37个宏，未计价/未展开0、最终check0；独立Decimal复核并执行--require-current **VERIFIED**，当前工作树输入差异0。网表SHA `d05ef13c3376d670d08be9b5e3b004d14ea80b843bfd6545be17d2d2925add9f`，证据 `D:/CPU2026AreaAudits/store_query_overlap_tagbanks_i128_r32p48rs8_standard_20261001`。相比同参数旧store管线one-hot版，总面积实际降低19.493460 µm²（0.042425%），不是用局部估计拼接。面积仍超36,000上限9,928.134894 µm²。07:03同一网表完整时序已完成 **23.560269654649 MHz / 42.4443359375 ns**，所有SRAM参与、遗漏存储边界0；不能使用旧cache或其它参数频率。上段待完成状态属于此结果之前的记录。目标仍是同一最终配置36,000µm²、1.0985、300MHz，三项均未达到。
