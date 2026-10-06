"""Qualify saved/head load identities before the late head-response choice."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A88_saved_load_report_priority'
TARGET = BASE/'A89_load_report_identity_prequalification'
REVIEW = BASE/'A89_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == '9c78baed8b428a67a7abba80664842a0311595e8fce1e7410de422112f85095a'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    marker = '    parameter integer SAVED_REPORT_PRIORITY = 0,'
    text = once(original, marker, marker+'\n    parameter integer HEAD_LOAD_IDENTITY_QUERY = 0,')
    marker = '    output wire [(1<<REPORT_ROB_LOW_BITS)+(1<<REPORT_ROB_HIGH_BITS)-1:0] load_complete_rob_query_o'
    text = once(text, marker, marker+''',
    // Candidate0 is saved/held report, candidate1 is saved queue-head identity.
    // The choice is meaningful only with an actual public completion event.
    output wire [2*ROB_TAG_WIDTH-1:0] load_report_identity_tags_o,
    output wire [2*((1<<REPORT_ROB_LOW_BITS)+(1<<REPORT_ROB_HIGH_BITS))-1:0] load_report_identity_queries_o,
    output wire load_report_identity_head_o''')
    marker = '    wire [REPORT_WIDTH-1:0] report_payload_tree [1:2*REPORT_ROWS-1];'
    text = once(text, marker, marker+'''
    localparam integer REPORT_IDENTITY_WIDTH=ROB_TAG_WIDTH+REPORT_ROB_QUERY_WIDTH;
    wire [REPORT_IDENTITY_WIDTH-1:0] saved_identity_tree [1:2*REPORT_ROWS-1];''')
    marker = '    localparam integer HEAD_STORE_ACK_ACTIVE=(HEAD_STORE_ACK_BYPASS!=0) && (ACK_SOURCE_QUERY!=0);'
    text = once(text, marker, marker+'''
    // Reuse the existing saved-head ROB tag read; unsupported profiles retain
    // their original selected-public-packet query and generation checks.
    localparam integer HEAD_LOAD_IDENTITY_ACTIVE=(HEAD_LOAD_IDENTITY_QUERY!=0) &&
        (SAVED_REPORT_PRIORITY!=0) && (LOAD_COMPLETION_BYPASS==2) &&
        (REPORT_ROB_PREDECODE!=0) && HEAD_STORE_ACK_ACTIVE;''')
    marker = '                assign commit_valid_tree[REPORT_ROWS+report_row]=valid_mem[report_row] && store_mem[report_row] &&'
    text = once(text, marker, '''                if(HEAD_LOAD_IDENTITY_ACTIVE!=0) begin:g_saved_identity_candidate
                    // Neither saved priority nor held identity depends on
                    // current response-valid. Preselect this full candidate.
                    wire saved_grant=report_hold_live_views[report_row/4] ?
                        report_hold_matches[report_row] : report_priority;
                    assign saved_identity_tree[REPORT_ROWS+report_row]=
                        {REPORT_IDENTITY_WIDTH{saved_grant}} &
                        {report_payload[REPORT_BASE_WIDTH +: REPORT_ROB_QUERY_WIDTH],rob_tag_mem[report_row]};
                end else begin:g_no_saved_identity_candidate
                    assign saved_identity_tree[REPORT_ROWS+report_row]=0;
                end
'''+marker)
    marker = '                assign report_payload_tree[REPORT_ROWS+report_row]=0;'
    text = once(text, marker, marker+'\n                assign saved_identity_tree[REPORT_ROWS+report_row]=0;')
    marker = '            assign report_payload_tree[report_node]=report_payload_tree[2*report_node] | report_payload_tree[2*report_node+1];'
    text = once(text, marker, marker+'\n            assign saved_identity_tree[report_node]=saved_identity_tree[2*report_node] | saved_identity_tree[2*report_node+1];')
    marker = '    generate if(REPORT_ROB_PREDECODE!=0) begin:g_report_rob_query'
    text = once(text, marker, '''    generate if(HEAD_LOAD_IDENTITY_ACTIVE!=0) begin:g_load_report_identity_candidates
        wire [REPORT_ROB_QUERY_WIDTH-1:0] head_query;
        wire [ROB_TAG_WIDTH-1:0] head_tag=store_ack_rob_query_tag_o;
        for(genvar head_low=0;head_low<REPORT_ROB_LOW_ROWS;head_low=head_low+1) begin:g_low
            assign head_query[head_low]=head_tag[3 +: REPORT_ROB_LOW_BITS]==head_low;
        end
        for(genvar head_high=0;head_high<REPORT_ROB_HIGH_ROWS;head_high=head_high+1) begin:g_high
            if(REPORT_ROB_HIGH_BITS>0) begin:g_bits
                assign head_query[REPORT_ROB_LOW_ROWS+head_high]=
                    head_tag[3+REPORT_ROB_LOW_BITS +: REPORT_ROB_HIGH_BITS]==head_high;
            end else begin:g_single_bank
                assign head_query[REPORT_ROB_LOW_ROWS+head_high]=1'b1;
            end
        end
        assign load_report_identity_tags_o={head_tag,saved_identity_tree[1][0 +: ROB_TAG_WIDTH]};
        assign load_report_identity_queries_o={head_query,
            saved_identity_tree[1][ROB_TAG_WIDTH +: REPORT_ROB_QUERY_WIDTH]};
        assign load_report_identity_head_o=fast_head_present && !report_hold_live;
    end else begin:g_original_load_report_identity
        assign load_report_identity_tags_o=0;
        assign load_report_identity_queries_o=0;
        assign load_report_identity_head_o=1'b0;
    end endgenerate

'''+marker)
    marker = '    always @* begin\n        complete_slot_found=report_valid_tree[1];'
    assert text[text.index(marker):] == original[original.index(marker):]
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer LSQ_SAVED_REPORT_PRIORITY = '+str(default)+','
        text = once(original, marker, marker+'\n    parameter integer LSQ_HEAD_LOAD_IDENTITY_QUERY = '+str(default)+',')
        if '/backend/' in name:
            marker = '    wire [LSQ_ROB_QUERY_WIDTH-1:0] lsq_load_complete_rob_query;'
            text = once(text, marker, marker+'''
    wire [2*TAG_WIDTH-1:0] lsq_report_identity_tags;
    wire [2*LSQ_ROB_QUERY_WIDTH-1:0] lsq_report_identity_queries;
    wire lsq_report_identity_head,lsq_report_identity_live;
    localparam integer LSQ_HEAD_LOAD_IDENTITY_ACTIVE=(LSQ_HEAD_LOAD_IDENTITY_QUERY!=0) &&
        (LSQ_SAVED_REPORT_PRIORITY!=0) && (LOAD_COMPLETION_BYPASS==2) &&
        (LSQ_ROB_QUERY_PREDECODE!=0) && (LSQ_HEAD_STORE_ACK_BYPASS!=0) &&
        (LSQ_STORE_ACK_SOURCE_QUERY!=0);''')
            marker = '    genvar status_row,status_source,status_lane;'
            text = once(text, marker, '''    // Two saved candidates perform the full live/GEN lookup in parallel.
    // Late head-return choice selects one bool, not a ROB address/tag packet.
    generate if(LSQ_HEAD_LOAD_IDENTITY_ACTIVE!=0) begin:g_load_report_identity_qualification
        wire [1:0] candidate_live;
        for(genvar identity_candidate=0;identity_candidate<2;identity_candidate=identity_candidate+1) begin:g_candidate
            wire [TAG_WIDTH-1:0] tag=lsq_report_identity_tags[identity_candidate*TAG_WIDTH +: TAG_WIDTH];
            wire [ROB_LIVE_WIDTH-1:0] live_state;
            rv32_frequency_array_read_bank_masks #(.WIDTH(ROB_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),
                .INDEX_WIDTH(ROB_SLOT_WIDTH)) live_read (
                .rows_i(rob_live_rows),
                .query_i(lsq_report_identity_queries[identity_candidate*LSQ_ROB_QUERY_WIDTH +: LSQ_ROB_QUERY_WIDTH]),
                .value_o(live_state));
            assign candidate_live[identity_candidate]=tag[0] &&
                tag[3 +: ROB_SLOT_WIDTH]<ROB_ENTRIES && live_state[ROB_GENERATION_WIDTH] &&
                tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]==live_state[0 +: ROB_GENERATION_WIDTH];
        end
        assign lsq_report_identity_live=lsq_report_identity_head ? candidate_live[1] : candidate_live[0];
    end else begin:g_original_load_identity_qualification
        assign lsq_report_identity_live=1'b0;
    end endgenerate

'''+marker)
            text = once(text, '.SAVED_REPORT_PRIORITY(LSQ_SAVED_REPORT_PRIORITY)',
                '.SAVED_REPORT_PRIORITY(LSQ_SAVED_REPORT_PRIORITY), .HEAD_LOAD_IDENTITY_QUERY(LSQ_HEAD_LOAD_IDENTITY_QUERY)')
            text = once(text, '.load_complete_rob_query_o(lsq_load_complete_rob_query),',
                '''.load_complete_rob_query_o(lsq_load_complete_rob_query),
        .load_report_identity_tags_o(lsq_report_identity_tags), .load_report_identity_queries_o(lsq_report_identity_queries),
        .load_report_identity_head_o(lsq_report_identity_head),''')
            marker = '''            if (producer_valid_r[producer_recovery_index] &&
                (!producer_tag_r[producer_recovery_index*TAG_WIDTH] ||
                 !producer_live_reads[producer_recovery_index*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH] ||
                 (producer_tag_r[(producer_recovery_index*TAG_WIDTH) + 3 + ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH] !=
                  producer_live_reads[producer_recovery_index*ROB_LIVE_WIDTH +: ROB_GENERATION_WIDTH])))'''
            text = once(text, marker, '''            if (producer_valid_r[producer_recovery_index] &&
                (((LSQ_HEAD_LOAD_IDENTITY_ACTIVE!=0) && producer_recovery_index==LSQ_SOURCE) ?
                 !lsq_report_identity_live :
                 (!producer_tag_r[producer_recovery_index*TAG_WIDTH] ||
                  !producer_live_reads[producer_recovery_index*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH] ||
                  (producer_tag_r[(producer_recovery_index*TAG_WIDTH) + 3 + ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH] !=
                   producer_live_reads[producer_recovery_index*ROB_LIVE_WIDTH +: ROB_GENERATION_WIDTH]))))''')
            marker = '''        producer_live_reads[LSQ_SOURCE*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH] &&
        lsq_load_complete_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]==
        producer_live_reads[LSQ_SOURCE*ROB_LIVE_WIDTH +: ROB_GENERATION_WIDTH];'''
            text = once(text, marker, '''        ((LSQ_HEAD_LOAD_IDENTITY_ACTIVE!=0) ? lsq_report_identity_live :
         (producer_live_reads[LSQ_SOURCE*ROB_LIVE_WIDTH+ROB_GENERATION_WIDTH] &&
          lsq_load_complete_tag[3+ROB_SLOT_WIDTH +: ROB_GENERATION_WIDTH]==
          producer_live_reads[LSQ_SOURCE*ROB_LIVE_WIDTH +: ROB_GENERATION_WIDTH]));''')
            # ALU/MDU queries and the subsequent original recovery-age guard
            # are preserved; private live qualification cannot bypass cancel.
            for start,end in [
                ('    genvar status_row,status_source,status_lane;','    // The accepted live branch can redirect fetch on its capture edge.'),
                ('        producer_recovery_rob_slot = 0;\n        producer_recovery_age = 0;','    assign producer_valid = producer_valid_r;')]:
                assert text[text.index(start):text.index(end)] == original[original.index(start):original.index(end)]
        else:
            text = once(text, '.LSQ_SAVED_REPORT_PRIORITY(LSQ_SAVED_REPORT_PRIORITY)',
                '.LSQ_SAVED_REPORT_PRIORITY(LSQ_SAVED_REPORT_PRIORITY), .LSQ_HEAD_LOAD_IDENTITY_QUERY(LSQ_HEAD_LOAD_IDENTITY_QUERY)')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_LOAD_REPORT_IDENTITY_PREQUALIFICATION_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],LSQ_HEAD_LOAD_IDENTITY_QUERY=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],LSQ_HEAD_LOAD_IDENTITY_QUERY=1,
        load_report_identity_new_ff_bits=0,load_report_identity_new_sram_bits=0,load_report_identity_new_pipeline_edges=0,
        load_report_identity_rob_live_candidates=2,load_report_identity_reuses_saved_head_tag_reader=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Preselect the original saved/held load-report full ROB tag and bank query independently of current head response. Reuse original saved LSQ head ROBtag read for second candidate. Both candidates query current ROB valid and full generation in parallel; the original head-fast/held choice selects only the final live bool used for LSQ producer and load-error qualification. Public packet/valid/ready/error/cancel, response capture and recovery age guard remain original.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        load_report_full_rob_identity_qualification_before_late_head_response=True,
        load_report_identity_prequalification_limit='Targets A83 response-dependent selected ROB query1.597ns -> live read1.785ns -> completion selection2.091ns. Late response now chooses a prequalified bool, retaining full ROB/LSQ GEN and actual event. Adds saved candidate identity routing and two live readers (old selected query becomes unused for LSQ qualification in active mode); no FF/SRAM/edge. Final payload and other response/format/cancel paths remain; mapping/area/Fmax unmeasured.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,rob_live_candidates=2,
        source_arguments=[
            'A88 makes general saved-report priority independent of current response. New private normal candidate uses the same full-tag held report when live, otherwise that saved-priority grant. The private head candidate reads original rob_tag_mem at saved head through the existing A86 head reader, without response/ACK-valid. Both bank masks encode their exact saved tag slot. No per-LSQ-row ROB lookup, extra result buffer or speculative live flag is stored.',
            'For any valid report: held ownership selects private normal candidate and original public held packet; absent held ownership with fast_head_present selects private saved head and original fast head packet; absent both selects saved normal candidate and original saved packet. Private selected full ROB tag and query thus agree with public on every actual report event. Idle private values are not a completion and do not drive publication. Full current LSQ row/valid/GEN/request_sent/response_wait qualification remains original.',
            'Each private candidate requires original tag-valid, slot<ROB_ENTRIES, current ROB entry-valid and equality of all ROB_GENERATION_WIDTH bits. Course configuration retains all8ROBGEN and9LSQGEN. Candidate masks/tag share the same saved source, including stale/recycled cases. Select only the precomputed live bool with original fast_head_present AND !report_hold_live, removing late selected packet->ROB read->GEN compare from LSQ target-live and accepted error capture.',
            'Only LSQ producer full-identity and LSQ error qualification use the private bool; ALU/MDU original status queries, original subsequent recovery-age guard and completion cancellation/unretired checks remain. Branch training loops cover only ALU sources [0,BE_WIDTH); no other LSQ producer_live_reads consumers were found beyond replaced target-live/error qualification. Existing selected query RTL remains for default compatibility and may be trimmed when unused; trimming is not assumed as measured area evidence.',
            'Public report payload/valid/error/value, held ownership/capture, original slot tournament, metadata completion acceptance/pop/capacity and all state tail are byte-identical. The actual event and full saved/ticket generations are unchanged; no new same-cycle result or bypass is introduced. Existing head tag reader is reused only if split ACK/head protocol, saved priority, head-only completion and bank predecode profiles all apply. Missing/default0/other bypass modes use original selected-public query checks.',
            'Two parallel live readers plus one saved candidate tag/query masked-OR cost combinational gates/fanout. Saved eligibility, head tag read/ROB live generation and payload value formatting may become new limits. No FF/SRAM/new pipeline edge; frequency, area within353um2 margin and aggregate IPC remain unmeasured. A84-A88 behaviors are inherited and not independently verified.',
            'Manual source/ownership/hash review only, no HDL/lint/formal/simulation/synthesis/STA/unit tests. Future coherent coverage includes held/saved/head simultaneous reports, backpressure and priority, recycled full ROB/LSQ generations, retired loads behind buffered stores, response errors/format/forwarding, reset/flush/recovery, all widths/queue geometry/fallback profiles, actual publication/reclaim/MMIO/full RV32IM and course performance. Full objective unproven.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
