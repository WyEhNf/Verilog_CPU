"""Count unique in-flight destination owners before physical bitmap decode."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A66_rat_suffix_branch_mapping'
TARGET = BASE/'A67_rob_unique_reclaim_count'
REVIEW = BASE/'A67_source_review.json'


def once(text, old, new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/backend/rv32_rob.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer CHECKPOINT_IMPL = 0,',
        '''    parameter integer CHECKPOINT_IMPL = 0,
    // Caller guarantees distinct nonzero physical destinations for all live
    // rd-writing entries. Default preserves arbitrary duplicate-input handling.
    parameter integer RECLAIM_UNIQUE_DESTINATIONS = 0,''')
    marker='    initial begin\n        if ((BE_WIDTH != 1) && (BE_WIDTH != 2) && (BE_WIDTH != 4)) begin'
    count='''    wire [RECLAIM_COUNT_WIDTH-1:0] recovery_reclaim_count;
    generate if(RECLAIM_UNIQUE_DESTINATIONS!=0) begin:g_unique_reclaim_count
        // Bitmap decode and count are parallel. Each qualified ROB owner
        // contributes one; no late physical decoder/OR feeds the count tree.
        localparam integer ROW_LEAVES=1<<SLOT_WIDTH;
        wire [RECLAIM_COUNT_WIDTH-1:0] counts [1:2*ROW_LEAVES-1];
        for(genvar row=0;row<ROW_LEAVES;row=row+1) begin:g_leaf
            if(row<ROB_ENTRIES) begin:g_present
                wire [PHYS_ADDR_WIDTH-1:0] destination=new_phys_mem[row];
                assign counts[ROW_LEAVES+row]=reclaim_eligible[row] &&
                    destination!=0 && destination<PHYS_REGS;
            end else begin:g_padding
                assign counts[ROW_LEAVES+row]=0;
            end
        end
        for(genvar node=1;node<ROW_LEAVES;node=node+1) begin:g_sum
            assign counts[node]=counts[2*node]+counts[2*node+1];
        end
        assign recovery_reclaim_count=counts[1];
    end else begin:g_distinct_bitmap_reclaim_count
        assign recovery_reclaim_count=reclaim_count_tree[1];
    end endgenerate

'''
    text=once(text,marker,count+marker)
    text=once(text,'        recovery_reclaim_count_o = reclaim_count_tree[1];',
        '        recovery_reclaim_count_o = recovery_reclaim_count;')
    # Reclaim bitmap, exact validity/age/GEN and all state writes remain exact.
    a='    // Decode killed destinations in parallel.'
    b=marker
    assert text[text.index(a):text.index(count)]==original[original.index(a):original.index(b)]
    tail='        if (recovery_preview_domains[2]) begin'
    assert text[text.index(tail):]==original[original.index(tail):]
    changes[name]=text
    name='rtl/backend/rv32_backend_joint.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer ROB_ALLOC_BANKED_WRITE = 0,',
        '    parameter integer ROB_ALLOC_BANKED_WRITE = 0,\n    parameter integer ROB_UNIQUE_RECLAIM_COUNT = 0,')
    text=once(text,'.ALLOC_BANKED_WRITE(ROB_ALLOC_BANKED_WRITE),',
        '.ALLOC_BANKED_WRITE(ROB_ALLOC_BANKED_WRITE), .RECLAIM_UNIQUE_DESTINATIONS(ROB_UNIQUE_RECLAIM_COUNT),')
    assert '.REGISTERED_FREE_POOL(1)' in text
    changes[name]=text
    for name,default in [('rtl/cpu_core.v',0),('rtl/course/student_top.v',1)]:
        text=(PARENT/name).read_text(encoding='utf-8')
        text=once(text,f'    parameter integer ROB_ALLOC_BANKED_WRITE = {default},',
            f'    parameter integer ROB_ALLOC_BANKED_WRITE = {default},\n    parameter integer ROB_UNIQUE_RECLAIM_COUNT = {default},')
        text=once(text,'.ROB_ALLOC_BANKED_WRITE(ROB_ALLOC_BANKED_WRITE),',
            '.ROB_ALLOC_BANKED_WRITE(ROB_ALLOC_BANKED_WRITE), .ROB_UNIQUE_RECLAIM_COUNT(ROB_UNIQUE_RECLAIM_COUNT),')
        changes[name]=text
    for name in parent['source_sha256']:
        destination=TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(status='SOURCE_ROB_UNIQUE_RECLAIM_COUNT_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_from_parent_files=list(changes),
        source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),
        tests_started=False,synthesis_started=False,timing_started=False,adopted=False,
        candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides']=dict(parent['parameter_overrides'],ROB_UNIQUE_RECLAIM_COUNT=1)
    record['enabled_profile']=dict(parent['enabled_profile'],rob_unique_reclaim_count=True,
        reclaim_count_bitmap_decode_bypassed=True,reclaim_row_leaves=32,reclaim_physical_leaves_legacy=64,
        reclaim_new_ff_bits=0,reclaim_new_sram_bits=0,reclaim_new_pipeline_edges=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Use the backend unique in-flight physical-destination invariant to sum qualified killed ROB writers before physical decoding. The exact reclaim bitmap and full recovery/age/GEN authority remain unchanged. Count path bypasses per-physical destination decoding and row OR; standalone default retains distinct-bit counting for duplicate inputs.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        reclaim_unique_owner_source_argument=True,reclaim_count_removed_dependency='physical destination predecode -> physical column OR -> physical bitmap popcount',
        reclaim_count_area_frequency_gain_unknown=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_ROB_UNIQUE_RECLAIM_COUNT_UNTESTED',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),tests_started=False,adopted=False,
        new_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,exact_reclaim_bitmap_unchanged=True,
        course_row_sum_leaves=32,course_legacy_physical_sum_leaves=64,
        source_arguments=[
            'Each accepted destination writer removes one distinct nonzero physical register from the free pool. Registers cannot return to that pool while their allocating ROB writer remains valid: normal commit releases old_phys of a retired replacing instruction in strict order, by which time any older allocating writer has retired; recovery returns only destinations of the suffix whose ROB validity clears on that same edge. No new rename occurs on restore.',
            'Thus all valid ROB rd-writer new_phys values are pairwise distinct under the backend allocator contract. Restricting them to the existing generation-qualified killed suffix preserves distinctness. After excluding zero/out-of-range destinations exactly as the physical bitmap does, each eligible row contributes exactly one set reclaim bit. Summing rows equals counting distinct bitmap bits.',
            'The reclaim bitmap still uses the original destination predecoders and row reductions byte-for-byte. Reclaim eligibility still uses original recovery_row_preview, rd_we and qualified recovery_preview_kill; no branch age, occupancy, live or GEN guard is removed. Only the count output chooses the separate row sum in enabled mode.',
            'Default0 keeps the original count for arbitrary duplicate physical destinations in standalone ROB tests. Backend/core default0 preserve the mode; course top1 enables the unique-owner contract of the unchanged registered free pool and strict commit/recovery owners. No FF/SRAM/pipeline state is introduced.',
            'The enabled count path is row eligibility/nonzero/bounds ->32-leaf balanced sum ->free count restore, parallel with bitmap construction. Legacy is destination predecode ->32-row column OR ->64-leaf physical sum ->restore. Actual mapped depth, area and Fmax remain unmeasured; old unused count logic must be pruned by synthesis.',
            'Manual legal-state invariant argument and exact source-block checks only, not HDL equivalence or measured gain. Future batch covers consecutive writes to one architectural destination, simultaneous older commits/new allocations, full/empty/free pool, branch capture with older commits, head/tail wrap, repeated recoveries, physical/ROB size variations and mode0 duplicate-destination fallback before adoption.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','changed_files','tests_started')})


if __name__=='__main__':
    main()
