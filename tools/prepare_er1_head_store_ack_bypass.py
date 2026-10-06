"""Publish/reclaim a fully qualified head store ack on its actual return edge."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A85_store_ack_source_query'
TARGET = BASE/'A86_head_store_ack_bypass'
REVIEW = BASE/'A86_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old,new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == 'caa8c4e38683a7aff619c7d08623bd16ab3759db0a7f7b0baab2b3236330dc8d'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest,name
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original,'    parameter integer ACK_SOURCE_QUERY = 0,',
        '    parameter integer ACK_SOURCE_QUERY = 0,\n    parameter integer HEAD_STORE_ACK_BYPASS = 0,')
    marker = next(l for l in original.splitlines() if 'store_ack_rob_tag_o,' in l and 'output' in l)
    text = once(text,marker,marker+'\n    output wire [ROB_TAG_WIDTH-1:0]    store_ack_rob_query_tag_o,')
    marker = '    wire [LSQ_ENTRIES-1:0] query_ack_accepted;'
    text = once(text,marker,marker+'''
    localparam integer HEAD_STORE_ACK_ACTIVE=(HEAD_STORE_ACK_BYPASS!=0) && (ACK_SOURCE_QUERY!=0);
    wire [LSQ_ENTRIES-1:0] fast_head_store_acks;
    wire fast_head_store_ack_present=|fast_head_store_acks;
    // Public ACK tag remains the original selected packet. The ROB's
    // optional private query can inspect saved head identity before ACK-valid.
    generate if(HEAD_STORE_ACK_ACTIVE!=0) begin:g_head_store_ack_identity
        wire [LSQ_ENTRIES*ROB_TAG_WIDTH-1:0] rows;
        for(genvar ack_head_row=0;ack_head_row<LSQ_ENTRIES;ack_head_row=ack_head_row+1) begin:g_row
            assign rows[ack_head_row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]=rob_tag_mem[ack_head_row];
        end
        rv32_frequency_array_read #(.WIDTH(ROB_TAG_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) head_reader (
            .rows_i(rows),.index_i(head_reg),.value_o(store_ack_rob_query_tag_o));
    end else begin:g_original_store_ack_identity
        assign store_ack_rob_query_tag_o=store_ack_rob_tag_o;
    end endgenerate''')
    old = '''                wire [ACK_WIDTH-1:0] ack_payload={store_ack_error_mem[report_row],
                    make_lsq_tag(report_row,generation_mem[report_row]),rob_tag_mem[report_row]};'''
    text = once(text,old,'''                assign fast_head_store_acks[report_row]=(HEAD_STORE_ACK_ACTIVE!=0) &&
                    !reset_i && !flush_i && !recovery_valid_i && occupancy_reg!=0 &&
                    head_query_views[report_row*SLOT_WIDTH +: SLOT_WIDTH]==report_row &&
                    valid_mem[report_row] && store_mem[report_row] && !load_mem[report_row] &&
                    store_commit_mem[report_row] && !store_ack_mem[report_row] && query_ack_accepted[report_row];
                wire ack_error=fast_head_store_acks[report_row] ? dcache_store_ack_error_i : store_ack_error_mem[report_row];
                wire [ACK_WIDTH-1:0] ack_payload={ack_error,
                    make_lsq_tag(report_row,generation_mem[report_row]),rob_tag_mem[report_row]};''')
    text = once(text,'''                    valid_mem[report_row] && store_mem[report_row] && store_ack_mem[report_row];''',
        '''                    valid_mem[report_row] && store_mem[report_row] &&
                    (store_ack_mem[report_row] || fast_head_store_acks[report_row]);''')
    text = once(text,'         (head_store && head_ack && store_ack_ready_i));',
        '''         (head_store && store_ack_ready_i &&
          (head_ack || ((HEAD_STORE_ACK_ACTIVE!=0) && fast_head_store_ack_present && store_ack_valid_o))));''')
    # All original capture/pop/state priorities and scalar capacity transitions
    # are retained. A stalled return is captured into the existing head row.
    marker = '    initial begin\n        if(RECLAIM_WIDTH!=1 && RECLAIM_WIDTH!=2)'
    assert text[text.index(marker):] == original[original.index(marker):]
    for marker in [
        'wire ack_event=(ACK_SOURCE_QUERY!=0) ? query_ack_accepted[metadata_row] :',
        'if(ack_event) begin',
        'store_ack_error_mem_write_data[metadata_row]=dcache_store_ack_error_i;',
        'if(pop_event) begin',
        'head_reg <= advance_slot(head_reg, pop_count_calc);',
        'occupancy_reg <= occupancy_reg - pop_count_calc + alloc_count_calc;']:
        assert marker in text,marker
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        text = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer LSQ_STORE_ACK_SOURCE_QUERY = '+str(default)+','
        text = once(text,marker,marker+'\n    parameter integer LSQ_HEAD_STORE_ACK_BYPASS = '+str(default)+',')
        if '/backend/' in name:
            text = once(text,'.ACK_SOURCE_QUERY(LSQ_STORE_ACK_SOURCE_QUERY),',
                '.ACK_SOURCE_QUERY(LSQ_STORE_ACK_SOURCE_QUERY), .HEAD_STORE_ACK_BYPASS(LSQ_HEAD_STORE_ACK_BYPASS),')
            marker = next(l for l in text.splitlines() if 'lsq_store_ack_rob_tag;' in l and 'wire' in l)
            text = once(text,marker,marker+'\n    wire [TAG_WIDTH-1:0] lsq_store_ack_rob_query_tag;')
            text = once(text,'.store_ack_rob_tag_o(lsq_store_ack_rob_tag),',
                '.store_ack_rob_tag_o(lsq_store_ack_rob_tag), .store_ack_rob_query_tag_o(lsq_store_ack_rob_query_tag),')
            text = once(text,'    assign rob_store_ack_tag = lsq_store_ack_rob_tag;',
                '''    assign rob_store_ack_tag = ((LSQ_HEAD_STORE_ACK_BYPASS!=0) && (LSQ_STORE_ACK_SOURCE_QUERY!=0)) ?
        lsq_store_ack_rob_query_tag : lsq_store_ack_rob_tag;''')
        else:
            text = once(text,'.LSQ_STORE_ACK_SOURCE_QUERY(LSQ_STORE_ACK_SOURCE_QUERY),',
                '.LSQ_STORE_ACK_SOURCE_QUERY(LSQ_STORE_ACK_SOURCE_QUERY), .LSQ_HEAD_STORE_ACK_BYPASS(LSQ_HEAD_STORE_ACK_BYPASS),')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_HEAD_STORE_ACK_BYPASS_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],LSQ_HEAD_STORE_ACK_BYPASS=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],LSQ_HEAD_STORE_ACK_BYPASS=1,
        head_store_ack_new_ff_bits=0,head_store_ack_new_sram_bits=0,head_store_ack_new_pipeline_edges=0,
        head_store_ack_wait_edge_removed=1,head_store_ack_backpressure_uses_original_capture=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'With optional split ACK queries, publish an accepted current-generation acknowledgement only for the nonempty committed LSQ head store on its return edge; release it only on original report-ready handshake. Retain original capture for stalls, saved reports for all other ACKs, error/full identities and scalar/pop ownership. Preselect private saved-head ROB tag before late ACK-valid, keeping full ROB GEN authority without an extra late packet-tag selection.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        accepted_head_store_ack_publication_and_reclaim_wait_edge_removed=True,
        head_store_ack_limit='Removes one head acknowledgement capture-to-publication/release wait edge. Benefit requires actual head return and ready; non-head ACKs remain saved and stale/recovery ACKs cannot bypass. No extra holding FF because original head cannot move while ACK-ready0 and captures exact packet. A85/new private saved-head identity reduce data-to-control serialization, but late ack/status to ROB/queue counts still needs STA. IPC/Fmax/area unknown.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'Original queue stores an accepted cache/MMIO ACK into store_ack/error flags, then selects only current head store on following cycle and releases with ACK-ready. New path requires original full-valid/row/allLSQGEN/request_sent/response_wait query match, nonempty current head, committed store/notload/notalreadyacked and no reset/flush/apply. Only that unique irrevocable head can publish early; all non-head/recovery/currently saved or stale responses keep original capture behavior.',
            'Fast payload uses original head fullROBtag, make_lsq_tag current full generation and the exact current unified ACK error. When ACK-ready0, no pop occurs, original ACK capture saves that same error/tag identity and clears response_wait; next cycle original saved report continues for same stationary head. No new result/ticket buffer or backpressure dependency is needed. A duplicate/stale response cannot overwrite a valid saved packet through fast path.',
            'Only original store_ack_valid AND ready on qualified fast head adds early metadata pop. The same original pop_count/second-load-prefix/head/count/cleared rows are used, with original ACK capture then pop priority. Pre-edge allocation capacity remains unchanged; a full queue cannot allocate into the freed row on this edge. Original committed-store recovery protection, data/cache side effects and RAM/MMIO priority are untouched.',
            'Any public ACK valid, saved or fast, belongs to the current valid store head. Private head ROBtag array read therefore equals public packet ROBtag whenever valid, while its idle value is not a result. Backend uses it only for combined query/head-bypass profile; actual ROB ACK-valid remains original LSQ output. Original ROB current valid/row/all8GEN checks, ACK error, ready/wait/halt and other write priorities remain exact. No shortened tag or speculative confirmation.',
            'Parameter0 or missing split-query profile disables fast ACK and uses original public ROBtag. No new FF/SRAM/edge, actual memory transaction or report port. Late ACK qualification/error to ROB/queue counts and extra head reader/parallel candidate targets still change timing/gates; no aggregate IPC or frequency/area guarantee. A83 original frozen measurement untouched.',
            'Manual source/temporal ownership/hash review only; no HDL/lint/formal/simulation/synthesis/STA/unit test. Future coherent coverage: accepted/stalled/saved head and non-head returns, cache bypass/saved/MMIO/both-source priority, exact error, stale LSQ/ROB generations and duplicate ACKs, pending committed stores across recovery, reset/flush, full/wrapped queue and second-load reclaim, simultaneous allocate/retire/ACK, MMIO exit and all widths/default/fallback modes. Full objective remains unproven.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
