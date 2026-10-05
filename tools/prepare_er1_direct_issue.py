"""Prepare a coherent direct-issue candidate while keeping local recovery guards."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
from manage_frozen_baseline_programs import read, sha, write
from review_frequency_dx_sources import blocks

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A7_mmio_retire_value'
TARGET=BASE/'A8_direct_issue_local_recovery'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists(),TARGET
    pm=read(PARENT/'candidate.json')
    for name,digest in pm['source_sha256'].items():assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/backend/rv32_backend_joint.v';text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer ISSUE_PIPELINE = 0,',
        '''    parameter integer ISSUE_PIPELINE = 0,
    // Execution registers need selective cancellation even when RS issues
    // directly. Default retains the standalone configuration relation.
    parameter integer LOCAL_EXEC_RECOVERY = (ISSUE_PIPELINE!=0),''')
    text=once(text,'''    // Local ownership is used only with the recovery-aware issue FIFO.
    localparam integer LOCAL_EXEC_RECOVERY=(ISSUE_PIPELINE!=0);''',
        '''    // Recovery guards are independent from the optional issue queue.
    // Core callers retain them for held ALU/MDU/LSQ results in direct mode.''')
    changes[name]=text
    name='rtl/cpu_core.v';text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,' .DISPATCH_PIPELINE(1), .ISSUE_PIPELINE(ISSUE_PIPELINE),',
        ' .DISPATCH_PIPELINE(1), .ISSUE_PIPELINE(ISSUE_PIPELINE), .LOCAL_EXEC_RECOVERY(1),')
    changes[name]=text
    name='rtl/course/student_top.v';text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'parameter integer DECODE_PIPELINE = 1, ISSUE_PIPELINE = 1,',
        'parameter integer DECODE_PIPELINE = 1, ISSUE_PIPELINE = 0,')
    changes[name]=text
    for name,text in changes.items():assert blocks(text)==blocks((PARENT/name).read_text(encoding='utf-8')),name
    for name in pm['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():(TARGET/name).write_text(text,encoding='utf-8')
    definitions=(TARGET/'rtl/rv32im_defs.vh').read_text(encoding='utf-8')
    op_width=int(re.search(r'`define\s+RV32IM_OP_WIDTH\s+(\d+)',definitions).group(1))
    tag_width=1+2+5+8
    payload_width=op_width+32+tag_width+6+32+32+32+70+3
    declared_queue_bits=4*(2*(payload_width+tag_width)+2+2+1+1)
    record=dict(pm)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={n:sha(TARGET/n) for n in pm['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),ordinary_integer_pipeline_depth=9)
    record['parameter_overrides']=dict(pm['parameter_overrides'],ISSUE_PIPELINE=0)
    record['enabled_profile']=dict(pm['enabled_profile'],LOCAL_EXEC_RECOVERY=1,
        ISSUE_PIPELINE=0,removed_issue_queue_declared_bits=declared_queue_bits)
    record['implemented_changes']=list(pm['implemented_changes'])+[
        'Use existing direct RS-to-registered-ALU path: one fewer dependency cycle, no two-entry issue buffers.',
        'Keep original local selective recovery/wakeup guards independently enabled for ALU/MDU/LSQ results.'
    ]
    record['material_gain_evidence']={
        'ready_base_load_ideal_allocation_to_prf_edges_ER1':8,
        'ready_base_load_ideal_allocation_to_prf_edges_candidate':4,
        'assumptions':'No older-store hazard, forwarding, request conflict, cache miss, queue/CDB backpressure or recovery; complete-source edge analysis only.',
        'dependent_alu_issue_boundary_cycles_removed':1,
        'unused_ROB_payload_bits_removed_at_ROB32':4224,
        'issue_queue_declared_bits_removed':declared_queue_bits,
        'sram_area_reduction_shape_formula_um2':3525.849900,
        'not_measured_ipc_or_ppa':True
    }
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_REVIEW_ONLY_NOT_FULL_CORE_PROOF',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),parent_sha256=sha(PARENT/'candidate.json'),
        changed_files=list(changes),new_state_bits=0,pipeline_cycles_removed=1,
        source_clocked_blocks_text_equal=True,tests_started=False,adopted=False,
        declared_issue_queue_capacity_removed_bits=declared_queue_bits,
        timing_risk='RS wake/age selection/operand read and ALU computation now share a cycle; candidate Fmax is unknown.',
        reasoning=[
            'ISSUE_PIPELINE=0 selects the existing direct generate branch; RS releases only when the selected ALU/MDU accepts.',
            'ALU result register and MDU/result ownership remain. Unaccepted RS work retains operands, full tag and metadata.',
            'RS valid selection depends on ready candidates, not downstream ready. ALU ready depends on registered output occupancy and cancellation, avoiding a ready/selection loop.',
            'INT_ISSUE_WIDTH=BE_WIDTH=4 preserves integer lane eligibility; the existing oldest selected MDU routing accepts only one MDU.',
            'LOCAL_EXEC_RECOVERY remains1, preserving local ALU/MDU cancellation, LSQ reporting and direct producer wake qualification from A7.',
            'During branch_pending/recovery no new executor acceptance is permitted; RS selective kill and held-result age guards preserve older work and cancel younger work.',
            'Full ROB valid+generation qualification before CDB/PRF and existing LSQ tag checks remain unchanged.',
            'Default standalone backend still derives local recovery from its issue option; CPU explicitly keeps selective guards in either mode.',
            'Removing the issue buffer shortens normal dependent ALU/AGU/branch chains by one acceptance edge when unblocked; actual IPC is unmeasured.',
            'Mapped area and setup timing need one complete candidate measurement; no frequency inference from ER1 is claimed.'
        ])
    write(BASE/'A8_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','declared_issue_queue_capacity_removed_bits','tests_started')})


if __name__=='__main__':main()
