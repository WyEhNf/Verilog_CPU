"""EK child: compare each saved memory-response address before MSHR selection."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def cache(text):
    old='''    wire response_matches = response_found &&
                            (mem_resp_line_addr_i ==
                             (query_response_mshr_writeback ?
                              query_response_mshr_victim_addr :
                              {query_response_mshr_addr[31:4], 4'b0}));'''
    new='''    // Registered per-row identity is ready before the returning MSHR index.
    // Compare both legal address sources in parallel; late selection carries
    // one comparison bit instead of a selected flag plus a 32-bit address mux.
    wire [MSHR_ENTRIES-1:0] response_address_match_rows;
    wire selected_response_address_match;
    generate for(genvar match_mshr=0;match_mshr<MSHR_ENTRIES;match_mshr=match_mshr+1) begin:g_response_address_match
        assign response_address_match_rows[match_mshr]=
            (mshr_writeback[match_mshr] && mem_resp_line_addr_i==mshr_victim_addr[match_mshr]) ||
            (!mshr_writeback[match_mshr] && mem_resp_line_addr_i=={mshr_addr[match_mshr][31:4],4'b0});
    end endgenerate
    rv32_frequency_array_read #(.WIDTH(1),.ENTRIES(MSHR_ENTRIES),.INDEX_WIDTH(8)) response_address_match_read (
        .rows_i(response_address_match_rows),.index_i(mem_resp_id_i),.value_o(selected_response_address_match));
    // The original valid/sent/range response authority remains mandatory.
    wire response_matches=response_found && selected_response_address_match;'''
    return change(text,old,new)


def main():
    parent=ROOT/'EK_lsq_response_match_domains'
    verify_parent(parent)
    # Retain the incomplete EL directory from an anchor mismatch; never
    # overwrite a candidate or turn that directory into measurement input.
    out=prepare('EL1_cache_response_match_before_select',parent,
        {'rtl/cache/rv32_dcache_nonblocking.v':cache},
        'Conditional EK child: compare returning memory-line identity with each registered demand/victim address before late MSHR selection; select one Boolean and retain original response_found authority. No state/latency/handshake change. Source-only, unadopted/unmeasured.')
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    record_delta(out,parent,groups+['cache_response_address_compare_before_mshr_select'])
    path=out/'candidate.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        declared_additional_state_bits_vs_parent=0,new_declared_sequential_state_bits=0,
        measured_parent_run=None,measured_reference_run='F:/CPU2026CourseRuns/architecture_EF_20261005',
        behavior='Original response_found, MSHR valid/sent/range authority, full 32-bit line comparison, full victim address versus demand address with low nibble cleared, all response success/error consumers, handshake and clocked writers retained. No speculative authority.',
        timing_tradeoff='Moves comparison in parallel for saved row addresses before response ID selection; removes late selected writeback flag driving 32 address mux bits in response_matches. Adds comparator replication and input line-address load. New global timing/area unknown.',
        current_MSHR_ENTRIES=4,current_full_32bit_address_comparators=8,
        existing_clocked_payload_refactor='No changed clocked text or added state.',
        saved_evidence=['F:/CPU2026Proofs/EF_selected_path_loads_20261005/summary.json',
                       'F:/CPU2026Proofs/EF_selected_gate_inputs_20261005/summary.json',
                       'F:/CPU2026Proofs/EF_mshr_flag_input_cones_20261005/summary.json'],
        selected_flag_identity_scope='Source/dataflow inference: all four D cones reach lifecycle dirty_victim bit14, matching writeback update. No formal private-net field equivalence claim.',
        adoption_condition='Complete combined source review and remaining architecture triage. Report final immutable candidate scope before any measurement; no intermediate tests.')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        adopted=False,tests_started=False,new_declared_state_bits=0)))


if __name__=='__main__':
    main()
