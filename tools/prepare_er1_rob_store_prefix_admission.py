"""Authorize a following store only when its older ROB prefix really retires."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A83_fast_store_identity_preselect'
TARGET = BASE/'A84_rob_store_prefix_admission'
REVIEW = BASE/'A84_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == 'f4101372d47ec5f690e93b555f63b7cc0f777ed97499251f28c7a0a228922447'
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_rob.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer FAST_STORE_IDENTITY_PRESELECT = 0,',
        '''    parameter integer FAST_STORE_IDENTITY_PRESELECT = 0,
    // Publish at most one following ordinary store when every older lane
    // actually retires on this edge; its own retirement still uses saved sent.
    parameter integer STORE_PREFIX_ADMISSION = 0,''')
    marker = '    // Allocation and all observable outputs are evaluated from old state.'
    assert marker in text
    early = '''    localparam integer STORE_PREFIX_ADMISSION_ACTIVE=(STORE_PREFIX_ADMISSION!=0) &&
        (BE_WIDTH>1) && (ROB_ENTRIES>=BE_WIDTH) && (ALLOC_BANKED_WRITE!=0) &&
        (STORE_BUFFERED_RETIRE!=0) && (LIGHT_RETIRE_PAYLOAD!=0) &&
        (MMIO_PREDECODE!=0) && (LEGACY_HALT_PAYLOAD==0) && (RETURN_VALUE_ENABLE==0);
    wire [TAG_WIDTH-1:0] prefix_admission_tag;
    generate if(STORE_PREFIX_ADMISSION_ACTIVE!=0) begin:g_store_prefix_identity
        wire [BE_WIDTH-1:0] potential,grants;
        wire [BE_WIDTH*TAG_WIDTH-1:0] tags;
        for(genvar admission_lane=0;admission_lane<BE_WIDTH;admission_lane=admission_lane+1) begin:g_lane
            wire [31:0] raw_slot=head_commit_index+admission_lane;
            wire [31:0] slot=(raw_slot>=ROB_ENTRIES) ? raw_slot-ROB_ENTRIES : raw_slot;
            // Identity depends only on saved head fields, before the late
            // true-retirement prefix and LSQ admission-ready qualification.
            assign potential[admission_lane]=head_valid[admission_lane] &&
                head_store[admission_lane] && !head_store_sent[admission_lane];
            if(admission_lane==0) begin:g_first
                assign grants[admission_lane]=potential[admission_lane];
            end else begin:g_later
                assign grants[admission_lane]=potential[admission_lane] && !(|potential[admission_lane-1:0]);
            end
            assign tags[admission_lane*TAG_WIDTH +: TAG_WIDTH]=make_tag(slot,head_generation[admission_lane]);
        end
        rv32_frequency_event_select #(.WIDTH(TAG_WIDTH),.EVENTS(BE_WIDTH),.PRIORITY(0)) identity_selector (
            .events_i(grants),.values_i(tags),.write_o(),.value_o(prefix_admission_tag));
    end else begin:g_original_store_identity
        assign prefix_admission_tag=0;
    end endgenerate

'''
    text = once(text, marker, early+marker)
    text = once(text, '''                        // Stores must become the actual ROB head before they
                        // enter the committed portion of the LSQ.  Admission
                        // to that queue is the retirement point; the LSQ then
                        // retains and drains the store like a store buffer.
                        // A store behind another lane is retried as lane zero
                        // because there is one store-admission port.''',
        '''                        // A store retires only from its registered admission
                        // state as actual head. Optional prefix admission may
                        // publish a following ordinary store on the same edge
                        // that all preceding lanes truly retire; no younger
                        // store retires here and there is still only one port.''')
    text = once(text, '''                        if (commit_lane == 0 && head_store[commit_lane] &&
                            !head_store_sent[commit_lane] &&
                            ((STORE_BUFFERED_RETIRE != 0) || !head_store_wait[commit_lane])) begin''',
        '''                        if ((commit_lane == 0 ||
                             (STORE_PREFIX_ADMISSION_ACTIVE!=0 && commit_ready_i &&
                              !head_mmio_word[commit_lane] && !head_halt[commit_lane] && !head_error[commit_lane])) &&
                            head_store[commit_lane] && !head_store_sent[commit_lane] &&
                            !store_commit_valid_o &&
                            ((STORE_BUFFERED_RETIRE != 0) || !head_store_wait[commit_lane])) begin''')
    text = once(text, '                            store_commit_tag_o = make_tag(commit_slot, head_generation[commit_lane]);',
        '''                            store_commit_tag_o = (STORE_PREFIX_ADMISSION_ACTIVE!=0) ?
                                prefix_admission_tag : make_tag(commit_slot, head_generation[commit_lane]);''')
    text = once(text, '    wire [WRITE_DOMAINS-1:0] local_store_sends;',
        '''    wire [WRITE_DOMAINS-1:0] local_store_sends;
    wire [WRITE_DOMAINS*SLOT_WIDTH-1:0] local_store_send_slots;
    generate if(STORE_PREFIX_ADMISSION_ACTIVE!=0) begin:g_prefix_send_slots
        rv32_frequency_control_tree #(.WIDTH(SLOT_WIDTH),.LEAVES(WRITE_DOMAINS)) slot_tree (
            .signal_i(prefix_admission_tag[SLOT_LSB +: SLOT_WIDTH]),.views_o(local_store_send_slots));
    end else begin:g_original_send_slots
        assign local_store_send_slots=0;
    end endgenerate''')
    text = once(text, '            wire sent=normal && local_store_sends[DOMAIN] && row_commit_head==command_row;',
        '''            wire [SLOT_WIDTH-1:0] row_send_slot=(STORE_PREFIX_ADMISSION_ACTIVE!=0) ?
                local_store_send_slots[DOMAIN*SLOT_WIDTH +: SLOT_WIDTH] : row_commit_head;
            wire sent=normal && local_store_sends[DOMAIN] && row_send_slot==command_row;''')
    # No change to ordinary publication-ready, actual retirement decision,
    # pop/head/credit, recovery, ack, fast completion or legacy state ownership.
    assert text[text.index('    end else begin:g_legacy_field_commands'): ] == original[original.index('    end else begin:g_legacy_field_commands'): ]
    for block in [
        '''                            if (commit_lane == 0) begin
                                if ((STORE_BUFFERED_RETIRE != 0) &&''',
        '''                            else
                                commit_valid_o[commit_lane] = 1'b0;''',
        '''                        if (commit_valid_o[commit_lane]) begin
                            pop_count = pop_count + 1;''',
        '''                            if (head_halt[commit_lane] || head_error[commit_lane] ||''',
        '            .signal_i(store_commit_valid_o && store_commit_ready_i),.views_o(local_store_sends));']:
        assert block in text, block
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v', 'rtl/cpu_core.v', 'rtl/course/student_top.v']:
        text = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        old = '    parameter integer FAST_STORE_IDENTITY_PRESELECT = '+str(default)+','
        text = once(text, old, old+'\n    parameter integer ROB_STORE_PREFIX_ADMISSION = '+str(default)+',')
        if '/backend/' in name:
            text = once(text, '.FAST_STORE_IDENTITY_PRESELECT(FAST_STORE_IDENTITY_PRESELECT),',
                '.FAST_STORE_IDENTITY_PRESELECT(FAST_STORE_IDENTITY_PRESELECT), .STORE_PREFIX_ADMISSION(ROB_STORE_PREFIX_ADMISSION),')
        else:
            text = once(text, '.FAST_STORE_IDENTITY_PRESELECT(FAST_STORE_IDENTITY_PRESELECT),',
                '.FAST_STORE_IDENTITY_PRESELECT(FAST_STORE_IDENTITY_PRESELECT), .ROB_STORE_PREFIX_ADMISSION(ROB_STORE_PREFIX_ADMISSION),')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_ROB_STORE_PREFIX_ADMISSION_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],ROB_STORE_PREFIX_ADMISSION=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],ROB_STORE_PREFIX_ADMISSION=1,
        rob_store_prefix_new_ff_bits=0,rob_store_prefix_new_sram_bits=0,rob_store_prefix_new_pipeline_edges=0,
        rob_store_admission_ports=1,rob_store_retirement_still_registered_sent=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'In light banked buffered-retire profiles, permit one ordinary nonterminal/error-free store behind the actual head to be admitted on the edge that its complete older prefix really retires. Keep its retirement blocked until actual head and registered admission, retain LSQ queue and memory order, early saved-head tag selection, per-selected-row sent ownership, and all original default/unsupported behavior.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        rob_consecutive_ready_store_ideal_admission_interval_before=2,
        rob_consecutive_ready_store_ideal_admission_interval_after=1,
        rob_store_prefix_limit='Source schedule opportunity only: BE2 consecutive ready stores can overlap retiring the already-admitted head with admitting the next store, changing ideal interval2 to1. Mixed old-integer/store may remove one admission bubble. No measured IPC/area/Fmax gain; head-field selector and late retirement-prefix gating may change timing.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'A83 original store behind any older lane sets commit_valid0 and cannot publish admission until actual head. Even ready consecutive ordinary buffered stores use one edge to admit and the next to retire, limiting ideal stream retirement to0.5 store/cycle despite one admission port/cycle. Prefix mode overlaps retiring already-admitted head with admission of following store; its own retirement remains from registered sent at actual head on next edge.',
            'The original commit loop reaches laneN only when every older valid/ready lane has original commit_valid1 and no halt/error/MMIO terminal break. New non-head admission additionally requires commit_ready_i, so all preceding lanes actually retire on this same edge. Their pop_count equalsN; the authorized store becomes actual head after this edge and cannot be speculatively killed by an older unretired instruction. No later lane can retire through this store because its commit_valid stays0.',
            'Exactly one original store-admission port and actual LSQ readiness handshake remain. Non-head MMIO terminal, halt/error, stalled older prefix or external retirement stall do not publish. Original head admission/precise MMIO waits are preserved. Recovery/hold global suppression, LSQ full ROB tag match and ready address/data, queued committed-store preservation/request ordering, cache acknowledgement and errors are unchanged.',
            'Select the earliest saved valid store with unsent state independently of the late true-retirement prefix. Any reached publishing store is necessarily that earliest potential store: an older unsent store would block the original commit loop. Complete tag uses same wrapped slot and original full generation. New row sent decoder uses this selected early slot with the original actual handshake; other ready/gen/error/retire/alloc/ack state ownership and priority are unchanged.',
            'Only banked light buffered-retire profiles with MMIO predecode and omitted legacy/value payloads activate. Option0/BE1/unsupported profiles retain original identity, head-only publication and command path. Legacy writer/state tails are byte-identical. No FF/SRAM/edge/port, same-edge new-store retirement, ready-to-head capacity bypass or broader speculative memory request is added.',
            'Manual source/prefix schedule/ownership reasoning and hashes only; no HDL/lint/formal/simulation/synthesis/STA/unit test. Course A83 run/source/manager remain frozen. Future: consecutive/mixed/BE4 prefixes, all commit-ready/LSQ-ready stalls, older incomplete and terminal/error instructions, MMIO full-mask exit, already-admitted head, wrapped head/GEN reuse, branch recovery, ack/error/alloc/retire collisions, defaults and all parameters. Timing/gate area and aggregate gains remain unproven.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
