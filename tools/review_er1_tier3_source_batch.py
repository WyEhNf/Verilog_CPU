"""Source-only review of ER1 early-load and capacity candidates; no tests."""
from pathlib import Path
import re
from manage_frozen_baseline_programs import ROOT, read, sha, write
from review_frequency_dx_sources import blocks
from prepare_er1_tier3_source_batch import PARENT, BASE


def main():
    out=BASE/'source_review.json'
    assert not out.exists()
    parent=read(PARENT/'candidate.json')
    a1=BASE/'A1_early_load_allocation'
    a2=BASE/'A2_early_load_r32_p56_rs8_d512'
    reviews=[]
    for candidate in (a1,a2):
        manifest=read(candidate/'candidate.json')
        clock_count=0
        changed=[]
        for name,expected in manifest['source_sha256'].items():
            assert sha(candidate/name)==expected
            if expected!=parent['source_sha256'][name]:changed.append(name)
            if name.endswith('.v'):
                old=blocks((PARENT/name).read_text(encoding='utf-8'))
                new=blocks((candidate/name).read_text(encoding='utf-8'))
                assert old==new,name
                clock_count+=len(new)
        assert set(changed)=={'rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v','rtl/backend/rv32_lsq.v'}
        # LSQ transactions and hazards are unchanged except legal spelling.
        old=(PARENT/'rtl/backend/rv32_lsq.v').read_bytes()
        new=(candidate/'rtl/backend/rv32_lsq.v').read_bytes()
        assert new.replace(b'response_query_matches',b'matches')==old
        text=(candidate/'rtl/backend/rv32_backend_joint.v').read_text(encoding='utf-8')
        assert '((EARLY_LOAD_ADDRESS != 0) && d_is_load[io_lane])) && rs_src1_ready[io_lane];' in text
        assert 'alu_exec_valid[io_lane] && alu_exec_is_memory[io_lane]' in text
        # Address enabled only from the original current PRF value/ready path;
        # same ordinary AGU and full LSQ-tag update remain in the source.
        reviews.append(dict(candidate=str(candidate),candidate_sha256=sha(candidate/'candidate.json'),
                            changed_files=changed,compound_clocked_blocks_text_equal=clock_count,
                            new_declared_state_bits=0,ordinary_AGU_kept=True,
                            LSQ_except_identifier_bytes_equal=True,tests_started=False,adopted=False))
    # A2 differs from A1 solely in four exposed resource defaults.
    for name in parent['source_sha256']:
        if name!='rtl/course/student_top.v':assert sha(a1/name)==sha(a2/name),name
    top1=(a1/'rtl/course/student_top.v').read_text(encoding='utf-8')
    top2=(a2/'rtl/course/student_top.v').read_text(encoding='utf-8')
    for key,value in dict(ROB_ENTRIES=64,PHYS_REGS=64,RS_ENTRIES=12,DCACHE_LINES=1024).items():
        top2,count=re.subn(r'\b'+key+r'\s*=\s*\d+',key+' = '+str(value),top2,count=1)
        assert count==1
    assert top1==top2
    active=read(ROOT/'build/cpu2026/active_frequency_implementation_20261004.json')
    for name,expected in active['source_sha256'].items():assert sha(ROOT/name)==expected,name
    frozen=Path(active['frozen_run'])
    current=read(frozen/'source_manifest.json')
    for name,expected in current['snapshot_sha256'].items():assert sha(frozen/'source'/name)==expected,name
    proof=dict(status='SOURCE_REVIEW_ONLY_NO_FUNCTIONAL_PROOF', candidates=reviews,
               parent_candidate_sha256=sha(PARENT/'candidate.json'),
               parameter_only_difference_between_candidates=True,
               source_lifecycle_reasoning=[
                   'Load immediates are the sign-extended I-type 12-bit offset. Existing allocation simm12 address equals the RS-captured ready base plus that offset modulo 2^32.',
                   'The original rs_src1_ready includes zero-register behavior, qualified WB bypass and same-bundle dependency suppression. No new ready shortcut is introduced.',
                   'LSQ allocation atomically captures its full generation-qualified tag, ROB tag, memory kind/size, address and ready. All older-store address/data hazards and forwarding permission equations are unchanged.',
                   'Ordinary RS allocation and AGU issue remain. Later identical-address AGU updates retain full LSQ tag checks and original overwrite priority. ALU load results do not become a second CDB completion.',
                   'Recovery, stale response handling and live ROB checks retain original implementation. Earlier speculation is still a behavior change requiring later whole-core correctness evidence.',
                   'A2 retains issue/dispatch widths and MSHR counts but reduces storage/selection capacities. Queue pressure and cache misses may counter IPC gains; no performance prediction is certified.'
               ],
               open_risks=['Early-load scheduling, normal AGU redundant updates and recovery/retirement boundaries need the eventual unified functional run.',
                           'The A2 parameter profile needs width/padding source audit and actual area/frequency/IPC measurement before adoption.'],
               main_and_current_frozen_source_unchanged=True,new_test_started=False)
    write(out,proof)
    print(read(out)['candidates'])


if __name__=='__main__':main()
