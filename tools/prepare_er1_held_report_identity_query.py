"""Prepare independent normal/head/held ROB qualification; no HDL tests."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import ROOT, read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A99_balanced_saved_identity'
TARGET = BASE/'A100_held_report_identity_query'
REVIEW = BASE/'A100_source_review.json'


def once(text,old,new):
    assert text.count(old) == 1, old
    return text.replace(old,new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    assert sha(PARENT/'candidate.json') == '9ce4ac5d048d7e5ab8c18854a097ebcb450f1abc18dc25ad339dc60702b32704'
    parent = read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    marker = '    parameter integer HEAD_LOAD_IDENTITY_QUERY = 0,'
    text = once(original,marker,marker+'\n    parameter integer HELD_LOAD_IDENTITY_QUERY = 0,')
    text = once(text,'    output wire load_report_identity_head_o\n',
        '    output wire load_report_identity_head_o,\n'
        '    output wire [ROB_TAG_WIDTH-1:0] load_report_held_identity_tag_o,\n'
        '    output wire [(1<<REPORT_ROB_LOW_BITS)+(1<<REPORT_ROB_HIGH_BITS)-1:0] load_report_held_identity_query_o,\n'
        '    output wire load_report_identity_held_o\n')
    marker = '    localparam integer HEAD_LOAD_PACKET_ACTIVE=(HEAD_LOAD_PACKET_PRESELECT!=0) && HEAD_LOAD_IDENTITY_ACTIVE;'
    text = once(text,marker,marker+'''
    localparam integer HELD_LOAD_IDENTITY_ACTIVE=(HELD_LOAD_IDENTITY_QUERY!=0) && HEAD_LOAD_IDENTITY_ACTIVE;
    localparam integer NORMAL_IDENTITY_WIDTH=ROB_TAG_WIDTH+REPORT_ROB_QUERY_WIDTH;
    localparam integer NORMAL_IDENTITY_WORDS=(NORMAL_IDENTITY_WIDTH+15)/16;
    wire [NORMAL_IDENTITY_WIDTH-1:0] normal_identity_tree [1:2*REPORT_ROWS-1];''')
    marker = '                if(HEAD_LOAD_IDENTITY_ACTIVE!=0) begin:g_saved_identity_candidate'
    text = once(text,marker,'''                if(HELD_LOAD_IDENTITY_ACTIVE!=0) begin:g_normal_identity_candidate
                    // Read ordinary priority independently of held-live. The
                    // full public packet still uses the original saved grant.
                    wire [NORMAL_IDENTITY_WIDTH-1:0] identity={
                        report_payload[REPORT_BASE_WIDTH +: REPORT_ROB_QUERY_WIDTH],rob_tag_mem[report_row]};
                    wire [NORMAL_IDENTITY_WORDS-1:0] grant_views;
                    rv32_frequency_control_tree #(.LEAVES(NORMAL_IDENTITY_WORDS)) mask_tree (
                        .signal_i(report_priority),.views_o(grant_views));
                    for(genvar normal_word=0;normal_word<NORMAL_IDENTITY_WORDS;normal_word=normal_word+1) begin:g_word
                        localparam integer LOW=normal_word*16;
                        localparam integer BITS=(NORMAL_IDENTITY_WIDTH-LOW>=16)?16:NORMAL_IDENTITY_WIDTH-LOW;
                        assign normal_identity_tree[REPORT_ROWS+report_row][LOW +: BITS]=
                            {BITS{grant_views[normal_word]}} & identity[LOW +: BITS];
                    end
                end else begin:g_no_normal_identity
                    assign normal_identity_tree[REPORT_ROWS+report_row]=0;
                end
'''+marker)
    marker = '                assign saved_identity_tree[REPORT_ROWS+report_row]=0;\n                assign ack_payload_tree'
    text = once(text,marker,'                assign saved_identity_tree[REPORT_ROWS+report_row]=0;\n                assign normal_identity_tree[REPORT_ROWS+report_row]=0;\n                assign ack_payload_tree')
    marker = '        for(report_node=1;report_node<REPORT_ROWS;report_node=report_node+1) begin:g_report_merge'
    text = once(text,marker,marker+'''
            if(HELD_LOAD_IDENTITY_ACTIVE!=0) begin:g_normal_identity_pair
                rv32_lsq_identity_pair_or #(.WIDTH(NORMAL_IDENTITY_WIDTH)) pair (
                    .left_i(normal_identity_tree[2*report_node]),
                    .right_i(normal_identity_tree[2*report_node+1]),
                    .value_o(normal_identity_tree[report_node]));
            end else begin:g_no_normal_identity_pair
                assign normal_identity_tree[report_node]=0;
            end''')
    old = '''        assign load_report_identity_tags_o={head_tag,saved_identity_tree[1][0 +: ROB_TAG_WIDTH]};
        assign load_report_identity_queries_o={head_query,
            saved_identity_tree[1][SAVED_IDENTITY_QUERY_LSB +: REPORT_ROB_QUERY_WIDTH]};'''
    new = '''        if(HELD_LOAD_IDENTITY_ACTIVE!=0) begin:g_independent_held_identity
            wire [LSQ_ENTRIES*ROB_TAG_WIDTH-1:0] held_rows;
            for(genvar held_row=0;held_row<LSQ_ENTRIES;held_row=held_row+1) begin:g_row
                assign held_rows[held_row*ROB_TAG_WIDTH +: ROB_TAG_WIDTH]=rob_tag_mem[held_row];
            end
            // The original full LSQ generation/range/live/complete checks still
            // decide held-live. Identity can be read before those checks finish.
            rv32_frequency_array_read #(.WIDTH(ROB_TAG_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) held_reader (
                .rows_i(held_rows),.index_i(report_hold_tag[TAG_SLOT_LSB +: SLOT_WIDTH]),
                .value_o(load_report_held_identity_tag_o));
            for(genvar held_low=0;held_low<REPORT_ROB_LOW_ROWS;held_low=held_low+1) begin:g_low
                assign load_report_held_identity_query_o[held_low]=
                    load_report_held_identity_tag_o[3 +: REPORT_ROB_LOW_BITS]==held_low;
            end
            for(genvar held_high=0;held_high<REPORT_ROB_HIGH_ROWS;held_high=held_high+1) begin:g_high
                if(REPORT_ROB_HIGH_BITS>0) begin:g_bits
                    assign load_report_held_identity_query_o[REPORT_ROB_LOW_ROWS+held_high]=
                        load_report_held_identity_tag_o[3+REPORT_ROB_LOW_BITS +: REPORT_ROB_HIGH_BITS]==held_high;
                end else begin:g_single_bank
                    assign load_report_held_identity_query_o[REPORT_ROB_LOW_ROWS+held_high]=1'b1;
                end
            end
            assign load_report_identity_tags_o={head_tag,normal_identity_tree[1][0 +: ROB_TAG_WIDTH]};
            assign load_report_identity_queries_o={head_query,
                normal_identity_tree[1][ROB_TAG_WIDTH +: REPORT_ROB_QUERY_WIDTH]};
            assign load_report_identity_held_o=report_hold_live;
        end else begin:g_original_saved_held_identity
            assign load_report_identity_tags_o={head_tag,saved_identity_tree[1][0 +: ROB_TAG_WIDTH]};
            assign load_report_identity_queries_o={head_query,
                saved_identity_tree[1][SAVED_IDENTITY_QUERY_LSB +: REPORT_ROB_QUERY_WIDTH]};
            assign load_report_held_identity_tag_o=0;
            assign load_report_held_identity_query_o=0;
            assign load_report_identity_held_o=1'b0;
        end'''
    text = once(text,old,new)
    marker = "        assign load_report_identity_head_o=1'b0;"
    text = once(text,marker,marker+"\n        assign load_report_held_identity_tag_o=0;\n        assign load_report_held_identity_query_o=0;\n        assign load_report_identity_held_o=1'b0;")
    marker = '    generate if(REPORT_ROB_PREDECODE!=0) begin:g_report_rob_query'
    assert text[text.index(marker):] == original[original.index(marker):]
    text = once(text,'    // Candidate0 is saved/held report, candidate1 is saved queue-head identity.',
        '    // Candidate0 is saved/held, or ordinary saved when independent held is\n    // enabled; candidate1 is saved queue-head. Held has its own optional port.')
    changes[name] = text
    name = 'rtl/backend/rv32_backend_joint.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    marker = '    parameter integer LSQ_HEAD_LOAD_IDENTITY_QUERY = 0,'
    text = once(original,marker,marker+'\n    parameter integer LSQ_HELD_LOAD_IDENTITY_QUERY = 0,')
    marker = '    wire lsq_report_identity_head,lsq_report_identity_live;'
    text = once(text,marker,marker+'''
    wire [TAG_WIDTH-1:0] lsq_report_held_identity_tag;
    wire [LSQ_ROB_QUERY_WIDTH-1:0] lsq_report_held_identity_query;
    wire lsq_report_identity_held;''')
    marker = '        (LSQ_STORE_ACK_SOURCE_QUERY!=0);'
    text = once(text,marker,marker+'''
    localparam integer LSQ_HELD_LOAD_IDENTITY_ACTIVE=(LSQ_HELD_LOAD_IDENTITY_QUERY!=0) && LSQ_HEAD_LOAD_IDENTITY_ACTIVE;
    localparam integer LSQ_REPORT_IDENTITY_CANDIDATES=(LSQ_HELD_LOAD_IDENTITY_ACTIVE!=0)?3:2;''')
    text = once(text,'        wire [1:0] candidate_live;','        wire [LSQ_REPORT_IDENTITY_CANDIDATES-1:0] candidate_live;')
    text = once(text,'identity_candidate<2;identity_candidate=identity_candidate+1','identity_candidate<LSQ_REPORT_IDENTITY_CANDIDATES;identity_candidate=identity_candidate+1')
    old = '            wire [TAG_WIDTH-1:0] tag=lsq_report_identity_tags[identity_candidate*TAG_WIDTH +: TAG_WIDTH];'
    new = '''            wire [TAG_WIDTH-1:0] tag;
            wire [LSQ_ROB_QUERY_WIDTH-1:0] query;
            if(identity_candidate==2) begin:g_held
                assign tag=lsq_report_held_identity_tag;
                assign query=lsq_report_held_identity_query;
            end else begin:g_saved_or_head
                assign tag=lsq_report_identity_tags[identity_candidate*TAG_WIDTH +: TAG_WIDTH];
                assign query=lsq_report_identity_queries[identity_candidate*LSQ_ROB_QUERY_WIDTH +: LSQ_ROB_QUERY_WIDTH];
            end'''
    text = once(text,old,new)
    text = once(text,'.query_i(lsq_report_identity_queries[identity_candidate*LSQ_ROB_QUERY_WIDTH +: LSQ_ROB_QUERY_WIDTH]),','.query_i(query),')
    old = '        assign lsq_report_identity_live=lsq_report_identity_head ? candidate_live[1] : candidate_live[0];'
    new = '''        if(LSQ_HELD_LOAD_IDENTITY_ACTIVE!=0) begin:g_choose_held
            assign lsq_report_identity_live=lsq_report_identity_held ? candidate_live[2] :
                (lsq_report_identity_head ? candidate_live[1] : candidate_live[0]);
        end else begin:g_original_choice
            assign lsq_report_identity_live=lsq_report_identity_head ? candidate_live[1] : candidate_live[0];
        end'''
    text = once(text,old,new)
    text = once(text,'.HEAD_LOAD_IDENTITY_QUERY(LSQ_HEAD_LOAD_IDENTITY_QUERY)',
        '.HEAD_LOAD_IDENTITY_QUERY(LSQ_HEAD_LOAD_IDENTITY_QUERY), .HELD_LOAD_IDENTITY_QUERY(LSQ_HELD_LOAD_IDENTITY_QUERY)')
    marker = '        .load_report_identity_head_o(lsq_report_identity_head),'
    text = once(text,marker,'''        .load_report_held_identity_tag_o(lsq_report_held_identity_tag),
        .load_report_held_identity_query_o(lsq_report_held_identity_query),
        .load_report_identity_held_o(lsq_report_identity_held),
'''+marker)
    text = once(text,'    // Two saved candidates perform the full live/GEN lookup in parallel.',
        '    // Saved, head and optional held identities perform the full live/GEN\n    // lookup independently; late report choice selects only a qualified bool.')
    changes[name] = text
    for name in ['rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer LSQ_HEAD_LOAD_IDENTITY_QUERY = '+str(default)+','
        text = once(original,marker,marker+'\n    parameter integer LSQ_HELD_LOAD_IDENTITY_QUERY = '+str(default)+',')
        text = once(text,'.LSQ_HEAD_LOAD_IDENTITY_QUERY(LSQ_HEAD_LOAD_IDENTITY_QUERY)',
            '.LSQ_HEAD_LOAD_IDENTITY_QUERY(LSQ_HEAD_LOAD_IDENTITY_QUERY), .LSQ_HELD_LOAD_IDENTITY_QUERY(LSQ_HELD_LOAD_IDENTITY_QUERY)')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_HELD_NORMAL_HEAD_INDEPENDENT_FULL_ROB_QUALIFICATION_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),source_root=str(TARGET),parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_from_parent_files=list(changes),
        source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},preparation_script_sha256=sha(Path(__file__)),
        source_review=str(REVIEW),tests_started=False,synthesis_started=False,timing_started=False,adopted=False,
        candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],LSQ_HELD_LOAD_IDENTITY_QUERY=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],LSQ_HELD_LOAD_IDENTITY_QUERY=1,
        independent_held_identity_new_ff_bits=0,independent_held_identity_new_sram_bits=0,
        independent_held_identity_new_pipeline_edges=0,independent_held_identity_extra_rob_live_queries=1)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Preselect ordinary saved full ROB identity/query without held-live, read held ROB identity from original held LSQ slot without late range/live qualification, independently query three complete current ROB valid/GEN states, then select one live bool by original held/head choice. All public completion payload/query/valid/hold/ACK/recovery/commit/state code unchanged. Removes held-live -> saved wide mask/OR -> ROB live-query/GEN from eligibility chain at cost of one narrow ordinary identity tree and one additional full ROB live read. Unmeasured; preserve option0 original A99.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        independent_held_identity_limit='A94 held-live0.6385/0.7101 -> saved query1.593 -> ROB live1.811 -> completion2.185 -> alloc/GEN3.385ns. A100 moves full held/ordinary queries before original held-live selection. Late held selection controls a bool rather than28-bit private identity; public85-bit packet remains original. One extra9-bit ROB lookup plus28-bit normal tree increases combination area; no measured savings or guarantee. A99 original PPA still running, which will decide net area/timing need before another measurement.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,
        added_declared_ff_bits=0,added_sram_bits=0,added_pipeline_edges=0,extra_rob_live_queries=1,
        source_arguments=[
            'When original held-live H=0, original saved_grant per row equals report_priority P. New normal tree uses exactly P and original unmasked query/ROBtag, with same OR recurrence; therefore candidate0 tag/query equals old saved candidate0 for all leaf vectors. Original head flag/query and candidate1 remain unchanged.',
            'When H=1, at least one original held_match exists. Its full tag_matches_slot includes tag[0], currentLSQvalid, exact slot bits and completeLSQGEN. Distinct valid rows have distinct representable slot values, so at most one match can exist even for arbitrary current row state. Its row is exactly held_tag slot. Original saved_grant=held_match thus old saved candidate is precisely rob_tag_mem[held_slot] plus its decoded ROBquery. New held reader reads exactly those saved bits; direct low/high bank decode equals original per-row query. No reachable-state assumption or removal of original range/valid/load/complete/reported/fullGEN checks.',
            'Backend retains each currentROBvalid, exactslot range, tag[0], all8GEN comparison. New third lookup receives held candidate beforeH; original H chooses its boolean. H0 selects head/normal identical to old. Actual producer event, reset/flush/recovery/cancel, CDBready/backpressure, original public payload and query, held capture/fullLSQidentity, storeACK/retire/allocation/state remain unchanged. Private outputs can differ when their branch is not chosen; those values never authorize events.',
            'Source suffix from original g_report_rob_query through all LSQ clocked state/helper modules is byte-identical. Original report_first/held_matches/held_live, eligibility/priority, saved_identity_tree/public packet assembly and head flag unchanged. Added normal tree uses at most16-bit grant leaves and pure kept OR helper; optional flag0 makes all additions dead and retains original two-candidate qualifier.',
            'Defaultcore/backend/LSQ flag0, course flag1; any HEAD_LOAD_IDENTITY_ACTIVE unsupported profile keeps original fallback. Widths derive from existing ROB/LSQ dimensions, bankhigh0 handles1bit geometry and non-power-of-two/padding uses original row tree/reader. No FF/SRAM/ISA/GEN/portcapacity/pipelineedge changes. FullM/GEN/recovery/MMIO/parameter coverage still required before adoption.',
            'No HDL/lint/formal/simulation/synthesis/STA/unit test or new CPU build. Candidate41source hash frozen independently of runningA99 source157/manager/old evidence. Three metrics unknown. Additional narrowtree/fullGENlookup combination area may exceed201um2 margin or earlier normalpriority/other paths may dominate. Use original A99 result to decide whether this next source is needed and has supported net gain; pre-report any later coherent measurement.'
        ],goal_complete=False,adopted=False)
    write(REVIEW,proof)
    print({k:proof[k] for k in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
