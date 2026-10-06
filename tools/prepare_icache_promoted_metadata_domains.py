"""Bound same-edge promoted-response metadata selection; source edits only."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def icache(t):
    return change(t, '''    wire [2*RESPONSE_META_WIDTH-1:0] response_metadata_values={
        mem_resp_error_i || !response_matches,
        (response_promoted?lookup_req_epoch:mshr_demand_epoch[response_index]),
        (response_promoted?mem_resp_line_addr_i:mshr_line[response_index]),
        (response_promoted?lookup_req_pc:mshr_pc[response_index]),
        1'b0,lookup_req_epoch,request_line,lookup_req_pc};''', '''    // Same-cycle promotion selects one completed metadata packet. Each
    // select leaf owns at most sixteen mux bits, rather than one condition
    // driving all epoch/PC/line-address bits after global mapping.
    localparam integer PROMOTED_META_WIDTH=64+EPOCH_WIDTH;
    localparam integer PROMOTED_META_WORDS=(PROMOTED_META_WIDTH+15)/16;
    wire [PROMOTED_META_WORDS-1:0] promoted_meta_views;
    wire [PROMOTED_META_WIDTH-1:0] promoted_meta_packet={
        lookup_req_epoch,mem_resp_line_addr_i,lookup_req_pc};
    wire [PROMOTED_META_WIDTH-1:0] stored_meta_packet={
        mshr_demand_epoch[response_index],mshr_line[response_index],mshr_pc[response_index]};
    wire [PROMOTED_META_WIDTH-1:0] memory_meta_packet;
    rv32_frequency_control_tree #(.LEAVES(PROMOTED_META_WORDS)) promoted_meta_tree (
        .signal_i(response_promoted),.views_o(promoted_meta_views));
    genvar promoted_meta_word;
    generate for(promoted_meta_word=0;promoted_meta_word<PROMOTED_META_WORDS;
                 promoted_meta_word=promoted_meta_word+1) begin:g_promoted_meta_word
        localparam integer LOW=promoted_meta_word*16;
        localparam integer BITS=(PROMOTED_META_WIDTH-LOW>=16)?16:PROMOTED_META_WIDTH-LOW;
        assign memory_meta_packet[LOW +: BITS]=promoted_meta_views[promoted_meta_word]?
            promoted_meta_packet[LOW +: BITS]:stored_meta_packet[LOW +: BITS];
    end endgenerate
    wire [2*RESPONSE_META_WIDTH-1:0] response_metadata_values={
        mem_resp_error_i || !response_matches,memory_meta_packet,
        1'b0,lookup_req_epoch,request_line,lookup_req_pc};''')


def main():
    parent=ROOT/'DZ_recovery_and_icache_queue_domains'
    verify_parent(parent)
    out=prepare('EA_combined_control_locality',parent,
        {'rtl/cache/rv32_icache_nonblocking.v':icache},
        'Combine DZ with word-group selection of promoted I-cache memory-response epoch, PC and line metadata. Original same-edge priority, MSHR reads, full epoch comparison and clocked state remain unchanged. Source-only hypothesis guided by the 113-load I-cache response cone in saved DM1 mapped connectivity; no new delay measurement.')
    record_delta(out,parent,['allocation_store_signed_12bit_adder','shared_store_signed_12bit_adder',
        'negative_polarity_distribution','local_lsq_request_and_forwarding_owner',
        'lsq_report_rob_slot_predecode','rat_recovery_architectural_domains',
        'icache_request_queue_word_owners','icache_promoted_response_metadata_domains'])
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        new_declared_sequential_state_bits=0,mapped_gain_proven=False,
        promoted_response_mux_bits_per_leaf=16,
        promoted_response_evidence_scope='113-load private mapped OR2 cone reaches I-cache response metadata/data write boundaries. Reachability alone does not prove its precise Boolean identity, sensitization or critical delay; the source has a concrete 64+EPOCH_WIDTH-bit response_promoted selector targeted here.')
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256((out/'candidate.json').read_bytes()).hexdigest(),
                          tests_started=False,adopted=False)))


if __name__=='__main__':main()
