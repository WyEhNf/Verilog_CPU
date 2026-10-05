"""Prepare RS capacity before current WB-assisted load/store skip decisions."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A96_fast_store_batch'
TARGET = BASE/'A97_rs_elastic_skip_capacity'
REVIEW = BASE/'A97_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == 'b8184faf6b03a70682edd2b3ffef97ec336acf531f9388640a1df756c9f39175'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer FAST_STORE_BATCH = '+str(default)+','
        text = once(original,marker,marker+'\n    parameter integer RS_ELASTIC_SKIP_CAPACITY = '+str(default)+',')
        if '/backend/' not in name:
            text = once(text,'.FAST_STORE_BATCH(FAST_STORE_BATCH)',
                '.FAST_STORE_BATCH(FAST_STORE_BATCH), .RS_ELASTIC_SKIP_CAPACITY(RS_ELASTIC_SKIP_CAPACITY)')
            changes[name] = text
            continue
        marker = '''    localparam integer LSQ_ALLOC_SLOT_PRESELECT_ACTIVE=(LSQ_ALLOC_SLOT_PRESELECT!=0) &&
        (DISPATCH_PIPELINE!=0) && (DISPATCH_ELASTIC!=0);'''
        text = once(text,marker,marker+'''
    localparam integer RS_ELASTIC_SKIP_CAPACITY_ACTIVE=(RS_ELASTIC_SKIP_CAPACITY!=0) &&
        (DISPATCH_PIPELINE!=0) && (DISPATCH_ELASTIC!=0);''')
        old = '''    // In batch mode every qualified RAM store may skip RS. Prepare all
    // capacity thresholds before those late one-bit qualifiers. Existence
    // of a qualifying subset S with B<=free+|S| is exactly B-F<=free,
    // where F counts all fast stores. No late popcount/subtract/compare chain.'''
        new = '''    // Preselect mode counts ALL saved D lanes before PRF/early-load
    // readiness. A valid load/store that skips RS contributes only a late
    // bool. Original batch-store mode still uses B excluding ready loads.
    // Existence of skip subset S with V<=free+|S| is exactly V-F<=free;
    // no current WB -> load skip -> demand counter -> capacity comparator.
    wire [CREDIT_WIDTH-1:0] d_rs_prepared_demand=(RS_ELASTIC_SKIP_CAPACITY_ACTIVE!=0) ?
        d_replace_rs_demand : d_rs_base_demand;
    wire [BE_WIDTH-1:0] d_rs_capacity_skip=(RS_ELASTIC_SKIP_CAPACITY_ACTIVE!=0) ?
        (d_valid & (load_without_agu | store_without_agu)) : store_without_agu;'''
        text = once(text,old,new)
        text = once(text,'generate if(FAST_STORE_BATCH_ACTIVE!=0) begin:g_batch_store_capacity',
            'generate if((FAST_STORE_BATCH_ACTIVE!=0) || (RS_ELASTIC_SKIP_CAPACITY_ACTIVE!=0)) begin:g_batch_store_capacity')
        text = once(text,'assign room[capacity_case]=d_rs_base_demand<=({1\'b0,rs_free_count}+CREDIT);',
            'assign room[capacity_case]=d_rs_prepared_demand<=({1\'b0,rs_free_count}+CREDIT);')
        text = once(text,'((store_without_agu & MASK)==MASK) && room[CREDIT];',
            '((d_rs_capacity_skip & MASK)==MASK) && room[CREDIT];')
        text = once(text,'wire d_rs_capacity_ok=(FAST_STORE_BATCH_ACTIVE!=0) ? d_rs_batch_capacity_ok :',
            'wire d_rs_capacity_ok=((FAST_STORE_BATCH_ACTIVE!=0) || (RS_ELASTIC_SKIP_CAPACITY_ACTIVE!=0)) ? d_rs_batch_capacity_ok :')
        # The actual demand/allocator/pop/credit/source/identity/state behavior
        # is untouched; only the equivalent capacity calculation changes.
        marker = '    assign d_admit=(DISPATCH_ELASTIC==0) ||'
        assert text[text.index(marker):] == original[original.index(marker):]
        marker = '    wire [BE_WIDTH-1:0] d_rs_need='
        end = '    localparam integer LSQ_ALLOC_SLOT_PRESELECT_ACTIVE='
        assert text[text.index(marker):text.index(end)] == original[original.index(marker):original.index(end)]
        marker = '    reg [CREDIT_WIDTH-1:0] d_replace_rs_demand,d_replace_lsq_demand;'
        end = '    // Preselect mode counts ALL saved D lanes'
        original_end = '    // In batch mode every qualified RAM store'
        assert text[text.index(marker):text.index(end)] == original[original.index(marker):original.index(original_end)]
        assert text.index('RS_ELASTIC_SKIP_CAPACITY_ACTIVE=') < text.index('d_rs_prepared_demand=')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_RS_ELASTIC_SKIP_CAPACITY_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],RS_ELASTIC_SKIP_CAPACITY=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],RS_ELASTIC_SKIP_CAPACITY=1,
        rs_elastic_skip_capacity_new_ff_bits=0,rs_elastic_skip_capacity_new_sram_bits=0,
        rs_elastic_skip_capacity_new_pipeline_edges=0,raw_saved_d_count_reused_from_original_replace_credit=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Prepare RS V<=free+k for ALL saved D valid lanes V, reusing original conservative replace-credit raw count before any current PRF/load/store readiness. Late d_valid&(load_without_AGU|store_without_AGU) only chooses fixed subset capacity booleans. Exact original actual RS demand is V-popcount(skip), so all admission/fire/pop/source/state remains cycle-identical for same inputs. Removes current WB-assisted load skip from capacity demand counter/comparator. Default0 retains original A96 load-excluded baseline.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        current_wb_load_ready_no_longer_precedes_capacity_count_comparison=True,
        original_saved_d_raw_credit_count_reused_no_second_raw_counter=True,
        skip_capacity_limit='A96 B=d_valid&~load_without_AGU still uses public PRF/current WB source1-ready through lsq_alloc_addr_valid. A97 precomputes thresholds from old raw saved d_replace_rs_demand, moving that entire late load dependency after all capacity arithmetic. Exact same input demand/admission by complement/subset algebra; no guaranteed measured frequency gain. Active A94 unchanged. Physical area/fanout/current path criticality and effect with inherited A95/A96 unmeasured.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'Existing source dependency: prf_read_ready includes original legal current-WB match; rs_src1_ready derives from it (and retains original intra-batch dependency guard); lsq_alloc_addr_valid requires original valid/memory/ready, load_without_AGU is original eligible nonstore-load bit. A96 baseline B counts d_valid & ~load_without_AGU before free+k comparison. Therefore a current valid/WB-ready dependency still precedes that counter/comparator, even after saved fast-store value classification is fixed.',
            'Let D=d_valid, S=D&(load_without_AGU|store_without_AGU), V=popcount(D), F=popcount(S). Exact original d_rs_need=D&~(load_without_AGU|store_without_AGU)=D&~S, so d_rs_demand=V-F for arbitrary bit patterns, including stale metadata of invalid lanes. S subsetD gives0<=F<=V. Exist nonempty subsetT of S with V<=free+|T|, or room0 for empty subset, iff V-F<=free; forward |T|<=F, reverse choose fullS. No disjoint-load/store assumption is required since OR/masking is exact.',
            'V reuses original d_replace_rs_demand, which counts all saved D valid lanes and deliberately excludes PRF/load-ready/current R input. Original raw count loop and conservative replace_credit are byte-identical. Active only DISPATCH_PIPELINE&&DISPATCH_ELASTIC. Constant extended17bit thresholds and1/3/15 subset masks for supportedBE1/2/4 retain A96 width/overflow handling. Late skip bits select prepared capacity terms; no runtime popcount/subtract/compare of current load/store skip remains in active capacity.',
            'The full backend source suffix from assign d_admit is byte-identical to parent, including reset/flush/busy/LSQroom, actual allocator valid/fire/pop, source values/ready/WB priorities, early AGU, full ROB/LSQ identities, recovery, commit/MMIO and queue state. d_rs_need/d_lsq_need and actual demand loops unchanged. Thus exact same inputs yield exact same admit/fire/pop and instruction behavior; no new bypass cycle, same-edge resource borrowing or credit feedback. A90 planned allocation-slot invariants remain.',
            'New RS_ELASTIC_SKIP_CAPACITY defaults core/backend0 and course top1, propagated once to OoO backend. Parameter0 preserves A96 original thresholds/load exclusion; nonelastic/no dispatch-pipeline falls back. New mode also works with FAST_STORE_BATCH disabled or fast-store profile unavailable: S still captures only original actually-skipped operations and exact need identity holds. No PRF/LSQ/ROB/RS/cache/completion/rename/helper changes, FF/SRAM/pipeline edges/port capacities added.',
            'Material timing hypothesis is structural movement of capacity arithmetic before current ready flags; ABC may already simplify some logic or new room fanout may offset benefit. This is not a numeric frequency claim or full correctness proof. No HDL/lint/formal/sim/synth/STA/unit test for A97. Frozen original A94 measurement untouched, pending A95/A96 changes inherited unmeasured; subsequent coherent test reported first and final numerical/full ISA/MMIO/GEN/parameter evidence remains required.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
