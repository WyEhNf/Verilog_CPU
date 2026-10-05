"""Capture ready PRF store data into its original LSQ row at allocation."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A34_region_query_native_compat'
TARGET=BASE/'A35_alloc_ready_store_data'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/backend/rv32_backend_joint.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer STORE_ALLOC_EARLY_ADDRESS = 1,',
        '    parameter integer STORE_ALLOC_EARLY_ADDRESS = 1,\n    parameter integer STORE_ALLOC_EARLY_DATA = 0,')
    text=once(text,'''    wire [BE_WIDTH-1:0] lsq_alloc_data_valid = (EARLY_STORE_ADDRESS != 0) ?
        {BE_WIDTH{1'b0}} : (d_is_store & d_valid);''','''    localparam integer ALLOC_STORE_DATA_ACTIVE=(STORE_ALLOC_EARLY_DATA!=0) && (EARLY_STORE_ADDRESS!=0);
    // D owns renamed physical sources. A ready src2 value is authoritative
    // even before this store reaches RS issue. Unknown sources retain the
    // original execution update and never advertise allocation data ready.
    wire [BE_WIDTH-1:0] lsq_alloc_data_valid = ALLOC_STORE_DATA_ACTIVE ?
        (d_is_store & d_valid & rs_src2_ready) : ((EARLY_STORE_ADDRESS != 0) ?
        {BE_WIDTH{1'b0}} : (d_is_store & d_valid));
    wire [BE_WIDTH*32-1:0] lsq_alloc_store_data;
    generate for(genvar store_data_lane=0;store_data_lane<BE_WIDTH;store_data_lane=store_data_lane+1) begin:g_alloc_store_data
        assign lsq_alloc_store_data[store_data_lane*32 +: 32]=ALLOC_STORE_DATA_ACTIVE ?
            rs_src2_value[store_data_lane*32 +: 32] : d_store_data[store_data_lane*32 +: 32];
    end endgenerate''')
    text=once(text,'.alloc_data_valid_i(lsq_alloc_data_valid), .alloc_store_data_i(d_store_data)',
        '.alloc_data_valid_i(lsq_alloc_data_valid), .alloc_store_data_i(lsq_alloc_store_data)')
    # Only allocation data inputs change. RS store metadata and the actual
    # ALU store update remain the parent's operands; no new completion path.
    assert '.alloc_store_data_i(d_store_data), .alloc_ready_o(rs_alloc_ready)' in text
    assert '.data_update_i(alu_exec_store_data)' in text
    marker='    // Rename and PRF form the operand/producer boundary.'
    old_suffix=original[original.index(marker):]
    new_suffix=text[text.index(marker):].replace(
        '.alloc_store_data_i(lsq_alloc_store_data)', '.alloc_store_data_i(d_store_data)')
    assert new_suffix==old_suffix
    changes[name]=text
    for name in ['rtl/cpu_core.v','rtl/course/student_top.v']:
        original=(PARENT/name).read_text(encoding='utf-8')
        default=1 if name.endswith('student_top.v') else 0
        anchor='    parameter integer EARLY_STORE_ADDRESS = '
        assert original.count(anchor)==1
        offset=original.index('\n',original.index(anchor))
        text=original[:offset]+f'\n    parameter integer STORE_ALLOC_EARLY_DATA = {default},'+original[offset:]
        text=once(text,'.EARLY_STORE_ADDRESS(EARLY_STORE_ADDRESS),',
            '.EARLY_STORE_ADDRESS(EARLY_STORE_ADDRESS), .STORE_ALLOC_EARLY_DATA(STORE_ALLOC_EARLY_DATA),')
        changes[name]=text
    for name in parent['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():(TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['parameter_overrides']=dict(parent['parameter_overrides'],STORE_ALLOC_EARLY_DATA=1)
    record['enabled_profile']=dict(parent['enabled_profile'],STORE_ALLOC_EARLY_DATA=1,
        ready_store_allocation_data_added_state_bits=0,ready_store_allocation_data_added_prf_ports=0,
        store_execution_and_rob_completion_retained=True)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Capture already-ready renamed PRF src2 into the existing LSQ store-data row at D allocation; allow existing load forwarding/hazard selection before store ALU completion, retain store execution/in-order commit/MMIO acknowledgement.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        original_early_store_mode_allocation_data_always_invalid=True,
        ready_store_data_allocation_reuses_prf_read_port=True,
        ready_store_data_added_state_bits=0,
        ready_store_data_allocation_benefit_trigger_and_ppa_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_READY_PRF_STORE_DATA_EARLY_ALLOCATION_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),
        added_state_bits=0,added_prf_ports=0,added_pipeline_edges=0,tests_started=False,adopted=False,
        source_arguments=[
            'Old EARLY_STORE_ADDRESS!=0 hardwired all allocation data-valid bits to zero. A35 optionally advertises data only for a valid store whose original RS src2 readiness is true, using the same PRF operand value that original RS allocation captures.',
            'Renamed physical identity and original readiness rule remain unchanged: P0 is ready zero; PRF-ready supplies allocated physical values; direct dispatch retains its explicit same-bundle producer dependency rejection, while pipelined D sees earlier rename allocation already clear PRF ready.',
            'No current wake value is injected into the allocation PRF read. A source not yet ready, including a same-edge completion, follows the original RS wake/ALU issue/store update path. This conservative missed opportunity preserves the register boundary.',
            'LSQ original allocation writes tag/generation/valid/data/data_ready on the same edge. A33 can then allow subsequent loads behind known stores; an earlier same-bundle store with ready address/data also satisfies its guard. Original next-cycle youngest-older byte forwarding chooses overlap.',
            'Store still allocates/issues in RS and sends the original ALU completion to ROB. The early copy cannot itself retire a store, write the cache, acknowledge MMIO or add a ROB/CDB completion producer.',
            'Later original ALU data update uses the same immutable renamed operand and full ROB-tag matching. All LSQ source, all clocked backend logic, store commit/ack, masks, forwarding/recovery/backpressure logic are unchanged.',
            'RS independent store data remains the original d_store_data zero from the course trace caller; it is not made another PRF copy. Disabled mode and legacy EARLY_STORE_ADDRESS=0 retain the original trace-based allocation payload and validity.',
            'This adds live 32-bit allocation data mux inputs per D lane and small readiness qualification to existing LSQ owners, with no new FF or PRF ports. It may increase mapped area and PRF-to-LSQ delay; exact area/IPC/Fmax remain unmeasured.',
            'No HDL build, lint, simulation, synthesis, STA, CPU/perf or unit tests. Later meaningful coverage includes zero/nonzero ready stores, not-ready/just-waking operands, same-bundle dependencies, byte/halfword forwarding, younger speculative stores, slot wrap/reuse and terminal MMIO order.'
        ])
    write(BASE/'A35_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':main()
