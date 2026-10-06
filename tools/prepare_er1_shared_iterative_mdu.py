"""Prepare an area tradeoff justified by the saved official static ISA mix."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A16R2_shared_barrel_elastic_dispatch'
TARGET = BASE/'A17R1_shared_iterative_mdu'
MIX = Path('F:/CPU2026Proofs/ER1_official_perf_static_instruction_mix_20261005.json')


def main():
    assert not TARGET.exists()
    mix = read(MIX)
    assert mix['all_six_texts_have_no_m_instructions'] and len(mix['results']) == 6
    assert all(row['static_m_instructions'] == 0 for row in mix['results'])
    parent = read(PARENT/'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    name = 'rtl/course/student_top.v'
    old = (PARENT/name).read_text(encoding='utf-8')
    pattern = r'\bMUL_IMPL\s*=\s*0\b'
    assert len(re.findall(pattern,old)) == 1
    new = re.sub(pattern,'MUL_IMPL = 2',old)
    assert new.replace('MUL_IMPL = 2','MUL_IMPL = 0') == old
    (TARGET/name).write_text(new,encoding='utf-8')
    # The unified implementation and its cancellation machinery are not edited.
    mdu = (TARGET/'rtl/rv32m_mdu_iterative.v').read_text(encoding='utf-8')
    controller = (TARGET/'rtl/backend/rv32m_mdu_reservation_station.v').read_text(encoding='utf-8')
    for operation in ('MUL','MULH','MULHSU','MULHU','DIV','DIVU','REM','REMU'):
        assert '`RV32IM_OP_'+operation in controller, operation
    for required in ('operation_cancel_guard','out_cancel_guard','request_cancel_guard',
                     'divide_zero','signed_overflow','req_rob_tag_i','req_target_live_i'):
        assert required in mdu, required
    backend = (TARGET/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
    assert '.MUL_IMPL(MUL_IMPL)' in backend and '.SELECTIVE_RECOVERY(LOCAL_EXEC_RECOVERY)' in backend
    record = dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=[name],source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)))
    record['parameter_overrides'] = dict(parent['parameter_overrides'],MUL_IMPL=2)
    record['enabled_profile'] = dict(parent['enabled_profile'],MUL_IMPL=2,
        mdu_execution_engines=1,mdu_algorithm_steps=32,mdu_is_area_latency_tradeoff=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Select existing shared 32-step RV32M iterative engine instead of separate pipelined Wallace multiplier/divider; full instruction functions, held output and local recovery retained.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        perf_static_m_instructions={row['name']:0 for row in mix['results']},
        static_mix_proof_sha256=sha(MIX),mdu_area_saving_unmeasured=True,
        dynamic_performance_effect_not_measured=True,
        m_instruction_dense_workloads_will_be_slower=True,
        iterative_arithmetic_and_sign_correction_fmax_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof = dict(status='SOURCE_AREA_LATENCY_TRADEOFF_UNTESTED',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_files=[name],parameter_before=dict(MUL_IMPL=0),parameter_after=dict(MUL_IMPL=2),
        unchanged_source_hash_entries=40,static_mix_proof=str(MIX),static_mix_proof_sha256=sha(MIX),
        tests_started=False,adopted=False,
        source_arguments=[
            'All six official linked .text disassemblies contain zero encoded RV32M instructions, verified from both mnemonics and opcode/funct7; perf_multiply is software shifts/adds. This is a static census, not dynamic execution evidence.',
            'All existing full RV32M RTL remains present. MUL_IMPL is parameterized and can select original Wallace/radix-4 implementations for multiplication-heavy workloads.',
            'Shared iterative mode uses one 65-bit shift state and one 32-bit operand, with 32 arithmetic steps, preserving signed high-half handling, divide-by-zero and signed-overflow behavior in the existing source.',
            'It retains full ROB tags, physical destinations, target-live checks, pending/output ownership, backpressure, and selective recovery cancellation. No whole-core serialization or removal of OoO is introduced.',
            'A M-free instruction stream should not exercise either M engine, but source text alone does not prove fetch confinement, IPC equivalence, mapped area or Fmax.',
            'The cost is lower RV32M throughput and longer M completion latency. Iterative compare/subtract/sign-correction arithmetic may become a timing bottleneck. No SRAM or capacities change.',
            'The six official perf programs do not cover RV32M operations; their answers cannot prove all eight M operations. Final adoption of this profile needs relevant existing M unit checks and recovery/backpressure coverage after area/timing gain is established.',
            'This candidate is independent of the immutable running A16R2. No new build, simulation, synthesis, STA or parameter sweep starts here.'
        ])
    proof['unsigned_division_source_argument'] = 'The controller admits all eight ops. The engine treats all non-MUL ops as divide; DIV/REM alone set signed flags, so DIVU/REMU use unchanged unsigned magnitudes, with REMU selecting remainder explicitly. Token presence is not a correctness proof.'
    write(BASE/'A17R1_source_review.json',proof)
    print({key:proof[key] for key in ('status','candidate','candidate_sha256','unchanged_source_hash_entries','tests_started')})


if __name__ == '__main__':
    main()
