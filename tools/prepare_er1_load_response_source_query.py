"""Compare saved/bypass LSQ tickets before late cache response selection."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A91_head_load_packet_preselect'
TARGET = BASE/'A92_load_response_source_query'
REVIEW = BASE/'A92_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == 'a8e25ceb8c851e50f5f176c5a9e2513794ed9d871f1ed792dacc573c3a44ee43'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    name = 'rtl/cache/rv32_dcache_nonblocking.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    marker = next(line for line in original.splitlines() if 'dcache_resp_lsq_tag_o,' in line and 'output' in line)
    text = once(original, marker, marker+'''
    output wire [1:0]              dcache_resp_query_valid_o,
    output wire [2*TAG_WIDTH-1:0]   dcache_resp_query_tags_o,''')
    marker = '    assign dcache_resp_valid_o = resp_valid_reg || bypass_load_hit;'
    text = once(text, marker, marker+'''
    // Same actual public source priority. Candidate identities are available
    // independently before the late bypass decision routes a public ticket.
    assign dcache_resp_query_valid_o={bypass_load_hit,resp_valid_reg && !bypass_load_hit};
    assign dcache_resp_query_tags_o={core_req_lsq_tag,resp_lsq_reg};''')
    # Original response payload, source priority and every state update stay.
    marker = '    localparam integer RESPONSE_TAG_WORDS='
    assert text[text.index(marker):] == original[original.index(marker):]
    changes[name] = text
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    marker = '    parameter integer RESPONSE_QUERY_PREDECODE = 0,'
    text = once(original, marker, marker+'\n    parameter integer RESPONSE_SOURCE_QUERY = 0,')
    marker = next(line for line in text.splitlines() if 'dcache_resp_lsq_tag_i,' in line and 'input' in line)
    text = once(text, marker, marker+'''
    input  wire [1:0]                   dcache_resp_query_valid_i,
    input  wire [2*TAG_WIDTH-1:0]        dcache_resp_query_tags_i,''')
    start = '    rv32_frequency_control_tree #(.WIDTH(RESPONSE_MATCH_WIDTH),.LEAVES(RESPONSE_MATCH_DOMAINS)) response_match_tree ('
    end = '    reg complete_slot_found;'
    old = text[text.index(start):text.index(end)]
    text = once(text, old, '''    generate if(RESPONSE_SOURCE_QUERY!=0) begin:g_response_source_query
        wire [RESPONSE_MATCH_DOMAINS*2-1:0] validity_views;
        wire [RESPONSE_MATCH_DOMAINS*2*TAG_WIDTH-1:0] tag_views;
        rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(RESPONSE_MATCH_DOMAINS)) validity_tree (
            .signal_i(dcache_resp_query_valid_i),.views_o(validity_views));
        rv32_frequency_control_tree #(.WIDTH(2*TAG_WIDTH),.LEAVES(RESPONSE_MATCH_DOMAINS)) identity_tree (
            .signal_i(dcache_resp_query_tags_i),.views_o(tag_views));
        for(genvar match_row=0;match_row<LSQ_ENTRIES;match_row=match_row+1) begin:g_row
            wire [TAG_WIDTH-1:0] saved_tag=tag_views[(match_row/4)*2*TAG_WIDTH +: TAG_WIDTH];
            wire [TAG_WIDTH-1:0] bypass_tag=tag_views[(match_row/4)*2*TAG_WIDTH+TAG_WIDTH +: TAG_WIDTH];
            wire saved_match=tag_matches_slot(saved_tag,match_row) && response_wait_mem[match_row];
            wire bypass_match=tag_matches_slot(bypass_tag,match_row) && response_wait_mem[match_row];
            assign response_match_rows[match_row]=
                (saved_match && validity_views[(match_row/4)*2]) ||
                (bypass_match && validity_views[(match_row/4)*2+1]);
        end
    end else begin:g_original_response_match
'''+old.replace('    generate for(', '    for(').replace('    end endgenerate', '    end')+'''    end endgenerate
''')
    marker = '    reg complete_slot_found;'
    # All users of the original qualified match rows and every later state
    # command/response formatter remain byte-identical.
    assert text[text.index(marker):] == original[original.index(marker):]
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer LSQ_ALLOC_SLOT_PRESELECT = '+str(default)+','
        text = once(original, marker, marker+'\n    parameter integer LSQ_RESPONSE_SOURCE_QUERY = '+str(default)+',')
        if '/backend/' in name:
            marker = next(line for line in text.splitlines() if 'dcache_resp_lsq_tag_i,' in line and 'input' in line)
            text = once(text, marker, marker+'''
    input  wire [1:0]                   dcache_resp_query_valid_i,
    input  wire [2*TAG_WIDTH-1:0]        dcache_resp_query_tags_i,''')
            text = once(text, '.RESPONSE_QUERY_PREDECODE(LSQ_RESPONSE_QUERY_PREDECODE)',
                '.RESPONSE_QUERY_PREDECODE(LSQ_RESPONSE_QUERY_PREDECODE), .RESPONSE_SOURCE_QUERY(LSQ_RESPONSE_SOURCE_QUERY)')
            text = once(text, '.dcache_resp_lsq_tag_i(dcache_resp_lsq_tag_i),',
                '.dcache_resp_lsq_tag_i(dcache_resp_lsq_tag_i), .dcache_resp_query_valid_i(dcache_resp_query_valid_i), .dcache_resp_query_tags_i(dcache_resp_query_tags_i),')
        else:
            text = once(text, '.LSQ_ALLOC_SLOT_PRESELECT(LSQ_ALLOC_SLOT_PRESELECT)',
                '.LSQ_ALLOC_SLOT_PRESELECT(LSQ_ALLOC_SLOT_PRESELECT), .LSQ_RESPONSE_SOURCE_QUERY(LSQ_RESPONSE_SOURCE_QUERY)')
            if name == 'rtl/cpu_core.v':
                marker = '    wire [ROB_TAG_WIDTH-1:0] dcache_resp_lsq_tag;'
                text = once(text, marker, marker+'''
    wire [1:0] dcache_resp_query_valid;
    wire [2*ROB_TAG_WIDTH-1:0] dcache_resp_query_tags;''')
                # Connect only the nonblocking cache call. Blocking/uncached
                # branches expose the actual original single public packet.
                start = '    if (DCACHE_MSHRS > 1) begin : g_nonblocking_dcache'
                end = '    end else begin : g_blocking_dcache'
                old = text[text.index(start):text.index(end)]
                new = once(old, '.dcache_resp_lsq_tag_o(dcache_resp_lsq_tag),',
                    '.dcache_resp_lsq_tag_o(dcache_resp_lsq_tag), .dcache_resp_query_valid_o(dcache_resp_query_valid), .dcache_resp_query_tags_o(dcache_resp_query_tags),')
                text = once(text, old, new)
                fallback = '''
    assign dcache_resp_query_valid={1'b0,dcache_resp_valid};
    assign dcache_resp_query_tags={{ROB_TAG_WIDTH{1'b0}},dcache_resp_lsq_tag};'''
                text = once(text, end, end+fallback)
                marker = '    end else begin : g_uncached_memory'
                text = once(text, marker, marker+fallback)
                start = '    rv32_backend_joint #('
                prefix,tail = text.split(start)
                tail = once(tail, '.dcache_resp_lsq_tag_i(dcache_resp_lsq_tag),',
                    '.dcache_resp_lsq_tag_i(dcache_resp_lsq_tag), .dcache_resp_query_valid_i(dcache_resp_query_valid), .dcache_resp_query_tags_i(dcache_resp_query_tags),')
                text = prefix+start+tail
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_LOAD_RESPONSE_SOURCE_QUERY_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],LSQ_RESPONSE_SOURCE_QUERY=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],LSQ_RESPONSE_SOURCE_QUERY=1,
        load_response_source_query_new_ff_bits=0,load_response_source_query_new_sram_bits=0,load_response_source_query_new_pipeline_edges=0,
        load_response_source_identity_candidates=2)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Expose actual saved-cache and hit-bypass response events with their full preselected candidate LSQ tickets. Qualify both tickets independently against original valid/current row/full GEN/response_wait before late response source gating. Preserve original public response priority/payload/capture and all consumers of actual matched rows; blocking/uncached supply exact original public packet as single candidate.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        late_cache_response_public_ticket_mux_removed_before_full_lsq_match=True,
        load_response_source_query_limit='Targets A83 mem response ID -> bypass_load_hit0.6518ns -> public response LSQ ticket0.7946ns -> full LSQ match. Two candidate full identities qualify before late source choice, which then gates only matches. Adds duplicate per-row tag comparators/query routing; output value/error/address formatting and original bypass validity remain. No FF/SRAM/edge or new IPC publication; timing/area unmeasured.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,identity_candidates=2,
        source_arguments=[
            'Original nonblocking cache public valid=resp_valid_reg OR bypass_load_hit and public ticket=bypass_load_hit?core_req_lsq_tag:resp_lsq_reg. New source1 valid=bypass_load_hit and full tag=core_req_lsq_tag; source0 valid=resp_valid_reg&&!bypass_load_hit and full tag=resp_lsq_reg. These events are mutually exclusive and their valid OR/public ticket exactly match the original on every actual response, including simultaneous saved/bypass priority. No assumption that hit/bypass or public cache output is fully registered is made.',
            'Each LSQ row independently applies exact existing tag_matches_slot to both full candidates and original response_wait_mem before actual candidate-valid gating. Thus response_match_rows equals old public-valid && tag_matches_slot(public selected ticket,row) && response_wait for coherent core candidates. All current valid/tag0/row/allLSQGEN checks remain, including stale/recycled/wrong-path response rejection; no shortened generation or saved live speculation is introduced.',
            'Original public cache valid/tag/address/line/word/error routing, handshake/backpressure/refill/capture and all subsequent state are byte-identical. Original LSQ response formatter/query, scalar response slot priority, head-only report, early wake, capture/error/reclaim and recovery commands consume the same matched events and are byte-identical. Only identity/control factorization changes; no additional same-cycle response event or new result storage.',
            'Native core nonblocking branch forwards private actual source events/tags. Blocking and uncached branches provide source0=original public valid/tag, source1=0, preserving exact single-packet behavior. Serial backend keeps old public inputs and ignores optional private queries. Default0 standalone backend/LSQ ignore extra inputs and retain original match expression; enabled optional contradictory query/public input combinations are outside the documented coherent packet contract.',
            'No FF/SRAM/pipeline edge or cache/LSQ transaction capacity added. Duplicate full per-row comparators and identity/validity fanout may increase combinational area and generation-Q loading; late original bypass/read control and formatting still remain. Numerical benefit and total area within existing352.966um2 margin are unproven; inherited A84-A91 options still need coherent measurement.',
            'Manual source/priority/full-ticket ownership/hash review only; no HDL/lint/formal/simulation/synthesis/STA/unit tests. Future coherent coverage includes no/saved/bypass/both response sources, actual request/coissue acceptance and backpressure, duplicate/stale/recycled ticket generations, full/wrapped LSQ, reset/flush/recovery, forwarding/sign/size/error, blocking/uncached/serial/default profiles, full RV32IM/parameterization/MMIO and course performance. Goal remains unproven.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
