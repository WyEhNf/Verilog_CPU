"""Make the existing LSQ load-selection slot fall through when empty."""
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A45_hybrid_direction_predictor'
TARGET=BASE/'A46_lsq_empty_selection_bypass'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/backend/rv32_lsq.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 0,',
        '    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 0,\n    parameter integer EMPTY_SELECTION_BYPASS = 0,')
    payload_width='    localparam integer SELECTION_PAYLOAD_WIDTH=SLOT_WIDTH+TAG_WIDTH+ROB_TAG_WIDTH+72;\n'
    text=once(text,payload_width,'')
    text=once(text,'    wire selection_discard=selection_valid && !selection_live;', '''    wire selection_discard=selection_valid && !selection_live;
    localparam integer SELECTION_PAYLOAD_WIDTH=SLOT_WIDTH+TAG_WIDTH+ROB_TAG_WIDTH+72;
    localparam integer VISIBLE_SELECTION_WORDS=(SELECTION_PAYLOAD_WIDTH+15)/16;
    wire [SELECTION_PAYLOAD_WIDTH-1:0] visible_selection_packet;
    wire [SELECTION_PAYLOAD_WIDTH-1:0] held_selection_packet={
        selection_slot,selection_lsq_tag,selection_rob_tag,selection_addr,
        selection_load,selection_size,selection_unsigned,selection_store_mask,selection_store_data};
    wire [GENERATION_WIDTH-1:0] direct_row_generation;
    wire direct_row_valid,direct_row_sent,direct_row_complete,direct_row_wait,
        direct_row_store,direct_row_commit,direct_row_load,direct_row_retired;
    rv32_frequency_array_read #(.WIDTH(SELECT_STATE_WIDTH),.ENTRIES(LSQ_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) direct_selection_state_read (
        .rows_i(selection_state_rows),.index_i(pick_slot[1]),
        .value_o({direct_row_generation,direct_row_valid,direct_row_sent,direct_row_complete,direct_row_wait,
                  direct_row_store,direct_row_commit,direct_row_load,direct_row_retired}));
    // Offer only a live, already allocated LOAD from the original oldest
    // eligible tournament. Unknown-store and byte-overlap guards are unchanged.
    // A held ticket retains priority; stores and newly allocated rows still
    // cross their original selection edge. This decision never uses ready.
    wire selection_direct_bypass=(EMPTY_SELECTION_BYPASS!=0) && (REQUEST_PIPELINE!=0) &&
        !reset_i && !flush_i && !recovery_valid_i && !selection_valid && pick_valid[1] && pick_load &&
        direct_row_valid && direct_row_load && !direct_row_store &&
        !direct_row_sent && !direct_row_complete && !direct_row_wait &&
        pick_generation==direct_row_generation;
    generate if(REQUEST_PIPELINE!=0) begin:g_visible_selection
        wire [VISIBLE_SELECTION_WORDS-1:0] direct_views;
        rv32_frequency_control_tree #(.LEAVES(VISIBLE_SELECTION_WORDS)) direct_tree (
            .signal_i(selection_direct_bypass),.views_o(direct_views));
        for(genvar selection_word=0;selection_word<VISIBLE_SELECTION_WORDS;selection_word=selection_word+1) begin:g_word
            localparam integer LOW=selection_word*16;
            localparam integer BITS=(SELECTION_PAYLOAD_WIDTH-LOW>=16)?16:SELECTION_PAYLOAD_WIDTH-LOW;
            assign visible_selection_packet[LOW +: BITS]=direct_views[selection_word]?
                normal_selection_packet[LOW +: BITS]:held_selection_packet[LOW +: BITS];
        end
    end else begin:g_unregistered_selection
        assign visible_selection_packet=normal_selection_packet;
    end endgenerate''')
    text=once(text,'''    wire [SLOT_WIDTH-1:0] selected_slot=(REQUEST_PIPELINE!=0)?selection_slot:pick_slot[1];
    wire [31:0] selected_addr=(REQUEST_PIPELINE!=0)?selection_addr:pick_addr[1];''', '''    wire [SLOT_WIDTH-1:0] selected_slot;
    wire [31:0] selected_addr;
    wire [1:0] selected_size;
    wire selected_unsigned,selected_load;
    wire [3:0] selected_store_mask;
    wire [31:0] selected_store_data;
    wire [ROB_TAG_WIDTH-1:0] selected_rob_tag;
    wire [TAG_WIDTH-1:0] selected_lsq_tag;
    assign {selected_slot,selected_lsq_tag,selected_rob_tag,selected_addr,
            selected_load,selected_size,selected_unsigned,selected_store_mask,selected_store_data}=visible_selection_packet;''')
    text=once(text,'    wire [1:0] selected_size=(REQUEST_PIPELINE!=0)?selection_size:pick_size;\n','')
    text=once(text,'''    wire selected_unsigned=(REQUEST_PIPELINE!=0)?selection_unsigned:pick_unsigned;
    wire selected_load=(REQUEST_PIPELINE!=0)?selection_load:pick_load;
    wire [3:0] selected_store_mask=(REQUEST_PIPELINE!=0)?selection_store_mask:pick_store_mask;
    wire [31:0] selected_store_data=(REQUEST_PIPELINE!=0)?selection_store_data:pick_store_data;
    wire [ROB_TAG_WIDTH-1:0] selected_rob_tag=(REQUEST_PIPELINE!=0)?selection_rob_tag:pick_rob_tag;
    wire [TAG_WIDTH-1:0] selected_lsq_tag=(REQUEST_PIPELINE!=0)?selection_lsq_tag:
        make_lsq_tag(pick_slot[1],pick_generation);
    wire selection_done=selection_live && (request_fire ||
        (selection_load && candidate_found && ((fwd_mask & target_mask)==target_mask)));''', '''    wire selection_done=(selection_live || selection_direct_bypass) && (request_fire ||
        (selected_load && candidate_found && ((fwd_mask & target_mask)==target_mask)));
    wire direct_selection_done=selection_direct_bypass && selection_done;''')
    text=once(text,'        (pick_valid[1] || allocation_load_found);',
        '        (pick_valid[1] || allocation_load_found) && !direct_selection_done;')
    text=once(text,'''            if(selection_input_fire || selection_done || selection_discard) forwarding_hold_valid<=0;
            else if(forwarding_hold_write) forwarding_hold_valid<=1;''', '''            // A first bypass offer that stalls captures the ticket AND its
            // exact forwarded bytes on this edge. They then own the held offer.
            // Consumed/discarded tickets still clear any obsolete byte snapshot.
            if(selection_done || selection_discard) forwarding_hold_valid<=0;
            else if(forwarding_hold_write) forwarding_hold_valid<=1;
            else if(selection_input_fire) forwarding_hold_valid<=0;''')
    text=once(text,'        candidate_found = (REQUEST_PIPELINE!=0)?selection_live:pick_valid[1];',
        '        candidate_found = (REQUEST_PIPELINE!=0)?(selection_live || selection_direct_bypass):pick_valid[1];')
    # The only new state behavior is bypass completion not being recaptured,
    # and simultaneous first blocked offer + ticket/forward-snapshot capture.
    # All allocation, age/hazard/byte-forwarding and lifecycle writer bodies
    # remain source-exact and consume the same full packet identity.
    marker='    // Admission is resolved beside bounded output groups.'
    assert text[text.index(marker):]==original[original.index(marker):]
    begin='    genvar age_slot;'; end='    always @* begin\n        free_count_calc'
    if end in original:
        assert text[text.index(begin):text.index(end)]==original[original.index(begin):original.index(end)]
    assert len(re.findall(r'^\s*reg\s+',text,re.M))==len(re.findall(r'^\s*reg\s+',original,re.M))
    assert text.count('    localparam integer SELECTION_PAYLOAD_WIDTH=')==1
    changes[name]=text

    name='rtl/backend/rv32_backend_joint.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer LSQ_RECLAIM_WIDTH = 1,',
        '    parameter integer LSQ_RECLAIM_WIDTH = 1,\n    parameter integer LSQ_EMPTY_SELECTION_BYPASS = 0,')
    text=once(text,'.RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH),',
        '.RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH), .EMPTY_SELECTION_BYPASS(LSQ_EMPTY_SELECTION_BYPASS),')
    changes[name]=text
    name='rtl/cpu_core.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer LSQ_RECLAIM_WIDTH = 1,',
        '    parameter integer LSQ_RECLAIM_WIDTH = 1,\n    parameter integer LSQ_EMPTY_SELECTION_BYPASS = 0,')
    text=once(text,'.LSQ_RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH),',
        '.LSQ_RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH), .LSQ_EMPTY_SELECTION_BYPASS(LSQ_EMPTY_SELECTION_BYPASS),')
    changes[name]=text
    name='rtl/course/student_top.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer LSQ_RECLAIM_WIDTH = 2,',
        '    parameter integer LSQ_RECLAIM_WIDTH = 2,\n    parameter integer LSQ_EMPTY_SELECTION_BYPASS = 1,')
    text=once(text,'.LSQ_RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH),',
        '.LSQ_RECLAIM_WIDTH(LSQ_RECLAIM_WIDTH), .LSQ_EMPTY_SELECTION_BYPASS(LSQ_EMPTY_SELECTION_BYPASS),')
    changes[name]=text
    for name in parent['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['parameter_overrides']=dict(parent['parameter_overrides'],LSQ_EMPTY_SELECTION_BYPASS=1)
    record['enabled_profile']=dict(parent['enabled_profile'],lsq_empty_selection_bypass=True,
        lsq_empty_selection_bypass_added_ff_bits=0,lsq_empty_selection_bypass_added_sram_bits=0,
        lsq_empty_selection_bypass_new_pipeline_edges=0,
        lsq_empty_selection_bypass_removed_required_wait_edges=1)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'An empty LSQ selection slot offers the original oldest eligible already-allocated live load to Dcache immediately, or completes original full-store forwarding at that edge. Carry its full slot/generation/ROB identity, address/size and original youngest-byte forwarding. If not accepted, existing selection and forwarding owners capture the exact offer together. Do not recapture a consumed bypass. Stores/new allocations and held selection priority stay on original paths.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],lsq_empty_selection_bypass={
        'parent_requires_empty_selection_capture_before_cache_offer':True,
        'new_bypass_removes_one_selection_wait_edge_for_eligible_loads':True,
        'includes_existing_full_tag_agu_address_lookthrough':True,
        'oldest_eligible_hazards_and_byte_forwarding_source_unchanged':True,
        'existing_blocked_offer_payload_and_forward_owners_reused':True,
        'added_ff_bits':0,'added_sram_bits':0,
        'eligible_hit_count_and_whole_program_gain_unknown':True,
        'new_agu_pick_forward_to_cache_path_requires_future_frequency_measurement':True})
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_LSQ_EMPTY_SELECTION_BYPASS_UNTESTED',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),tests_started=False,adopted=False,
        added_ff_bits=0,added_sram_bits=0,added_pipeline_edges=0,removed_required_wait_edges=1,
        source_arguments=[
            'Direct offer only when the selection register is empty. Original oldest-eligible tournament must select a load, and a direct state read checks live/valid/load/not-store/not-sent/not-complete/not-wait and full generation. No newly allocated row bypasses ownership; no store takes this shortcut; held ticket priority is unchanged.',
            'The direct packet includes original winner slot, full LSQ generation tag, ROB tag, address, load/size/unsigned and store fields. Bounded16-bit word selects distribute the same direct-vs-held choice. Original age, unknown-address store exclusion, overlapping unknown store-data guards and youngest-per-byte forwarding source stay unchanged.',
            'A successful direct cache handshake, or original full-byte forwarding, completes the selection without recapturing it. Original lifecycle source marks sent/wait or full-forward complete under the same row identity and event. Generation state and normal load/ROB completion authority do not change.',
            'If the initial direct request stalls, the existing selection owner and36-bit forwarding owner capture that exact offer together. Forward-valid priority now lets this first write win over simultaneous ticket capture, while done/discard clears obsolete snapshots. No data/mask changes under continued backpressure; later acceptance releases both owners.',
            'For parameter0, direct offer is constant0 and visible packet is the original saved/pick packet. Changed forward-valid priority is equivalent on old reachable events: forwarding write cannot coexist with selection done/discard and can coexist with selection input only for the new empty direct offer. REQUEST_PIPELINE0 preserves original unregistered packet; flush/recovery suppress the new path.',
            'Existing full-tag AGU lookthrough may feed this direct load. This removes a real wait edge, but introduces AGU/hazard/oldest-pick/forwarding to SRAM-address timing that was formerly separated by the selection register. A44 removes a different measured front PC bottleneck; it does not prove this new path meets300MHz.',
            'No additional state, SRAM or physical request/response port. Extra mux, state reader and control logic can increase area; actual whole-program IPC, area and Fmax are unknown. Structural one-edge removal is not a measured benchmark gain.',
            'No HDL/lint/simulation/synthesis/STA/unit tests. Later coverage must include empty bypass hit/miss, current AGU update, full/partial youngest-byte forwarding, unknown stores, first/sustained backpressure and changing older stores, direct consume without duplicate capture, occupied/full replacement, generation reuse/late response, allocation/reclaim collision, recovery and fallback parameters.'
        ])
    write(BASE/'A46_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','changed_files','removed_required_wait_edges','tests_started')})


if __name__=='__main__':
    main()
