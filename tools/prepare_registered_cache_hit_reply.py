"""EN child: use existing cache response owners instead of combinational hit reply."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def cache(text):
    text=change(text,'    parameter integer LOCAL_ACTION_DECODE = 0,',
        '''    parameter integer LOCAL_ACTION_DECODE = 0,
    // Default retains the fast hit reply. Zero uses existing held response
    // metadata/data owners, adding no state and cutting late arbitration.
    parameter integer HIT_BYPASS = 1,''')
    return change(text,'    wire bypass_load_hit = (TAG_SRAM != 0) && !reset_i && core_req_valid &&',
        '    wire bypass_load_hit = (HIT_BYPASS != 0) && (TAG_SRAM != 0) && !reset_i && core_req_valid &&')


def core(text):
    return change(text,'    rv32_dcache_nonblocking #(.LOCAL_SRAM_COMMANDS(DCACHE_LOCAL_SRAM_COMMANDS),',
        '    rv32_dcache_nonblocking #(.HIT_BYPASS(0), .LOCAL_SRAM_COMMANDS(DCACHE_LOCAL_SRAM_COMMANDS),')


def main():
    parent=ROOT/'EN_mmio_narrow_request_domains'
    verify_parent(parent)
    transforms={'rtl/cache/rv32_dcache_nonblocking.v':cache,'rtl/cpu_core.v':core}
    for name,transform in transforms.items():
        transform((parent/name).read_text(encoding='utf-8'))
    out=prepare('EO_registered_cache_hit_reply',parent,transforms,
        'EN child: CPU disables only Dcache load-hit bypass; existing metadata/data owners capture on the original hit edge and resp_valid_reg retains the reply until consumed. Cuts response arbitration through output mux into LSQ selection/extraction. Zero added state; first empty-slot hit response is one cycle later; full pipeline integer depth unchanged.')
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    record_delta(out,parent,groups+['existing_register_cache_hit_response_boundary'])
    path=out/'candidate.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        new_declared_sequential_state_bits=0,declared_additional_state_bits_vs_parent=0,
        measured_parent_run=None,measured_reference_run='F:/CPU2026CourseRuns/architecture_EL1_20261005',
        behavior='Existing request_fire, response_hit_capture, metadata/data capture, held-response slot, reset/recovery, store-ack bypass and all clocked source text retained. HIT_BYPASS=0 selects the already implemented held-hit path for every hit. Parameter default1 retains original generic behavior.',
        timing_tradeoff='Cuts the actual EF response_output_tree bit0/bypass_load_hit critical link. With current TAG_SRAM1, outputs use existing response owners, rather than same-cycle hit fields. First empty-slot hit returns one cycle later; throughput and IPC require final measurement.',
        source_evidence=['F:/CPU2026Proofs/EF_mapped_paths_20261005/saved_path_analysis.json'],
        clock_text_warning='Clocked source text equality does not imply cycle-equivalence: resp_valid_reg <= !(bypass_load_hit && ready) intentionally changes after constant bypass=0.',
        adoption_condition='Complete final combination and finite source/handshake review; report before one overall measurement. Do not test EN or hit-bypass separately.')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        adopted=False,tests_started=False,new_declared_state_bits=0)))


if __name__=='__main__':
    main()
