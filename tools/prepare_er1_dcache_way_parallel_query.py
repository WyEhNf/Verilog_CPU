"""Prepare per-way data provenance so store writes need not block an unused read way."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A41_lsq_two_prefix_reclaim'
TARGET = BASE / 'A42_dcache_way_parallel_query'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/cache/rv32_dcache_nonblocking.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer LOCAL_SRAM_COMMANDS = 0,',
        '    parameter integer LOCAL_SRAM_COMMANDS = 0,\n    parameter integer WAY_PARALLEL_QUERY = 0,')
    text = once(text, '        reg query_data_valid, query_data_from_sram;',
        '        reg [CACHE_WAYS-1:0] query_data_valid, query_data_from_sram;\n        wire [CACHE_WAYS-1:0] input_way_reads;')
    text = once(text, '''        wire input_data_read = input_fire && !data_we;
        wire deferred_data_read = query_valid && !query_data_valid &&
            request_dirty_victim && !data_we && !tag_array_write;''',
        '''        // Data writes own one physical way. The remaining ways can read
        // the incoming tag query on that edge; never treat the written way's
        // undefined SRAM Q as a read result or as valid held data.
        wire input_data_read = input_fire && ((WAY_PARALLEL_QUERY!=0) || !data_we);
        wire deferred_data_read = query_valid && !request_data_ready &&
            (request_dirty_victim ||
             ((WAY_PARALLEL_QUERY!=0) && query_load && request_hit)) &&
            !data_we && !tag_array_write;
        for(genvar read_way=0;read_way<CACHE_WAYS;read_way=read_way+1) begin:g_input_way_read
            assign input_way_reads[read_way]=input_data_read &&
                !(data_we && ((data_addr%CACHE_WAYS)==read_way));
        end''')
    text = once(text, '                                   (!data_we || dcache_req_is_store_i) &&',
        '                                   ((WAY_PARALLEL_QUERY!=0) || !data_we || dcache_req_is_store_i) &&')
    text = once(text, '''        wire [2*LOOKUP_WORDS-1:0] lookup_read_views;
        rv32_frequency_control_tree #(.WIDTH(2),.LEAVES(LOOKUP_WORDS)) lookup_read_tree (''',
        '''        localparam integer LOOKUP_SELECT_WIDTH=CACHE_WAYS+1;
        wire [LOOKUP_SELECT_WIDTH*LOOKUP_WORDS-1:0] lookup_read_views;
        rv32_frequency_control_tree #(.WIDTH(LOOKUP_SELECT_WIDTH),.LEAVES(LOOKUP_WORDS)) lookup_read_tree (''')
    text = once(text, 'lookup_read_views[2*lookup_word]?',
        'lookup_read_views[LOOKUP_SELECT_WIDTH*lookup_word]?')
    text = once(text, 'lookup_read_views[2*(LOOKUP_TAG_WORDS+lookup_word)]?',
        'lookup_read_views[LOOKUP_SELECT_WIDTH*(LOOKUP_TAG_WORDS+lookup_word)]?')
    text = once(text, 'lookup_read_views[2*(2*LOOKUP_TAG_WORDS+lookup_word)+1]?',
        'lookup_read_views[LOOKUP_SELECT_WIDTH*(2*LOOKUP_TAG_WORDS+lookup_word)+1+(lookup_word/8)]?')
    text = once(text, '''        wire [3*CACHE_WAYS-1:0] hold_event_views;
        rv32_frequency_control_tree #(.WIDTH(3),.LEAVES(CACHE_WAYS)) hold_event_tree (''',
        '''        localparam integer HOLD_SELECT_WIDTH=CACHE_WAYS+2;
        wire [HOLD_SELECT_WIDTH*CACHE_WAYS-1:0] hold_event_views;
        rv32_frequency_control_tree #(.WIDTH(HOLD_SELECT_WIDTH),.LEAVES(CACHE_WAYS)) hold_event_tree (''')
    text = once(text, '            assign {local_reset,data_copy,tag_copy}=hold_event_views[hold_way*3 +: 3];',
        '''            assign local_reset=hold_event_views[hold_way*HOLD_SELECT_WIDTH+CACHE_WAYS+1];
            assign data_copy=hold_event_views[hold_way*HOLD_SELECT_WIDTH+1+hold_way];
            assign tag_copy=hold_event_views[hold_way*HOLD_SELECT_WIDTH];''')
    text = once(text, '        assign request_data_ready = query_data_valid;',
        '''        // Only the selected hit/victim way supplies load/victim data.
        assign request_data_ready = query_data_valid[request_data_entry%CACHE_WAYS];''')
    text = once(text, "                query_data_valid <= 1'b0;", '                query_data_valid <= 0;')
    text = once(text, "                query_data_from_sram <= 1'b0;", '                query_data_from_sram <= 0;')
    text = once(text, '                query_data_from_sram <= input_data_read || deferred_data_read;',
        '                query_data_from_sram <= input_way_reads | {CACHE_WAYS{deferred_data_read}};')
    text = once(text, "                if (deferred_data_read) query_data_valid <= 1'b1;",
        "                if (deferred_data_read) query_data_valid <= {CACHE_WAYS{1'b1}};")
    text = once(text, '                    query_data_valid <= !data_we;',
        '                    query_data_valid <= input_way_reads;')
    text = once(text, '(!request_dirty_victim || request_data_ready) &&',
        '''(!(request_dirty_victim ||
                                    ((WAY_PARALLEL_QUERY!=0) && (TAG_SRAM!=0) &&
                                     request_is_load && request_hit)) || request_data_ready) &&''')
    text = once(text, '        request_is_load && request_hit && !resp_valid_reg &&',
        '        request_is_load && request_hit && request_data_ready && !resp_valid_reg &&')
    # All global writes, physical macros, miss/merge rules and held data
    # payloads retain their original source. Only read provenance/admission
    # and the required visibility guard change.
    assert text[text.index('    // Encode precisely the existing request priority'):] == \
        original[original.index('    // Encode precisely the existing request priority'):]
    assert text.count('query_data_valid <=') == original.count('query_data_valid <=')
    changes[name] = text

    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer DCACHE_LOCAL_SRAM_COMMANDS = 0,',
        '    parameter integer DCACHE_LOCAL_SRAM_COMMANDS = 0,\n    parameter integer DCACHE_WAY_PARALLEL_QUERY = 0,')
    text = once(text, '.HIT_BYPASS(1), .LOCAL_SRAM_COMMANDS(DCACHE_LOCAL_SRAM_COMMANDS),',
        '.HIT_BYPASS(1), .LOCAL_SRAM_COMMANDS(DCACHE_LOCAL_SRAM_COMMANDS), .WAY_PARALLEL_QUERY(DCACHE_WAY_PARALLEL_QUERY),')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer DCACHE_LOCAL_SRAM_COMMANDS = 1,',
        '    parameter integer DCACHE_LOCAL_SRAM_COMMANDS = 1,\n    parameter integer DCACHE_WAY_PARALLEL_QUERY = 1,')
    text = once(text, '.DCACHE_LOCAL_SRAM_COMMANDS(DCACHE_LOCAL_SRAM_COMMANDS),',
        '.DCACHE_LOCAL_SRAM_COMMANDS(DCACHE_LOCAL_SRAM_COMMANDS), .DCACHE_WAY_PARALLEL_QUERY(DCACHE_WAY_PARALLEL_QUERY),')
    changes[name] = text
    for name in parent['source_sha256']:
        target = TARGET / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, target)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT / 'candidate.json'),
        changed_from_parent_files=list(changes),
        source_sha256={name: sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), tests_started=False, adopted=False)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], DCACHE_WAY_PARALLEL_QUERY=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], dcache_way_parallel_query=True,
        dcache_per_way_data_provenance=True, dcache_way_parallel_added_ff_bits=2,
        dcache_way_parallel_added_sram_bits=0, dcache_way_parallel_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Permit incoming load tag query during a store hit data write. Physically unwritten ways read concurrently; per-way valid/provenance bits control SRAM-vs-held selection and copying. Missing selected-way data forces an ordinary deferred read and gates both request acceptance and immediate hit response, without changing write/merge/refill/forwarding ownership.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        original_input_load_blocked_by_any_data_write=True,
        physical_data_way_write_priority_already_present=True,
        way_parallel_new_ff_bits=2, way_parallel_sram_capacity_and_macro_count_unchanged=True,
        way_parallel_benefit_opportunities='following load hits unwritten way or misses without dirty victim; written-way data defers rather than publishing X',
        way_parallel_ipc_frequency_and_mapped_area_unmeasured=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_DCACHE_WAY_PARALLEL_QUERY_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        added_ff_bits=2, added_sram_bits=0, added_pipeline_edges=0,
        tests_started=False, adopted=False,
        source_arguments=[
            'Parent blocks any incoming load if data_we, although only one physical way writes and other ways have independent1RW macros. Current per-way command modules already give writes priority and read unused ways when input_read is asserted.',
            'Accept a tag query while a preceding store hit writes one way; input_way_reads marks only macros that actually read. That way alone chooses new SRAM Q and copies it to its existing held owner. Written/idle macros never masquerade as valid read data.',
            'Both tag and data payload identities keep the original input_fire edge. Tag writes continue blocking new queries, so no refill tag read/write conflict is opened. Full-generation LSQ/ROB identities are unchanged.',
            'A selected hit/victim way must have data before load hit acceptance or dirty eviction. If missing, deferred_data_read reads all ways at the saved request index on a port-free edge. Crucially bypass_load_hit also requires selected-way data; otherwise a new early tag hit would publish undefined data before formal request acceptance.',
            'A following load hitting the unwritten way, or missing without a dirty victim, can progress one edge earlier. A hit/dirty victim in the written way defers; its service edge is no later than the old blocked-input-then-read sequence absent new contention. Actual frequency of these transitions and whole-program speedup is unknown.',
            'request_data_entry selects exactly the original hit or victim way. Global writes, SRAM masks/addresses and write priority, hold bank forwarding, hit response capture, MSHR/waiter/refill/local-fill state, store acknowledgement and byte merge source after static-request-action are byte-exact parent text.',
            'At CACHE_WAYS2 data-valid and SRAM-origin each widen from1 to2 bits: two added state bits, no added payload or memory macros/ports/capacity. Extra metadata selection/control buffering must be measured; no mapped area claim.',
            'WAY_PARALLEL_QUERY0 retains original incoming-load block and simultaneous-all-way provenance; TAG_SRAM0 retains its original branch. One-way mode simply defers write-conflicted hit data, never assumes another bank exists.',
            'No HDL/lint/simulation/synthesis/STA/unit tests. Later coverage must include store→load in either way, same/different set, partial store masks, selected written/unwritten dirty victim, input and deferred collisions, held data copying with invalid macro Q, refill/local fill/tag writes, output backpressure, errors, same-line LSQ forwarding, and parameter0/1way/TAG_SRAM0 fallback.'
        ])
    write(BASE / 'A42_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'added_ff_bits', 'tests_started')})


if __name__ == '__main__':
    main()
