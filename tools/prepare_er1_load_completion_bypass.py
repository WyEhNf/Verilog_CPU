"""Prepare a generation-qualified LSQ return bypass with held-result identity."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A17R1_shared_iterative_mdu'
TARGET = BASE/'A18_load_completion_bypass'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old,new)


LOCK = '''
    // A bypassed response is always captured by its original row on this
    // edge. If CDB cannot accept it, lock that full LSQ identity and select
    // the same saved packet until accepted or killed/recycled. No duplicate
    // value buffer is needed; incoming and saved values have identical format.
    wire report_hold_valid;
    wire [TAG_WIDTH-1:0] report_hold_tag;
    wire [LSQ_ENTRIES-1:0] report_hold_matches;
    localparam integer REPORT_HOLD_DOMAINS=(LSQ_ENTRIES+3)/4;
    wire [REPORT_HOLD_DOMAINS*TAG_WIDTH-1:0] report_hold_tag_views;
    rv32_frequency_control_tree #(.WIDTH(TAG_WIDTH),.LEAVES(REPORT_HOLD_DOMAINS)) report_hold_tag_tree (
        .signal_i(report_hold_tag),.views_o(report_hold_tag_views));
    wire report_hold_live=report_hold_valid && (|report_hold_matches);
    wire [REPORT_HOLD_DOMAINS:0] report_hold_live_views;
    rv32_frequency_control_tree #(.LEAVES(REPORT_HOLD_DOMAINS+1)) report_hold_live_tree (
        .signal_i(report_hold_live),.views_o(report_hold_live_views));
    generate if(LOAD_COMPLETION_BYPASS!=0) begin:g_report_hold_owner
        reg valid;
        assign report_hold_valid=valid;
        wire capture=!reset_i && !flush_i && load_complete_valid_o && !load_complete_ready_i;
        rv32_frequency_word_bank #(.WIDTH(TAG_WIDTH)) identity_owner (
            .clk_i(clk_i),.write_i(capture),.data_i(load_complete_lsq_tag_o),.data_o(report_hold_tag));
        always @(posedge clk_i) begin
            if(reset_i || flush_i) valid<=1'b0;
            else valid<=load_complete_valid_o && !load_complete_ready_i;
        end
    end else begin:g_no_report_hold_owner
        assign report_hold_valid=1'b0;
        assign report_hold_tag=0;
    end endgenerate
'''


def main():
    assert not TARGET.exists()
    parent = read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original,'    parameter integer LOAD_ADDRESS_LOOKTHROUGH = 0,',
        '    parameter integer LOAD_ADDRESS_LOOKTHROUGH = 0,\n    parameter integer LOAD_COMPLETION_BYPASS = 0,')
    text = once(text,'    genvar report_row,report_word,report_node,report_decode;',
        LOCK+'\n    genvar report_row,report_word,report_node,report_decode;')
    text = once(text,'                wire [REPORT_BASE_WIDTH-1:0] base_report_payload={', '''                // Reuse the exact existing LSQ response value: full byte
                // forwarding merge and signed/unsigned load formatting.
                // response_match_rows already checks LSQ valid/generation
                // and response_wait; only ordinary live loads may bypass.
                wire row_fast_response=(LOAD_COMPLETION_BYPASS!=0) &&
                    !reset_i && !flush_i && !recovery_valid_i &&
                    response_match_rows[report_row] && load_mem[report_row] &&
                    !store_mem[report_row] && request_sent_mem[report_row] &&
                    !complete_mem[report_row] && !load_reported_mem[report_row];
                wire [2:0] row_fast_views;
                rv32_frequency_control_tree #(.LEAVES(3)) fast_mode_tree (
                    .signal_i(row_fast_response),.views_o(row_fast_views));
                wire [31:0] report_value;
                assign report_value[15:0]=row_fast_views[0]?payload_response_value[15:0]:complete_value_mem[report_row][15:0];
                assign report_value[31:16]=row_fast_views[1]?payload_response_value[31:16]:complete_value_mem[report_row][31:16];
                wire report_error=row_fast_views[2]?dcache_resp_error_i:complete_error_mem[report_row];
                wire [REPORT_BASE_WIDTH-1:0] base_report_payload={''')
    text = once(text,'                    complete_error_mem[report_row],complete_value_mem[report_row],',
        '                    report_error,report_value,')
    text = once(text,'valid_mem[report_row] && load_mem[report_row] && complete_mem[report_row] && !load_reported_mem[report_row];',
        'valid_mem[report_row] && load_mem[report_row] && (complete_mem[report_row] || row_fast_response) && !load_reported_mem[report_row];')
    text = once(text,'                if(report_row==0) begin:g_first_direct_report', '''                // A held packet is already saved; keep new-return validity
                // out of the full-tag lock -> priority control path.
                assign report_hold_matches[report_row]=row_in_report_range &&
                    valid_mem[report_row] && load_mem[report_row] && complete_mem[report_row] &&
                    !load_reported_mem[report_row] &&
                    tag_matches_slot(report_hold_tag_views[(report_row/4)*TAG_WIDTH +: TAG_WIDTH],report_row);
                wire report_priority;
                assign report_first[report_row]=report_hold_live_views[report_row/4]?
                    report_hold_matches[report_row]:report_priority;
                if(report_row==0) begin:g_first_direct_report''')
    text = once(text,'                    assign report_first[report_row]=report_upper[report_row] ||',
        '                    assign report_priority=report_upper[report_row] ||')
    text = once(text,'                    assign report_first[report_row]=\n                        (report_upper[report_row]',
        '                    assign report_priority=\n                        (report_upper[report_row]')
    text = once(text,'        complete_slot_select=complete_slot_found?report_slot_tree[1]:head_reg;',
        '''        complete_slot_select=complete_slot_found?
            (report_hold_live_views[REPORT_HOLD_DOMAINS]?
             report_hold_tag[TAG_SLOT_LSB +: SLOT_WIDTH]:report_slot_tree[1]):head_reg;''')
    # Original capture, metadata response/report event priority, recovery,
    # hazard/forwarding/request logic and every existing clock block remain.
    marker = '    // Wide payload fields have no reset state.'
    assert text.split(marker,1)[1] == original.split(marker,1)[1]
    assert text.count('assign report_first[report_row]') == 1
    assert text.count('assign report_priority=') == 2
    changes[name] = text
    name = 'rtl/backend/rv32_backend_joint.v'
    text = (PARENT/name).read_text(encoding='utf-8')
    text = once(text,'    parameter integer EARLY_LOAD_ADDRESS = 0,',
        '    parameter integer EARLY_LOAD_ADDRESS = 0,\n    parameter integer LOAD_COMPLETION_BYPASS = 0,')
    text = once(text,'.LOAD_ADDRESS_LOOKTHROUGH(EARLY_LOAD_ADDRESS>=3),',
        '.LOAD_ADDRESS_LOOKTHROUGH(EARLY_LOAD_ADDRESS>=3), .LOAD_COMPLETION_BYPASS(LOAD_COMPLETION_BYPASS),')
    changes[name] = text
    name = 'rtl/cpu_core.v'
    text = (PARENT/name).read_text(encoding='utf-8')
    text = once(text,'    parameter integer EARLY_LOAD_ADDRESS = 0,',
        '    parameter integer EARLY_LOAD_ADDRESS = 0,\n    parameter integer LOAD_COMPLETION_BYPASS = 0,')
    text = once(text,'.EARLY_LOAD_ADDRESS(EARLY_LOAD_ADDRESS),',
        '.EARLY_LOAD_ADDRESS(EARLY_LOAD_ADDRESS), .LOAD_COMPLETION_BYPASS(LOAD_COMPLETION_BYPASS),')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT/name).read_text(encoding='utf-8')
    text = once(text,'    parameter integer EARLY_LOAD_ADDRESS = 3,',
        '    parameter integer EARLY_LOAD_ADDRESS = 3,\n    parameter integer LOAD_COMPLETION_BYPASS = 1,')
    text = once(text,'.EARLY_LOAD_ADDRESS(EARLY_LOAD_ADDRESS),',
        '.EARLY_LOAD_ADDRESS(EARLY_LOAD_ADDRESS), .LOAD_COMPLETION_BYPASS(LOAD_COMPLETION_BYPASS),')
    changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)))
    record['parameter_overrides'] = dict(parent['parameter_overrides'],LOAD_COMPLETION_BYPASS=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],LOAD_COMPLETION_BYPASS=1,
        load_report_hold_identity_bits=17)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Publish a full-generation-matching load return through the existing LSQ report tree on its response edge; original row capture supplies fallback and a full-tag hold protects stalled packet identity.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        load_return_added_wait_edges_before=1,load_return_added_wait_edges_after=0,
        load_report_hold_declared_state_bits=17,
        bypass_mapped_gain_unmeasured=True,bypass_cache_lsq_cdb_prf_combined_timing_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof = dict(status='SOURCE_LSQ_LOAD_RETURN_PROTOCOL_REVIEW_UNTESTED',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),parent_sha256=sha(PARENT/'candidate.json'),
        changed_files=list(changes),original_row_owners_and_request_hazard_recovery_suffix_exact=True,
        tests_started=False,adopted=False,
        source_arguments=[
            'The fast row requires normal mode, full LSQ generation/slot validity, response_wait, request_sent, load-only, not already complete/reported. Arbitrary/stale/store responses do not publish through it.',
            'Incoming value and error use precisely the original byte forwarding merge, line/word selection and signed/unsigned format. Full ROB tag, physical destination, LSQ tag, unretired flag and local recovery cancellation remain in the selected packet.',
            'Raw row eligibility is computed independently of CDB ready. The existing oldest tournament chooses among saved completions and a new return; no valid/ready combinational loop is introduced.',
            'Original result/value/error/complete capture still runs on every qualified response, even when it reports directly. An accepted report sets reported in the same row; complete still becomes true. It cannot report twice.',
            'If not accepted, a 17-bit valid/full-LSQ-tag lock selects the same original row after its value is saved. Hold matches include full generation; killed/recycled tags cannot hold a new row. The same lock also stabilizes ordinary saved report packets against later arrivals.',
            'Metadata complete_slot_select follows the held row, not the unforced oldest winner, so report/pop bookkeeping always refers to the actual published packet.',
            'During reset/flush/owner recovery no new response bypass is asserted. Original row recovery and cancellation remain unchanged; a live older held row persists, a killed row loses lock matching after invalidation.',
            'No original clock block or the complete request/hazard/forwarding/metadata/storage suffix changes. LOAD_COMPLETION_BYPASS=0 removes the new hold owner and keeps saved-only eligibility/payload/oldest selection.',
            'The cost is a longer cache-return -> LSQ report -> CDB/PRF combinational interval, a small result mux and hold identity. Fmax>300, area and real IPC must be measured; 17 declared bits are not a mapped-area claim.',
            'Inherits A17R1 shared iterative MDU and its explicit M-throughput/coverage risks. The running A16R2 snapshot is unchanged; no new CPU/EDA test is dispatched.'
        ])
    write(BASE/'A18_source_review.json',proof)
    print({key:proof[key] for key in ('status','candidate','candidate_sha256','tests_started')})


if __name__ == '__main__':
    main()
