"""Prepare load-only AGU-to-LSQ-selection lookthrough; no hardware tests."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
from manage_frozen_baseline_programs import read, sha, write
from review_frequency_dx_sources import blocks

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A12_one_cycle_instruction_lines'
TARGET=BASE/'A13_load_address_lookthrough'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


LOOKTHROUGH='''
    // Only an already allocated load can use its current full-tag-matched
    // AGU update in request selection. Older store hazards continue to use
    // their saved address/data/mask, so unknown stores remain blocking.
    // Selection is still registered: this folds address ownership and
    // selection capture into one edge without a bypass to the D-cache.
    wire [31:0] request_addr [0:LSQ_ENTRIES-1];
    wire request_addr_ready [0:LSQ_ENTRIES-1];
    genvar address_row,address_lane,address_word;
    generate for(address_row=0;address_row<LSQ_ENTRIES;address_row=address_row+1) begin:g_load_address_lookthrough
        if(LOAD_ADDRESS_LOOKTHROUGH!=0 && REQUEST_PIPELINE!=0) begin:g_enabled
            wire [BE_WIDTH-1:0] load_address_matches;
            for(address_lane=0;address_lane<BE_WIDTH;address_lane=address_lane+1) begin:g_match
                assign load_address_matches[address_lane]=!reset_i && !flush_i && !recovery_valid_i &&
                    load_mem[address_row] && !store_mem[address_row] && !addr_ready_mem[address_row] &&
                    addr_update_valid_i[address_lane] &&
                    tag_matches_slot(addr_update_tag_i[address_lane*TAG_WIDTH +: TAG_WIDTH],address_row);
            end
            wire update_present;
            wire [31:0] updated_address;
            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(BE_WIDTH)) update_select (
                .events_i(load_address_matches),.values_i(addr_update_i),.write_o(update_present),.value_o(updated_address));
            wire [1:0] update_views;
            rv32_frequency_control_tree #(.LEAVES(2)) update_tree (
                .signal_i(update_present),.views_o(update_views));
            for(address_word=0;address_word<2;address_word=address_word+1) begin:g_word
                assign request_addr[address_row][address_word*16 +: 16]=update_views[address_word]?
                    updated_address[address_word*16 +: 16]:addr_mem[address_row][address_word*16 +: 16];
            end
            assign request_addr_ready[address_row]=addr_ready_mem[address_row] || update_present;
        end else begin:g_saved_address
            assign request_addr[address_row]=addr_mem[address_row];
            assign request_addr_ready[address_row]=addr_ready_mem[address_row];
        end
    end endgenerate

'''


def main():
    assert not TARGET.exists(),TARGET
    pm=read(PARENT/'candidate.json')
    for name,digest in pm['source_sha256'].items():assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/backend/rv32_lsq.v';old=(PARENT/name).read_text(encoding='utf-8');text=old
    text=once(text,'    parameter integer REQUEST_PIPELINE = 0,',
        '    parameter integer REQUEST_PIPELINE = 0,\n    parameter integer LOAD_ADDRESS_LOOKTHROUGH = 0,')
    text=once(text,'    wire [LSQ_ENTRIES-1:0] request_eligible;',
        LOOKTHROUGH+'    wire [LSQ_ENTRIES-1:0] request_eligible;')
    text=once(text,"{12'b0, access_mask(size_mem[age_slot])} << addr_mem[age_slot][3:0];",
        "{12'b0, access_mask(size_mem[age_slot])} << request_addr[age_slot][3:0];")
    text=once(text,'assign pick_addr[LSQ_ENTRIES+age_slot] = addr_mem[age_slot];',
        'assign pick_addr[LSQ_ENTRIES+age_slot] = request_addr[age_slot];')
    text=once(text,'                       addr_mem[request_slot][31:4]) &&',
        '                       request_addr[request_slot][31:4]) &&')
    text=once(text,'((load_mem[request_slot] && addr_ready_mem[request_slot] &&',
        '((load_mem[request_slot] && request_addr_ready[request_slot] &&')
    assert blocks(text)==blocks(old)
    # Deliberately keep these store/hazard/forwarding paths unchanged.
    for anchor in ('!addr_ready_mem[older_slot] ||',
                   'store_mem[request_slot] && addr_ready_mem[request_slot]',
                   'wire selection_input_fire=(REQUEST_PIPELINE!=0) && !reset_i && !flush_i && !recovery_valid_i &&',
                   '.store_offset_i(addr_mem[age_slot][3:0])',
                   'assign store_line_mask[age_slot] =',
                   'tag[TAG_GEN_LSB +: GENERATION_WIDTH] == generation_mem[tag_slot]'):
        assert anchor in old and anchor in text,anchor
    changes[name]=text
    name='rtl/backend/rv32_backend_joint.v';old=(PARENT/name).read_text(encoding='utf-8');text=old
    text=once(text,'.STORE_ADDRESS_PROBE(EARLY_STORE_ADDRESS == 2), .REQUEST_PIPELINE(1),',
        '.STORE_ADDRESS_PROBE(EARLY_STORE_ADDRESS == 2), .REQUEST_PIPELINE(1), .LOAD_ADDRESS_LOOKTHROUGH(EARLY_LOAD_ADDRESS>=3),')
    assert blocks(text)==blocks(old)
    changes[name]=text
    name='rtl/course/student_top.v';old=(PARENT/name).read_text(encoding='utf-8')
    changes[name]=once(old,'parameter integer EARLY_LOAD_ADDRESS = 2,','parameter integer EARLY_LOAD_ADDRESS = 3,')
    for name in pm['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():(TARGET/name).write_text(text,encoding='utf-8')
    record=dict(pm)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={n:sha(TARGET/n) for n in pm['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)))
    record['parameter_overrides']=dict(pm['parameter_overrides'],EARLY_LOAD_ADDRESS=3)
    record['enabled_profile']=dict(pm['enabled_profile'],EARLY_LOAD_ADDRESS=3,LOAD_ADDRESS_LOOKTHROUGH=1)
    record['implemented_changes']=list(pm['implemented_changes'])+[
        'Fold current full-LSQ-tag-matched AGU load address into the existing registered request selection; keep all older store hazards conservative.'
    ]
    record['material_gain_evidence']=dict(pm['material_gain_evidence'],
        dependent_load_agu_address_to_selection_edges_before=2,
        dependent_load_agu_address_to_selection_edges_after=1,
        load_address_lookthrough_new_state_bits=0,
        load_address_lookthrough_frequency_risk='AGU tag/address selection plus original LSQ eligibility and tournament now share one combinational interval.')
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_PROTOCOL_REVIEW_UNTESTED_NOT_FULL_CORE_PROOF',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),parent_sha256=sha(PARENT/'candidate.json'),
        changed_files=list(changes),new_state_bits=0,source_clocked_blocks_text_equal=True,
        tests_started=False,adopted=False,
        source_argument=[
            'Lookthrough requires valid full LSQ tag and current row generation, load-only classification, address not yet saved, and no reset/flush/recovery.',
            'Later-lane address priority matches the existing address owner updates. Requests for already ready addresses use exactly their saved address.',
            'Only load eligibility, its line mask, its hazard comparison address and tournament address use the effective address.',
            'Older store unknown-address/data hazards, byte masks, forwarding data, commit permission and store selection remain unchanged and conservative.',
            'The selected request is captured in the existing register on the same edge as its matched address update. No direct request-to-cache combinational bypass is added.',
            'Uncompleted address-unready load rows cannot retire/reallocate on that edge; full generation matching and normal selection guards exclude stale/recovery updates.',
            'No LSQ state owner, memory transaction, response generation, retirement or ROB/PRF identity guard is removed.',
            'Default mode or REQUEST_PIPELINE=0 reconnects the original saved-address inputs.',
            'This saves one eligibility/selection edge only for a winning newly addressed load with no older hazard or backpressure. Actual frequency and dynamic IPC remain unmeasured.'
        ])
    write(BASE/'A13_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','new_state_bits','tests_started')})


if __name__=='__main__':main()
