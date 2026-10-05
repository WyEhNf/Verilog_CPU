"""Prepare opcode-independent parallel integer add/sub without changing latency."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A110_lsq_wake_identity_precompare'
TARGET = BASE/'A111_alu_parallel_add_sub'
REVIEW = BASE/'A111_source_review.json'
FLAG = 'ALU_PARALLEL_ADD_SUB'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    assert sha(PARENT/'candidate.json') == 'abe407fd2556c0c80fa95927b4ff0b653f3c452e97979a3400e853f001b0dd2f'
    parent = read(PARENT/'candidate.json')
    assert not parent['adopted'] and not parent['tests_started']
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    files = ['rtl/rv32i_alu.v','rtl/backend/rv32_backend_joint.v',
             'rtl/cpu_core.v','rtl/course/student_top.v']
    originals = {name:(PARENT/name).read_text(encoding='utf-8') for name in files}
    texts = dict(originals)
    for name in files[1:]:
        default = 1 if name.endswith('student_top.v') else 0
        old = f'    parameter integer SHIFT_SHARED_BARREL = {default},'
        texts[name] = once(texts[name], old, old+f'\n    parameter integer {FLAG} = {default},')
        if name != files[1]:
            old = '.SHIFT_SHARED_BARREL(SHIFT_SHARED_BARREL),'
            texts[name] = once(texts[name], old, old+f' .{FLAG}({FLAG}),')
    name = files[1]
    old = '.SHIFT_SHARED_BARREL(SHIFT_SHARED_BARREL),'
    texts[name] = once(texts[name], old, old+' .PARALLEL_ADD_SUB(ALU_PARALLEL_ADD_SUB),')
    name = files[0]
    old = '    parameter integer SHIFT_SHARED_BARREL = 0,'
    texts[name] = once(texts[name], old, old+'\n    parameter integer PARALLEL_ADD_SUB = 0,')
    old = '''    wire [31:0] integer_sum=fast_add_carry(issue_src1_value_i,integer_adjusted_rhs,integer_subtract_views[2]);'''
    new = '''    wire [31:0] integer_sum;
    generate if(PARALLEL_ADD_SUB!=0) begin:g_parallel_integer_arithmetic
        // Opcode selection follows both complete arithmetic cones. The
        // original registered result and its acceptance events are unchanged.
        wire [31:0] add_value=fast_add_carry(issue_src1_value_i,issue_src2_value_i,1'b0);
        wire [31:0] subtract_value=fast_add_carry(issue_src1_value_i,~issue_src2_value_i,1'b1);
        for(genvar arithmetic_word=0;arithmetic_word<2;arithmetic_word=arithmetic_word+1) begin:g_result_word
            assign integer_sum[arithmetic_word*16 +: 16]=integer_subtract_views[arithmetic_word]?
                subtract_value[arithmetic_word*16 +: 16]:add_value[arithmetic_word*16 +: 16];
        end
    end else begin:g_original_integer_arithmetic
        assign integer_sum=fast_add_carry(issue_src1_value_i,integer_adjusted_rhs,integer_subtract_views[2]);
    end endgenerate'''
    texts[name] = once(texts[name], old, new)
    marker = '    wire [31:0] address_sum='
    assert texts[name][texts[name].index(marker):] == originals[name][originals[name].index(marker):]
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT/name, destination)
    for name, content in texts.items():
        (TARGET/name).write_text(content, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_OPCODE_INDEPENDENT_PARALLEL_INTEGER_ADD_SUB_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),source_root=str(TARGET),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=files,source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),
        tests_started=False,synthesis_started=False,timing_started=False,adopted=False,
        candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],**{FLAG:1})
    record['enabled_profile'] = dict(parent['enabled_profile'],alu_parallel_integer_add_sub=True,
        alu_parallel_add_sub_new_ff_bits=0,alu_parallel_add_sub_new_sram_bits=0,
        alu_parallel_add_sub_new_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Optional ALU parallel add/sub computes the original fast_add_carry function with fixed (rhs,0) and (~rhs,1) inputs in parallel. Exact original SUB predicate chooses the completed 32-bit result through two original <=16-bit subtract-control views. Thus selected opcode no longer starts the operand inversion and whole integer carry/sum network. Original public operation decode, output class selector, all registered result/valid/recovery/shift/acceptance/state and AGU/branch/MDU remain byte-identical. Default0 retains the original arithmetic. Extra combinational arithmetic is an unmeasured area tradeoff; no extra FF/SRAM/latency.'
    ]
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=files,
        tests_started=False,new_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        arithmetic_function_and_agu_classification_clocked_state_suffix_byte_identical=True,
        extra_combinational_arithmetic_cones_per_used_alu=1,
        arithmetic_pipeline_claim_correction='The original fast_add_carry nibble carry/prefix network is combinational. The integer ALU has its original one-cycle registered result, not eight/nine/ten arithmetic register stages; the course backend has ISSUE_PIPELINE=0. Older overall-nine-stage descriptions do not prove a register cut in this measured RS-to-ALU path.',
        source_arguments=[
            'A105 measured top path selects the RS payload at2.427ns, enters ALU integer_subtract_tree at2.595ns/leaf2.631ns and arrives at result FF3.586ns. The opcode-derived subtract predicate previously controls both 32-bit RHS inversion and carry_in before the whole combinational fast_add_carry network. A111 replaces that control-to-arithmetic ordering with two opcode-independent complete sums followed by the same predicate selecting their results. This is source-level path removal, not measured MHz evidence; operand/value/other control paths may become critical.',
            'Let S be the exact original issue_op_i==RV32IM_OP_SUB predicate, and F(a,b,c) be the unchanged pure combinational fast_add_carry function. Every original subtract-tree view equals S. Original integer_sum=F(a,b XOR {32{S}},S). By substituting S0 or S1, it equals S?F(a,~b,1):F(a,b,0). A111 implements exactly this substitution for both 16-bit result words, for all binary opcodes/operands, including unused/invalid operations and empty RS outputs. It requires no onehot issue-selection invariant, signed-age interpretation, or speculative value.',
            'The full suffix beginning at original address_sum, including fast_add_carry itself, comparator/shifter/address/branch/public result-class calculations, result payload registers, valid/ready/hold/reset/recovery/cancel/live-tag/metadata/shift state, is byte-identical. Only the integer_sum definition and inactive-by-default parameter change. All actual issue/completion events and values remain equivalent under the original predicate. ADD/SUB modulo32 arithmetic, x0 handling, signed comparisons, jumps, loads/stores and all eight M operations retain their original logic. No new execution stage, FF, SRAM, read port or completion source.',
            'Public core/backend flag default0; course top default1; backend passes flag as ALU PARALLEL_ADD_SUB. The two same 16-bit output slices span exactly32 bits and are independent of BE_WIDTH, ROB/RS/PRF/cache/tag widths, ISSUE_PIPELINE and SHIFT_IMPL. Parameter0 uses the exact original integer_sum function expression; serial core profile is unchanged. Original subtract tree and input-adjusted RHS are retained, and unused original active-mode circuitry is eligible for ordinary synthesis pruning, never excluded from area/timing accounting.',
            'Adds one integer arithmetic cone per used ALU and an output selection. Actual cell sharing/pruning/driver loading/total area may differ. A94 total area margin is201.027322002046um2; A105 exceeded area56.01807799771632um2 before A106-A109 changes. It is not established that this fits. A110 pre-choice tag comparisons also add area. Future batch must use actual standard-cell plus unchanged SRAM total and inspect the critical path. Do not infer IPC1.115 from zero new clock edges or inherit A109 metrics.',
            'Source audit correction: ALU fast_add_carry has eight four-bit chunks and combinational prefix levels, followed by the original result register; chunk/prefix levels are not clock pipeline stages. Course ISSUE_PIPELINE0 joins wake, RS arbitration/payload and integer arithmetic into one register-to-register timing path. Prior description of a nine-stage arithmetic pipeline is unsupported. This new review supersedes that interpretation without changing frozen earlier scripts/reports/results.',
            'Prepared source only. No HDL/lint/formal/simulation/synthesis/STA/unit test or CPU build has run for A110/A111. Original A109 running sources remain frozen. Do not dispatch a measurement solely because A111 exists: inspect original A109 terminal evidence, consider all remaining bottlenecks/area tradeoffs, finish the coherent material batch and report to the user before its test. The complete objective remains Fmax>300MHz, IPC>=1.1, total area including SRAM<=36000um2, full RV32IM/OoO/inorder/MMIO/parameterization and closing correctness.'
        ],candidate_metrics=None,adopted=False,goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
