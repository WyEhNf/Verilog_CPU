"""Allow WB data readiness without restoring WB base/address classification."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A92_load_response_source_query'
TARGET = BASE/'A93_fast_store_wb_data'
REVIEW = BASE/'A93_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == '113a0b3d696a4884a5dff09c94604dfbd48f4e3273c7a35b83380e1d6e0e56c2'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer FAST_STORE_SAVED_OPERANDS = '+str(default)+','
        text = once(original, marker, marker+'\n    parameter integer FAST_STORE_WB_DATA = '+str(default)+',')
        if '/backend/' in name:
            old = '''            // Matching WB uses the original RS execution fallback, even if
            // a stored value was already ready. No extra D hold is introduced.
            wire operands_qualified=(FAST_STORE_SAVED_ACTIVE!=0) ?
                (prf_read_stored_ready[2*ready_store_lane] &&
                 prf_read_stored_ready[2*ready_store_lane+1] &&
                 !prf_read_bypass_pending[2*ready_store_lane] &&
                 !prf_read_bypass_pending[2*ready_store_lane+1]) :
                (lsq_alloc_addr_valid[ready_store_lane] && lsq_alloc_data_valid[ready_store_lane]);'''
            new = '''            // The base must still be saved and cannot have a current WB:
            // its saved address flags must describe the actual LSQ address.
            // Data has no address-class role. Allow its original WB readiness
            // and exact original LSQ data capture, without a data-value test.
            wire data_qualified=(FAST_STORE_WB_DATA!=0) ?
                (prf_read_stored_ready[2*ready_store_lane+1] ||
                 prf_read_bypass_pending[2*ready_store_lane+1]) :
                (prf_read_stored_ready[2*ready_store_lane+1] &&
                 !prf_read_bypass_pending[2*ready_store_lane+1]);
            wire operands_qualified=(FAST_STORE_SAVED_ACTIVE!=0) ?
                (prf_read_stored_ready[2*ready_store_lane] &&
                 !prf_read_bypass_pending[2*ready_store_lane] && data_qualified) :
                (lsq_alloc_addr_valid[ready_store_lane] && lsq_alloc_data_valid[ready_store_lane]);'''
            text = once(text,old,new)
            start = '    // Count raw D demand before gating either allocator,'
            assert text[text.index(start):] == original[original.index(start):]
        else:
            text = once(text,'.FAST_STORE_SAVED_OPERANDS(FAST_STORE_SAVED_OPERANDS)',
                '.FAST_STORE_SAVED_OPERANDS(FAST_STORE_SAVED_OPERANDS), .FAST_STORE_WB_DATA(FAST_STORE_WB_DATA)')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_FAST_STORE_WB_DATA_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],FAST_STORE_WB_DATA=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],FAST_STORE_WB_DATA=1,
        fast_store_wb_data_new_ff_bits=0,fast_store_wb_data_new_sram_bits=0,fast_store_wb_data_new_pipeline_edges=0,
        fast_store_base_still_requires_saved_ready_and_no_wb=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'While saved-base/no-base-WB keeps fast-store address classification independent of current WB value, data source may be original stored-ready OR matching legal WB-ready. Actual LSQ store data/ready, highest WB lane, real allocation and full ROB identity remain original. Superset of A92 fast candidates for same inputs, without reintroducing a WB-data-value/address-class cone. Parameter0 retains original strict both-saved/no-WB condition.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        wb_store_data_fast_completion_coverage_recovered_without_wb_address_classification=True,
        fast_store_wb_data_limit='A87 excluded both base and data matching WB; only base participates in RAM/alignment class. Current data WB-ready is a control bit and actual LSQ already captures exact PRF highest-WB data. Restores subset of A83 fast-store opportunities while retaining saved base and two-case capacity. Dynamic incidence, IPC, control-bit timing and mapped area unmeasured; running A92 remains frozen.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'A87 requires stored-ready and no current WB for both sources to disconnect WB value from store address legality. Address uses only src1+saved canonical immediate. Therefore data WB need not be excluded: src2 stored-ready OR original legal matching-WB flag is exactly original PRF public data readiness, including P0/out-of-range/duplicate WB source handling. Base remains original stored-ready AND no matching base WB, so actual LSQ address still equals saved fallback flags.',
            'Original actual LSQ data value uses original public PRF read with highest matched WB lane; original data_valid requires valid store, early-data profile and src2-ready. New data-qualified implies those old data-ready terms. Explicit nonzero trace data still excludes all fast stores, so original ALU override is preserved. Any accepted fast store therefore captures the same authoritative data without a later ALU update. Only real LSQ allocation publishes fast ROB ready; full valid/row/GEN/type, ordered authorization/cache/ACK remain.',
            'For identical saved packet/PRF/current WB inputs, old strict data qualifier=stored_ready&&!WB implies new stored_ready||WB. Potential identity grant is unchanged and response data never enters address classifier. New ready candidates cannot remove an old fast-store eligibility for the same inputs; at most one store and the original two-case capacity equation/atomic D credit still hold. Dynamic aggregate IPC is not guaranteed monotonic.',
            'No current WB data value or data legality comparison is added to fast-store control. Current WB valid/physical identity already reached old !WB guard; changing data guard to ready-OR may change mapping but does not restore original data->base add/address class dependency. Actual LSQ data payload naturally still carries WB value. Base-current-WB/unready/misaligned/nonRAM/MMIO/explicit override tuples retain original RS/ALU execution.',
            'Parameter0 retains original A92 strict data condition; missing saved fast-store profile uses original public LSQ ready regardless of this new option. No PRF/LSQ/ROB/cache/RS/completion/rename state or ports are changed, no FF/SRAM/edge. No HDL/lint/formal/simulation/synthesis/STA/unit tests. Future coherent coverage includes all saved/WB source combinations, equal base/data phys, highest duplicate WB priority, invalid/P0 phys, actual data/error/capture and full GEN/recovery/MMIO/width/default/full RV32IM/course performance. Running A92 source and results cannot apply to A93.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
