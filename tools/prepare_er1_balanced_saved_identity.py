"""Prepare balanced saved identity aggregation and the A94-cycle frequency profile."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import ROOT, read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A98_saved_identity_word_mask'
TARGET = BASE/'A99_balanced_saved_identity'
REVIEW = BASE/'A99_source_review.json'
REFERENCE = ROOT/'build/cpu2026/er1_a94_complete_result_20261006.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == 'e7a05310b99a1d483af4245c18dceaaef6ea07fcbdeacb20ce372d65a4e26a21'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    assert sha(REFERENCE) == '4f764cfad284d2266046be5b51ad43548da2da305ab07b5b1666b5852ffcfe6c'
    measured = read(REFERENCE)['metrics']
    assert measured['candidate'] == 'A94_localparam_dependency_order'
    assert measured['ipc'] >= 1.1 and measured['area_um2'] < 36000 and measured['fmax_mhz'] < 300
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    marker = '    parameter integer SAVED_IDENTITY_WORD_MASK = 0,'
    text = once(original,marker,marker+'\n    parameter integer SAVED_IDENTITY_BALANCED_MERGE = 0,')
    old = '            assign saved_identity_tree[report_node]=saved_identity_tree[2*report_node] | saved_identity_tree[2*report_node+1];'
    new = '''            if((SAVED_IDENTITY_BALANCED_MERGE!=0) && HEAD_LOAD_IDENTITY_ACTIVE) begin:g_saved_identity_pair
                // Preserve each binary OR level as an independent combinational
                // cone, so mapping cannot fuse the whole arbitration/data tree
                // into a long alternating priority-like AOI/OAI chain.
                rv32_lsq_identity_pair_or #(.WIDTH(REPORT_IDENTITY_WIDTH)) pair (
                    .left_i(saved_identity_tree[2*report_node]),
                    .right_i(saved_identity_tree[2*report_node+1]),
                    .value_o(saved_identity_tree[report_node]));
            end else begin:g_original_saved_identity_merge
                assign saved_identity_tree[report_node]=saved_identity_tree[2*report_node] | saved_identity_tree[2*report_node+1];
            end'''
    text = once(text,old,new)
    text += '''

// Pure two-input bitwise OR; no priority, assumptions, state or clock.
(* keep_hierarchy = 1 *)
module rv32_lsq_identity_pair_or #(parameter integer WIDTH=85) (
    input wire [WIDTH-1:0] left_i,right_i,
    output wire [WIDTH-1:0] value_o
);
    assign value_o=left_i | right_i;
endmodule
'''
    assert old in text
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer LSQ_SAVED_IDENTITY_WORD_MASK = '+str(default)+','
        text = once(original,marker,marker+'\n    parameter integer LSQ_SAVED_IDENTITY_BALANCED_MERGE = '+str(default)+',')
        if '/backend/' in name:
            text = once(text,'.SAVED_IDENTITY_WORD_MASK(LSQ_SAVED_IDENTITY_WORD_MASK)',
                '.SAVED_IDENTITY_WORD_MASK(LSQ_SAVED_IDENTITY_WORD_MASK), .SAVED_IDENTITY_BALANCED_MERGE(LSQ_SAVED_IDENTITY_BALANCED_MERGE)')
        else:
            text = once(text,'.LSQ_SAVED_IDENTITY_WORD_MASK(LSQ_SAVED_IDENTITY_WORD_MASK)',
                '.LSQ_SAVED_IDENTITY_WORD_MASK(LSQ_SAVED_IDENTITY_WORD_MASK), .LSQ_SAVED_IDENTITY_BALANCED_MERGE(LSQ_SAVED_IDENTITY_BALANCED_MERGE)')
        if name.endswith('student_top.v'):
            text = once(text,'    parameter integer FAST_STORE_BATCH = 1,',
                '    parameter integer FAST_STORE_BATCH = 0,')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_BALANCED_SAVED_IDENTITY_A94_CYCLE_FREQUENCY_PROFILE_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],LSQ_SAVED_IDENTITY_BALANCED_MERGE=1,FAST_STORE_BATCH=0)
    record['enabled_profile'] = dict(parent['enabled_profile'],LSQ_SAVED_IDENTITY_BALANCED_MERGE=1,FAST_STORE_BATCH=0,
        balanced_saved_identity_new_ff_bits=0,balanced_saved_identity_new_sram_bits=0,
        balanced_saved_identity_new_pipeline_edges=0,fast_store_batch_optional_disabled_in_frequency_profile=True,
        fast_store_batch_max_ready_stores='1 in active frequency profile; original BE_WIDTH optional mode retained')
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Preserve original binary OR recurrence of saved full report identity in independent combinational pair modules; no grant/order/data/query/state changes. A94 mapped chain after high-fanout held grant has ten alternating multi-input AOI/OAI stages before ROB query. Protected OR levels limit cross-level factoring, with combination area tradeoff. Select FAST_STORE_BATCH0 in course frequency profile because measured A94 already meets IPC1.1 and has201um2 margin: retain optional multi-store feature but use original one-identity/one-fast-store behavior. A95 predicate/A97 capacity/A98 mask/this OR change are binary-cycle equivalent to A94, pending measurement.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        measured_a94_complete_result_sha256=sha(REFERENCE),measured_a94_ipc=measured['ipc'],
        balanced_merge_limit='A94 held-report path goes from _223269_ at1.270ns through _227852_.._227863_ alternating AOI33/OAI31/AOI31/OAI311 ten stages toquery1.593ns. RTL report merge is nominal balancedOR16; mapped factorization no longer preserves that level structure. Pure kept pair OR cones make each level independent, removing the opportunity to fuse masks/arbitration across levels. Actual stage attribution remains inference; new OR buffering/area may negate gain. A94 IPC1.115262692/area35798.972678 achieved; frequency still290.2494. Inherited A95/A97/A98 logic equivalence permits targeted frequency-only batch; A96 optional expansion disabled, not removed.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        measured_reference=str(REFERENCE),measured_reference_sha256=sha(REFERENCE),
        source_arguments=[
            'Original saved_identity_tree leaf functions from A98 are unchanged. At every nonleaf n the pair helper computes bitwise left|right, exactly original saved_identity_tree[2n]|saved_identity_tree[2n+1]. Induction over the existing power-of-two REPORT_ROWS tree proves identical root bits for any leaf vector, all geometry/padding/packet/query widths and grants, without onehot assumption. Pure combinational helper has no clock/state/handshake. Mode0 retains original OR expression; HEAD identity inactive retains old fallback.',
            'A94 mapped critical query segment contains ten alternating multi-input AOI/OAI stages1.270->1.593ns despite nominal balanced merge; some arbitration/leaf predicates may be fused, exact original aliases unavailable. Kept pair hierarchy partitions all OR levels from leaf predicates. Course16 rows gives4OR levels; existing A98 mask leaves remain <=16bit. This is a mapping-structure hypothesis, not guaranteed111.979ps savings. Additional priced OR/driver logic may increase area and other paths may dominate.',
            'Completed original A94 full three metrics: IPC1.11526269183481, Fmax290.249433106576, area35798.972677997954 including SRAM; six perf expected results pass, 19 correctness not run. Therefore no further IPC protocol change is needed to meet current numeric IPC gate. Select optional FAST_STORE_BATCH0 in active course top; core/backend/ROB default already0 and feature remains available. Backend static BATCH_ACTIVE0 restores original single preselected tag, firstpotential fast eligibility and ROB one-identity owner width. This profile tradeoff controls unnecessary duplicated fullGEN comparison area while preserving all required functionality/goal.',
            'Relative to A94, A95 replaces saved RAM predicate with exact signed12 arithmetic equality, A97 replaces capacity predicate with exact d_valid complement/subset equality, A98 replaces saved identity bitmask with same grant&bit, and A99 preserves each OR equation. A96 behavior expansion is disabled. Thus binary-input transition/handshake/allocator/packet/value/qualifier/GEN/hold/retire behavior is expected cycle-identical to A94; no borrowed numeric metric or full correctness claim. Core/LSQ defaults new option0; course1. No ISA/MMIO/GEN/queue/cache/predictor/width/source data/normal edge changes.',
            'No HDL/lint/formal/simulation/synthesis/STA/unit test or new CPU build for A99. All old successful scripts/manifests/reports and completed original A94 artifacts remain immutable; primary E EU source not adopted. Need one coherent pre-reported measurement after remaining supported same-path changes, then full19 correctness/M/GEN/recovery/MMIO/parameter coverage before goal/adoption claim. Numeric three targets and original RV32IM/OoO/in-order commit objective remain unchanged.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
