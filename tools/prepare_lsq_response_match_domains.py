"""EJ child: local full response identity/validity for four-row match domains."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def lsq(text):
    text=change(text,'    reg response_fire;', '''    reg response_fire;
    // The returning full LSQ identity drives independent four-row domains.
    // Scalar slot walk and direct payload query reuse the SAME row matches.
    localparam integer RESPONSE_MATCH_DOMAINS=(LSQ_ENTRIES+3)/4;
    localparam integer RESPONSE_MATCH_WIDTH=TAG_WIDTH+1;
    wire [RESPONSE_MATCH_DOMAINS*RESPONSE_MATCH_WIDTH-1:0] response_match_views;
    wire [LSQ_ENTRIES-1:0] response_match_rows;
    rv32_frequency_control_tree #(.WIDTH(RESPONSE_MATCH_WIDTH),.LEAVES(RESPONSE_MATCH_DOMAINS)) response_match_tree (
        .signal_i({dcache_resp_valid_i,dcache_resp_lsq_tag_i}),.views_o(response_match_views));
    generate for(genvar match_row=0;match_row<LSQ_ENTRIES;match_row=match_row+1) begin:g_response_match_row
        wire local_valid;
        wire [TAG_WIDTH-1:0] local_tag;
        assign {local_valid,local_tag}=
            response_match_views[(match_row/4)*RESPONSE_MATCH_WIDTH +: RESPONSE_MATCH_WIDTH];
        assign response_match_rows[match_row]=local_valid &&
            tag_matches_slot(local_tag,match_row) && response_wait_mem[match_row];
    end endgenerate''')
    text=change(text,
        '            if (dcache_resp_valid_i && tag_matches_slot(dcache_resp_lsq_tag_i, i) && response_wait_mem[i]) begin',
        '            if (response_match_rows[i]) begin')
    return change(text,'''            assign matches[query_row]=dcache_resp_valid_i &&
                tag_matches_slot(dcache_resp_lsq_tag_i,query_row) && response_wait_mem[query_row];''',
        '            assign matches[query_row]=response_match_rows[query_row];')


def main():
    parent=ROOT/'EJ_lsq_response_query_predecode'
    verify_parent(parent)
    out=prepare('EK_lsq_response_match_domains',parent,
        {'rtl/backend/rv32_lsq.v':lsq},
        'Conditional EJ child: distribute complete response LSQ tag+valid into four-row domains and share exact matches between original scalar walk and direct query. Full valid/generation/response_wait authority retained, no state or cycles. Source-only, unadopted/unmeasured.')
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    record_delta(out,parent,groups+['lsq_full_response_identity_four_row_domains'])
    path=out/'candidate.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        declared_additional_state_bits_vs_parent=0,new_declared_sequential_state_bits=0,
        measured_parent_run=None,measured_reference_run='F:/CPU2026CourseRuns/architecture_EF_20261005',
        behavior='Same full response row-match equations through logical identity views; original highest-row scalar selection, fire, payload/default priority and clocked updates retained.',
        timing_tradeoff='Reduce direct response tag-bit comparison load per leaf to at most four row comparators; add explicit distribution depth. New mapped load, area and frequency unknown.',
        existing_clocked_payload_refactor='No clocked or new-state change.',
        limiting_load_evidence='F:/CPU2026Proofs/EF_selected_path_loads_20261005/summary.json',
        current_response_match_domains=4,max_response_row_comparators_per_leaf=4,
        selected_gate_mapping_scope='Saved timed AOI21 output has 18 direct pins, 16 are XNOR2 comparators, and uses first low response-tag output-select leaf. Individual private field bit is not identified.',
        adoption_condition='Complete source review. Do not infer elimination of the separate 50-load cache response-read gate; report final scope before measurement.')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        adopted=False,tests_started=False,new_declared_state_bits=0)))


if __name__=='__main__':
    main()
