"""Match cache/MMIO acknowledgement identities before late source validity."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A84_rob_store_prefix_admission'
TARGET = BASE/'A85_store_ack_source_query'
REVIEW = BASE/'A85_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == '2b524c9472a3420c98290f9e9be6b8fcd5fd26731e3c84932f19dcf29270f880'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    name = 'rtl/cache/rv32_dcache_nonblocking.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    marker = next(l for l in original.splitlines() if 'dcache_store_ack_lsq_tag_o,' in l)
    text = once(original,marker,marker+'\n    output wire [TAG_WIDTH-1:0]     dcache_store_ack_query_tag_o,')
    marker = '    assign dcache_store_ack_error_o = !ack_output_views[RESPONSE_TAG_WORDS] && ack_error_reg;'
    text = once(text,marker,marker+'''
    // Private candidate identity, meaningful only with actual ack-valid.
    // A saved ack wins; otherwise a valid bypass must belong to core_req.
    // Public valid/tag/error and all capture/consumption rules stay exact.
    wire [RESPONSE_TAG_WORDS-1:0] saved_ack_identity_views;
    rv32_frequency_control_tree #(.LEAVES(RESPONSE_TAG_WORDS)) ack_identity_tree (
        .signal_i(ack_valid_reg),.views_o(saved_ack_identity_views));
    generate for(genvar query_word=0;query_word<RESPONSE_TAG_WORDS;query_word=query_word+1) begin:g_ack_query_tag
        localparam integer LOW=query_word*16;
        localparam integer BITS=(TAG_WIDTH-LOW>=16)?16:TAG_WIDTH-LOW;
        assign dcache_store_ack_query_tag_o[LOW +: BITS]=saved_ack_identity_views[query_word] ?
            ack_lsq_reg[LOW +: BITS] : core_req_lsq_tag[LOW +: BITS];
    end endgenerate''')
    assert text[text.index('    assign mem_req_valid_o'): ] == original[original.index('    assign mem_req_valid_o'): ]
    changes[name] = text
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original,'    parameter integer STORE_ADMISSION_BYPASS = 0,',
        '    parameter integer STORE_ADMISSION_BYPASS = 0,\n    parameter integer ACK_SOURCE_QUERY = 0,')
    marker = next(l for l in original.splitlines() if 'dcache_store_ack_error_i,' in l and 'input' in l)
    text = once(text,marker,marker+'''
    input  wire [1:0]                   store_ack_query_valid_i,
    input  wire [2*TAG_WIDTH-1:0]       store_ack_query_tag_i,''')
    marker = '    wire ack_valid_tree [1:2*REPORT_ROWS-1];'
    text = once(text,marker,marker+'''
    wire [LSQ_ENTRIES-1:0] query_ack_accepted;
    generate if(ACK_SOURCE_QUERY!=0) begin:g_store_ack_source_query
        localparam integer DOMAINS=(LSQ_ENTRIES+3)/4;
        wire [DOMAINS*2-1:0] validity_views;
        // Source1 is cache and has exactly the original core priority over
        // source0 MMIO. Identities are compared independently before this
        // late actual-valid qualification; never invent a completion event.
        rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(DOMAINS)) validity_tree (
            .signal_i({store_ack_query_valid_i[1],
                store_ack_query_valid_i[0] && !store_ack_query_valid_i[1]}),.views_o(validity_views));
        for(genvar query_row=0;query_row<LSQ_ENTRIES;query_row=query_row+1) begin:g_row
            wire waiting=request_sent_mem[query_row] && response_wait_mem[query_row];
            wire mmio_match=tag_matches_slot(store_ack_query_tag_i[0 +: TAG_WIDTH],query_row) && waiting;
            wire cache_match=tag_matches_slot(store_ack_query_tag_i[TAG_WIDTH +: TAG_WIDTH],query_row) && waiting;
            assign query_ack_accepted[query_row]=
                (mmio_match && validity_views[(query_row/4)*2]) ||
                (cache_match && validity_views[(query_row/4)*2+1]);
        end
    end else begin:g_original_store_ack_query
        assign query_ack_accepted=0;
    end endgenerate''')
    old = '''        wire ack_event=metadata_events[metadata_row*7+2] &&
            tag_matches_slot(dcache_store_ack_lsq_tag_i,metadata_row) &&
            request_sent_mem[metadata_row] && response_wait_mem[metadata_row];'''
    text = once(text,old,'''        wire ack_event=(ACK_SOURCE_QUERY!=0) ? query_ack_accepted[metadata_row] :
            (metadata_events[metadata_row*7+2] &&
             tag_matches_slot(dcache_store_ack_lsq_tag_i,metadata_row) &&
             request_sent_mem[metadata_row] && response_wait_mem[metadata_row]);''')
    for marker in [
        'store_ack_error_mem_write_data[metadata_row]=dcache_store_ack_error_i;',
        'wire metadata_pop=(occupancy_reg!=0) && head_valid &&',
        'wire [ACK_WIDTH-1:0] ack_payload={store_ack_error_mem[report_row],',
        'assign dcache_req_valid_o' if 'assign dcache_req_valid_o' in original else 'dcache_resp_ready_o = 1\'b1;']:
        assert marker in text,marker
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer ROB_STORE_PREFIX_ADMISSION = '+str(default)+','
        text = once(original,marker,marker+'\n    parameter integer LSQ_STORE_ACK_SOURCE_QUERY = '+str(default)+',')
        if '/backend/' in name:
            marker = next(l for l in text.splitlines() if 'dcache_store_ack_error_i,' in l and 'input' in l)
            text = once(text,marker,marker+'''
    input  wire [1:0]                   store_ack_query_valid_i,
    input  wire [2*TAG_WIDTH-1:0]       store_ack_query_tag_i,''')
            text = once(text,'.STORE_ADMISSION_BYPASS(LSQ_STORE_ADMISSION_BYPASS),',
                '.STORE_ADMISSION_BYPASS(LSQ_STORE_ADMISSION_BYPASS), .ACK_SOURCE_QUERY(LSQ_STORE_ACK_SOURCE_QUERY),')
            text = once(text,'.store_ack_ready_i(1\'b1),',
                '.store_ack_ready_i(1\'b1), .store_ack_query_valid_i(store_ack_query_valid_i), .store_ack_query_tag_i(store_ack_query_tag_i),')
        else:
            text = once(text,'.ROB_STORE_PREFIX_ADMISSION(ROB_STORE_PREFIX_ADMISSION),',
                '.ROB_STORE_PREFIX_ADMISSION(ROB_STORE_PREFIX_ADMISSION), .LSQ_STORE_ACK_SOURCE_QUERY(LSQ_STORE_ACK_SOURCE_QUERY),')
            if name.endswith('cpu_core.v'):
                marker = '    wire [ROB_TAG_WIDTH-1:0] cache_store_ack_lsq_tag;'
                text = once(text,marker,marker+'\n    wire [ROB_TAG_WIDTH-1:0] cache_store_ack_query_tag;')
                start = text.index('    if (DCACHE_MSHRS > 1) begin : g_nonblocking_dcache')
                end = text.index('    end else begin : g_blocking_dcache',start)
                block = once(text[start:end],'.dcache_store_ack_lsq_tag_o(cache_store_ack_lsq_tag),',
                    '.dcache_store_ack_lsq_tag_o(cache_store_ack_lsq_tag), .dcache_store_ack_query_tag_o(cache_store_ack_query_tag),')
                text = text[:start]+block+text[end:]
                text = once(text,'    end else begin : g_blocking_dcache',
                    '    end else begin : g_blocking_dcache\n    assign cache_store_ack_query_tag=cache_store_ack_lsq_tag;')
                start = text.index('    end else begin : g_ooo_backend')
                block = once(text[start:],'.dcache_store_ack_error_i(dcache_store_ack_error), .commit_ready_i(commit_ready),',
                    '''.dcache_store_ack_error_i(dcache_store_ack_error),
        .store_ack_query_valid_i({cache_store_ack_valid,mmio_ack_pending}),
        .store_ack_query_tag_i({cache_store_ack_query_tag,mmio_ack_lsq_tag}), .commit_ready_i(commit_ready),''')
                text = text[:start]+block
                public = '''    assign dcache_store_ack_valid = cache_store_ack_valid || mmio_ack_pending;
    assign dcache_store_ack_lsq_tag = cache_store_ack_valid ?
        cache_store_ack_lsq_tag : mmio_ack_lsq_tag;
    assign dcache_store_ack_error = cache_store_ack_valid ?
        cache_store_ack_error : 1'b0;'''
                assert public in text
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_STORE_ACK_SOURCE_QUERY_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],LSQ_STORE_ACK_SOURCE_QUERY=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],LSQ_STORE_ACK_SOURCE_QUERY=1,
        store_ack_source_query_new_ff_bits=0,store_ack_source_query_new_sram_bits=0,store_ack_source_query_new_pipeline_edges=0,
        store_ack_cache_over_mmio_priority_preserved=True,store_ack_public_interface_unchanged=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Expose a private nonblocking-cache ack tag selected by saved ack_valid rather than late bypass_store_ack. Compare that cache candidate and saved MMIO candidate independently against every original LSQ full valid/row/GEN/wait identity; gate with original actual source validity/cache-over-MMIO priority. Public ACK signals, capture/error/state/reclaim timing stay unchanged; flag0 uses exact original single-source matcher.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        store_ack_late_tag_muxes_before_current_identity_removed_in_enabled_profile=2,
        store_ack_source_query_limit='No latency/IPC edge removed. Preparatory clock-path rewrite before a possible head-ack bypass. Saves late cache bypass-tag and core cache/MMIO-tag selection before full LSQ identity; adds parallel candidate comparisons. No numerical timing/area gain or mapping pruning guaranteed.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'Cache public ack_valid=ack_valid_reg OR bypass_store_ack; bypass requires !ack_valid_reg. Therefore when actual cache ack is valid, private saved-ack-priority tag equals exact public tag: ack_lsq_reg if saved valid, else core_req_lsq_tag. Public valid/tag/error and all saved-state/handshake rules remain byte-identical; private idle candidate is intentionally not a public valid result.',
            'Core public unified ACK remains cache_valid OR mmio_pending with cache priority and unchanged error. New query input1=actual cache-valid/private cache tag; input0=saved MMIO pending/tag. Cache grant suppresses MMIO exactly as original, including both-valid collisions. Blocking cache uses its unchanged public tag as query. Both named backend call modes retain original public signals; only OoO gets this optional query bus.',
            'Per-row accepted query distributes OR over the original selected-tag match: full tag_matches_slot with original current valid/row/GEN and request_sent/response_wait is evaluated for both candidates, then actual source grants qualify it. For coherent core inputs this is exactly original ack_event, including reset/recovery phases and arbitrary legal tags. No source-valid or generation bit is invented/removed.',
            'Enabled metadata ACK capture uses exact query accepted bit, otherwise original bounded local valid and tag matcher. Error capture still uses original unified error. Original output ACK packet/arbitration, queue pop/head/count, all response/request/store-commit/retirement/recovery/error priorities and state edges remain unchanged. Additional candidates are optional component inputs and default flag0 ignores them.',
            'This prepares a potential head-only ACK report/reclaim bypass without late source-tag muxes in front of generation lookup. No FF/SRAM/edge/new memory or ROB report port. Extra parallel match gates and private tag selection cost area; actual timing/mapping/IPC unknown and A83 frozen run/source untouched. No HDL/lint/formal/simulation/synthesis/STA/unit tests run.',
            'Future coherent batch: saved/cache-bypass/MMIO/no ACK and both-valid priority, backpressure, stale full LSQ generation/row aliases, accepted waiting and rejected sent/wait flags, reset/flush/recovery, blocking/nonblocking cache and TAG_SRAM modes, query flag0/1 and widths1/2/4. No equivalence claim for contradictory independently supplied optional query/public inputs.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
