"""Prepare two source candidates; do not execute HDL, simulation or EDA."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def save_candidate(parent_path, target_path, changes, profile, evidence, description, arguments):
    assert not target_path.exists(), target_path
    parent = read(parent_path/'candidate.json')
    assert not parent['tests_started'] and not parent['adopted']
    for name, digest in parent['source_sha256'].items():
        assert sha(parent_path/name) == digest, name
    for name in parent['source_sha256']:
        target = target_path/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(parent_path/name, target)
    for name, text in changes.items():
        (target_path/name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(target_path), created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(parent_path), parent_candidate_sha256=sha(parent_path/'candidate.json'),
        changed_from_parent_files=list(changes), source_sha256={n:sha(target_path/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), tests_started=False, adopted=False)
    record['enabled_profile'] = dict(parent['enabled_profile'], **profile)
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'], **evidence)
    record['implemented_changes'] = list(parent['implemented_changes']) + [description]
    if 'DISPATCH_FULL_REPLACE' in profile:
        record['parameter_overrides'] = dict(parent['parameter_overrides'], DISPATCH_FULL_REPLACE=1)
    write(target_path/'candidate.json', record)
    proof = dict(status='SOURCE_REVIEW_UNTESTED', candidate=str(target_path),
        candidate_sha256=sha(target_path/'candidate.json'), parent_candidate_sha256=sha(parent_path/'candidate.json'),
        changed_files=list(changes), source_arguments=arguments, tests_started=False, adopted=False)
    write(BASE/(target_path.name.split('_',1)[0]+'_source_review.json'), proof)
    print({key:proof[key] for key in ('status','candidate','candidate_sha256','tests_started')})


def shared_feedback():
    parent = BASE/'A19_prefix_iterative_mdu'
    target = BASE/'A20_shared_prefix_feedback'
    name = 'rtl/rv32m_mdu_iterative.v'
    original = (parent/name).read_text(encoding='utf-8')
    text = once(original, '''    wire [32:0] multiply_low_sum=prefix_add32(shift_state[63:32],
        shift_state[0]?operand:32'b0,1'b0);
    wire [32:0] multiply_upper_sum={shift_state[64]^multiply_low_sum[32],multiply_low_sum[31:0]};
    wire [64:0] division_shifted=shift_state<<1;
    wire [32:0] division_low_difference=prefix_add32(division_shifted[63:32],~operand,1'b1);
    wire division_no_borrow=division_shifted[64] || division_low_difference[32];
    wire [32:0] division_difference={division_shifted[64]^!division_low_difference[32],division_low_difference[31:0]};''', '''    wire [64:0] division_shifted=shift_state<<1;
    // Multiply and divide cannot execute together. Select their operands
    // before one common feedback adder; final correction stays in its own
    // registered completion interval. Each mode leaf controls 16 mux bits.
    wire [3:0] feedback_mode_views;
    rv32_frequency_control_tree #(.LEAVES(4)) feedback_mode_tree (
        .signal_i(mode_mul),.views_o(feedback_mode_views));
    wire [31:0] feedback_lhs,feedback_rhs;
    genvar feedback_word;
    generate for(feedback_word=0;feedback_word<2;feedback_word=feedback_word+1) begin:g_feedback_operands
        assign feedback_lhs[feedback_word*16 +: 16]=feedback_mode_views[feedback_word]?
            shift_state[32+feedback_word*16 +: 16]:division_shifted[32+feedback_word*16 +: 16];
        assign feedback_rhs[feedback_word*16 +: 16]=feedback_mode_views[2+feedback_word]?
            (shift_state[0]?operand[feedback_word*16 +: 16]:16'b0):~operand[feedback_word*16 +: 16];
    end endgenerate
    wire [32:0] feedback_sum=prefix_add32(feedback_lhs,feedback_rhs,!mode_mul);
    wire [32:0] multiply_upper_sum={shift_state[64]^feedback_sum[32],feedback_sum[31:0]};
    wire division_no_borrow=division_shifted[64] || feedback_sum[32];
    wire [32:0] division_difference={division_shifted[64]^!feedback_sum[32],feedback_sum[31:0]};''')
    assert text.count('=prefix_add32(') == 2  # feedback and separate final correction
    assert text.split('    always @* begin',1)[1] == original.split('    always @* begin',1)[1]
    save_candidate(parent,target,{name:text},
        dict(iterative_mdu_feedback_adders=1, iterative_mdu_feedback_added_state_bits=0),
        dict(iterative_mdu_feedback_adders_before=2, iterative_mdu_feedback_adders_after=1,
             shared_feedback_operand_mux_added=True, shared_feedback_mapped_gain_unmeasured=True),
        'Share one prefix feedback adder between mutually exclusive iterative multiply/divide; keep final sign correction after its register boundary.',
        [
            'For mode_mul=1 the common operands are the original multiply upper word and conditional operand, with carry-in zero. For mode_mul=0 they are the same shifted division low remainder and complemented divisor, with carry-in one.',
            'The carry/XOR multiply upper bit, division no-borrow decision and difference upper bit read the same 33-bit sum their separate original adders produced. Only the active mode result is used.',
            'All combinational next-state/result selection and all sequential logic following the arithmetic declarations are exactly parent bytes: iteration count, extra finishing edge, full tags, live/recovery cancellation and backpressure do not change.',
            'Two independent 32-bit feedback prefix calls become one; sign correction retains a separate call after its register. No new state or execution edge is added.',
            'Two 32-bit operand muxes and a four-leaf mode distribution tree are added. This is a source area argument, not mapped saving or proof of Fmax>300MHz.',
            'The A16R2 measurement and all old candidate hashes remain unchanged. No HDL build, test, synthesis, STA or parameter sweep is started.'
        ])


def dispatch_replace():
    parent = BASE/'A20_shared_prefix_feedback'
    target = BASE/'A21_credit_guaranteed_dispatch_replace'
    name = 'rtl/backend/rv32_backend_joint.v'
    original = (parent/name).read_text(encoding='utf-8')
    text = once(original,'    parameter integer DISPATCH_ELASTIC = 0,',
        '    parameter integer DISPATCH_ELASTIC = 0,\n    parameter integer DISPATCH_FULL_REPLACE = 0,')
    text = once(text,'rv32_elastic_dispatch_packet #(.LANES(BE_WIDTH),.PAYLOAD_WIDTH(DISPATCH_PAYLOAD_WIDTH),',
        'rv32_elastic_dispatch_packet #(.FULL_REPLACE(DISPATCH_FULL_REPLACE),.LANES(BE_WIDTH),.PAYLOAD_WIDTH(DISPATCH_PAYLOAD_WIDTH),')
    text = once(text,'                .consume_i(d_admit));',
        '                .replace_credit_i(d_replace_credit),.consume_i(d_admit));')
    text = once(text,'    assign d_admit=(DISPATCH_ELASTIC==0) ||', '''    // This conservative credit path intentionally has no PRF read, early
    // load readiness, allocation result or R-input dependency. Counting ALL
    // valid lanes as RS demand guarantees admission regardless of which
    // ready loads later skip RS. Thus replace_credit implies d_admit/pop.
    reg [CREDIT_WIDTH-1:0] d_replace_rs_demand,d_replace_lsq_demand;
    integer replace_lane;
    always @* begin
        d_replace_rs_demand=0;d_replace_lsq_demand=0;
        for(replace_lane=0;replace_lane<BE_WIDTH;replace_lane=replace_lane+1) begin
            d_replace_rs_demand=d_replace_rs_demand+d_valid[replace_lane];
            d_replace_lsq_demand=d_replace_lsq_demand+
                (d_valid[replace_lane] && (d_is_load[replace_lane] || d_is_store[replace_lane]));
        end
    end
    wire d_replace_credit=(DISPATCH_FULL_REPLACE!=0) && (|d_valid) &&
        !reset_i && !flush_i && !branch_busy_domains[3] &&
        d_replace_rs_demand<=rs_free_count && d_replace_lsq_demand<=lsq_free_count;
    assign d_admit=(DISPATCH_ELASTIC==0) ||''')
    module_start = text.index('module rv32_elastic_dispatch_packet #(')
    before, queue = text[:module_start], text[module_start:]
    old_queue = original[original.index('module rv32_elastic_dispatch_packet #('):]
    queue = once(queue,'    parameter integer LANES=2,PAYLOAD_WIDTH=160,TAG_WIDTH=16,ROB_ENTRIES=32,',
        '    parameter integer FULL_REPLACE=0,\n    parameter integer LANES=2,PAYLOAD_WIDTH=160,TAG_WIDTH=16,ROB_ENTRIES=32,')
    queue = once(queue,'    input wire consume_i', '''    // Caller guarantees consume_i when this credit is asserted. It is a
    // saved-capacity proof, not a late consume/PRF combinational ready path.
    input wire replace_credit_i,
    input wire consume_i''')
    queue = once(queue,'    assign ready_o=normal && count<2;', '''    // At full occupancy read_slot==write_slot. The old head is consumed
    // before this edge; nonblocking writes replace it as the new tail. The
    // existing pop-then-push validity priority deliberately makes push win.
    assign ready_o=normal && (count<2 ||
        ((FULL_REPLACE!=0) && count==2 && replace_credit_i));''')
    assert queue.split('    always @(posedge clk_i) begin',1)[1] == old_queue.split('    always @(posedge clk_i) begin',1)[1]
    changes = {name:before+queue}
    name = 'rtl/cpu_core.v'
    text = (parent/name).read_text(encoding='utf-8')
    text = once(text,'    parameter integer DISPATCH_ELASTIC = 0,',
        '    parameter integer DISPATCH_ELASTIC = 0,\n    parameter integer DISPATCH_FULL_REPLACE = 0,')
    text = once(text,'.DISPATCH_ELASTIC(DISPATCH_ELASTIC),',
        '.DISPATCH_ELASTIC(DISPATCH_ELASTIC), .DISPATCH_FULL_REPLACE(DISPATCH_FULL_REPLACE),')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (parent/name).read_text(encoding='utf-8')
    text = once(text,'    parameter integer DISPATCH_ELASTIC = 1,',
        '    parameter integer DISPATCH_ELASTIC = 1,\n    parameter integer DISPATCH_FULL_REPLACE = 1,')
    text = once(text,'.DISPATCH_ELASTIC(DISPATCH_ELASTIC),',
        '.DISPATCH_ELASTIC(DISPATCH_ELASTIC), .DISPATCH_FULL_REPLACE(DISPATCH_FULL_REPLACE),')
    changes[name] = text
    save_candidate(parent,target,changes,
        dict(DISPATCH_FULL_REPLACE=1, dispatch_replace_added_state_bits=0),
        dict(dispatch_full_pop_and_push_supported=True, dispatch_replace_uses_prf_readiness=False,
             dispatch_replace_added_pipeline_edges=0, dispatch_replace_mapped_gain_unmeasured=True),
        'Allow full elastic queue pop/push on one edge when saved RS/LSQ capacity guarantees the complete old head can be admitted; avoid late PRF/consume feedback to rename.',
        [
            'The original queue blocks R acceptance for all count=2 cycles, including cycles where D consumes its old head. The new path admits a replacement only on a conservative saved-capacity credit.',
            'Conservative RS demand counts every queued valid lane. Actual RS demand masks out qualified ready loads, so actual <= conservative. Conservative LSQ demand equals actual valid load/store demand. Both are checked against the same saved free counts and reset/flush/branch guard, hence replace_credit implies d_admit.',
            'At count=2 a nonempty head is guaranteed by queue validity invariants. With normal and replace_credit, consume_i=d_admit and count!=0 ensure pop. A new push therefore never overwrites an unconsumed head.',
            'All queue clock logic is exactly parent bytes. At full pop+push count stays2, both pointers toggle, the prior second entry becomes the new head, and the old head slot becomes the new tail. Nonblocking payload writes retain the consumed old packet through the acceptance edge; the later validity push assignment wins over pop on the same slot.',
            'Credit uses queued head valid/memory fields and registered occupancy only, in a separate combinational process. It does not use PRF read_ready, load_without_agu, allocation fire, incoming R bundle or consume_i, so no PRF-to-rename ready path or allocation combinational loop is intentionally added.',
            'Reset/flush/branch hold/recovery disable normal ready and pop. Existing full-generation/ROB age recovery and sparse-lane validity retain exactly their prior ownership and ordering.',
            'No extra state, nominal pipeline edge, capacity shrink or resource overbooking. Default DISPATCH_FULL_REPLACE=0 keeps prior count-only readiness. Loads admitted with zero RS capacity still use the existing slower readiness path after count falls below full.',
            'The shorter acceptance bubble is a structural opportunity; actual frequency, area and IPC remain unmeasured. No HDL build or test is executed by this preparer.'
        ])


if __name__ == '__main__':
    shared_feedback()
    dispatch_replace()
