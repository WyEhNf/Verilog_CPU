"""Distribute the unchanged actual LSQ allocation-fire bits to row owners."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import ROOT, read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A103_report_recovery_age_width'
TARGET=BASE/'A104_lsq_alloc_fire_distribution'
REVIEW=BASE/'A104_source_review.json'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    assert sha(PARENT/'candidate.json')=='f6349d45fbb02afa9c9b845044e84f8fc72a27e43fb417585a694e8e2cc33f06'
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/backend/rv32_lsq.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    marker='    parameter integer ALLOC_SLOT_PRESELECT = 0,'
    text=once(original,marker,marker+'\n    parameter integer ALLOC_FIRE_DISTRIBUTE = 0,')
    marker='    assign alloc_ready_o = !flush_i && (free_count_calc != 0);'
    text=once(text,marker,marker+'''

    localparam integer ALLOCATION_FIRE_DOMAINS=(LSQ_ENTRIES+3)/4;
    wire [BE_WIDTH*ALLOCATION_FIRE_DOMAINS-1:0] allocation_fire_views;
    generate if(ALLOC_FIRE_DISTRIBUTE!=0) begin:g_allocation_fire_distribution
        // Actual sparse allocation/count/capacity logic stays authoritative.
        // Each at-most-four-row domain drives its metadata and payload owners,
        // preventing one late admission bit from driving every row comparator.
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(ALLOCATION_FIRE_DOMAINS)) fire_tree (
            .signal_i(alloc_fire_o),.views_o(allocation_fire_views));
    end else begin:g_original_allocation_fire
        assign allocation_fire_views={ALLOCATION_FIRE_DOMAINS{alloc_fire_o}};
    end endgenerate''')
    text=once(text,'            assign allocations[payload_lane]=normal && alloc_fire_o[payload_lane] &&',
        '            assign allocations[payload_lane]=normal && allocation_fire_views[(payload_row/4)*BE_WIDTH+payload_lane] &&')
    text=once(text,'            assign alloc_matches[metadata_lane]=alloc_fire_o[metadata_lane] &&',
        '            assign alloc_matches[metadata_lane]=allocation_fire_views[(metadata_row/4)*BE_WIDTH+metadata_lane] &&')
    marker='    always @* begin\n        // Allocation/response temporaries retain unconditional defaults.'
    start=text.index(marker);end=text.index('    end\n',start)+8
    old_start=original.index(marker);old_end=original.index('    end\n',old_start)+8
    assert text[start:end]==original[old_start:old_end]
    changes[name]=text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original=(PARENT/name).read_text(encoding='utf-8')
        default=1 if name.endswith('student_top.v') else 0
        marker='    parameter integer LSQ_ALLOC_SLOT_PRESELECT = '+str(default)+','
        text=once(original,marker,marker+'\n    parameter integer LSQ_ALLOC_FIRE_DISTRIBUTE = '+str(default)+',')
        if '/backend/' in name:
            text=once(text,'.ALLOC_SLOT_PRESELECT(LSQ_ALLOC_SLOT_PRESELECT_ACTIVE)',
                '.ALLOC_SLOT_PRESELECT(LSQ_ALLOC_SLOT_PRESELECT_ACTIVE), .ALLOC_FIRE_DISTRIBUTE(LSQ_ALLOC_FIRE_DISTRIBUTE)')
        else:
            text=once(text,'.LSQ_ALLOC_SLOT_PRESELECT(LSQ_ALLOC_SLOT_PRESELECT)',
                '.LSQ_ALLOC_SLOT_PRESELECT(LSQ_ALLOC_SLOT_PRESELECT), .LSQ_ALLOC_FIRE_DISTRIBUTE(LSQ_ALLOC_FIRE_DISTRIBUTE)')
        changes[name]=text
    for name in parent['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():(TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(status='SOURCE_PREQUALIFIED_REPORT_RECOVERY_AND_DISTRIBUTED_LSQ_ALLOC_FIRE_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),source_root=str(TARGET),parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_from_parent_files=list(changes),
        source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},preparation_script_sha256=sha(Path(__file__)),
        source_review=str(REVIEW),tests_started=False,synthesis_started=False,timing_started=False,adopted=False,
        candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides']=dict(parent['parameter_overrides'],LSQ_ALLOC_FIRE_DISTRIBUTE=1)
    record['enabled_profile']=dict(parent['enabled_profile'],LSQ_ALLOC_FIRE_DISTRIBUTE=1,
        allocation_fire_rows_per_domain=4,allocation_fire_new_ff_bits=0,allocation_fire_new_sram_bits=0,allocation_fire_new_pipeline_edges=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Distribute each original actual alloc_fire_o lane through functional control_tree to at-most-four-row LSQ metadata/payload groups. Internal allocation-match masks use group views instead of one shared late source; publicallocvalid/ready/fire/count/ticket and all capacity/slot/GEN/writepriority calculations unchanged. Root _240947_ late allocation/admission-related NAND3 has212ps/24.14fF in A99 path; reduce metadata/payload row fanout while adding pricedreal inverter tree, nostate/pipeline/capacity change. Keep exact A103 modular-age recovery prequalification.'
    ]
    write(TARGET/'candidate.json',record)
    proof=dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,
        new_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'Original rv32_frequency_control_tree is a hierarchy of real inversions/restored polarity; for every binary inputbit eachviewbit equals corresponding inputbit. For any rowr andlanej newview[(r/4)*BE+j]=originalalloc_fire[j]. Thus metadata/payload allocations perrow remain normal&&fire&&originalplannedslot==row. All original actual_sparse_allocator valid/memtype/freecount/count/fire/publicticket equations unchanged. No newevent orcycle; flag0 concatenates sameinput toallviews.',
            'Only two internal row-match uses change. Original rowspecificnormal/reset/flush/recovery, plannedslot, fullLSQGEN updates, packetdata/ready/mask/store/MMIO/writepriority held/reclaim behavior retained. Admission credit/RSskip and accepted D bundle unchanged. Tree is purelycombinational and cannot form creditloop because originalfiredepends only actualinputvalid/memtype/free_count, not itsrowviews/matches.',
            'Course16rows yields4domains, eachconsumed by atmost4metadata and4payload rowselectors perlane instead ofall16+16. Publicfire/tagvalid still originalnet and someotherconsumers remain, so actualmapped rootload maynotfall proportionally. A99 lateNAND3_240947_212ps/24.14fF before validticket alias d_rob_value_tree.signal_i[0]=lsq_alloc_tag[0]; rowowners leadcriticalLSQload/GENwrites. Source-to-mappedgate association partlyinference, not a guaranteeddelay estimate.',
            'Addedreal inverterdriver tree incurs fullASAP7 area/timing, noidealbuffer/blackbox/customlibrary/falsepath. No declaredFF/SRAM/pipelineedge, ISA/GEN/queue/cache/predictor/portcapacity reduction. Core/backend/LSQnewoption0/top1, generalized domains ceil(rows/4), existing helper widths support all positivegeometry. Net area/frequency stillunmeasured, current84um2 margin tight.',
            'A103 fixes originalagewidth source assumption before anyHDLtest; thiscandidate retains unsignedROBSLOTWIDTH age/branch_age and unsignedcomparisons. A102 wrong assumption superseded, nevermeasured/adopted. OptionalA100/A101thirdquery remains disabled in coursefrequencyprofile. MainEsource and alloldsuccessful scripts/proofs/reports/runtime/source snapshots untouched.',
            'NoHDL/lint/formal/sim/synthesis/STA/unit tests orCPU builds. Coherent nextbatch shouldtarget newA99 recovery→LSQreporttagclassification andlateallocation fanout, pre-report beforePPA; onlyPPA dualgate passes then sixIPC. Finalthreegoals/19course+fourfrozenedge/parametercoverage beforeadoption retained.'
        ],goal_complete=False,adopted=False)
    write(REVIEW,proof)
    print({k:proof[k] for k in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__=='__main__':
    main()
