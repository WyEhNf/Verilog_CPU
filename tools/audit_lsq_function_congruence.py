"""Compose the literal LSQ function SAT lemmas with unchanged module context.

This does not rewrite a proof netlist, assume function outputs, or suppress
module outputs/state. It checks that the only RTL changes are the new parameter
and a pure function whose actual bodies were proved equal for every argument.
Under named equal parameters and the default SLOT_WIDTH, substitution therefore
preserves the full transition/output relation for the listed depths. The
independent monolithic sequential proof may continue separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def tokens(text):
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)
    return re.sub(r'\s+', '', text)


FUNCTION = re.compile(r'function\s+\[SLOT_WIDTH-1:0\]\s+advance_slot\s*;.*?endfunction', re.S)
NEW_PARAMETER = '    parameter integer DIRECT_ADVANCE = 0,\n'
FUNCTION_HEADER = '''function [SLOT_WIDTH-1:0] advance_slot;
        input [SLOT_WIDTH-1:0] start;
        input integer amount;
        integer p;
        integer n;
        begin
'''


def check_context(original, candidate):
    old_functions, new_functions = FUNCTION.findall(original), FUNCTION.findall(candidate)
    assert len(old_functions) == len(new_functions) == 1, 'unique helper required'
    old, new = old_functions[0], new_functions[0]
    assert candidate.count(NEW_PARAMETER) == 1, 'sole new parameter declaration required'
    # Byte-for-byte unchanged source context, after newline normalization only.
    restored = candidate.replace(NEW_PARAMETER, '').replace(new, old)
    assert restored == original, 'RTL outside the pure helper changed'
    assert 'DIRECT_ADVANCE' not in FUNCTION.sub('', candidate.replace(NEW_PARAMETER, ''))
    assert tokens(old).startswith(tokens(FUNCTION_HEADER))
    assert tokens(new).startswith(tokens(FUNCTION_HEADER))
    body = old.split('        begin\n', 1)[1].rsplit('        end\n', 1)[0]
    assert tokens(body) == tokens('''p = start;
        for (n = 0; n < LSQ_ENTRIES; n = n + 1) begin
            if (n < amount) begin
                if (p == LSQ_ENTRIES - 1) p = 0; else p = p + 1;
            end
        end
        advance_slot = p[SLOT_WIDTH-1:0];'''), 'original function structure changed'
    expected = FUNCTION_HEADER + '''if (DIRECT_ADVANCE != 0) begin
        if (LSQ_ENTRIES == 1)
            advance_slot = (amount > 0) ? {SLOT_WIDTH{1'b0}} : start;
        else if (amount <= 0 || amount >= LSQ_ENTRIES)
            advance_slot = start;
        else
            advance_slot = start + amount;
        end else begin
''' + body + '''end
        end
    endfunction'''
    assert tokens(new) == tokens(expected), 'candidate function structure changed'
    assert original.count('parameter integer SLOT_WIDTH = (LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES)') == 1
    # Only the listed locals/arguments/parameters are read; all assignments are
    # to locals or the function result. Thus the helper has no external effects.
    no_comments = re.sub(r'//[^\n]*', '', new)
    assigned = set(re.findall(r'\b(\w+)\s*=(?!=)', no_comments))
    assert assigned == {'p', 'n', 'advance_slot'}, assigned
    return old, new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-root', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    root, out = args.candidate_root.resolve(), args.outdir.resolve()
    assert not out.exists(), 'preserve existing evidence'
    literal_root = root / 'literal_proof'
    literal_path = literal_root / 'report.json'
    literal = json.loads(literal_path.read_text(encoding='utf-8-sig'))
    assert literal['status'] == 'COMPLETE' and literal['extracted_actual_bodies']
    assert {row['depth'] for row in literal['results']} == {1, 2, 4, 8, 16, 32, 64, 128}
    hashes = {str(literal_path): sha(literal_path), str(Path(__file__).resolve()): sha(__file__)}
    hashes.update(literal['input_sha256'])
    for entry in literal['compiled_origins'].values(): hashes[entry['path']] = entry['sha256']
    for path, value in hashes.items(): assert sha(path) == value, path
    original = (root / 'baseline/rv32_lsq.v').read_text()
    candidate = (root / 'rtl/backend/rv32_lsq.v').read_text()
    old, new = check_context(original, candidate)
    miter_path = literal_root / 'actual_function_miter.v'
    miter = miter_path.read_text()
    assert FUNCTION.findall(miter) == [old, new], 'SAT did not use exact actual function bodies'
    assert miter.count('input wire signed [31:0] amount') == 3
    assert miter.count('parameter integer DIRECT_ADVANCE=1') == 3
    assert miter.count('SLOT_WIDTH=(LSQ_ENTRIES<=1)?1:$clog2(LSQ_ENTRIES)') == 3
    assert 'advance_gold #(.LSQ_ENTRIES(LSQ_ENTRIES)) gold(start,amount,gold_result);' in miter
    assert 'advance_gate #(.LSQ_ENTRIES(LSQ_ENTRIES)) gate(start,amount,gate_result);' in miter
    assert 'assign matches=(gold_result==gate_result);' in miter
    for row in literal['results']:
        assert row['status'] == 'PROVEN' and row['arbitrary_head'] and row['arbitrary_signed_32bit_amount']
        depth = row['depth']
        script, log = literal_root / f'lsq{depth}.ys', literal_root / f'lsq{depth}.log'
        assert sha(script) == row['script_sha256'] and sha(log) == row['log_sha256']
        lines = script.read_text().splitlines()
        assert len(lines) == 5
        assert lines[0] == 'read_verilog "' + miter_path.as_posix() + '"'
        assert lines[1:] == [f'chparam -set LSQ_ENTRIES {depth} student_top',
                             'prep -top student_top -flatten', 'opt',
                             'sat -verify -prove matches 1 -show-inputs -show-outputs']
        assert 'SAT proof finished - no model found: SUCCESS!' in log.read_text()
        hashes[str(script)], hashes[str(log)] = sha(script), sha(log)
    # Corruptions outside the helper, to fallback semantics, to the optimized
    # arithmetic, and to hidden side effects must all fail this certificate.
    mutations = {
        'external_output': candidate.replace('module rv32_lsq #(', 'module wrong_lsq #(', 1),
        'candidate_arithmetic': candidate.replace('advance_slot = start + amount;', 'advance_slot = start - amount;', 1),
        'fallback_body': candidate.replace('p = start;', 'p = start + 1;', 1),
        'external_function_effect': candidate.replace('advance_slot = start + amount;', 'head_reg = start; advance_slot = start + amount;', 1),
        'additional_parameter_use': candidate.replace('    parameter integer STORE_ADMISSION_BYPASS = 0,', '    parameter integer STORE_ADMISSION_BYPASS = DIRECT_ADVANCE,', 1),
        'pointer_width': candidate.replace('parameter integer SLOT_WIDTH = (LSQ_ENTRIES <= 1) ? 1 : $clog2(LSQ_ENTRIES)', 'parameter integer SLOT_WIDTH = 32', 1),
    }
    rejected = []
    for name, mutated in mutations.items():
        assert mutated != candidate
        try: check_context(original, mutated)
        except AssertionError: rejected.append(name)
        else: raise AssertionError('accepted mutation ' + name)
    out.mkdir(parents=True)
    report = dict(status='VERIFIED', input_sha256=hashes,
        proof_method='Congruence of a total pure combinational function in byte-identical enclosing RTL',
        depths=[1,2,4,8,16,32,64,128], direct_advance_modes=[0,1],
        conditions=['SLOT_WIDTH is its original default for the selected LSQ_ENTRIES',
                    'All other module parameters have equal named bindings in gold and candidate',
                    'Two-state semantics, as in the unrestricted-input literal SAT lemmas'],
        original_rtl_context_byte_identical=True, all_outputs_and_state_preserved=True,
        pure_function_no_external_side_effects=True, all_function_arguments_unrestricted=True,
        full_module_transition_and_output_relation_preserved=True,
        conclusion='For the stated parameters every function call is equal, so unchanged combinational equations and sequential assignments are equal at every step. No input protocol or reachable-state assumptions are needed.',
        fallback_body_token_identical=True, negative_mutations_rejected=rejected,
        monolithic_sequential_proof_status='separate running work, not claimed complete by this certificate',
        claims_whole_cpu=False, claims_four_state_equivalence=False,
        claims_custom_slot_width=False, claims_other_depths=False,
        claims_positional_parameter_api_compatibility=False)
    for path, value in hashes.items(): assert sha(path) == value, path
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status='VERIFIED', input_count=len(hashes), depths=report['depths'],
                         rejected_mutations=rejected, report=str(out/'report.json')), indent=2))


if __name__ == '__main__': main()
