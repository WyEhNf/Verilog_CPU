"""Prepare one structural width/cache tradeoff, without parameter sweeps."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A13_load_address_lookthrough'
TARGET=BASE/'A14_two_wide_backend_er1_dcache'
VALUES={'BE_WIDTH':2,'INT_ISSUE_WIDTH':2,'CDB_WIDTH':2,'DCACHE_LINES':1024}


def main():
    assert not TARGET.exists(),TARGET
    pm=read(PARENT/'candidate.json')
    for name,digest in pm['source_sha256'].items():assert sha(PARENT/name)==digest,name
    name='rtl/course/student_top.v';old=(PARENT/name).read_text(encoding='utf-8');text=old
    before={}
    for key,value in VALUES.items():
        pattern=r'\b'+key+r'\s*=\s*(\d+)'
        matches=list(re.finditer(pattern,text));assert len(matches)==1,key
        before[key]=int(matches[0].group(1))
        text=re.sub(pattern,key+' = '+str(value),text)
    for name in pm['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name,dest)
    (TARGET/'rtl/course/student_top.v').write_text(text,encoding='utf-8')
    record=dict(pm)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=['rtl/course/student_top.v'],
        source_sha256={n:sha(TARGET/n) for n in pm['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)))
    record['parameter_overrides']=dict(pm['parameter_overrides'],**VALUES)
    record['enabled_profile']=dict(pm['enabled_profile'],**VALUES,
        ROB_ENTRIES=32,PHYS_REGS=56,RS_ENTRIES=8,LSQ_ENTRIES=16,
        prf_dispatch_read_ports=4,direct_completion_sources=4)
    record['implemented_changes']=list(pm['implemented_changes'])+[
        'Use one two-wide dispatch/execute/retire backend with four-wide fetch, and restore the measured ER1 1024-line two-way D-cache working capacity.'
    ]
    record['material_gain_evidence']=dict(pm['material_gain_evidence'],
        backend_width_tradeoff_before=before,backend_width_tradeoff_after=VALUES,
        prf_read_ports_before=8,prf_read_ports_after=4,
        integer_alu_instances_before=4,integer_alu_instances_after=2,
        backend_max_retire_per_edge_before=4,backend_max_retire_per_edge_after=2,
        completion_sources_before=6,completion_sources_after=4,
        completion_lanes_before=3,completion_lanes_after=2,
        dcache_data_bytes_before=8192,dcache_data_bytes_after=16384,
        sram_area_expected_um2=7825.666854,
        sram_increase_relative_to_a8_um2=3525.8499,
        mapped_area_and_ipc_not_predicted=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_STRUCTURAL_TRADEOFF_UNTESTED_NOT_FULL_CORE_PROOF',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_sha256=sha(PARENT/'candidate.json'),parameter_changes=dict(before=before,after=VALUES),
        changed_files=['rtl/course/student_top.v'],tests_started=False,adopted=False,
        rationale=[
            'A8 measured total area37638.0513um2 and IPC0.76398585. Its rsort cycle count244978 is32.894% above ER1 184341; cause is not isolated, cache capacity/resource pressure remain competing explanations.',
            'Restored D-cache geometry is the measured ER1 geometry, preserving its16KiB working capacity and known SRAM cost. This adds3525.8499um2 versus A8 and must be paid for by logic reduction.',
            'One fixed two-wide backend halves dispatch PRF read ports and integer ALUs and reduces completion producers/selection lanes. It is an architectural tradeoff, not measured gain or a parameter sweep.',
            'Frontend remains four-wide and its FIFO emits only the contiguous accepted two-lane prefix; extra lanes stay queued. Branch predictor capacity/geometry and metadata are retained.',
            'ROB32, PRF56, RS8, LSQ16 and full tag generations stay unchanged. Registered one-edge L0 hits and dependent-load address lookthrough are retained.',
            'Two-wide in-order retirement still has a2IPC ceiling above the1.1 target, but lower burst execution/retirement bandwidth can worsen real IPC and correctness completion times.',
            'No tests, synthesis, STA, adoption or speculative area/IPC claims are made for this candidate. Further source area cuts remain necessary before selecting the next unified measurement.'
        ])
    write(BASE/'A14_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':main()
