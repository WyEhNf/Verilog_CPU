"""Prepare hit bypass plus one held load response without adding a reply port."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A42_dcache_way_parallel_query'
TARGET = BASE / 'A43_dcache_hit_response_coissue'


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
    text = once(original, '    parameter integer WAY_PARALLEL_QUERY = 0,',
        '    parameter integer WAY_PARALLEL_QUERY = 0,\n    parameter integer HIT_RESPONSE_COISSUE = 0,')
    text = once(text, '    wire load_can_accept = (request_hit ?', '''    // A query hit can leave through the existing combinational bypass while
    // a waiter/refill takes the existing held reply slot at the same edge.
    // The offer never depends on ready. A blocked hit is captured once and
    // the competing reply remains at its original owner until a later edge.
    // Exclude local-fill candidates before response-ready arbitration, so
    // neither this offer nor request acceptance depends on refill priority.
    wire hit_coissue_offer=(HIT_RESPONSE_COISSUE!=0) && (HIT_BYPASS!=0) &&
        (TAG_SRAM!=0) && !reset_i && core_req_valid && request_is_load &&
        request_hit && request_data_ready && !resp_valid_reg && !local_fill_found;
    wire hit_coissue_holds_slot=hit_coissue_offer && !dcache_resp_ready_i;
    wire load_can_accept = (request_hit ?''')
    text = once(text, '''                            (resp_slot_free && !waiter_load_ready_found &&
                             !response_emits_load) :''', '''                            (resp_slot_free && (hit_coissue_offer ||
                             (!waiter_load_ready_found && !response_emits_load))) :''')
    text = once(text, '''    wire bypass_load_hit = (HIT_BYPASS != 0) && (TAG_SRAM != 0) && !reset_i && core_req_valid &&
        request_is_load && request_hit && request_data_ready && !resp_valid_reg &&
        !waiter_load_ready_found && !response_emits_load;''', '''    wire bypass_load_hit = hit_coissue_offer ||
        ((HIT_BYPASS != 0) && (TAG_SRAM != 0) && !reset_i && core_req_valid &&
         request_is_load && request_hit && request_data_ready && !resp_valid_reg &&
         !waiter_load_ready_found && !response_emits_load);''')
    text = once(text, '    assign mem_resp_ready_o = response_found && !response_needs_output;', '''    assign mem_resp_ready_o = response_found && !response_needs_output &&
        !(hit_coissue_holds_slot && response_emits_load);
    // Demand refills and failed victim writebacks both own a load reply.
    // A waiter must retain its ready row whenever either producer captures.
    wire load_response_capture=mem_resp_valid_i && mem_resp_ready_o && response_emits_load;''')
    text = once(text, '    wire waiter_load_consume=resp_slot_free && waiter_load_ready_found && !demand_response_fire;', '''    wire waiter_load_consume=resp_slot_free && waiter_load_ready_found &&
        !((HIT_RESPONSE_COISSUE!=0)?load_response_capture:demand_response_fire) &&
        !hit_coissue_holds_slot;''')
    # Payload selectors and reply-valid priority are already hit < waiter <
    # writeback failure < demand response. Keep every owner and state edge.
    marker = '    localparam integer DCACHE_RESPONSE_META_WIDTH=TAG_WIDTH+34;'
    assert text[text.index(marker):] == original[original.index(marker):]
    marker = '    reg [3:0] static_request_action;'
    end = '    wire waiter_allocate_event=static_request_action==4\'d5;'
    assert text[text.index(marker):text.index(end)] == original[original.index(marker):original.index(end)]
    assert len(re.findall(r'^\s*reg\s+', text, re.M)) == len(re.findall(r'^\s*reg\s+', original, re.M))
    assert text.count('sram_fakeram #') == original.count('sram_fakeram #')
    changes[name] = text

    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer DCACHE_WAY_PARALLEL_QUERY = 0,',
        '    parameter integer DCACHE_WAY_PARALLEL_QUERY = 0,\n    parameter integer DCACHE_HIT_RESPONSE_COISSUE = 0,')
    text = once(text, '.WAY_PARALLEL_QUERY(DCACHE_WAY_PARALLEL_QUERY),',
        '.WAY_PARALLEL_QUERY(DCACHE_WAY_PARALLEL_QUERY), .HIT_RESPONSE_COISSUE(DCACHE_HIT_RESPONSE_COISSUE),')
    changes[name] = text
    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer DCACHE_WAY_PARALLEL_QUERY = 1,',
        '    parameter integer DCACHE_WAY_PARALLEL_QUERY = 1,\n    parameter integer DCACHE_HIT_RESPONSE_COISSUE = 1,')
    text = once(text, '.DCACHE_WAY_PARALLEL_QUERY(DCACHE_WAY_PARALLEL_QUERY),',
        '.DCACHE_WAY_PARALLEL_QUERY(DCACHE_WAY_PARALLEL_QUERY), .DCACHE_HIT_RESPONSE_COISSUE(DCACHE_HIT_RESPONSE_COISSUE),')
    changes[name] = text

    for name in parent['source_sha256']:
        dest = TARGET / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, dest)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(source_root=str(TARGET), created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT), parent_candidate_sha256=sha(PARENT / 'candidate.json'),
        changed_from_parent_files=list(changes),
        source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), tests_started=False, adopted=False)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], DCACHE_HIT_RESPONSE_COISSUE=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], dcache_hit_response_coissue=True,
        dcache_hit_response_coissue_added_ff_bits=0,
        dcache_hit_response_coissue_added_sram_bits=0,
        dcache_hit_response_coissue_added_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'A synchronous load hit may leave through the original ready-independent bypass while a waiter or memory load response captures into the existing held slot. If the hit stalls, competing load producers retain ownership. No second LSQ reply port or added payload state; failed victim writebacks participate in waiter capture priority.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        dcache_hit_response_coissue={
            'parent_serializes_immediate_hit_with_registered_load_producers':True,
            'new_success_edge':'one hit delivered, one waiter/refill retained for next edge',
            'course_lsq_ready':'rv32_lsq.v assigns dcache_resp_ready_o=1 unconditionally',
            'no_measured_collision_count_or_speedup':True,
            'added_ff_bits':0,'added_sram_bits':0,'added_pipeline_edges':0})
    write(TARGET/'candidate.json',record)
    proof = {
        'status':'SOURCE_DCACHE_HIT_RESPONSE_COISSUE_UNTESTED',
        'candidate':str(TARGET),'candidate_sha256':sha(TARGET/'candidate.json'),
        'changed_files':list(changes),'added_ff_bits':0,'added_sram_bits':0,
        'added_pipeline_edges':0,'tests_started':False,'adopted':False,
        'source_arguments':[
            'Original hit bypass and registered waiter/refill producers unnecessarily compete for a held slot even when the hit can be delivered immediately. Enabled mode offers a valid hit independently of consumer ready, and admits it through the existing hit transaction.',
            'When ready=1, the hit is consumed on this edge; existing higher-priority waiter/refill payload and valid writers retain the competing load exactly once in the original register for the following edge.',
            'When ready=0, a bypass hit reserves the held slot. A load-producing memory response is backpressured and a ready waiter does not consume; original hit payload capture and reply-valid retain the hit. Non-load memory responses may still progress.',
            'Excluding any local_fill_found candidate makes the new offer independent of memory-response arbitration and guarantees the local matching-fill guard cannot prevent this offered hit transaction from firing. Query tags/data already belong to the accepted saved request. TAG_SRAM0 and HIT_BYPASS0 disable the new mode.',
            'Mode1 waiter selection excludes every accepted load response, including a failed dirty-victim writeback. Original selection excluded only demand_response_fire and could consume a ready waiter whose payload was overwritten by the higher-priority failure response. Mode0 preserves the original predicate.',
            'All payload selectors, load/store/MSHR lifecycle writers, macro commands, byte merging, original scalar reply-valid ordering and generation tags remain exact parent source. No second external reply, no changed completion authority, no added state or pipeline edge.',
            'Course LSQ ready is constant1, so the new backpressure dependency folds away in this profile; general standalone backpressure is still explicitly supported. A collision-rate and IPC improvement cannot be inferred without later measurement.',
            'No HDL/lint/simulation/synthesis/STA/unit tests. Later coverage must include hit+waiter, hit+demand refill, hit+failed writeback, all three producers, ready0/1 transitions, refill errors/address mismatch, same-set replacement, held responses, local-fill exclusion and parameter fallbacks.'
        ]}
    write(BASE/'A43_source_review.json',proof)
    print(proof)


if __name__=='__main__':
    main()
