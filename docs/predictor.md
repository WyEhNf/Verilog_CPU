# A-02 分支预测器和 BTB

`rv32_branch_predictor` 包含 64 项 2-bit bimodal 表和 16 项直接映射 BTB。BHT 使用 `PC[7:2]` 索引，复位为弱 taken (`10`)；BTB 使用 `PC[5:2]` 索引并保存 `PC[31:6]` tag、目标和控制流种类。

条件分支只有在 BHT 高位为 1、BTB tag 命中且 BTB kind 为 branch 时才预测 taken。BTB miss 一律预测顺序地址，避免使用冲突项的旧目标。JAL 从机器码重排立即数并直接预测 taken，不占 BTB；JALR 必须命中 kind 正确的 BTB，保存目标时清零 bit 0。

所有表项只在 `feedback_valid_i` 的提交沿训练，flush/redirect 不回滚预测器。条件分支 taken 时更新 BTB 并饱和增加 BHT，not-taken 时饱和减少 BHT；JALR taken 时更新 BTB。查询同时输出 BHT/BTB 索引和当前计数器，供 ROB 保存预测 metadata 和定位误预测。

统计计数器同样只在提交反馈握手时增加。正确预测要求 taken 状态一致；实际 taken 时还要求目标一致。验证入口 `make a02` 覆盖 taken/not-taken 饱和、交替状态迁移、BHT alias、BTB tag 冲突、miss/hit、JAL、JALR 目标 bit 0 清零和统计值。
