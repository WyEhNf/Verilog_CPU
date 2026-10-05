"""Select youngest overlapping store bytes by exact circular one-hot grants."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A77_lsq_pick_local_validity'
TARGET = BASE / 'A78_lsq_forward_onehot'
REVIEW = BASE / 'A78_source_review.json'


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT / 'candidate.json')
    assert sha(PARENT / 'candidate.json') == 'e3f9d51d28dada5bc375bb887cb664e3a554de6613c3032f2da66b45b26ed52d'
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT / name).read_text(encoding='utf-8')
    text = once(original, '    parameter integer PICK_LOCAL_VALIDITY = 0,',
        '''    parameter integer PICK_LOCAL_VALIDITY = 0,
    // Exact youngest-byte selection for the circular power-of-two queue.
    // The original tournament remains the default/other-geometry fallback.
    parameter integer FORWARD_ONEHOT = 0,''')
    start = text.index('        // Each byte independently selects the youngest overlapping older')
    end = text.index('    endgenerate', start)
    legacy = text[start:end]
    assert legacy.endswith('        end\n')
    replacement = '''        if(FORWARD_ONEHOT!=0 && CIRCULAR_ORDER_POWER2) begin:g_onehot_forward
            // Ascending physical leaves in the old tournament select the
            // highest row of the wrapped class, or highest ordinary row if
            // no wrapped byte overlaps. Grants express that same order.
            for(forward_byte=0;forward_byte<4;forward_byte=forward_byte+1) begin:g_byte
                wire [LSQ_ENTRIES-1:0] eligible,wrapped_eligible,grants;
                wire [LSQ_ENTRIES*8-1:0] values;
                localparam integer GRANT_DOMAINS=(LSQ_ENTRIES+3)/4;
                wire [GRANT_DOMAINS-1:0] no_wrapped_views;
                rv32_frequency_control_tree #(.LEAVES(GRANT_DOMAINS)) class_tree (
                    .signal_i(!(|wrapped_eligible)),.views_o(no_wrapped_views));
                for(forward_slot=0;forward_slot<LSQ_ENTRIES;forward_slot=forward_slot+1) begin:g_row
                    assign eligible[forward_slot]=store_overlap[forward_slot][forward_byte];
                    assign wrapped_eligible[forward_slot]=eligible[forward_slot] &&
                        circular_wrap_views[forward_slot*8+1+forward_byte];
                    wire last_ordinary,last_wrapped;
                    if(forward_slot==LSQ_ENTRIES-1) begin:g_last
                        assign last_ordinary=eligible[forward_slot];
                        assign last_wrapped=wrapped_eligible[forward_slot];
                    end else begin:g_earlier
                        assign last_ordinary=eligible[forward_slot] &&
                            !(|eligible[LSQ_ENTRIES-1:forward_slot+1]);
                        assign last_wrapped=wrapped_eligible[forward_slot] &&
                            !(|wrapped_eligible[LSQ_ENTRIES-1:forward_slot+1]);
                    end
                    assign grants[forward_slot]=last_wrapped ||
                        (no_wrapped_views[forward_slot/4] && last_ordinary);
                    assign values[forward_slot*8 +: 8]=store_forward_data[forward_slot][forward_byte*8 +: 8];
                end
                assign tree_forward_mask[forward_byte]=|eligible;
                rv32_frequency_event_select #(.WIDTH(8),.EVENTS(LSQ_ENTRIES),.PRIORITY(0)) byte_selector (
                    .events_i(grants),.values_i(values),.write_o(),
                    .value_o(tree_forward_data[forward_byte*8 +: 8]));
            end
        end else begin:g_original_forward
''' + legacy + '        end\n'
    text = text[:start] + replacement + text[end:]
    # All payload and state before/after this byte selector remain original,
    # including source overlap predicates and all actual request handshakes.
    original_end = original.index('    endgenerate', original.index('        // Each byte independently selects the youngest overlapping older'))
    assert text[text.index('    endgenerate', text.index('        end else begin:g_original_forward')):] == original[original_end:]
    for marker in ['(addr_mem[age_slot][31:4] == local_load_addr[31:4]) ? local_overlap : 4\'b0;',
                   'forwarding_hold_mask:tree_forward_mask;',
                   'forwarding_hold_data[0 +: 16]:tree_forward_data[0 +: 16];',
                   'forwarding_hold_data[16 +: 16]:tree_forward_data[16 +: 16];',
                   'candidate_found && selected_load &&',
                   'if(selection_done || selection_discard) forwarding_hold_valid<=0;']:
        assert marker in text, marker
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        text = (PARENT / name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        text = once(text, '    parameter integer LSQ_PICK_LOCAL_VALIDITY = '+str(default)+',',
            '    parameter integer LSQ_PICK_LOCAL_VALIDITY = '+str(default)+',\n    parameter integer LSQ_FORWARD_ONEHOT = '+str(default)+',')
        old = '.PICK_LOCAL_VALIDITY(LSQ_PICK_LOCAL_VALIDITY)' if '/backend/' in name else '.LSQ_PICK_LOCAL_VALIDITY(LSQ_PICK_LOCAL_VALIDITY)'
        text = once(text, old, old+', '+('.FORWARD_ONEHOT' if '/backend/' in name else '.LSQ_FORWARD_ONEHOT')+'(LSQ_FORWARD_ONEHOT)')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PARENT / name, destination)
    for name, text in changes.items():
        (TARGET / name).write_text(text, encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_LSQ_FORWARD_ONEHOT_UNTESTED', source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(), parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT / 'candidate.json'), changed_from_parent_files=list(changes),
        source_sha256={name:sha(TARGET / name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)), source_review=str(REVIEW),
        tests_started=False, synthesis_started=False, timing_started=False, adopted=False,
        candidate_ipc=None, candidate_area_um2=None, candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'], LSQ_FORWARD_ONEHOT=1)
    record['enabled_profile'] = dict(parent['enabled_profile'], LSQ_FORWARD_ONEHOT=1,
        lsq_per_byte_youngest_onehot=True, lsq_onehot_new_ff_bits=0,
        lsq_onehot_new_sram_bits=0, lsq_onehot_new_pipeline_edges=0)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Keep original per-store/per-byte overlap and value calculation. Express the original power-of-two youngest-store tournament as mutually exclusive highest-physical-row grants: highest overlapping wrapped row first, else highest overlapping nonwrapped row. Select each byte with original bounded one-hot event routing, preserve byte mask, saved forwarding snapshot, original request owner and all state/handshake edges. Default/other geometry retains byte tournament.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        a75_forward_overlap_anchor_ns=2.138, a75_raw_forward_data_anchor_ns=2.937,
        lsq_onehot_forward_limit='Removes repeated data/age/wrap selection after late overlap; prefix/class reductions and OR payload tree remain. Observed0.799ns interval is not a predicted saving. No equal-edge IPC gain claimed and no new test started; exact mapped area/Fmax and cumulative head-completion effects unknown.')
    write(TARGET / 'candidate.json', record)
    proof = dict(status=record['status'], candidate=str(TARGET), candidate_sha256=sha(TARGET / 'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'], changed_files=list(changes),
        measured_timing=parent['material_gain_evidence']['a75_measured_timing'],
        tests_started=False, adopted=False, added_declared_ff_bits=0, new_sram_bits=0, new_pipeline_edges=0,
        source_arguments=[
            'A75 measured longest LSQ path has local overlap at2.138ns, raw forwarded byte data at2.937ns and endpoint3.282ns. This change addresses that exact selector dependency while A75 performance continues independently. No claimed causal0.799ns saving.',
            'For a power-of-two tree with ascending physical leaves, original choose_left selects its valid left child when right is invalid or left is wrapped and right is not; both valid in the same class select the right child. Inductively the root is highest physical wrapped eligible leaf if any wrapped overlap exists, otherwise highest physical eligible leaf. This holds for any head/eligibility pattern without occupancy or active-row invariants, including explicit slot-width aliases because original row_wrap remains identical.',
            'For each byte, wrapped eligibility and ordinary eligibility are unchanged. A row grant is its wrapped eligibility with no greater wrapped row, OR its ordinary eligibility with no greater eligible row and no wrapped row anywhere. These grants select exactly one original youngest leaf if any is eligible and none otherwise. One-hot masked-OR data is therefore the same selected8bit word, or0 when the original valid tree was0. Forward mask is the identical OR of overlap eligibility.',
            'Every byte retains independent winner selection, original older-store/liveness/address/data/mask guards, line equality, byte-window alignment and final saved-forwarding mux. No load bypasses an unknown older store; no speculative aliasing, request/response/commit policy, port, SRAM/FF state or pipeline edge is introduced.',
            'The exact original forward tournament is retained under parameter0 and for non-power-of-two geometry; original initial geometry validation is unchanged. Option1 only rewrites the combinational selector. No HDL/lint/formal/simulation/synthesis/STA/unit test run. Source proof is manual/inductive, not full formal or dynamic equivalence.',
            'Future complete-batch scope: no/single/multiple overlapping stores with different winner perbyte, wrapped and ordinary classes, highest/lowest rows, unknown data/address, natural aligned byte/half/word loads, held forwarding with older stores departing, reset/recovery/full-tag row reuse, option0/1, widths1/2/4, LSQ powers of two including1, and exact area/Fmax/IPC. Net mapping gain and area remain unknown.'
        ], goal_complete=False)
    write(REVIEW, proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
