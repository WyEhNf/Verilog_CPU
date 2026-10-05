"""Prepare multiple independent ready RAM stores without a late tag mux."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A95_store_class_compare'
TARGET = BASE/'A96_fast_store_batch'
REVIEW = BASE/'A96_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == '7b5654aa0f7887e8282ad14ba2d3025ce4aeb17c30881528815c2dc16bab3a3e'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer FAST_STORE_CLASS_COMPARE = '+str(default)+','
        text = once(original,marker,marker+'\n    parameter integer FAST_STORE_BATCH = '+str(default)+',')
        if '/backend/' not in name:
            text = once(text,'.FAST_STORE_CLASS_COMPARE(FAST_STORE_CLASS_COMPARE)',
                '.FAST_STORE_CLASS_COMPARE(FAST_STORE_CLASS_COMPARE), .FAST_STORE_BATCH(FAST_STORE_BATCH)')
            changes[name] = text
            continue
        marker = '''    localparam integer FAST_STORE_SAVED_ACTIVE=(FAST_STORE_SAVED_OPERANDS!=0) &&
        FAST_STORE_COMPLETE_ACTIVE && PARALLEL_STORE_ADDRESS;'''
        text = once(text,marker,marker+'''
    localparam integer FAST_STORE_BATCH_ACTIVE=(FAST_STORE_BATCH!=0) && FAST_STORE_SAVED_ACTIVE;''')
        text = once(text,'rob_fast_store_publish_valid=(FAST_STORE_IDENTITY_PRESELECT!=0) ?',
            'rob_fast_store_publish_valid=((FAST_STORE_IDENTITY_PRESELECT!=0) && !FAST_STORE_BATCH_ACTIVE) ?')
        text = once(text,'rob_fast_store_publish_tag=(FAST_STORE_IDENTITY_PRESELECT!=0) ?',
            'rob_fast_store_publish_tag=((FAST_STORE_IDENTITY_PRESELECT!=0) && !FAST_STORE_BATCH_ACTIVE) ?')
        text = once(text,'((FAST_STORE_IDENTITY_PRESELECT==0) || potential_store_grants[ready_store_lane]);',
            '(FAST_STORE_BATCH_ACTIVE || (FAST_STORE_IDENTITY_PRESELECT==0) || potential_store_grants[ready_store_lane]);')
        old = '''                    ((FAST_STORE_IDENTITY_PRESELECT!=0) ? potential_store_grants[ready_store_lane] :
                    !(|ready_store_candidates[ready_store_lane-1:0]));'''
        new = '''                    (FAST_STORE_BATCH_ACTIVE ||
                     ((FAST_STORE_IDENTITY_PRESELECT!=0) ? potential_store_grants[ready_store_lane] :
                      !(|ready_store_candidates[ready_store_lane-1:0])));'''
        text = once(text,old,new)
        text = once(text,'''    // At most one store skips RS. Compute both capacity cases before
    // its late qualification, instead of counting that bit then comparing.''',
            '''    // Default mode lets one store skip RS. Its two capacity cases
    // precede late qualification; batch mode prepares every threshold below.''')
        old = '''    wire d_rs_capacity_ok=(FAST_STORE_SAVED_ACTIVE!=0) ?
        (d_rs_room_ordinary || ((|store_without_agu) && d_rs_room_with_fast)) :
        (d_rs_demand<=rs_free_count);'''
        new = '''    // In batch mode every qualified RAM store may skip RS. Prepare all
    // capacity thresholds before those late one-bit qualifiers. Existence
    // of a qualifying subset S with B<=free+|S| is exactly B-F<=free,
    // where F counts all fast stores. No late popcount/subtract/compare chain.
    function integer fast_store_subset_count;
        input integer mask;
        integer subset_bit;
        begin
            fast_store_subset_count=0;
            for(subset_bit=0;subset_bit<BE_WIDTH;subset_bit=subset_bit+1)
                fast_store_subset_count=fast_store_subset_count+((mask>>subset_bit)&1);
        end
    endfunction
    wire d_rs_batch_capacity_ok;
    generate if(FAST_STORE_BATCH_ACTIVE!=0) begin:g_batch_store_capacity
        localparam integer SUBSETS=(1<<BE_WIDTH)-1;
        wire [BE_WIDTH:0] room;
        wire [SUBSETS-1:0] qualifying_subsets;
        for(genvar capacity_case=0;capacity_case<=BE_WIDTH;capacity_case=capacity_case+1) begin:g_room
            localparam [16:0] CREDIT=capacity_case;
            assign room[capacity_case]=d_rs_base_demand<=({1'b0,rs_free_count}+CREDIT);
        end
        for(genvar capacity_subset=0;capacity_subset<SUBSETS;capacity_subset=capacity_subset+1) begin:g_subset
            localparam [BE_WIDTH-1:0] MASK=capacity_subset+1;
            localparam integer CREDIT=fast_store_subset_count(capacity_subset+1);
            assign qualifying_subsets[capacity_subset]=
                ((store_without_agu & MASK)==MASK) && room[CREDIT];
        end
        assign d_rs_batch_capacity_ok=room[0] || (|qualifying_subsets);
    end else begin:g_no_batch_store_capacity
        assign d_rs_batch_capacity_ok=1'b0;
    end endgenerate
    wire d_rs_capacity_ok=(FAST_STORE_BATCH_ACTIVE!=0) ? d_rs_batch_capacity_ok :
        (FAST_STORE_SAVED_ACTIVE!=0) ?
        (d_rs_room_ordinary || ((|store_without_agu) && d_rs_room_with_fast)) :
        (d_rs_demand<=rs_free_count);'''
        text = once(text,old,new)
        text = once(text,'.FAST_STORE_IDENTITY_PRESELECT(FAST_STORE_IDENTITY_PRESELECT), .STORE_PREFIX_ADMISSION',
            '.FAST_STORE_IDENTITY_PRESELECT(FAST_STORE_IDENTITY_PRESELECT), .FAST_STORE_BATCH(FAST_STORE_BATCH_ACTIVE), .STORE_PREFIX_ADMISSION')
        # Demand/fire/credit/state logic is retained; only the exact capacity
        # expression above and eligibility/publisher width policy change.
        marker = '    assign d_admit=(DISPATCH_ELASTIC==0) ||'
        old_tail = original[original.index(marker):]
        expected_tail = once(old_tail,'.FAST_STORE_IDENTITY_PRESELECT(FAST_STORE_IDENTITY_PRESELECT), .STORE_PREFIX_ADMISSION',
            '.FAST_STORE_IDENTITY_PRESELECT(FAST_STORE_IDENTITY_PRESELECT), .FAST_STORE_BATCH(FAST_STORE_BATCH_ACTIVE), .STORE_PREFIX_ADMISSION')
        assert text[text.index(marker):] == expected_tail
        marker = '    reg [CREDIT_WIDTH-1:0] d_replace_rs_demand,d_replace_lsq_demand;'
        end = '    wire d_rs_room_ordinary='
        assert text[text.index(marker):text.index(end)] == original[original.index(marker):original.index(end)]
        changes[name] = text
    name = 'rtl/backend/rv32_rob.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    marker = '    parameter integer FAST_STORE_IDENTITY_PRESELECT = 0,'
    text = once(original,marker,marker+'\n    parameter integer FAST_STORE_BATCH = 0,')
    old = '    localparam integer FAST_STORE_OWNER_LANES=(FAST_STORE_IDENTITY_PRESELECT!=0) ? 1 : BE_WIDTH;'
    new = '''    localparam integer FAST_STORE_OWNER_LANES=
        ((FAST_STORE_IDENTITY_PRESELECT!=0) && (FAST_STORE_BATCH==0)) ? 1 : BE_WIDTH;'''
    text = once(text,old,new)
    marker = '    localparam integer FAST_STORE_DOMAINS='
    assert text[text.index(marker):] == original[original.index(marker):]
    changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_FAST_STORE_BATCH_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],FAST_STORE_BATCH=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],FAST_STORE_BATCH=1,
        fast_store_batch_new_ff_bits=0,fast_store_batch_new_sram_bits=0,fast_store_batch_new_pipeline_edges=0,
        fast_store_batch_max_ready_stores='BE_WIDTH',full_identity_compared_before_each_late_valid=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'All currently qualified saved-base RAM stores in an atomic D batch skip RS/ALU, rather than only first potential store. Every lane carries its unchanged saved full ROB tag to independent original row/GEN comparison, so late validity never selects a wide tag. Precompute B<=free+k for k0..BE, accept if an eligible subset of k fast stores exists; exact B-F<=free without late popcount/subtraction/comparison. Actual LSQ allocation, per-row ready-only fast completion, original buffered in-order commit/ACK/MMIO and D replace credit remain.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        all_ready_ram_stores_in_saved_atomic_batch_avoid_redundant_rs_alu=True,
        first_unready_potential_store_no_longer_blocks_later_ready_fast_store=True,
        batch_capacity_precomputed_before_late_fast_qualification=True,
        batch_store_limit='Restores secondary ready store when first potential is unready and allows BE qualified stores, freeing redundant AGU/RS work and earlier ROB preparation; no new memory request bandwidth or unordered effect. Extra per-lane fullGEN comparisons/subset-capacity routing cost area/fanout; incidence, IPC and current criticality unmeasured. Active A94 original frozen measurement unaffected. Existing supported BE_WIDTH1/2/4 gives 1/3/15 constant subsets; no speculative state or shortened tags.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        external_architecture_sources=[
            'https://docs.boom-core.org/en/latest/sections/load-store-unit.html',
            'https://docs.boom-core.org/en/latest/sections/reorder-buffer.html'],
        source_arguments=[
            'Each enabled lane retains original complete eligibility: real saved valid store/no load, canonical signed12 immediate, saved base ready/no matching baseWB, ready data or legitimate highest-priorityWB, original RAM/natural alignment/op/size and zero explicit override. LSQ already receives original authoritative address/data on actual allocation. Therefore redundant AGU work is unnecessary for every eligible lane, not just first potential; MMIO/malformed/unready remain original RS. No branch/MDU/register-writing instruction uses fast completion.',
            'Distinct actual D instructions carry unchanged full saved ROB tags. Batch publisher uses original lane valid and d_tag vectors, not one selected tag; ROB uses original per-lane current valid/row/full8GEN/store/no-rd/no-branch/no-halt target comparison, independently before late valid. Existing per-row OR/readiness updater accepts multiple distinct rows in same edge and is byte-identical. Actual fast valid requires reset/flush/branch guard and corresponding real LSQ alloc_fire. No fake completion, no GEN shortening, and simultaneous normal completion priority/state logic remains original.',
            'Let B=popcount(d_valid & ~load_without_AGU) and F=popcount(all eligible store_without_AGU). Fast stores are a subset of base demand (they are valid nonload stores), hence 0<=F<=B. Actual RS demand remains original popcount(d_rs_need)=B-F. Exist subset S of eligible store lanes with k=|S| and B<=free+k iff B-F<=free: forward k<=F; reverse choose entire fast set, or room0 when empty. Constant masks/counts at elaboration and extended17bit free+k preserve arithmetic without overflow at65535. BE1/2/4 uses1/3/15 subsets, late controls are bit reductions and one final OR, not a late arithmetic count/subtract/compare.',
            'Original actual d_rs_need/d_lsq_need, raw demand counts, d_admit reset/flush/busy/LSQroom, atomic allocator fire, saved credit counting ALL valid lanes and replacement FIFO remain byte-identical. Thus capacity still exactly supports actual RS entries. Entire D atomic pop/fire semantics and A90 planned slot proof still hold: whenever any actual LSQfire occurs, full raw memory plan fits original free and fire equals plan. Full source suffix from d_admit remains identical except ROB static parameter connection.',
            'Fast preparation only marks existing ROB ready state; original store_sent/ACK/error state/ordinary-prefix authorization, buffered retirement, ordered LSQ requests/forwarding and memory side effects are unchanged. BOOM primary documentation independently separates ready address/data in STQ from committed in-order drain; it motivates the separation, but does not prove this RTL or numerical gain. Course memory/MMIO/ISA semantics remain original.',
            'Default FAST_STORE_BATCH0 retains exactly A95 eligibility/one-identity/at-most-one capacity; active requires saved fast-store profile. General supported issue width1/2/4 uses constant-mask capacity generation without fixed dual-width protocol. Extra full identity comparisons and control fanout may increase area or hurt frequency; no claim of preserving aggregate IPC. No HDL/lint/formal/sim/synth/STA/unit test or measurement for A96, no source adoption, no changes to original A94 run; future coherent measurement first reported and full correctness/M/GEN/MMIO/parameter evidence required before adoption.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
