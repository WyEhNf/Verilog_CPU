"""Prepare direct RAM classification from the existing simm12 carry prefix."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A94_localparam_dependency_order'
TARGET = BASE/'A95_store_class_compare'
REVIEW = BASE/'A95_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == 'e36c9dc817c1c0ffa06add5261b2b212fc9ed2f26b441733f9c24ab2ded4d927'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    name = 'rtl/common/rv32_asap7_fanout.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    marker = '''module rv32_frequency_add_simm12 (
    input wire [31:0] base_i,
    input wire [11:0] immediate_i,
    output wire [31:0] sum_o
);'''
    text = once(original,marker,'''module rv32_frequency_add_simm12 #(
    parameter integer CLASS_COMPARE=0
) (
    input wire [31:0] base_i,
    input wire [11:0] immediate_i,
    output wire [31:0] sum_o,
    output wire [2:0] class_flags_o
);''')
    marker = '''    endgenerate
endmodule


// Read a packed row array using two already-decoded index banks.'''
    text = once(text,marker,'''    endgenerate
    // A signed12 displacement changes base[31:12] by only -1,0,+1.
    // Classify each possible high word before the existing low12 carry;
    // do not form four late adjusted sum bits and then reduce them.
    generate if(CLASS_COMPARE!=0) begin:g_class_compare
        wire high_zero=base_i[31:28]==4'h0;
        wire high_ones=base_i[31:28]==4'hf;
        wire high_one=base_i[31:28]==4'h1;
        // These exact lower16 reductions already exist for the full sum.
        wire middle_ones=ones_prefix[5][15];
        wire middle_zero=zeros_prefix[5][15];
        wire ram_increment=middle_ones ? high_ones : high_zero;
        wire ram_decrement=middle_zero ? high_one : high_zero;
        wire ram_carry_zero=immediate_i[11] ? ram_decrement : high_zero;
        wire ram_carry_one=immediate_i[11] ? high_zero : ram_increment;
        wire ram=generate_stage[2][2] ? ram_carry_one : ram_carry_zero;
        assign class_flags_o={sum_o[1:0]==2'b00,!sum_o[0],ram};
    end else begin:g_no_class_compare
        assign class_flags_o=3'b0;
    end endgenerate
endmodule


// Read a packed row array using two already-decoded index banks.''')
    # The sum's original carry-prefix/XOR implementation is retained verbatim.
    marker = '    wire [2:0] generate_stage [0:2];'
    old_body = original[original.index(marker):original.index('    endgenerate\nendmodule',original.index(marker))+len('    endgenerate')]
    assert old_body in text
    changes[name] = text
    name = 'rtl/rv32_physical_register_file.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    marker = '    parameter integer STORE_SAVED_QUERY = 0,'
    text = once(original,marker,marker+'\n    parameter integer STORE_CLASS_COMPARE = 0,')
    old = '''                    rv32_frequency_add_simm12 stored_address (
                        .base_i(stored_tree[1]),
                        .immediate_i(store_offset_i[(rp/2)*12 +: 12]),
                        .sum_o(address_values[0 +: 32]));
                    if(STORE_SAVED_QUERY!=0) begin:g_saved_address_flags
                        wire [31:0] saved_address=address_values[0 +: 32];
                        assign store_saved_flags_o[(rp/2)*3 +: 3]={
                            saved_address[1:0]==2'b00,!saved_address[0],
                            saved_address[31:28]==4'b0000};
                    end else begin:g_no_saved_address_flags'''
    new = '''                    wire [2:0] stored_class_flags;
                    rv32_frequency_add_simm12 #(.CLASS_COMPARE(STORE_CLASS_COMPARE)) stored_address (
                        .base_i(stored_tree[1]),
                        .immediate_i(store_offset_i[(rp/2)*12 +: 12]),
                        .sum_o(address_values[0 +: 32]),.class_flags_o(stored_class_flags));
                    if(STORE_SAVED_QUERY!=0) begin:g_saved_address_flags
                        if(STORE_CLASS_COMPARE!=0) begin:g_direct_class
                            assign store_saved_flags_o[(rp/2)*3 +: 3]=stored_class_flags;
                        end else begin:g_original_class
                            wire [31:0] saved_address=address_values[0 +: 32];
                            assign store_saved_flags_o[(rp/2)*3 +: 3]={
                                saved_address[1:0]==2'b00,!saved_address[0],
                                saved_address[31:28]==4'b0000};
                        end
                    end else begin:g_no_saved_address_flags'''
    text = once(text,old,new)
    marker = '                    for(genvar address_lane=0;address_lane<BE_WIDTH;address_lane=address_lane+1)'
    assert text[text.index(marker):] == original[original.index(marker):]
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer FAST_STORE_WB_DATA = '+str(default)+','
        text = once(original,marker,marker+'\n    parameter integer FAST_STORE_CLASS_COMPARE = '+str(default)+',')
        if '/backend/' in name:
            text = once(text,'.STORE_SAVED_QUERY(FAST_STORE_SAVED_ACTIVE)) prf (',
                '.STORE_SAVED_QUERY(FAST_STORE_SAVED_ACTIVE), .STORE_CLASS_COMPARE((FAST_STORE_CLASS_COMPARE!=0) && FAST_STORE_SAVED_ACTIVE)) prf (')
        else:
            text = once(text,'.FAST_STORE_WB_DATA(FAST_STORE_WB_DATA)',
                '.FAST_STORE_WB_DATA(FAST_STORE_WB_DATA), .FAST_STORE_CLASS_COMPARE(FAST_STORE_CLASS_COMPARE)')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_STORE_CLASS_COMPARE_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],FAST_STORE_CLASS_COMPARE=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],FAST_STORE_CLASS_COMPARE=1,
        store_class_compare_new_ff_bits=0,store_class_compare_new_sram_bits=0,store_class_compare_new_pipeline_edges=0,
        original_full_store_address_and_wb_selector_preserved=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Direct RAM predicate for saved base+signed12 offset: reuse original low12 carry and high-prefix middle16 zero/ones reductions, precompute RAM for carry0/carry1, then select one bool. Original complete address sum, alignment bits, read/ready/WB priority, fast-store qualification and actual LSQ state/commit behavior stay identical. Default0 retains old saved sum[31:28] comparison.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        signed12_ram_predicate_no_longer_depends_on_four_adjusted_upper_sum_bits=True,
        class_compare_limit='A83 has PRF WB address high-bit class on its measured critical chain, 2.292ns->2.755ns; A94 disconnected WB value but still computes saved class after full sum. A95 moves high-word equality before low12 carry. Original adder already has carry prefixes, so no duplicated low12 addition. Latest criticality, mapping/area/fanout improvement and quantitative frequency gain remain unmeasured; original A94 measurement is frozen and unaffected.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'Let H=base[31:12], L=base[11:0], U=immediate[11:0], s=immediate[11], c=floor((L+U)/4096). Unsigned32 wrapping address has high20 word (H+c-s) mod2^20. Existing generate_stage[2][2] is exactly c, proven by unchanged original 3x4bit carry prefix. Therefore high adjustment is -1,0,+1 only.',
            'For c=0,s=0 or c=1,s=1 high20 is H, RAM iff high nibble0. For c=1,s=0 high20 is H+1: middle16 allones carries to high nibble, so RAM iff high nibbleF when allones, otherwise high nibble0. For c=0,s=1 high20 is H-1: middle16 zero borrows from high nibble, so RAM iff high nibble1 when zero, otherwise high nibble0. These four exhaustive sign/carry cases prove exact RAM predicate for every32bit base and12bit immediate, including modulo32 wrap and RAM boundaries; not an address assumption.',
            'Reuse original ones_prefix[5][15] and zeros_prefix[5][15], exact reductions of base[27:12]. Sign and high-word predicates precede carry selection; alignment uses unchanged original sum[1:0]. Full original32 sum/carry/XOR body remains byte-identical. Additional output only drives saved flags under new parameter1; parameter0 selects original saved sum comparison. Original WB candidate flags, priority, all data/ready/state code, LSQ/ROB/RS/cache/completion/rename files and instruction interfaces remain unchanged.',
            'CORE/BACKEND default0, course top1; only active saved fast-store profile enables PRF class output. Complete fast eligibility including actual admit/LSQfire, stored base/no baseWB, data stored or legitimateWB, canonical immediate, ordinary RAM/alignment/op, zero explicit override, fullGEN/recovery and ordered memory effects is unchanged. No additional stored state, edge, memory, port capacity or speculation. Exact predicate equality gives unchanged fast opportunities for same inputs; aggregate timing/area correctness still unmeasured.',
            'No HDL/lint/formal/simulation/synthesis/STA/unit test for A95. Original A94 PID84416 snapshot remains independently frozen; no A95 metric may borrow A94/A83 results. Future coherent test must be separately reported after material supported work, and adoption still requires numerical target and full RV32IM/19correctness/M/GEN/MMIO/parameter evidence.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
