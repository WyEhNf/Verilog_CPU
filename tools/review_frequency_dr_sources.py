"""Record file identities and unchanged grant equations; no HDL execution."""
import difflib
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from prepare_staged_frequency_candidate import ROOT
from prepare_prf_precompare_and_store_imm12 import verify_parent
from prepare_late_lsq_completion_grants import original_grant_module


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate',default='DR_late_lsq_completion_grants')
    parser.add_argument('--proof',type=Path,default=Path('F:/CPU2026Proofs/DR_source_review_20261005'))
    args=parser.parse_args()
    base=ROOT/'DM1_lsq_report_bound_widths'
    combined=ROOT/args.candidate
    main_root=Path('E:/Verilog_cpu')
    active=json.loads((main_root/'build/cpu2026/active_frequency_implementation_20261004.json').read_text(encoding='utf-8'))
    for relative,expected in active['source_sha256'].items():
        if sha(main_root/relative)!=expected:
            raise ValueError('Active source changed: '+relative)
    candidates=[]
    chain=('DM1_lsq_report_bound_widths','DP_store_alloc_simm12',
           'DQ_prf_compare_before_completion','DR_late_lsq_completion_grants',
           'DS_direct_prf_operand_bypass','DT_completion_local_prf_enable')
    for name in chain[:chain.index(args.candidate)+1]:
        p=ROOT/name
        verify_parent(p)
        manifest=json.loads((p/'candidate.json').read_text(encoding='utf-8'))
        candidates.append({'candidate':str(p),'manifest_sha256':sha(p/'candidate.json'),
                           'input_identities':len(manifest['source_sha256']),
                           'same_39_course_overrides':manifest['parameter_overrides']==active['parameter_overrides']})
    dm1=json.loads((base/'candidate.json').read_text(encoding='utf-8'))
    dr=json.loads((combined/'candidate.json').read_text(encoding='utf-8'))
    changed=[n for n,s in dr['source_sha256'].items() if s!=dm1['source_sha256'][n]]
    patch=''.join(''.join(difflib.unified_diff((base/n).read_text(encoding='utf-8').splitlines(keepends=True),
                 (combined/n).read_text(encoding='utf-8').splitlines(keepends=True),
                 fromfile=base.name+'/'+n,tofile=combined.name+'/'+n)) for n in changed)
    patch_path=combined/'changes_vs_measured_DM1.patch'
    patch_path.write_text(patch,encoding='utf-8')
    old_network=(ROOT/'DQ_prf_compare_before_completion/rtl/backend/rv32_completion_network.v').read_text(encoding='utf-8')
    expected_module=original_grant_module(old_network)
    common=(combined/'rtl/common/rv32_asap7_fanout.v').read_text(encoding='utf-8')
    if not common.endswith(expected_module):
        raise ValueError('Extracted original grant equations changed')
    first_start='    always @(posedge clk_i) begin\n        if (BYPASS != 2 || reset_i || flush_i) begin'
    first_end='    always @* begin\n        producer_ready_o = {SOURCES{1\'b0}};'
    second_start='    always @(posedge clk_i) begin\n        if (BYPASS != 0) begin'
    second_end='    initial begin\n        if (SOURCES < 1 || BYPASS < 0 || BYPASS > 2) begin'
    current=(combined/'rtl/backend/rv32_completion_network.v').read_text(encoding='utf-8')
    for start,end in ((first_start,first_end),(second_start,second_end)):
        if old_network[old_network.index(start):old_network.index(end)]!=current[current.index(start):current.index(end)]:
            raise ValueError('Completion sequential/backpressure state equations changed')
    proof=args.proof
    proof.mkdir(exist_ok=True)
    review={
        'status':'SOURCE_IDENTITIES_AND_MANUAL_ALGEBRA_ONLY',
        'created_at':datetime.now(timezone.utc).isoformat(),
        'no_hdl_compiler_lint_simulation_synthesis_sta_or_formal_run':True,
        'active_before_adoption':active['candidate'],
        'active_input_identities_verified':len(active['source_sha256']),
        'candidate_chain':candidates,
        'changed_files_vs_measured_DM1':changed,
        'changes_vs_DM1_patch':str(patch_path),'patch_sha256':sha(patch_path),
        'extracted_grant_function_text_equals_original_equations':True,
        'completion_hold_and_fifo_state_text_unchanged':True,
        'grant_function_sha256':hashlib.sha256(expected_module.encode('utf-8')).hexdigest(),
        'new_declared_sequential_state_bits':0,
        'ordinary_integer_pipeline_stages':10,
        'internal_cpu_enables':{'STORE_ALLOC_IMM12':1,'PRF_BYPASS_PRECOMPARE':1,'COMPLETION_LATE_LOAD_SELECT':1},
        'current_configuration':{'BE_WIDTH':4,'CDB_WIDTH':3,'completion_sources':6,
            'PRF_reads':8,'PHYS_ADDR_WIDTH':6,'ROB_generation_width':8,'full_ROB_tag_width':17},
        'manual_reasoning':[
            'For base=4096*H+L and immediate=U-4096*sign, output upper=H+carry12-sign modulo 2^20. Low nibble carry-select and upper all-ones/all-zeros prefixes implement this arithmetic without another clock edge.',
            'A legal store decoder supplies the signed twelve-bit displacement. Generic standalone backend defaults retain the old full-width addition. Invalid allocation address payload may differ, but addr_ready remains clear until the ordinary AGU writes it.',
            'For a zero-or-one-hot completion source grant, equality of the selected physical destination with a nonzero legal PRF query equals OR(grant AND each-source equality). Actual write_valid and highest write-lane priority remain in the PRF.',
            'The branch-link override selects branch_pending_phys equality on precisely the lane and condition used by the physical address/value override.',
            'For late eligibility e, F(e,x) equals e ? F(1,x) : F(0,x); both copies retain full producer/held tags, cursor and all other eligibility bits. Only the unchanged full-qualified e chooses the grants actually published.',
            'Round-robin cursor, held-source state, producer ready, reset/flush qualification, payload routing, ordinary ROB-generation checks and all clocked state update blocks are retained.'
        ],
        'limitations':'File/text identities and manual algebra do not establish HDL syntax acceptance, complete functional or parameter equivalence, mapped fanout/capacitance, area, IPC or frequency. No new measured result exists.'
    }
    if args.candidate in ('DS_direct_prf_operand_bypass','DT_completion_local_prf_enable'):
        review['internal_cpu_enables']['PRF_DIRECT_OPERAND_BYPASS']=1
        review['manual_reasoning'].extend([
            'Fused value routing computes each legal completion-lane hit from its selected source equality AND actual backend PRF write-valid, suppresses the overridden branch-link lane, and retains the highest matching lane. Its source-grant OR routes precisely that lane producer value.',
            'A matching branch link wins over all lower active lanes. A nonmatching branch link still suppresses the old normal destination on the overridden lane, allowing a matching lower lane to supply the read.',
            'Normal completion outputs and PRF clocked value/ready writes remain unchanged; fused read data changes only combinational routing. Default-disabled standalone/other completion modes keep their original read path.'
        ])
    if args.candidate=='DT_completion_local_prf_enable':
        review['manual_reasoning'].append('In direct mode cdb_valid AND cdb_rd_we equals !reset AND !flush AND OR(selected_source AND producer_rd_we AND !producer_is_store). DT uses exactly that expression for the actual PRF write-enable; source grants still carry full original eligibility.')
    path=proof/'source_review.json'
    path.write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'review':str(path),'candidate':str(combined),
                      'changed_RTL_files':len(changed),'tests_started':False},ensure_ascii=False))


if __name__=='__main__':
    main()
