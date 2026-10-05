"""Shorten iterative arithmetic and isolate final correction; no HDL execution."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A18_load_completion_bypass'
TARGET = BASE/'A19_prefix_iterative_mdu'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old,new)


def prefix_function():
    alu = (PARENT/'rtl/rv32i_alu.v').read_text(encoding='utf-8')
    start = alu.index('    function [31:0] fast_add_carry;')
    end = alu.index('    endfunction',start)+len('    endfunction')
    function = alu[start:end].replace('function [31:0] fast_add_carry;', 'function [32:0] prefix_add32;')
    function = function.replace('fast_add_carry[chunk*4 +: 4]', 'prefix_add32[chunk*4 +: 4]')
    function = once(function,'        end\n    endfunction',
        '            prefix_add32[32]=carry[8];\n        end\n    endfunction')
    return function


def main():
    assert not TARGET.exists()
    parent = read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    name = 'rtl/rv32m_mdu_iterative.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original,'    reg busy;','''    reg busy;
    // One extra completion edge separates iteration from sign correction.
    // No request may replace operation/tag state while this phase is valid.
    reg finishing;
    reg [31:0] finishing_magnitude;
    reg finishing_negate,finishing_increment;''')
    text = once(text,'    assign occupied_o=busy || out_valid;',
        '    assign occupied_o=busy || finishing || out_valid;')
    text = once(text,'.active_i(busy),.tag_i(operation_tag),',
        '.active_i(busy || finishing),.tag_i(operation_tag),')
    marker = '    always @* begin\n        next_state = shift_state;'
    additions = '''    // The lower-word carry also supplies the 33-bit unsigned
    // subtraction decision. u33 >= d32 iff u33[32] or low-word no-borrow.
    // The difference top bit is u33[32] XOR borrow, including u33[32]=1.
    wire [32:0] multiply_low_sum=prefix_add32(shift_state[63:32],
        shift_state[0]?operand:32'b0,1'b0);
    wire [32:0] multiply_upper_sum={shift_state[64]^multiply_low_sum[32],multiply_low_sum[31:0]};
    wire [64:0] division_shifted=shift_state<<1;
    wire [32:0] division_low_difference=prefix_add32(division_shifted[63:32],~operand,1'b1);
    wire division_no_borrow=division_shifted[64] || division_low_difference[32];
    wire [32:0] division_difference={division_shifted[64]^!division_low_difference[32],division_low_difference[31:0]};
    wire [32:0] finishing_correction=prefix_add32(~finishing_magnitude,32'b0,finishing_increment);
    wire [31:0] finishing_corrected=finishing_negate?finishing_correction[31:0]:finishing_magnitude;
    wire operation_is_remainder=(operation==`RV32IM_OP_REM || operation==`RV32IM_OP_REMU);
    wire [31:0] finishing_value=(!mode_mul && divide_zero)?
        (operation_is_remainder?original_a:32'hffffffff):
        ((!mode_mul && signed_overflow)?
         ((operation==`RV32IM_OP_REM)?32'b0:32'h80000000):finishing_corrected);
'''+prefix_function()+'\n\n'
    text = once(text,marker,additions+marker)
    text = once(text,'''            upper_sum = shift_state[64:32] +
                (shift_state[0] ? {1'b0, operand} : 33'b0);''',
        '            upper_sum = multiply_upper_sum;')
    text = once(text,'''            next_state = shift_state << 1;
            if (next_state[64:32] >= {1'b0, operand}) begin
                next_state[64:32] = next_state[64:32] - {1'b0, operand};''',
        '''            next_state = division_shifted;
            if (division_no_borrow) begin
                next_state[64:32] = division_difference;''')
    text = once(text,'!request_cancel && !busy && out_slot_ready;',
        '!request_cancel && !busy && !finishing && out_slot_ready;')
    text = once(text,"            busy <= 1'b0;\n            out_valid <= 1'b0;",
        "            busy <= 1'b0;\n            finishing <= 1'b0;\n            out_valid <= 1'b0;")
    text = once(text,"            if(operation_cancel) busy<=1'b0;",
        "            if(operation_cancel) begin busy<=1'b0;finishing<=1'b0;end")
    text = once(text,'''                    busy <= 1'b0;
                    out_valid <= 1'b1;
                    out_value <= final_value;
                    out_tag <= operation_tag;
                    out_phys <= operation_phys;
                    out_live <= operation_live;''', '''                    busy <= 1'b0;
                    finishing <= 1'b1;
                    finishing_magnitude <= result_magnitude;
                    finishing_negate <= result_needs_negate;
                    finishing_increment <= result_negate_increment;''')
    text = once(text,'            if (req_valid_i && req_ready_o) begin', '''            if(finishing && !operation_cancel && out_slot_ready) begin
                finishing<=1'b0;
                out_valid<=1'b1;
                out_value<=finishing_value;
                out_tag<=operation_tag;
                out_phys<=operation_phys;
                out_live<=operation_live;
            end

            if (req_valid_i && req_ready_o) begin''')
    # Input magnitude, flags, full tags and physical ownership remain exactly.
    assert text.split('            if (req_valid_i && req_ready_o) begin',1)[1] == original.split('            if (req_valid_i && req_ready_o) begin',1)[1]
    for n in parent['source_sha256']:
        destination = TARGET/n
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/n,destination)
    (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=[name],source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)))
    record['enabled_profile'] = dict(parent['enabled_profile'],iterative_mdu_final_correction_edges=1,
        iterative_mdu_extra_declared_state_bits=35)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Replace compare-then-subtract division feedback by prefix subtraction/no-borrow; use prefix multiply addition, and register the final magnitude before a separate sign/exception completion edge.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        iterative_division_serial_compare_then_subtract_removed=True,
        iteration_and_sign_correction_separate_intervals=True,
        iterative_mdu_extra_declared_state_bits=35,
        iterative_mdu_added_final_completion_edges=1,
        new_mdu_frequency_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof = dict(status='SOURCE_ITERATIVE_MDU_PREFIX_AND_FINAL_STAGE_REVIEW_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),parent_sha256=sha(PARENT/'candidate.json'),
        changed_files=[name],request_capture_suffix_exact_parent=True,tests_started=False,adopted=False,
        source_arguments=[
            'prefix_add32 clones the existing ALU nibble carry-select/prefix function and exposes its already computed carry[8]. Its mathematical output is the 33-bit sum of two 32-bit words plus carry-in; this is a source argument, not formal equivalence.',
            'Multiply lower-word addition and XOR carry into the old upper bit preserve the original modulo-2^33 upper_sum and 65-bit right shift.',
            'Division shifts the same 65-bit state. Subtracting d32 from u33 uses low no-borrow carry: comparison is u33[32] OR carry, high difference bit u33[32] XOR NOT carry; remainder/quotient choice is identical algebraically, including high-bit and zero-divisor intermediate states.',
            'Final step captures magnitude/negate/increment in35 extra bits. Next edge applies sign correction and original divide-zero/overflow selection, then publishes the same full tag, physical destination and target-live metadata.',
            'Req_ready excludes finishing, protecting retained operation flags/tag/phys/original_a until the final result is published. Out_slot_ready prevents overwriting an older held output; finishing is included in occupied and full-tag recovery cancellation.',
            'Reset/flush/cancel clear finishing validity; the finishing output event requires no operation cancellation. A retained older finishing operation survives younger-branch recovery exactly as its old busy operation did.',
            'Latency increases by one completion edge for M instructions. All six official text images have no static M ops; no dynamic IPC equality or full ISA correctness is claimed.',
            'Only the iterative module changes. A18 load return bypass, cache capacities, OoO/ROB in-order commit, full instruction set decode and original other M implementations remain present.',
            'Fmax, mapped area and full arithmetic/recovery/backpressure behavior remain untested. This is an independent source candidate; original A16R2 measurement is unchanged.'
        ])
    write(BASE/'A19_source_review.json',proof)
    print({key:proof[key] for key in ('status','candidate','candidate_sha256','tests_started')})


if __name__ == '__main__':
    main()
