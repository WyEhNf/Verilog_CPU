"""Read-only architecture/parameter source audit for measured A109; no HDL tests."""
from datetime import datetime, timezone
from pathlib import Path
import re

from manage_frozen_baseline_programs import ROOT, read, sha, write
from manage_er1_a109_measurement import check, live, RUN

CANDIDATE = Path('F:/CPU2026Candidates/tier3_er1_20261005/A109_rob_occupancy_distribution')
PROOF = ROOT/'build/cpu2026/er1_a109_architecture_source_audit_20261006.json'
REPORT = ROOT/'reports/ER1_A109_architecture_parameter_source_audit_2026-10-06.md'


def main():
    assert not PROOF.exists() and not REPORT.exists()
    plan = check()
    assert sha(CANDIDATE/'candidate.json') == plan['candidate_sha256']
    candidate = read(CANDIDATE/'candidate.json')
    for name, digest in candidate['source_sha256'].items():
        assert sha(CANDIDATE/name) == digest and sha(RUN/'source'/name) == digest, name
    names = ['rtl/course/student_top.v','rtl/cpu_core.v','rtl/rv32im_decoder.v',
        'rtl/rv32i_alu.v','rtl/rv32m_mdu_iterative.v','rtl/rv32_physical_register_file.v',
        'rtl/rv32_rename_unit.v','rtl/backend/rv32_backend_joint.v','rtl/backend/rv32_rob.v',
        'rtl/backend/rv32_lsq.v','rtl/backend/rv32_reservation_station.v',
        'rtl/cache/rv32_icache_nonblocking.v','rtl/cache/rv32_dcache_nonblocking.v',
        'rtl/backend/rv32m_mdu_reservation_station.v']
    texts = {name:(CANDIDATE/name).read_text(encoding='utf-8') for name in names}
    top, core, decoder, alu, mdu, prf, rename, backend, rob, lsq, rs, icache, dcache = [texts[name] for name in names[:-1]]
    mdu_route = texts[names[-1]]
    isa = set('LUI AUIPC JAL JALR BEQ BNE BLT BGE BLTU BGEU LB LH LW LBU LHU SB SH SW ADDI SLTI SLTIU XORI ORI ANDI SLLI SRLI SRAI ADD SUB SLL SLT SLTU XOR SRL SRA OR AND MUL MULH MULHSU MULHU DIV DIVU REM REMU'.split())
    decoded = set(re.findall(r'op_o\s*=\s*`RV32IM_OP_(\w+)',decoder))-{'INVALID','HALT'}
    assert decoded == isa and len(isa) == 45
    for op in 'MUL MULH MULHSU MULHU DIV DIVU REM REMU'.split():
        assert '`RV32IM_OP_'+op in mdu_route and '`RV32IM_OP_'+op in backend
    assert "finishing_value=(!mode_mul && divide_zero)?" in mdu
    assert "req_is_signed_div && req_src1_i==32'h80000000 && req_src2_i==32'hffffffff" in mdu
    assert "(LEGACY_SENTINEL_HALT)" in core or 'LEGACY_SENTINEL_HALT' in core
    assert re.search(r'parameter integer LEGACY_SENTINEL_HALT\s*=\s*0',core)
    assert re.search(r'parameter integer SERIAL_BACKEND\s*=\s*0',top)
    assert 'target_live_mem[entry_index] && src1_ready_effective[entry_index] &&' in rs
    assert 'older_ready[rank_other]=ready_candidates[rank_other] && older;' in rs
    assert 'commit_slot = head_commit_index + commit_lane;' in rob
    assert 'if (!commit_break)' in rob and 'if (head_valid[commit_lane] && head_ready[commit_lane])' in rob
    assert 'end else commit_break = 1\'b1;' in rob
    assert "(memory_dreq_addr == 32'h80000000)" in core and "(memory_dreq_mask == 16'h000f)" in core
    assert 'memory_dreq_wdata[mmio_word*16 +: 16]' in core and "16'h000f : normal_mem_d_req_wmask" in core
    dimensions = ['FE_WIDTH','BE_WIDTH','INT_ISSUE_WIDTH','ROB_ENTRIES','PHYS_REGS','RS_ENTRIES',
        'LSQ_ENTRIES','ICACHE_LINES','ICACHE_WAYS','DCACHE_LINES','DCACHE_WAYS']
    profile = {}
    for parameter in dimensions:
        match = re.search(r'\b'+parameter+r'\s*=\s*(\d+)',top)
        assert match and f'.{parameter}({parameter})' in top, parameter
        profile[parameter] = int(match[1])
    for term in ['.BE_WIDTH(BE_WIDTH)', '.PHYS_REGS(PHYS_REGS)', '.ROB_ENTRIES(ROB_ENTRIES)',
                 '.RS_ENTRIES(RS_ENTRIES)', '.LSQ_ENTRIES(LSQ_ENTRIES)', '.INT_ISSUE_WIDTH(INT_ISSUE_WIDTH)']:
        assert term in core, term
    for term in ['.ENTRIES(RS_ENTRIES)', '.PHYS_REGS(PHYS_REGS)', '.ROB_ENTRIES(ROB_ENTRIES)', '.LSQ_ENTRIES(LSQ_ENTRIES)']:
        assert term in backend, term
    assert '$clog2(PHYS_REGS)' in prf and '$clog2(PHYS_REGS)' in rename
    assert 'for (entry_index = 0; entry_index < ENTRIES;' in rs
    assert '$clog2(ROB_ENTRIES)' in rob and '$clog2(LSQ_ENTRIES)' in lsq
    for term in ['.CACHE_LINES(ICACHE_LINES)', '.CACHE_WAYS(ICACHE_WAYS)',
                 '.CACHE_LINES(DCACHE_LINES)', '.CACHE_WAYS(DCACHE_WAYS)']:
        assert term in core, term
    assert 'CACHE_SETS = CACHE_LINES / CACHE_WAYS' in icache and 'CACHE_SETS = CACHE_LINES / CACHE_WAYS' in dcache
    assert "prefix!=mem_resp_line_addr_i[31 -: REGION_STORAGE_WIDTH]" in icache
    assert "else if(region_invalidate[metadata_entry]) valid_q<=1'b0;" in icache
    assert 'prefix==demand[31 -: REGION_STORAGE_WIDTH]' in icache
    source_notes = [
        'RV32IM decoder exposes all45 required instruction classes, including all8 funct7=1 M operations and all8 integer load/store forms. ALU retains full32-bit operations, shift masking, JAL/JALR/compare/address logic; unified MDU retains signed/unsigned/high-half classification, sign correction, explicit dividezero/original dividend and signed overflow cases. Legacy sentinel halt remains default0. This is source review plus planned finite CPU tests, not a formal complete ISA proof.',
        'The course SERIAL_BACKEND0 path instantiates the rename/PRF/RS/ALU-MDU/completion/ROB/LSQ network. RS ready_candidates independently filters valid/live/operand-ready rows; older_ready counts only older READY rows. Therefore an older blocked row does not prevent a younger ready row being selected. No in-order instruction-head gate was added to issue. ROB commits only a contiguous head+lane prefix, stops on the first invalid/unready/nonretiring store or precise terminal, and updates head by the actually accepted prefix. Ordinary stores retain registered admission/actual-head retirement; prefix admission never retires a younger store.',
        'MMIO request checks exact address80000000 and low16mask000f, routes original32-bit payload through uncached external writes and forces word strobes; cache cannot absorb it. ROB MMIO retirement waits for actual head/store wait state and stops younger commits. RAM addresses remain32bit and external256MiB range is the unchanged course driver; Dcache full tag includes all high address bits. Icache shared high-region prefix is stored perway and participates in hits; prefix change invalidates all old rows in that way, so it is capacity/invalidation sharing, not high-bit alias truncation.',
        'All requested dimensions are actual top parameters passed through core/backend/cache instances, not labels only: issue width via BE_WIDTH/INT_ISSUE_WIDTH, ROB32 course and parameter-sized row/ring/tags, PRF56 course and clog2-sized physical identities/storage, RS8 and parameter-sized ready/wake/rank/payload domains, Icache128lines2way and Dcache1024lines2way with CACHE_SETS=LINES/WAYS, index/tag/array/SRAM dimensions. Current supported core FE/BE widths1/2/4, ROB power-of-two>=2, PRF>=33; nonblocking caches accept power-of-two16..4096lines and1/2ways with legal region/MSHR settings. Unsupported geometries explicitly finish/fatal; no claim that every integer parameter is valid or that arbitrary supported profiles were dynamically tested now.',
        'A95-A109 proofs are already frozen to the measured source; A102 erroneous signed32 recovery age reasoning is explicitly superseded by A103 correct unsigned ROB_SLOT_WIDTH age and A106 exact circular rewrite. Full ROB/LSQ generation/range/current-live checks and actual events remain. A105 optional row-live boolean mode is0 in A109; A107 private planned allocation payload is consumed only under original actual fire; A108 exact five-word packet selects preserve public payload; A109 views all equal one original occupancy FF. A110/A111 are separate unmeasured sources and are not part of measured A109 or any closing executable.',
        'Existing parameter_sensitivity.md and architecture_exploration.md contain actual earlier single-parameter IPC experiments and tradeoffs; their latency20/older tooling/versions remain historical and cannot be used as current pinned-course scores. This audit preserves these artifacts read-only. Final A109 report must distinguish current three metrics atlatency10 from those historical parameter experiments; do not claim a fresh course-profile sweep or mix IPC/area/frequency from different builds.'
    ]
    REPORT.write_text('''# A109 架构与关键参数源级审阅

本记录只读取原A109实测源，检查41文件SHA与原课程运行源一致，未运行HDL/lint/仿真/综合/STA/单元或参数扫描。所有结论按下列证据范围解释，不把文本匹配当完整行为证明。

'''+ '\n\n'.join(source_notes)+ '\n\n当前默认关键配置：'+str(profile)+'''

仍需原A109六perf实际IPC及答案完成，再集中19官方+4冻结边界程序。当前CPU有限正确性还未结束，主E未采用，目标未完成。旧九级算术流水说法已由A111审阅纠正：ALU算术chunk/prefix是组合层，原ISSUE_PIPELINE0无RS→ALU额外寄存级。
''',encoding='utf-8')
    historical = [ROOT/'reports/parameter_sensitivity.md',ROOT/'reports/architecture_exploration.md']
    proof = dict(status='PROGRESS_A109_ARCHITECTURE_PARAMETER_SOURCE_REVIEW_NO_NEW_TESTS',
        classification='PROGRESS',recorded_at=datetime.now(timezone.utc).isoformat(),
        candidate=str(CANDIDATE),candidate_sha256=sha(CANDIDATE/'candidate.json'),
        source_manifest_sha256=plan['source_manifest_sha256'],source_file_count=41,
        source_sha256={name:sha(CANDIDATE/name) for name in names},required_decoded_ops=sorted(isa),
        parameter_profile=profile,source_review_notes=source_notes,
        supported_parameter_limits_source_reviewed=True,arbitrary_parameter_simulations_run=False,
        original_a109_pid=103132,original_a109_pid_alive=live(103132),
        original_frozen_measurement_check_passed=True,new_tests_started=False,goal_complete=False,
        architecture_preservation_source_review_complete=True,current_cpu_closing_correctness_complete=False,
        artifacts_sha256={str(path):sha(path) for path in [Path(__file__),REPORT,CANDIDATE/'candidate.json']+historical})
    write(PROOF,proof)
    print(dict(status=proof['status'],candidate_sha256=proof['candidate_sha256'],
        parameters=profile,decoded_required_ops=45,proof=str(PROOF),proof_sha256=sha(PROOF),goal_complete=False))


if __name__ == '__main__':
    main()
