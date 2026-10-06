"""Complete one ready RAM store from its LSQ allocation, with full ROB authority."""
from datetime import datetime,timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import ROOT,read,sha,write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A78_lsq_forward_onehot'
TARGET = BASE/'A79_ready_ram_store_complete'
REVIEW = BASE/'A79_source_review.json'


def once(text,old,new):
    assert text.count(old) == 1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == '26e2af0ad1acef1121dbdcbb2f9f1811c88fc085f81fc1701459cfd4250d113c'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest,name
    audit = ROOT/'build/cpu2026/er1_ready_store_source_opportunity_20261006.json'
    assert sha(audit) == '4bd4c780e22c74ea12251a8a791120e9f47f6618ee828eef6160a9b24ef1cb16'
    terminal = ROOT/'build/cpu2026/er1_a75_complete_result_20261006.json'
    assert sha(terminal) == '3124ca9883c4e769d494d0f345de5c35be5c57a974e50c4d13951556658b44d4'
    changes = {}
    name = 'rtl/backend/rv32_backend_joint.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original,'    parameter integer STORE_ALLOC_EARLY_DATA = 0,',
        '''    parameter integer STORE_ALLOC_EARLY_DATA = 0,
    // One already-ready RAM store may complete from its actual LSQ allocation.
    // The original RS/ALU path remains for other stores and unsupported profiles.
    parameter integer FAST_STORE_COMPLETE = 0,''')
    marker = '    // Count raw D demand before gating either allocator, avoiding an'
    insert = '''    localparam integer FAST_STORE_COMPLETE_ACTIVE=(FAST_STORE_COMPLETE!=0) &&
        (DISPATCH_PIPELINE!=0) && (DISPATCH_ELASTIC!=0) &&
        (STORE_ALLOC_EARLY_ADDRESS!=0) && (EARLY_STORE_ADDRESS!=0) &&
        (STORE_ALLOC_EARLY_DATA!=0) && (ROB_ALLOC_BANKED_WRITE!=0) &&
        (ROB_ENTRIES>=BE_WIDTH) && (LIGHT_RETIRE_PAYLOAD!=0) &&
        (ROB_MMIO_PREDECODE!=0) && (ROB_LEGACY_HALT_PAYLOAD==0) &&
        (ROB_RETURN_VALUE_ENABLE==0);
    wire [BE_WIDTH-1:0] ready_store_candidates,store_without_agu,rob_fast_store_valid;
    generate if(FAST_STORE_COMPLETE_ACTIVE!=0) begin:g_ready_ram_store_complete
        for(genvar ready_store_lane=0;ready_store_lane<BE_WIDTH;ready_store_lane=ready_store_lane+1) begin:g_lane
            wire [31:0] address=lsq_alloc_addr[ready_store_lane*32 +: 32];
            wire [31:0] immediate=d_imm[ready_store_lane*32 +: 32];
            wire [`RV32IM_OP_WIDTH-1:0] op=d_op[ready_store_lane*`RV32IM_OP_WIDTH +: `RV32IM_OP_WIDTH];
            wire [1:0] size=d_mem_size[ready_store_lane*2 +: 2];
            wire ordinary_store=(op==`RV32IM_OP_SB && size==2'd0) ||
                (op==`RV32IM_OP_SH && size==2'd1 && !address[0]) ||
                (op==`RV32IM_OP_SW && size==2'd2 && address[1:0]==2'b00);
            wire canonical_immediate=(STORE_ALLOC_IMM12==0) ||
                immediate[31:12]=={20{immediate[11]}};
            // LSQ already trusts these authoritative address/data values.
            // Exclude MMIO/non-RAM and malformed/misaligned tuples from this
            // optimization; they retain their original execution protocol.
            assign ready_store_candidates[ready_store_lane]=d_valid[ready_store_lane] &&
                d_is_store[ready_store_lane] && !d_is_load[ready_store_lane] &&
                lsq_alloc_addr_valid[ready_store_lane] && lsq_alloc_data_valid[ready_store_lane] &&
                address[31:28]==4'b0000 && ordinary_store && canonical_immediate;
            if(ready_store_lane==0) begin:g_first
                assign store_without_agu[ready_store_lane]=ready_store_candidates[ready_store_lane];
            end else begin:g_later
                assign store_without_agu[ready_store_lane]=ready_store_candidates[ready_store_lane] &&
                    !(|ready_store_candidates[ready_store_lane-1:0]);
            end
            // Only a real atomic D/LSQ allocation may publish completion.
            // Saved D tags remain separate per lane, so ROB identity matching
            // can finish before the late ready/allocation event arrives.
            assign rob_fast_store_valid[ready_store_lane]=!reset_i && !flush_i &&
                !branch_busy_domains[3] && store_without_agu[ready_store_lane] &&
                lsq_alloc_fire[ready_store_lane];
        end
    end else begin:g_original_store_execution
        assign ready_store_candidates={BE_WIDTH{1'b0}};
        assign store_without_agu={BE_WIDTH{1'b0}};
        assign rob_fast_store_valid={BE_WIDTH{1'b0}};
    end endgenerate

'''
    text = once(text,marker,insert+marker)
    text = once(text,'    wire [BE_WIDTH-1:0] d_rs_need=d_valid & ~load_without_agu;',
        '    wire [BE_WIDTH-1:0] d_rs_need=d_valid & ~(load_without_agu | store_without_agu);')
    text = once(text,'.RECLAIM_UNIQUE_DESTINATIONS(ROB_UNIQUE_RECLAIM_COUNT)',
        '.RECLAIM_UNIQUE_DESTINATIONS(ROB_UNIQUE_RECLAIM_COUNT), .FAST_STORE_COMPLETE(FAST_STORE_COMPLETE_ACTIVE)')
    text = once(text,'        .completion_valid_i(rob_completion_valid)',
        '        .fast_store_valid_i(rob_fast_store_valid), .fast_store_tag_i(d_tag),\n        .completion_valid_i(rob_completion_valid)')
    # LSQ authority and all actual completion/wakeup/side effect routing remain
    # original. The only admission change is exact removal of the chosen store
    # from RS demand; original LSQ demand and full-replace proof stay unchanged.
    for marker in ['assign lsq_alloc_valid=d_lsq_need & {BE_WIDTH{d_admit}};',
                   'wire d_replace_credit=(DISPATCH_FULL_REPLACE!=0)',
                   'd_replace_rs_demand<=rs_free_count && d_replace_lsq_demand<=lsq_free_count;',
                   'assign lsq_load_complete_ready = producer_ready[LSQ_SOURCE];']:
        assert marker in text,marker
    changes[name] = text
    name = 'rtl/backend/rv32_rob.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    text = once(original,'    parameter integer ALLOC_BANKED_WRITE = 0,',
        '''    parameter integer ALLOC_BANKED_WRITE = 0,
    // Caller offers at most one already-allocated ordinary RAM store event.
    // Only light local-row command profiles can consume this extra event.
    parameter integer FAST_STORE_COMPLETE = 0,''')
    text = once(text,'    input  wire [BE_WIDTH-1:0]           completion_valid_i,',
        '''    input  wire [BE_WIDTH-1:0]           fast_store_valid_i,
    input  wire [(BE_WIDTH*TAG_WIDTH)-1:0] fast_store_tag_i,
    input  wire [BE_WIDTH-1:0]           completion_valid_i,''')
    text = once(text,'    genvar command_row,command_lane,command_node;',
        '''    localparam integer FAST_STORE_OWNER_ACTIVE=(FAST_STORE_COMPLETE!=0) &&
        (ALLOC_BANKED_WRITE!=0) && (ROB_ENTRIES>=BE_WIDTH) &&
        (LIGHT_RETIRE_PAYLOAD!=0) && (MMIO_PREDECODE!=0) &&
        (LEGACY_HALT_PAYLOAD==0) && (RETURN_VALUE_ENABLE==0);
    localparam integer FAST_STORE_DOMAINS=(ROB_ENTRIES+3)/4;
    wire [FAST_STORE_DOMAINS*BE_WIDTH-1:0] fast_store_valid_views;
    wire [FAST_STORE_DOMAINS*BE_WIDTH*TAG_WIDTH-1:0] fast_store_tag_views;
    generate if(FAST_STORE_OWNER_ACTIVE!=0) begin:g_fast_store_owner_inputs
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH),.LEAVES(FAST_STORE_DOMAINS)) valid_tree (
            .signal_i(fast_store_valid_i),.views_o(fast_store_valid_views));
        rv32_frequency_control_tree #(.WIDTH(BE_WIDTH*TAG_WIDTH),.LEAVES(FAST_STORE_DOMAINS)) tag_tree (
            .signal_i(fast_store_tag_i),.views_o(fast_store_tag_views));
    end else begin:g_no_fast_store_owner_inputs
        assign fast_store_valid_views=0;
        assign fast_store_tag_views=0;
    end endgenerate

    genvar command_row,command_lane,command_node;''')
    text = once(text,'            wire completed=|completion_match;',
        '''            // Full current ROB identity is checked independently per D
            // lane before late allocation-valid qualification. No shortened
            // generation, selected-tag lookup or ordinary CDB ready is used.
            wire [BE_WIDTH-1:0] fast_store_matches;
            for(genvar fast_lane=0;fast_lane<BE_WIDTH;fast_lane=fast_lane+1) begin:g_fast_store_match
                if(FAST_STORE_OWNER_ACTIVE!=0) begin:g_enabled
                    wire [TAG_WIDTH-1:0] tag=
                        fast_store_tag_views[((command_row/4)*BE_WIDTH+fast_lane)*TAG_WIDTH +: TAG_WIDTH];
                    wire target=tag_matches(tag,command_row) && store_mem[command_row] &&
                        !rd_we_mem[command_row] && !branch_mem[command_row] && !halt_mem[command_row];
                    assign fast_store_matches[fast_lane]=normal && target &&
                        fast_store_valid_views[(command_row/4)*BE_WIDTH+fast_lane];
                end else begin:g_disabled
                    assign fast_store_matches[fast_lane]=1'b0;
                end
            end
            wire fast_store_completed=|fast_store_matches;
            wire completed=|completion_match;''')
    text = once(text,'                ready_mem_write_enable[command_row]=row_reset || killed || completed || retire || allocate;',
        '                ready_mem_write_enable[command_row]=row_reset || killed || completed || fast_store_completed || retire || allocate;')
    text = once(text,'                ready_mem_write_data[command_row]=!row_reset && !allocate && !retire && completed;',
        '                ready_mem_write_data[command_row]=!row_reset && !allocate && !retire && (completed || fast_store_completed);')
    text = once(text,'                mmio_word_mem_write_enable[command_row]=(MMIO_PREDECODE!=0) && completed;\n                mmio_word_mem_write_data[command_row]=completed_mmio;',
        '''                mmio_word_mem_write_enable[command_row]=(MMIO_PREDECODE!=0) && (completed || fast_store_completed);
                // The extra event is exclusively ordinary RAM. Original CDB
                // data wins if a caller offers both events for the same tag.
                mmio_word_mem_write_data[command_row]=completed ? completed_mmio : 1'b0;''')
    # Existing metadata/side-effect/retirement/payload state owners and the
    # whole legacy writer remain unchanged. Normal CDB errors and store ack
    # retain their priority. Fast events are suppressed throughout recovery.
    tail = '    end else begin:g_legacy_field_commands'
    assert text[text.index(tail):] == original[original.index(tail):]
    for marker in ['assign completion_match[command_lane]=!row_reset && c_valid && c_done &&',
                   'tag_matches(c_tag,command_row) && (!row_recovery || row_age<=row_branch_age);',
                   'store_wait_mem_write_data[command_row]=!row_reset && !allocate && !retire && acknowledged;',
                   'store_sent_mem_write_data[command_row]=!row_reset && !allocate && !retire && sent;',
                   'error_mem_write_enable[command_row]=row_reset || allocate ||',
                   'generation_mem_write_enable[command_row]=row_reset || allocate;']:
        assert marker in text,marker
    changes[name] = text
    for name in ['rtl/cpu_core.v','rtl/course/student_top.v']:
        text = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        old = '    parameter integer STORE_ALLOC_EARLY_DATA = '+str(default)+','
        text = once(text,old,old+'\n    parameter integer FAST_STORE_COMPLETE = '+str(default)+',')
        text = once(text,'.STORE_ALLOC_EARLY_DATA(STORE_ALLOC_EARLY_DATA)',
            '.STORE_ALLOC_EARLY_DATA(STORE_ALLOC_EARLY_DATA), .FAST_STORE_COMPLETE(FAST_STORE_COMPLETE)')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_READY_RAM_STORE_COMPLETE_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],FAST_STORE_COMPLETE=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],FAST_STORE_COMPLETE=1,
        ready_ram_store_completion_events_per_cycle=1,fast_store_full_rob_generation_bits=8,
        fast_store_new_ff_bits=0,fast_store_new_sram_bits=0,fast_store_new_prf_ports=0,
        fast_store_normal_allocation_to_ready_edges_removed_if_unstalled=2,
        fast_store_mmio_uses_original_execution=True)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'At most one lowest eligible D-lane ordinary RAM SB/SH/SW with authoritative ready LSQ allocation address/data, matching size/alignment and canonical immediate, skips redundant RS/ALU execution. Only actual LSQ alloc_fire publishes a dedicated store-ready event. ROB performs full current valid/slot/8GEN and store/non-rd/non-branch/non-halt checks per saved lane before late valid, setting ready and MMIO=false. All LSQ capture, atomic admission, store commit/admission/request/ack/recovery and physical/CDB write rules remain original. Unsupported/default profiles and all other stores retain RS/ALU.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        source_opportunity_proof=str(audit),source_opportunity_proof_sha256=sha(audit),
        measured_a75_complete_proof=str(terminal),measured_a75_complete_proof_sha256=sha(terminal),
        ready_ram_store_limit='Removes two unstalled execution-to-ROB-ready edges for one eligible store; no predicted program cycles or IPC gain. ROB head/cache/ack/source readiness can hide benefit. New D address/readiness to RS admission and dedicated ready metadata paths, tag-match and priority gate area require later measurement. A76-A79 metrics all unknown.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),
        tests_started=False,adopted=False,added_declared_ff_bits=0,new_sram_bits=0,new_prf_ports=0,
        logical_fast_store_completion_events_per_cycle=1,new_pipeline_edges=0,
        source_arguments=[
            'Course enabled profile has saved elastic D, original early authoritative address/data, banked local ROB writes, light retirement, MMIO predecode and omitted legacy/value payloads. Fast path requires exactly this full profile; option0 and any unsupported profile produce zero candidates/events and retain original RS/ALU. ROB has matching constant-profile activation, and its legacy command writer/state owners are byte-identical.',
            'A candidate must be valid D store, not load, with both original LSQ alloc_addr_valid and alloc_data_valid, recognized SB/SH/SW matching mem_size and natural alignment, RAM upper address nibble0 and canonical sign-extended12 immediate when that address implementation is used. At most the lowest candidate lane is selected; all later stores use ordinary RS. No load/branch/MDU tuple, MMIO or unknown source is relaxed.',
            'Exactly that selected store is removed from RS demand before original atomic D readiness calculation; LSQ demand is unchanged. The same store produces ROB fast-valid only with actual LSQ alloc_fire and no reset/flush/branch busy. Therefore waiting or unallocated stores cannot be marked done, allocated chosen stores cannot execute twice, and a D packet is still consumed only through original admission. Original conservative full-replace credit counts all lanes and still implies the weaker RS demand, so no credit-to-PRF/alloc combinational loop is introduced.',
            'D owns a previously allocated ROB tag. ROB checks current valid, exact row and all8 generation bits using original tag_matches, plus stored store/non-rd/non-branch/non-halt fields. Each saved lane identity is compared before the late selected allocation-valid bit, avoiding a selected-tag serial query. Wrong generation/invalid/non-store identities cannot mutate ready. Recovery normal=0 suppresses fast event; simultaneous fresh redirect can only make a younger store ready before the next recovery kills it, never authorize an out-of-order side effect.',
            'ROB changes only ready and MMIO=false for an accepted RAM event. Original reset/new allocation/retirement dominance remains; original ordinary completion MMIO data wins if both event types target the same row. Error, generation, RAT/PRF, value, branch, checkpoint, store_wait/sent and all actual commit/admission/ack rules are unchanged. LSQ remains the sole authoritative address/data owner and cannot send a speculative store before original ROB ordered authorization.',
            'Current course profile omits the generic value/address/mask/data retirement owners, so fast ready need not duplicate payload. MMIO and non-RAM stores retain original ALU/full-mask terminal handling. No FF/SRAM, PRF write port, CDB payload lane, result buffer, architectural instruction restriction or parameter removal is added. Extra combinational tag and eligibility routing cost remains unknown.',
            'Ideal unstalled allocation-to-ROB-ready reduces from D->RS edge, RS->ALU edge, ALU->completion/ROB edge to D/LSQ capture and ready on the same edge: two edges, not two guaranteed benchmark cycles. Ready-store coverage/ROB-head/cache/ack waits can mask gain. A75 only saved33 qsort cycles with prior credit/reclaim changes; this is a new structural opportunity, not measured evidence of IPC1.1.',
            'Manual source/ownership/priority review only; no HDL/lint/formal/simulation/synthesis/STA/unit run. Future batch coverage: accepted/stalled/dual ready stores, noncontiguous surviving D lanes, zero/forwarded data, load/store mixes, one chosen and ordinary later store, opcode/size/imm/alignment exclusions, MMIO exits, full LSQ/RS/ROB, fresh redirect/apply/flush/reset, stale tag/GEN/reuse and complete+allocation/retire priority, bytes/halves/words, parameter widths1/2/4 and all default/fallback profiles. Full RV32IM and required correctness remain unproven.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
