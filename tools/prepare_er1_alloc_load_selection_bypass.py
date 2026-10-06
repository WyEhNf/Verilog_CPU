"""Capture an allocated ready load into existing LSQ selection, no HDL runs."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A27_compact_indirect_btb'
TARGET=BASE/'A28_alloc_load_selection_bypass'


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
    text=once(original,'    parameter integer LOAD_WAKE_BYPASS = 0,',
        '    parameter integer LOAD_WAKE_BYPASS = 0,\n    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 0,')
    old='''    wire selection_input_fire=(REQUEST_PIPELINE!=0) && !reset_i && !flush_i && !recovery_valid_i &&
        (!selection_valid || selection_discard || selection_done) && pick_valid[1];
    // Same unreset selection fields, data and clock edge. Bound each final
    // qualified enable to at most 16 payload hold muxes, including the tags.
    localparam integer SELECTION_PAYLOAD_WIDTH=SLOT_WIDTH+TAG_WIDTH+ROB_TAG_WIDTH+72;
    rv32_frequency_word_bank #(.WIDTH(SELECTION_PAYLOAD_WIDTH)) selection_payload_owner (
        .clk_i(clk_i),.write_i(selection_input_fire),
        .data_i({pick_slot[1],make_lsq_tag(pick_slot[1],pick_generation),pick_rob_tag,
                 pick_addr[1],pick_load,pick_size,pick_unsigned,pick_store_mask,pick_store_data}),
        .data_o({selection_slot,selection_lsq_tag,selection_rob_tag,selection_addr,
                 selection_load,selection_size,selection_unsigned,selection_store_mask,selection_store_data}));'''
    new='''    // The existing candidate retains priority. A newly allocated ready
    // load may fill an otherwise unused selection on its allocation edge.
    // This conservative shortcut never passes an existing store or a store
    // in an earlier lane of the same allocated bundle.
    localparam integer SELECTION_PAYLOAD_WIDTH=SLOT_WIDTH+TAG_WIDTH+ROB_TAG_WIDTH+72;
    wire [LSQ_ENTRIES-1:0] allocation_older_stores;
    wire [BE_WIDTH-1:0] allocation_prior_store,allocation_load_match,allocation_load_grant;
    wire [BE_WIDTH*SELECTION_PAYLOAD_WIDTH-1:0] allocation_load_values;
    wire allocation_load_found;
    wire [SELECTION_PAYLOAD_WIDTH-1:0] allocation_load_packet;
    genvar early_row,early_lane;
    generate
        for(early_row=0;early_row<LSQ_ENTRIES;early_row=early_row+1) begin:g_allocation_store_guard
            assign allocation_older_stores[early_row]=valid_mem[early_row] && store_mem[early_row];
        end
        for(early_lane=0;early_lane<BE_WIDTH;early_lane=early_lane+1) begin:g_allocation_load_selection
            if(early_lane==0) begin:g_first
                assign allocation_prior_store[early_lane]=1'b0;
                assign allocation_load_grant[early_lane]=allocation_load_match[early_lane];
            end else begin:g_later
                assign allocation_prior_store[early_lane]=allocation_prior_store[early_lane-1] ||
                    (alloc_fire_o[early_lane-1] && alloc_is_store_i[early_lane-1]);
                assign allocation_load_grant[early_lane]=allocation_load_match[early_lane] &&
                    !(|allocation_load_match[early_lane-1:0]);
            end
            assign allocation_load_match[early_lane]=(ALLOC_LOAD_SELECTION_BYPASS!=0) &&
                (REQUEST_PIPELINE!=0) && !(|allocation_older_stores) &&
                !allocation_prior_store[early_lane] && alloc_fire_o[early_lane] &&
                alloc_is_load_i[early_lane] && !alloc_is_store_i[early_lane] && alloc_addr_valid_i[early_lane];
            assign allocation_load_values[early_lane*SELECTION_PAYLOAD_WIDTH +: SELECTION_PAYLOAD_WIDTH]={
                alloc_lsq_tag_o[early_lane*TAG_WIDTH+3 +: SLOT_WIDTH],
                alloc_lsq_tag_o[early_lane*TAG_WIDTH +: TAG_WIDTH],
                alloc_rob_tag_i[early_lane*ROB_TAG_WIDTH +: ROB_TAG_WIDTH],
                alloc_addr_i[early_lane*32 +: 32],1'b1,
                alloc_size_i[early_lane*2 +: 2],alloc_unsigned_i[early_lane],4'b0,32'b0};
        end
    endgenerate
    rv32_frequency_event_select #(.WIDTH(SELECTION_PAYLOAD_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) allocation_load_selector (
        .events_i(allocation_load_grant),.values_i(allocation_load_values),
        .write_o(allocation_load_found),.value_o(allocation_load_packet));
    wire selection_input_fire=(REQUEST_PIPELINE!=0) && !reset_i && !flush_i && !recovery_valid_i &&
        (!selection_valid || selection_discard || selection_done) &&
        (pick_valid[1] || allocation_load_found);
    wire [SELECTION_PAYLOAD_WIDTH-1:0] normal_selection_packet={
        pick_slot[1],make_lsq_tag(pick_slot[1],pick_generation),pick_rob_tag,
        pick_addr[1],pick_load,pick_size,pick_unsigned,pick_store_mask,pick_store_data};
    wire [SELECTION_PAYLOAD_WIDTH-1:0] selection_input_packet;
    rv32_frequency_event_select #(.WIDTH(SELECTION_PAYLOAD_WIDTH),.EVENTS(2),.PRIORITY(0)) selection_input_selector (
        .events_i({!pick_valid[1] && allocation_load_found,pick_valid[1]}),
        .values_i({allocation_load_packet,normal_selection_packet}),
        .write_o(),.value_o(selection_input_packet));
    // Original selection register boundary and full row-generation check.
    rv32_frequency_word_bank #(.WIDTH(SELECTION_PAYLOAD_WIDTH)) selection_payload_owner (
        .clk_i(clk_i),.write_i(selection_input_fire),.data_i(selection_input_packet),
        .data_o({selection_slot,selection_lsq_tag,selection_rob_tag,selection_addr,
                  selection_load,selection_size,selection_unsigned,selection_store_mask,selection_store_data}));'''
    text=once(text,old,new)
    marker='    wire forwarding_hold_write='
    assert text[text.index(marker):]==original[original.index(marker):]
    # All allocation/payload/metadata clocks, response capture, store ordering,
    # request acceptance, full-generation/discard/recovery logic remain exact.
    changes[name]=text
    name='rtl/backend/rv32_backend_joint.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer LOAD_WAKE_BYPASS = 0,',
        '    parameter integer LOAD_WAKE_BYPASS = 0,\n    parameter integer ALLOC_LOAD_SELECTION_BYPASS = 0,')
    text=once(text,'.LOAD_WAKE_BYPASS(RS_LOAD_RETURN_WAKE),',
        '.LOAD_WAKE_BYPASS(RS_LOAD_RETURN_WAKE), .ALLOC_LOAD_SELECTION_BYPASS(ALLOC_LOAD_SELECTION_BYPASS),')
    changes[name]=text
    for name,default in [('rtl/cpu_core.v',0),('rtl/course/student_top.v',1)]:
        text=(PARENT/name).read_text(encoding='utf-8')
        text=once(text,f'    parameter integer LOAD_WAKE_BYPASS = {default},',
            f'    parameter integer LOAD_WAKE_BYPASS = {default},\n    parameter integer ALLOC_LOAD_SELECTION_BYPASS = {default},')
        text=once(text,'.LOAD_WAKE_BYPASS(LOAD_WAKE_BYPASS),',
            '.LOAD_WAKE_BYPASS(LOAD_WAKE_BYPASS), .ALLOC_LOAD_SELECTION_BYPASS(ALLOC_LOAD_SELECTION_BYPASS),')
        changes[name]=text
    for name in parent['source_sha256']:
        dest=TARGET/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['parameter_overrides']=dict(parent['parameter_overrides'],ALLOC_LOAD_SELECTION_BYPASS=1)
    record['enabled_profile']=dict(parent['enabled_profile'],ALLOC_LOAD_SELECTION_BYPASS=1,
        ready_allocated_load_selection_wait_edges_removed=1,allocation_load_bypass_added_state_bits=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'A ready newly allocated load can fill the existing request selection on its allocation edge only with no existing/earlier-lane stores and no prior eligible request; keep full owner generation and original request/backpressure/recovery boundary.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        ready_allocated_load_to_selection_edges_before=2,
        ready_allocated_load_to_selection_edges_after=1,
        allocation_load_bypass_added_state_bits=0,
        allocation_load_bypass_timing_risk='Existing dispatch PRF/address add plus allocation/grant to selection register.',
        allocation_load_bypass_dynamic_coverage_and_ppa_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_READY_ALLOCATED_LOAD_REQUEST_SELECTION_ONE_EDGE_EARLIER_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),tests_started=False,
        source_arguments=[
            'Normal pick_valid candidate has absolute priority. Allocated ready load shortcut is enabled only in registered selection mode and only when that register can accept its next packet by the original discard/done/empty guard.',
            'Any existing valid store, including uncommitted/unknown-address/in-flight-ack stores, disables shortcut. Any accepted store in an earlier allocation lane disables that and all following lanes. Younger stores cannot forward to or retire before this older load.',
            'First eligible allocated load is selected, carrying exact full new-generation LSQ tag from alloc_lsq_tag_o, compacted slot, full ROB tag, original allocation address/size/unsigned and load-only identity.',
            'Same allocation edge writes row payload/valid/generation and selection packet. The original next-cycle selection_live checks row generation/tag/valid/wait/sent/complete before issuing; a failed or killed identity is discarded normally.',
            'No cache request leaves on allocation edge and no nominal register boundary is removed. One idle wait before existing selection is eliminated. Original response capture, CDB/formal completion and selective recovery boundaries are unchanged.',
            'Entire source suffix from forwarding_hold_write, including all clocked LSQ row ownership/allocation, store forwarding/hazards, request handshakes, generation/recovery and commit logic is exact parent bytes. No extra state or new allocation-ready feedback.',
            'Added area is allocation packet selection and store guards; new critical possibility is dispatch source/address/allocated-tag to selection capture. Actual trigger rate, IPC gain and Fmax remain unmeasured.',
            'No HDL build, lint, simulation, synthesis, STA, performance or unit tests. Later targeted coverage must include older/earlier-lane stores, sparse allocations/wrap/generation, current request drain+new allocation, stalls and recovery.'
        ])
    write(BASE/'A28_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':
    main()
