"""EL1 child: narrow strobed MMIO data and partition qualified mux consumers."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def core(text):
    text=change(text,'''    wire normal_memory_dreq_valid = memory_dreq_valid && !mmio_exit_request;
    assign memory_dreq_ready = mmio_exit_request ? mem_d_req_ready :''',
        '''    // Qualify once, then partition the final request consumers. The
    // acknowledgement retains the original predicate and capture edge.
    wire [10:0] mmio_exit_views;
    rv32_frequency_control_tree #(.LEAVES(11)) mmio_exit_request_tree (
        .signal_i(mmio_exit_request),.views_o(mmio_exit_views));
    wire normal_memory_dreq_valid = memory_dreq_valid && !mmio_exit_views[0];
    assign memory_dreq_ready = mmio_exit_views[1] ? mem_d_req_ready :''')
    text=change(text,'''    assign mem_d_req_valid = mmio_exit_request || normal_mem_d_req_valid;
    assign mem_d_req_write = mmio_exit_request ? 1'b1 : normal_mem_d_req_write;
    assign mem_d_req_line_addr = mmio_exit_request ? 32'h80000000 :
                                  normal_mem_d_req_line_addr;
    assign mem_d_req_wdata = mmio_exit_request ? memory_dreq_wdata :
                              normal_mem_d_req_wdata;
    assign mem_d_req_wmask = mmio_exit_request ? 16'h000f :
                              normal_mem_d_req_wmask;
    assign mem_d_req_id = mmio_exit_request ? 8'hfe : normal_mem_d_req_id;
    assign normal_mem_d_req_ready = mem_d_req_ready && !mmio_exit_request;''',
        '''    assign mem_d_req_valid = mmio_exit_views[2] || normal_mem_d_req_valid;
    assign mem_d_req_write = mmio_exit_views[3] ? 1'b1 : normal_mem_d_req_write;
    assign normal_mem_d_req_ready = mem_d_req_ready && !mmio_exit_views[4];
    genvar mmio_word;
    generate for(mmio_word=0;mmio_word<2;mmio_word=mmio_word+1) begin:g_mmio_request_word
        localparam [15:0] EXIT_ADDRESS_WORD=32'h80000000 >> (16*mmio_word);
        assign mem_d_req_line_addr[mmio_word*16 +: 16]=mmio_exit_views[5+mmio_word] ?
            EXIT_ADDRESS_WORD : normal_mem_d_req_line_addr[mmio_word*16 +: 16];
        assign mem_d_req_wdata[mmio_word*16 +: 16]=mmio_exit_views[7+mmio_word] ?
            memory_dreq_wdata[mmio_word*16 +: 16] : normal_mem_d_req_wdata[mmio_word*16 +: 16];
    end endgenerate
    // Every MMIO exit has mask 000f: upper words issue no AXI write and are
    // never part of its architectural payload. Keep the normal source there,
    // avoiding 96 irrelevant MMIO mux bits; preserve the full normal line.
    assign mem_d_req_wdata[127:32]=normal_mem_d_req_wdata[127:32];
    assign mem_d_req_wmask = mmio_exit_views[9] ? 16'h000f : normal_mem_d_req_wmask;
    assign mem_d_req_id = mmio_exit_views[10] ? 8'hfe : normal_mem_d_req_id;''')
    return text


def main():
    parent=ROOT/'EL1_cache_response_match_before_select'
    verify_parent(parent)
    core((parent/'rtl/cpu_core.v').read_text(encoding='utf-8'))
    out=prepare('EN_mmio_narrow_request_domains',parent,{'rtl/cpu_core.v':core},
        'EL1 child from measured 165-load MMIO-equivalent root: select only the active low32 MMIO data and distribute qualified request selection to 11 bounded consumer domains; unchanged address/mask/ID/handshake/acknowledgement. Upper96 raw data differs only under fixed MMIO mask000f. No added state/latency; source-only.')
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    record_delta(out,parent,groups+['mmio_active_word_and_final_request_domains'])
    path=out/'candidate.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        new_declared_sequential_state_bits=0,declared_additional_state_bits_vs_parent=0,
        measured_parent_run='F:/CPU2026CourseRuns/architecture_EL1_20261005',
        behavior='MMIO detection and acknowledgement clocked text unchanged. Each request select view equals the qualified original flag. All fields and active MMIO low32 payload are identical; only masked upper96 MMIO data uses the normal source. The bridge never issues words whose nibble mask is zero.',
        timing_tradeoff='Removes 96 MMIO data mux consumers and bounds remaining mux groups to16 bits. Extra inversion distribution stages; new global timing/area unknown.',
        source_evidence=['F:/CPU2026Proofs/EL1_mapped_paths_20261005/saved_path_analysis.json',
                         'F:/CPU2026Proofs/EL1_mapped_load_census_20261005.json',
                         'F:/CPU2026Proofs/EL1_selected_mmio_gate_20261005/summary.json'],
        mapped_identity_scope='Under the current nonblocking-cache + MMIO profile, normal mask is allffff or0000; enabled_words low bit equals MMIO request. The alias does not establish exclusive ownership by the bridge function.',
        adoption_condition='Complete combined source review and report the final whole candidate before measurement. No individual test.')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        adopted=False,tests_started=False,new_declared_state_bits=0)))


if __name__=='__main__':
    main()
