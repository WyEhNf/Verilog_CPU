"""Retain unused free-pool ownership through recovery; no HDL execution."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A67_rob_unique_reclaim_count'
TARGET=BASE/'A68_retain_free_pool_restore'
REVIEW=BASE/'A68_source_review.json'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/rv32_rename_unit.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer REGISTERED_FREE_POOL = 0,',
        '''    parameter integer REGISTERED_FREE_POOL = 0,
    // Caller restores the complete logical free set, including current unused
    // pool entries, and prevents architectural rename on that restore edge.
    parameter integer RETAIN_FREE_POOL_ON_RESTORE = 0,''')
    text=once(text,'''        // Restore receives the complete logical free bitmap, including all
        // previous pool entries. Return them and refill from that new bitmap.
        if(reset_i || restore_valid_i || REGISTERED_FREE_POOL==0) pool_count<=0;
        else pool_count<=pool_next_count;''',
        '''        // Payload writes remain suppressed on restore. Retained unused
        // candidates already belong to the restored free set; no new priority
        // search or instruction acceptance occurs on this recovery edge.
        if(reset_i || REGISTERED_FREE_POOL==0) pool_count<=0;
        else if(restore_valid_i) begin
            if(RETAIN_FREE_POOL_ON_RESTORE==0) pool_count<=0;
        end else pool_count<=pool_next_count;''')
    text=once(text,'''                else if(rename_restore_views[32+free_word])
                    bits_next=restore_free_bitmap_i[LOW +: BITS];''',
        '''                else if(rename_restore_views[32+free_word]) begin
                    // Keep logical F as disjoint owners: unreserved F\\P and
                    // the unchanged unused pool P. Export still returns F.
                    if(REGISTERED_FREE_POOL!=0 && RETAIN_FREE_POOL_ON_RESTORE!=0)
                        bits_next=restore_free_bitmap_i[LOW +: BITS] & ~pool_bitmap[LOW +: BITS];
                    else bits_next=restore_free_bitmap_i[LOW +: BITS];
                end''')
    # Existing pool payload enable excludes reset and restore; current P is
    # exported in the original logical free state. All normal paths stay exact.
    for marker in [
        'REGISTERED_FREE_POOL!=0 && !reset_i && !restore_valid_i && pool_write[pool_index]',
        'assign free_bitmap_state_o = (REGISTERED_FREE_POOL!=0)?(free_bitmap | pool_bitmap):free_bitmap;',
        'available_for_rename=(REGISTERED_FREE_POOL!=0)?pool_count:free_count;',
        'free_count <= restore_free_count_i;',
    ]:
        assert marker in text,marker
    a='    // Preselect the first BE_WIDTH free physical registers from registered'
    assert text[text.index(a):]==original[original.index(a):]
    changes[name]=text
    name='rtl/backend/rv32_backend_joint.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer RAT_READ_BYPASS = 0,',
        '    parameter integer RAT_READ_BYPASS = 0,\n    parameter integer RENAME_RETAIN_FREE_POOL = 0,')
    text=once(text,'.REGISTERED_FREE_POOL(1)) rename (',
        '.REGISTERED_FREE_POOL(1), .RETAIN_FREE_POOL_ON_RESTORE(RENAME_RETAIN_FREE_POOL)) rename (')
    for marker in [
        'recovery_free_bitmap = free_bitmap_state | recovery_descriptor_reclaim;',
        'recovery_free_count = free_count + recovery_descriptor_reclaim_count;',
        '.rename_ready_i(!halted_o && !flush_i && !branch_busy_domains[1] && dispatch_packet_ready)',
    ]:
        assert marker in text,marker
    changes[name]=text
    for name,default in [('rtl/cpu_core.v',0),('rtl/course/student_top.v',1)]:
        text=(PARENT/name).read_text(encoding='utf-8')
        text=once(text,f'    parameter integer RAT_READ_BYPASS = {default},',
            f'    parameter integer RAT_READ_BYPASS = {default},\n    parameter integer RENAME_RETAIN_FREE_POOL = {default},')
        text=once(text,'.RAT_READ_BYPASS(RAT_READ_BYPASS),',
            '.RAT_READ_BYPASS(RAT_READ_BYPASS), .RENAME_RETAIN_FREE_POOL(RENAME_RETAIN_FREE_POOL),')
        changes[name]=text
    for name in parent['source_sha256']:
        destination=TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(status='SOURCE_RETAIN_FREE_POOL_RESTORE_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_from_parent_files=list(changes),
        source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),
        tests_started=False,synthesis_started=False,timing_started=False,adopted=False,
        candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides']=dict(parent['parameter_overrides'],RENAME_RETAIN_FREE_POOL=1)
    record['enabled_profile']=dict(parent['enabled_profile'],retain_free_pool_on_restore=True,
        restored_logical_free_set_unchanged=True,restore_priority_encoder_added=False,
        new_ff_bits_for_pool_restore=0,new_sram_bits_for_pool_restore=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Preserve current unused free-pool payload/count on recovery and restore unreserved bits as logical_free minus that pool. The backend already exports unused pooled registers in its logical free bitmap and blocks rename on restore. Free count and restored RAT are unchanged; nonempty saved candidates can serve the first post-recovery rename without an extra refill edge.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        free_pool_restore_ownership_argument=True,one_refill_wait_edge_avoided_when_pool_nonempty=True,
        free_pool_restore_limit='Pool-empty recovery still needs refill; target fetch/decode readiness can hide the benefit. No measured or guaranteed useful-cycle gain.')
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_RETAIN_FREE_POOL_RESTORE_UNTESTED',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),tests_started=False,adopted=False,
        new_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,new_priority_encoder=False,
        source_arguments=[
            'Let P be the current pool bitmap and U the unreserved bitmap. Existing logical free state is U union P. Current pool entries are unused, pairwise distinct nonzero registers; accepting an allocation removes that candidate before subsequent pool state. The backend supplies restored logical F=(U union P) union qualified younger destination reclaim, so P is a subset of F.',
            'On restore backend branch_pending blocks architectural rename and direct/staged ROB apply blocks commit/allocation. Pool payload writes already exclude restore. Retain count and payload P, restore unreserved bits to F minus P, and retain the original free_count=|F| restore. Exported logical free state becomes (F minus P) union P=F exactly, with disjoint pool and bitmap owners.',
            'Next ordinary refill searches only F minus P, so it cannot select any retained pool candidate twice. Allocation removes a prefix of P and normal compaction/refill/commit priority remains original. Reset still clears count; REGISTERED_FREE_POOL0 still clears count and restores the ordinary bitmap. Option0 restores original clear-and-refill behavior.',
            'No raw priority encoding is introduced on the recovery path. The only new restore data operation is a bitwise exclusion of the registered pool bitmap already used to export logical free state. No FF/SRAM/ordinary pipeline edge is added. Pool-empty recovery still refills normally.',
            'Manual source ownership/set argument only, not formal equivalence or measured IPC/area/frequency. Future coherent batch must cover pool counts0/1/2, captured-edge allocation/normal refill, later restore, head/ROB/physical reuse, several consecutive redirects, empty free bitmap, first post-recovery dual rename, reset/flush, widths1/2/4, option0 and unregistered fallback. Backend contract is required for enabled standalone tuples.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','changed_files','tests_started')})


if __name__=='__main__':
    main()
