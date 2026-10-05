"""Use exact circular oldest one-hot grants for the complete LSQ request packet."""
from datetime import datetime,timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read,sha,write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A81_fast_store_original_data_contract'
TARGET = BASE/'A82_lsq_pick_onehot'
REVIEW = BASE/'A82_source_review.json'


def once(text,old,new):
    assert text.count(old) == 1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == 'b908da4e20d11a9f604c62bbab2377f2145b8108fbbc4b507b9a1284d78a7baf'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest,name
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original,'    parameter integer FORWARD_ONEHOT = 0,',
        '''    parameter integer FORWARD_ONEHOT = 0,
    // Route the same oldest current request packet with circular one-hot
    // grants; default and other geometry retain the original tournament.
    parameter integer PICK_ONEHOT = 0,''')
    start = text.index('        for (pick_node = 1;')
    end = text.index('        if(FORWARD_ONEHOT',start)
    legacy = text[start:end]
    assert legacy.endswith('        end\n')
    replacement = '''        if(PICK_ONEHOT!=0 && CIRCULAR_ORDER_POWER2 && LSQ_ENTRIES>1) begin:g_onehot_pick
            wire [LSQ_ENTRIES-1:0] eligible,nonwrapped,grants;
            wire [LSQ_ENTRIES*PICK_SELECT_WIDTH-1:0] values;
            localparam integer GRANT_DOMAINS=(LSQ_ENTRIES+3)/4;
            wire [GRANT_DOMAINS-1:0] no_nonwrapped_views;
            wire no_requests=!(|eligible);
            rv32_frequency_control_tree #(.LEAVES(GRANT_DOMAINS)) class_tree (
                .signal_i(!(|nonwrapped)),.views_o(no_nonwrapped_views));
            for(genvar pick_row=0;pick_row<LSQ_ENTRIES;pick_row=pick_row+1) begin:g_row
                assign eligible[pick_row]=pick_valid[LSQ_ENTRIES+pick_row];
                assign nonwrapped[pick_row]=eligible[pick_row] && !pick_wrap[LSQ_ENTRIES+pick_row];
                wire first_any,first_nonwrapped;
                if(pick_row==0) begin:g_first
                    assign first_any=eligible[pick_row];
                    assign first_nonwrapped=nonwrapped[pick_row];
                end else begin:g_later
                    assign first_any=eligible[pick_row] && !(|eligible[pick_row-1:0]);
                    assign first_nonwrapped=nonwrapped[pick_row] && !(|nonwrapped[pick_row-1:0]);
                end
                // The old all-invalid tournament recursively chooses its
                // right child, hence the final physical leaf. Preserve even
                // that unobservable packet rather than inventing zero data.
                assign grants[pick_row]=first_nonwrapped ||
                    (no_nonwrapped_views[pick_row/4] && first_any) ||
                    ((pick_row==LSQ_ENTRIES-1) && no_requests);
                assign values[pick_row*PICK_SELECT_WIDTH +: PICK_SELECT_WIDTH]={
                    pick_slot[LSQ_ENTRIES+pick_row],pick_age[LSQ_ENTRIES+pick_row],pick_wrap[LSQ_ENTRIES+pick_row],
                    pick_addr[LSQ_ENTRIES+pick_row],pick_payload[LSQ_ENTRIES+pick_row]};
            end
            wire [PICK_SELECT_WIDTH-1:0] root_packet;
            rv32_frequency_event_select #(.WIDTH(PICK_SELECT_WIDTH),.EVENTS(LSQ_ENTRIES),.PRIORITY(0)) packet_selector (
                .events_i(grants),.values_i(values),.write_o(),.value_o(root_packet));
            assign pick_valid[1]=|eligible;
            assign {pick_slot[1],pick_age[1],pick_wrap[1],pick_addr[1],pick_payload[1]}=root_packet;
            // Internal tournament nodes have no consumers in this branch.
            // Give them constant drivers so no dangling undriven nets remain.
            for(pick_node=2;pick_node<LSQ_ENTRIES;pick_node=pick_node+1) begin:g_unused_node
                assign pick_valid[pick_node]=0;
                assign {pick_slot[pick_node],pick_age[pick_node],pick_wrap[pick_node],
                        pick_addr[pick_node],pick_payload[pick_node]}=0;
            end
        end else begin:g_original_pick
''' + legacy + '        end\n'
    text = text[:start]+replacement+text[end:]
    # The original leaves/eligibility/aliases remain exact, and all consumers
    # still use only the identical complete root packet. The forward selector,
    # request owner, all held tickets and metadata/scalar state stay untouched.
    original_end = original.index('        if(FORWARD_ONEHOT',original.index('        for (pick_node = 1;'))
    assert text[text.index('        if(FORWARD_ONEHOT',text.index('        end else begin:g_original_pick')):] == original[original_end:]
    for marker in ['assign pick_valid[LSQ_ENTRIES+age_slot] = request_eligible[age_slot];',
                   'assign pick_slot[LSQ_ENTRIES+age_slot] = age_slot;',
                   'pick_payload_rows[PAYLOAD_SLOT*PICK_PAYLOAD_WIDTH +: PICK_PAYLOAD_WIDTH];',
                   'assign pick_wrap[LSQ_ENTRIES+wrap_row]=circular_wrap_views[wrap_row*8];',
                   'wire selection_input_fire=(REQUEST_PIPELINE!=0)']:
        assert marker in text,marker
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        text = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        old = '    parameter integer LSQ_FORWARD_ONEHOT = '+str(default)+','
        text = once(text,old,old+'\n    parameter integer LSQ_PICK_ONEHOT = '+str(default)+',')
        old = '.FORWARD_ONEHOT(LSQ_FORWARD_ONEHOT)' if '/backend/' in name else '.LSQ_FORWARD_ONEHOT(LSQ_FORWARD_ONEHOT)'
        text = once(text,old,old+', '+('.PICK_ONEHOT' if '/backend/' in name else '.LSQ_PICK_ONEHOT')+'(LSQ_PICK_ONEHOT)')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_LSQ_PICK_ONEHOT_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],LSQ_PICK_ONEHOT=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],LSQ_PICK_ONEHOT=1,
        lsq_oldest_request_onehot_packet=True,lsq_oldest_no_request_original_last_leaf_preserved=True,
        lsq_pick_onehot_new_ff_bits=0,lsq_pick_onehot_new_sram_bits=0,lsq_pick_onehot_new_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'For power-of-two LSQ>1 express the original oldest request as the lowest eligible nonwrapped physical row, else lowest eligible wrapped row. Select the complete original leaf slot/age/wrap/address/aliased payload packet with one-hot masked-OR routing. Preserve original rightmost-leaf payload when every request is invalid. Default/LSQ1/other geometry keeps exact original tournament; eligibility, request/forwarding/held ownership and state edges unchanged.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        a75_request_pick_control_anchor_ns=[0.7442,0.8426,0.9440,1.0430],
        lsq_pick_onehot_limit='Replaces observed serial packet/valid/wrap tournament routing; one-hot prefix/class reduction, eligibility, bounded control fanout and wide OR remain. No guaranteed saving of0.2988ns or IPC gain. Gate area and cumulative A76-A82 IPC/Fmax/area unknown.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        source_arguments=[
            'A75 top5 measured LSQ paths traverse g_pick[11/5/2/1] choice controls at0.7442/0.8426/0.9440/1.0430ns before the second state read and byte forwarding. This rewrite targets that same earlier serial selection, complementing A77 local qualification and A78 forwarding. Intervals are evidence of dependency, not promised savings.',
            'In the original power-of-two tree with ascending physical leaves, a valid left child wins if right invalid or left nonwrapped or right wrapped. Within either wrap class, the lower physical leaf wins; the nonwrapped class always precedes wrapped. Inductively the root is lowest eligible nonwrapped physical row, else lowest eligible wrapped row. Both-invalid nodes choose right, yielding the rightmost leaf when root invalid.',
            'New grants encode first_nonwrapped OR(no_nonwrapped && first_any), plus only the last leaf when no request exists. Exactly one grant always selects the same original complete leaf packet, including invalid-root payload. Valid output remains OReligibility. Original slot width truncation, PAYLOAD_SLOT alias, generation, row-local direct predicate, request address, age and wrap all follow that same leaf; no custom slot-width or idle-payload behavior is discarded.',
            'Original request eligibility/older-store hazards, leaf construction, saved selection full generation/liveness, byte forwarding and held snapshot, actual request/response/commit handshakes and metadata/scalar updates remain byte-identical. Option0, LSQ1 and other geometry retain original tournament. No FF/SRAM/edge, age priority, port, FIFO depth, speculative memory bypass or parameter removal is introduced.',
            'Manual source/inductive priority reasoning only, no HDL/lint/formal/simulation/synthesis/STA/unit run. Future batch: all-invalid/single/multiple requests, both wrap classes and boundary rows, held/direct request stalls, data/address hazards, allocation/full-tag reuse/reset/recovery, slot aliases, options0/1 and widths1/2/4, LSQ1/2/4/8/16/32, area/Fmax/IPC. Exact mapping and full equivalence unproven.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
