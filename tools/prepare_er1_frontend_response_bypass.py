"""Bypass empty frontend queue into existing decode buffer; no HDL runs."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A29_multibank_branch_feedback'
TARGET=BASE/'A30_frontend_response_bypass'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/frontend/rv32_fetch_frontend.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer COMPACT_PRED_TARGET = 0,',
        '    parameter integer COMPACT_PRED_TARGET = 0,\n    parameter integer RESPONSE_BYPASS = 0,')
    text=once(text,'''    wire response_live = (if_resp_epoch_i == epoch_reg) &&
                         (if_resp_line_addr_i == {if_resp_pc_i[31:4], 4'b0000});''','''    wire response_live = (if_resp_epoch_i == epoch_reg) &&
                         (if_resp_line_addr_i == {if_resp_pc_i[31:4], 4'b0000});
    // Response acceptance depends on saved occupancy/epoch, never on decode
    // readiness. Empty-queue bypass therefore has no ready-to-valid loop.
    wire response_bypass=(RESPONSE_BYPASS!=0) && count_reg==0 &&
        if_resp_valid_i && if_resp_ready_o && !if_resp_error_i &&
        !frozen_reg && !stop_i && !error_i;
    wire [31:0] output_available=response_bypass?
        {{(32-BUNDLE_COUNT_WIDTH){1'b0}},bundle_count}:count_reg;''')
    old='''            rv32_frequency_event_select #(.WIDTH(READ_DATA_WIDTH),.EVENTS(1)) packet_selector (
                .events_i(public_lane<count_reg),
                .values_i({queue_read_packets[public_lane*PACKET_WIDTH +: PACKET_WIDTH],
                           queue_read_metadata[public_lane*16 +: 16]}),.write_o(),
                .value_o({fetch_packet_o[public_lane*PACKET_WIDTH +: PACKET_WIDTH],
                          fetch_pred_metadata_o[public_lane*16 +: 16]}));'''
    new='''            if(RESPONSE_BYPASS!=0) begin:g_empty_bypass
                wire [PACKET_WIDTH-1:0] response_packet=
                    `RV32IM_FETCH_PACKET_PACK(bundle_pc[public_lane*32 +: 32],
                        bundle_inst[public_lane*32 +: 32],bundle_pred_taken[public_lane],
                        bundle_pred_target[public_lane*32 +: 32],bundle_pred_kind[public_lane*2 +: 2],
                        bundle_pred_btb_hit[public_lane],bundle_epoch);
                wire [15:0] response_metadata=(PREDICTOR_META!=0)?
                    if_resp_pred_metadata_i[public_lane*16 +: 16]:16'b0;
                rv32_frequency_event_select #(.WIDTH(READ_DATA_WIDTH),.EVENTS(2),.PRIORITY(0)) packet_selector (
                    .events_i({response_bypass && public_lane<bundle_count,
                        !response_bypass && public_lane<count_reg}),
                    .values_i({response_packet,response_metadata,
                        queue_read_packets[public_lane*PACKET_WIDTH +: PACKET_WIDTH],
                        queue_read_metadata[public_lane*16 +: 16]}),.write_o(),
                    .value_o({fetch_packet_o[public_lane*PACKET_WIDTH +: PACKET_WIDTH],
                        fetch_pred_metadata_o[public_lane*16 +: 16]}));
            end else begin:g_queued
                rv32_frequency_event_select #(.WIDTH(READ_DATA_WIDTH),.EVENTS(1)) packet_selector (
                    .events_i(public_lane<count_reg),
                    .values_i({queue_read_packets[public_lane*PACKET_WIDTH +: PACKET_WIDTH],
                               queue_read_metadata[public_lane*16 +: 16]}),.write_o(),
                    .value_o({fetch_packet_o[public_lane*PACKET_WIDTH +: PACKET_WIDTH],
                              fetch_pred_metadata_o[public_lane*16 +: 16]}));
            end'''
    text=once(text,old,new)
    text=once(text,'''            if (j < count_reg) begin
                fetch_valid_o[j] = 1'b1;
            end
            if ((j < count_reg) && (deq_count == j) && fetch_ready_i[j])''','''            if (j < output_available) begin
                fetch_valid_o[j] = 1'b1;
            end
            if ((j < output_available) && (deq_count == j) && fetch_ready_i[j])''')
    # Same count update enq-deq and modulo pointers. When initially empty,
    # both advance past the newly bypassed prefix; remaining rows stay queued.
    clock='    always @(posedge clk_i) begin\n        if (reset_i) begin'
    assert text[text.index(clock):]==original[original.index(clock):]
    payload='    localparam integer PAYLOAD_WIDTH='
    # Queue writes still save the entire accepted bundle, including harmless
    # rows consumed via bypass on this same edge. No stored fields are omitted.
    assert 'count_storage_reg <= count_reg + enq_count - deq_count;' in text
    changes[name]=text
    name='rtl/cpu_core.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer FRONTEND_QUEUE_PAYLOAD_BANKS = 0,',
        '    parameter integer FRONTEND_QUEUE_PAYLOAD_BANKS = 0,\n    parameter integer FRONTEND_RESPONSE_BYPASS = 0,')
    text=once(text,'.COMPACT_PRED_TARGET(COMPACT_TARGET_ACTIVE), .PREDICTOR_META(PREDICTOR_DIRECT_BRANCH_TARGET == 2), .LEGACY_SENTINEL_HALT',
        '.RESPONSE_BYPASS(FRONTEND_RESPONSE_BYPASS && (DECODE_PIPELINE!=0) && !SERIAL_BACKEND), .COMPACT_PRED_TARGET(COMPACT_TARGET_ACTIVE), .PREDICTOR_META(PREDICTOR_DIRECT_BRANCH_TARGET == 2), .LEGACY_SENTINEL_HALT')
    changes[name]=text
    name='rtl/course/student_top.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer FRONTEND_QUEUE_PAYLOAD_BANKS = 1,',
        '    parameter integer FRONTEND_QUEUE_PAYLOAD_BANKS = 1,\n    parameter integer FRONTEND_RESPONSE_BYPASS = 1,')
    text=once(text,'.FRONTEND_QUEUE_PAYLOAD_BANKS(FRONTEND_QUEUE_PAYLOAD_BANKS),',
        '.FRONTEND_QUEUE_PAYLOAD_BANKS(FRONTEND_QUEUE_PAYLOAD_BANKS), .FRONTEND_RESPONSE_BYPASS(FRONTEND_RESPONSE_BYPASS),')
    changes[name]=text
    for name in parent['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():(TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['parameter_overrides']=dict(parent['parameter_overrides'],FRONTEND_RESPONSE_BYPASS=1)
    record['enabled_profile']=dict(parent['enabled_profile'],FRONTEND_RESPONSE_BYPASS=1,
        empty_fq_response_to_decode_wait_edges_removed=1,frontend_bypass_added_state_bits=0,
        original_queue_capacity_retained=16,registered_decode_boundary_retained=True)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'When FQ is empty, let existing registered decode accept the returned instruction prefix directly; original queue writes/count/pointers retain all unconsumed instructions, saving one response-to-decode waiting edge.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        empty_fq_response_to_decode_accept_edges_before=2,
        empty_fq_response_to_decode_accept_edges_after=1,
        frontend_empty_bypass_added_state_bits=0,
        frontend_empty_bypass_registered_decode_still_required=True,
        frontend_empty_bypass_timing_risk='Instruction-cache response/predictor prefix plus decoder now share an interval.',
        frontend_empty_bypass_ipc_area_frequency_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_EMPTY_FRONTEND_QUEUE_RESPONSE_TO_REGISTERED_DECODE_BYPASS_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),
        tests_started=False,source_arguments=[
            'Bypass requires empty saved FQ, a live accepted nonerror response, no reset/redirect/frozen/stop/error, and the original decoder register enabled in OoO core. Other profiles retain original queued semantics.',
            'Packet and prediction metadata are built from exactly the same accepted bundle fields used by row writes, including full PC/instruction/epoch and configured compact prediction token. Predicted-taken/sentinel prefix remains unchanged.',
            'Original if_resp_ready depends only on saved occupancy/response epoch/redirect, not on fetch_ready. Bypass valid therefore never depends on decode ready; decode prefix readiness determines only consumed count.',
            'Original row write, enq_count and all clocked state remain exact source. With count0, accepted N and consumed K<=N, tail advancesN, head advancesK, count becomesN-K; stored suffix rowsK..N-1 remain available. Consumed row writes are harmless.',
            'Decode full/partial acceptance preserves remainder. If nothing is accepted, complete bundle simply enters FQ normally. Nonempty FQ is unchanged. Reset/redirect flush, stale epoch and error responses cannot bypass.',
            'Removes one waiting edge for empty-FQ refill, especially after redirect or frontend starvation. No extra state/capacity or new rename/commit/recovery boundary. Still requires dynamic trigger/IPC measurement.',
            'New combinational interval includes cache response/predictor prefix/public packet selection plus existing decoder. This is a material Fmax risk, not assumed safe at300MHz; analyze prefix/control fanout before the later coherent measurement.',
            'No HDL build, lint, simulation, synthesis, STA, performance or unit tests. Later coverage must include partial prefix consumption, same-edge next request, redirect/stale/error, PC line offset and pointer wrap.'
        ])
    write(BASE/'A30_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':main()
