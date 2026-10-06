"""Prepare final EN1/EO1 source variants, preserving previous draft branches."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta
from prepare_mmio_narrow_request_domains import core as narrow_core
from prepare_registered_cache_hit_reply import core as held_hit_core, cache as held_hit_cache


def stable_core(text):
    text=narrow_core(text)
    text=change(text,'    wire [10:0] mmio_exit_views;','    wire [16:0] mmio_exit_views;')
    text=change(text,'    rv32_frequency_control_tree #(.LEAVES(11)) mmio_exit_request_tree (',
        '    rv32_frequency_control_tree #(.LEAVES(17)) mmio_exit_request_tree (')
    text=change(text,'''    // Every MMIO exit has mask 000f: upper words issue no AXI write and are
    // never part of its architectural payload. Keep the normal source there,
    // avoiding 96 irrelevant MMIO mux bits; preserve the full normal line.
    assign mem_d_req_wdata[127:32]=normal_mem_d_req_wdata[127:32];''',
        '''    // Every MMIO exit has mask 000f. Upper words issue no AXI write;
    // zero them during MMIO instead of selecting arbitrary MMIO data. This
    // keeps the entire held request stable even if normal cache data changes.
    generate for(genvar upper_word=0;upper_word<6;upper_word=upper_word+1) begin:g_mmio_masked_word
        assign mem_d_req_wdata[32+upper_word*16 +: 16]=
            {16{!mmio_exit_views[11+upper_word]}} & normal_mem_d_req_wdata[32+upper_word*16 +: 16];
    end endgenerate''')
    return text


def finish(out,parent,extra,scope):
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    record_delta(out,parent,groups+[extra])
    p=out/'candidate.json'
    m=json.loads(p.read_text(encoding='utf-8'))
    m.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        new_declared_sequential_state_bits=0,declared_additional_state_bits_vs_parent=0,
        measured_reference_run='F:/CPU2026CourseRuns/architecture_EL1_20261005',
        behavior=scope,
        preparation_relation='EN1 adds zero-gated masked upper words for full MMIO request stability. Prior EN/EO drafts are preserved, unadopted and untested.',
        source_evidence=['F:/CPU2026Proofs/EL1_mapped_paths_20261005/saved_path_analysis.json',
                         'F:/CPU2026Proofs/EL1_mapped_load_census_20261005.json',
                         'F:/CPU2026Proofs/EL1_selected_mmio_gate_20261005/summary.json',
                         'F:/CPU2026Proofs/EF_mapped_paths_20261005/saved_path_analysis.json'],
        adoption_condition='Finish the combined source/handshake review and report before one overall timing measurement; no intermediate tests.')
    p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                         source_groups=len(m['implemented_groups']),adopted=False,tests_started=False)))


def main():
    parent=ROOT/'EL1_cache_response_match_before_select'
    verify_parent(parent)
    stable_core((parent/'rtl/cpu_core.v').read_text(encoding='utf-8'))
    en=prepare('EN1_mmio_narrow_stable_domains',parent,{'rtl/cpu_core.v':stable_core},
        'Narrow MMIO active data to low32, zero masked upper96 in six16-bit gate domains, and distribute qualified select to seventeen consumers. Entire MMIO request stays stable under backpressure. No state/latency change; source-only.')
    finish(en,parent,'mmio_active_word_and_final_request_domains',
        'Original MMIO predicate/ack edge, active low32 data, address80000000, mask000f, IDfe, and handshake preserved. Masked upper96 are zero during MMIO and full normal data otherwise. Seventeen final-control domains bound each data leaf to16 bits. No added state or cycle.')
    verify_parent(en)
    transforms={'rtl/cache/rv32_dcache_nonblocking.v':held_hit_cache,'rtl/cpu_core.v':held_hit_core}
    for n,f in transforms.items():
        f((en/n).read_text(encoding='utf-8'))
    eo=prepare('EO1_registered_cache_hit_reply',en,transforms,
        'Complete EN1 plus Dcache HIT_BYPASS0. Use existing response owners and held valid; cut arbitration→live-output→LSQ link. No new state; first empty-slot hit response one cycle later. Ordinary integer pipeline10; source-only.')
    finish(eo,en,'existing_register_cache_hit_response_boundary',
        'Inherits stable/narrow MMIO and all EL1 changes. Only Dcache load hit bypass disabled in CPU; parameter default1 retains generic behavior. Existing hit capture, metadata/data owners, slot backpressure, reset, store-ack bypass and clocked source text retained. HIT_BYPASS0 intentionally makes first empty-slot hit return one cycle later; IPC/throughput unmeasured.')


if __name__=='__main__':
    main()
