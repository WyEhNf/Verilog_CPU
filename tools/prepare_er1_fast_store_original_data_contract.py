"""Keep the original ALU explicit-store-data override outside fast completion."""
from datetime import datetime,timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read,sha,write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A80_fast_store_address_predecode'
TARGET = BASE/'A81_fast_store_original_data_contract'
REVIEW = BASE/'A81_source_review.json'


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == '17afbcc548938f8def7c416dda7550dde38cf637987de549447fe065d3f0bee5'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest,name
    name = 'rtl/backend/rv32_backend_joint.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    old = '                address_flags[0] && ordinary_store && canonical_immediate;'
    assert original.count(old) == 1
    text = original.replace(old,'''                address_flags[0] && ordinary_store && canonical_immediate &&
                // Original ALU uses explicit trace store data when nonzero,
                // otherwise its authoritative src2. Core always passes0;
                // other callers keep that exact override on the old path.
                d_store_data[ready_store_lane*32 +: 32]==32'b0;''')
    core = (PARENT/'rtl/cpu_core.v').read_text(encoding='utf-8')
    assert core.count('.trace_store_data_i({BE_WIDTH*128{1\'b0}})') == 2
    alu = (PARENT/'rtl/rv32i_alu.v').read_text(encoding='utf-8')
    assert '.signal_i(calc_is_store && issue_store_data_i==32\'b0)' in alu
    assert 'issue_src2_value_i[store_word*16 +: 16]:issue_store_data_i[store_word*16 +: 16];' in alu
    for file in parent['source_sha256']:
        destination = TARGET/file
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/file,destination)
    (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_FAST_STORE_ORIGINAL_DATA_CONTRACT_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=[name],source_sha256={file:sha(TARGET/file) for file in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['enabled_profile'] = dict(parent['enabled_profile'],fast_store_original_explicit_data_override_preserved=True,
        core_explicit_store_data_constant_zero=True,fast_store_data_contract_new_ff_bits=0,fast_store_data_contract_new_sram_bits=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Require zero original explicit D store-data field before fast completion; this is the exact condition under which the original ALU uses authoritative src2, matching the existing LSQ allocation data. Both core backend call sites pass constant zero. Nonzero external trace overrides retain ordinary RS/ALU execution and its original final LSQ data update.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        fast_store_original_data_contract_source_verified=True,
        fast_store_original_data_contract_limit='No new performance optimization; preserves the component override contract. Core tied-zero guard may prune but exact mapping unmeasured. Cumulative A76-A81 IPC/area/Fmax unknown.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=[name],tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'Original ALU chooses explicit issue_store_data_i when nonzero, else issue_src2_value_i. Existing ready LSQ allocation data uses authoritative rs_src2_value. A79/A80 fast completion skipped the later ALU update, which must not bypass a nonzero explicit override supplied through the standalone backend interface.',
            'New guard requires d_store_data==0 for fast eligibility. Nonzero override cannot enter store_without_agu and therefore keeps original RS demand, ALU execution, full ordinary completion and final LSQ update. Zero override uses exactly the authoritative src2 value already captured by LSQ, including a legitimate zero src2.',
            'Both serial and OoO core backend call sites tie trace_store_data_i to BE_WIDTH*128 zeros. Therefore every valid core D packet has zero explicit data and this guard does not reduce course-profile fast-store coverage. No FF/SRAM/edge or authority relaxation added; exact gate pruning and cumulative metrics remain unmeasured.',
            'Manual source reasoning/hashes only, no HDL/lint/formal/simulation/synthesis/STA/unit test. Future complete-batch coverage includes zero/nonzero explicit override with different src2, zero src2 value, width1/2/4, normal/default profiles and full store/MMIO/recovery/parameter requirements.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
