"""Record a concrete ready-store completion direction; do not claim implementation."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT,read,sha,write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
CANDIDATE = BASE/'A78_lsq_forward_onehot'
STATE = ROOT/'build/cpu2026/tier3_er1_optimization_20261005.json'
PROOF = ROOT/'build/cpu2026/er1_ready_store_source_opportunity_20261006.json'
REPORT = ROOT/'reports/ER1_ready_store_completion_direction_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    state = read(STATE)
    assert state['last_measured_candidate'] == 'A75_branch_capture_phase_valid'
    assert state['current_source_candidate'] == CANDIDATE.name
    terminal = Path(state['measurement_terminal_proof'])
    assert sha(terminal) == state['measurement_terminal_proof_sha256']
    candidate = read(CANDIDATE/'candidate.json')
    assert sha(CANDIDATE/'candidate.json') == state['pending_source_candidate_sha256']
    for name,digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE/name) == digest,name
    source = {}
    for name in ['rtl/course/student_top.v','rtl/cpu_core.v','rtl/backend/rv32_backend_joint.v',
                 'rtl/backend/rv32_rob.v','rtl/backend/rv32_lsq.v','rtl/rv32i_alu.v']:
        source[name] = (CANDIDATE/name).read_text(encoding='utf-8')
    top,core,backend,rob,lsq,alu = [source[n] for n in source]
    for marker in ['.DISPATCH_PIPELINE(1)', '.ROB_LEGACY_HALT_PAYLOAD(LEGACY_SENTINEL_HALT)', '.ROB_RETURN_VALUE_ENABLE(RETURN_VALUE_ENABLE)']:
        assert marker in core,marker
    assert '.RETURN_VALUE_ENABLE(0)' in top
    assert '.LEGACY_SENTINEL_HALT(0)' in top
    assert 'parameter integer LIGHT_RETIRE_PAYLOAD = 1,' in top
    assert 'parameter integer ROB_MMIO_PREDECODE = 1,' in top
    assert 'parameter integer STORE_ALLOC_EARLY_DATA = 1,' in top
    assert '(d_is_store & d_valid & rs_src2_ready)' in backend
    assert 'rs_src2_value[store_data_lane*32 +: 32] : d_store_data' in backend
    assert 'wire [BE_WIDTH-1:0] d_rs_need=d_valid & ~load_without_agu;' in backend
    assert '(d_is_load & ~d_is_store & lsq_alloc_addr_valid)' in backend
    assert 'assign rs_alloc_valid=d_rs_need & {BE_WIDTH{d_admit}};' in backend
    assert 'assign lsq_alloc_valid=d_lsq_need & {BE_WIDTH{d_admit}};' in backend
    assert '(tag[GEN_LSB +: GENERATION_WIDTH] == generation_mem' in rob
    assert 'mmio_word_mem_write_data[bank_slot_index] = (completion_store_addr_i' in rob
    assert 'completion_store_mask_i[(bank_complete_lane*4) +: 4] == 4\'hf' in rob
    assert 'alloc_data_valid_i' in lsq and 'store_admission_fire' in lsq
    assert 'assign calc_rd_we=(|value_classes) || calc_is_load;' in alu
    locations = []
    patterns = dict(
        already_ready_data='wire [BE_WIDTH-1:0] lsq_alloc_data_valid',
        already_ready_address='assign lsq_alloc_addr_valid[io_lane]',
        ordinary_store_rs_demand='wire [BE_WIDTH-1:0] d_rs_need=',
        atomic_allocation='assign lsq_alloc_valid=d_lsq_need',
        full_rob_generation='(tag[GEN_LSB +: GENERATION_WIDTH] == generation_mem',
        original_mmio='mmio_word_mem_write_data[bank_slot_index] = (completion_store_addr_i')
    for role,needle in patterns.items():
        for name,text in source.items():
            if needle in text:
                locations.append(dict(role=role,file=str(CANDIDATE/name),line=text[:text.index(needle)].count('\n')+1,
                    source_sha256=sha(CANDIDATE/name)))
                break
    REPORT.write_text('\n'.join([
        '# 就绪存储的完成通路：下一项架构修改方向', '',
        '这是基于A78源码和A75已完成测量的设计审查，尚未实现候选，也没有启动测试。A75 IPC1.05188539，距1.1仍需提高4.5741%；A70–A75只让qsort减少33周期，已证实单纯信用与第二回收调整不足。', '',
        '当前D级已能把已就绪的基址加立即数作为LSQ分配地址，同时把权威PRF/前递src2值作为存储数据写入LSQ。但是RS豁免仅适用于加载，所有存储仍进入RS，再由ALU生成相同地址/数据，经过普通完成端口把ROB置为ready。', '',
        '| 项目 | 原通路 | 待实现方向 |', '|---|---|---|',
        '| 已就绪普通RAM存储 | D分配RS/LSQ → RS选择 → ALU结果寄存器 → 普通完成 → ROB ready | D原子分配LSQ，同时由一个专用、完整标签校验的仅存储完成事件将ROB ready置位 |',
        '| 数据与地址 | LSQ已有权威捕获，之后接受重复ALU更新 | 以原LSQ捕获作为执行结果所有者 |',
        '| 内存副作用 | ROB顺序提交授权，LSQ请求、确认和回收 | 原流程全部保留 |',
        '| 其他存储 | 等待操作数后执行，MMIO退出也由原协议处理 | 原通路保留 |', '',
        '建议每拍至多选择一个最低有效D槽的就绪存储走快完成，其他槽继续原RS/ALU流程；不拆分原子D束、不增加PRF/CDB写口，也不为每个LSQ行新增完成数据缓存。首版仅对合法SB/SH/SW、opcode与size一致、自然对齐、地址位于256MiB RAM且两操作数已就绪的存储启用。MMIO与未满足资格的元组保留原行为。', '',
        '仅在已寄存且弹性的D级、轻量ROB退休载荷、MMIO预解码、无legacy halt/value载荷、原早期地址/数据开启的完整配置中启用；默认及其他参数配置保留原通路。课程当前配置满足这些结构条件。', '',
        '实现必须在真实LSQ alloc_fire之后才发出快完成；ROB使用完整有效/行/8位代数和store标志检查，不允许以“D看起来有效”替代ROB身份。所选快存储必须同步从RS需求中剔除，避免重复执行；若D因容量或恢复暂停，则两条动作都不发生。', '',
        '普通RAM存储在ROB只需要就绪位和MMIO=false元数据；该配置的地址/掩码/值/存储数据退休载荷已经被裁剪。候选可为一个额外仅存储事件增加本地标签查询，而不用扩宽所有通用完成数据路由。原恢复、提交、确认、重分配写优先级必须保留；尤其分配新代数不能被旧完成污染。', '',
        '在原RS立即发射、ALU与完成端口无阻塞的理想情况下，此方向能够减少约两个“执行结果到ROB就绪”边沿；这不代表减少两个程序总周期。存储尚未到ROB头、缓存/确认等待可能遮蔽收益。需要实际就绪存储覆盖率和之后的一次集中测量，不能从旧停顿计数推算1.1。', '',
        '目标是不新增状态或SRAM，但新增标签/资格/行更新组合门成本和D到ROB路径长度尚未知；现A75面积余量仅341.2286μm²。因此先完成完整所有权与优先级实现，再结合A77/A78检查时序与面积成本，形成有充分依据的批次后测试前汇报。', '',
    ]),encoding='utf-8')
    proof = dict(status='READY_STORE_COMPLETION_SOURCE_OPPORTUNITY_NOT_IMPLEMENTED',
        recorded_at=datetime.now(timezone.utc).isoformat(),candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),
        measured_terminal_proof=str(terminal),measured_terminal_proof_sha256=sha(terminal),source_locations=locations,
        already_authoritative_lsq_allocation_address_and_data=True,ordinary_store_still_uses_rs_alu_completion=True,
        actual_fast_store_rtl_implemented=False,measured_gain=None,
        proposed_profile_default_off=True,proposed_single_ram_store_event_per_cycle=True,
        proposed_identity=dict(rob_generation_bits=8,full_rob_tag_bits=16),
        source_cost_target=dict(new_ff_bits=0,new_sram_bits=0,actual_mapping_unknown=True),
        original_store_side_effect_order_preserved_requirement=True,new_tests_started=False,
        report=str(REPORT),report_sha256=sha(REPORT),goal_complete=False)
    write(PROOF,proof)
    state.update(last_architectural_source_audit=str(PROOF),last_architectural_source_audit_sha256=sha(PROOF),
        last_background_progress=str(PROOF),last_background_progress_sha256=sha(PROOF),
        last_goal_turn_classification='PROGRESS_A75_RESULT_A77_A78_RTL_READY_STORE_OWNERSHIP_SOURCE_DIRECTION',
        next_work=['Implement one ready RAM-store fast completion event in an independent A78 descendant, preserving exact LSQ allocation/ROB identity/side-effect ordering.',
            'Review cumulative A76-A78 timing against A75 measured LSQ path; do not claim their metrics.',
            'Do not run per-edit tests; report before one materially justified complete native batch.',
            'Retain A55R2 and continue toward verified IPC1.1, Fmax>300MHz, area includingSRAM<=36000um2.',
            'Before adoption verify full course correctness, RV32IM/recovery/OoO/commit/MMIO/parameter requirements.'])
    write(STATE,state)
    print(dict(status=proof['status'],proof=str(PROOF),proof_sha256=sha(PROOF),report=str(REPORT),
        actual_fast_store_rtl_implemented=False,new_tests_started=False))


if __name__ == '__main__':
    main()
