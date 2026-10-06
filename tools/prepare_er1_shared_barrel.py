"""Prepare shared immediate/register barrel shifters; run no hardware tools."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A15_atomic_elastic_dispatch'
TARGET = BASE/'A16_shared_barrel_elastic_dispatch'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists(), TARGET
    parent = read(PARENT/'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    name = 'rtl/rv32i_alu.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer SHIFT_IMPL = 0,',
        '    parameter integer SHIFT_IMPL = 0,\n    parameter integer SHIFT_SHARED_BARREL = 0,')
    text = once(text, '    generate if(SHIFT_IMPL==0) begin:g_parallel_barrel', '''    // Only one operation is accepted per ALU edge. Immediate and register
    // shifts share the barrel; the existing five-bit amount selects its input.
    // The original parallel implementation remains available by default.
    generate if(SHIFT_IMPL==0 && SHIFT_SHARED_BARREL!=0) begin:g_shared_barrel
        wire [31:0] shared_left,shared_right;
        rv32_frequency_barrel32 shared_barrel (
            .value_i(issue_src1_value_i),.amount_i(issue_shift_amount),.fill_i(shift_sign_fill),
            .left_o(shared_left),.right_o(shared_right));
        assign immediate_shift_left=shared_left;
        assign immediate_shift_right=shared_right;
        assign register_shift_left=shared_left;
        assign register_shift_right=shared_right;
    end else if(SHIFT_IMPL==0) begin:g_parallel_barrel''')
    # Nothing below the shift datapath changes, including iterative timing.
    marker = '    // Compare four-bit chunks in parallel'
    assert text.split(marker, 1)[1] == original.split(marker, 1)[1]
    changes[name] = text
    name = 'rtl/backend/rv32_backend_joint.v'
    text = (PARENT/name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer SHIFT_IMPL = 0,',
        '    parameter integer SHIFT_IMPL = 0,\n    parameter integer SHIFT_SHARED_BARREL = 0,')
    text = once(text, '.SHIFT_IMPL(SHIFT_IMPL), .FORWARD_METADATA(RS_ISSUE_METADATA)',
        '.SHIFT_IMPL(SHIFT_IMPL), .SHIFT_SHARED_BARREL(SHIFT_SHARED_BARREL), .FORWARD_METADATA(RS_ISSUE_METADATA)')
    text = once(text, '    initial begin\n        if (RS_ISSUE_METADATA', '''    initial begin
        if ((DISPATCH_ELASTIC!=0 && DISPATCH_ELASTIC!=1) ||
            (DISPATCH_ELASTIC!=0 && DISPATCH_PIPELINE==0)) begin
            $display("ERROR: DISPATCH_ELASTIC must be 0 or 1; elastic mode requires DISPATCH_PIPELINE");
            $finish;
        end
        if (RS_ISSUE_METADATA''')
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT/name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer SHIFT_IMPL = 0,',
        '    parameter integer SHIFT_IMPL = 0,\n    parameter integer SHIFT_SHARED_BARREL = 0,')
    text = once(text, '.MUL_IMPL(MUL_IMPL), .SHIFT_IMPL(SHIFT_IMPL), .PHYS_TAG_IMPL',
        '.MUL_IMPL(MUL_IMPL), .SHIFT_IMPL(SHIFT_IMPL), .SHIFT_SHARED_BARREL(SHIFT_SHARED_BARREL), .PHYS_TAG_IMPL')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT/name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer RAT_RECOVERY_IMPL = 1,',
        '    parameter integer SHIFT_SHARED_BARREL = 1,\n    parameter integer RAT_RECOVERY_IMPL = 1,')
    text = once(text, '.SHIFT_IMPL(SHIFT_IMPL),',
        '.SHIFT_IMPL(SHIFT_IMPL), .SHIFT_SHARED_BARREL(SHIFT_SHARED_BARREL),')
    changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT/name, destination)
    for name, text in changes.items():
        (TARGET/name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),
        source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)))
    record['parameter_overrides'] = dict(parent['parameter_overrides'], SHIFT_SHARED_BARREL=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], SHIFT_SHARED_BARREL=1,
        parallel_barrel_instances=2)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Share immediate/register barrel shifters within each ALU, selecting only the five-bit shift amount; reject unsupported elastic/direct-dispatch parameter combinations.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        parallel_barrel_instances_before=4, parallel_barrel_instances_after=2,
        shared_barrel_added_state_bits=0, shared_barrel_added_pipeline_edges=0,
        shared_barrel_timing_cost='Five-bit amount mux before the original five-stage barrel; actual Fmax unmeasured.')
    write(TARGET/'candidate.json', record)
    proof = dict(status='SOURCE_DATAPATH_AND_DISPATCH_REVIEW_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'), changed_files=list(changes),
        tests_started=False, adopted=False,
        source_arguments=[
            'Immediate shifts select imm[4:0]; register shifts select src2[4:0]. Both already use the same src1 and arithmetic-fill predicate. Aliased outputs are observed only by their matching exclusive opcode class.',
            'SHIFT_IMPL=1 and all result validity, recovery, stall, arithmetic, branch and memory logic below the barrel are unchanged; no execution edge or payload owner is added.',
            'Default SHIFT_SHARED_BARREL=0 retains both original barrels. The course top enables sharing in its existing two ALUs.',
            'A15 D allocators count the same saved occupancy that their sparse allocation loops use. Raw d_valid consumers supply only payload/live metadata; RS/LSQ owners and backend D maps write on alloc_fire, which is gated by common d_admit.',
            'In count=1 simultaneous push/pop use different physical entries; count=0 cannot pop and count=2 cannot push. Recovery masks both full-tag rows, retains their order and repairs count/pointers without copying payloads.',
            'Queued source physical versions cannot be freed by a younger overwriter before an older queued consumer retires. Source readiness is reread at D, so delayed wakeups need no separate queue operand capture.',
            'The registered D boundary is required when DISPATCH_ELASTIC=1; invalid standalone parameter combinations now fail explicitly instead of silently dropping D work.',
            'Source reasoning and hashes are not simulation, equivalence, IPC, mapped area or timing evidence.'
        ])
    write(BASE/'A16_source_review.json', proof)
    print({key:proof[key] for key in ('status','candidate','candidate_sha256','tests_started')})


if __name__ == '__main__':
    main()
