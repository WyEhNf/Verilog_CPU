"""Prepare gshare with compact targets, bank-parallel indexed training, early history repair."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE / 'A39_recovery_preview_older_issue'
TARGET = BASE / 'A40_compact_gshare_parallel_feedback'
PROFILE = Path('F:/CPU2026Proofs/ER1_A36_three_case_profile_20261005/result.json')


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists()
    parent = read(PARENT / 'candidate.json')
    for name, digest in parent['source_sha256'].items():
        assert sha(PARENT / name) == digest, name
    profile = read(PROFILE)
    assert profile['status'] == 'THREE_CASE_HOST_PROFILE_COMPLETE'
    changes = {}

    name = 'rtl/predictor/rv32_branch_predictor.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer COMPACT_INDIRECT_BTB = 0,',
                '    parameter integer COMPACT_INDIRECT_BTB = 0,\n    parameter integer COMPACT_BTB_ENTRIES = 64,')
    text = once(text, '''    localparam integer BTB_ENTRIES = 64 >> BANK_BITS;
    localparam integer BTB_COMPACT_ACTIVE=(COMPACT_INDIRECT_BTB!=0) && (DIRECT_BRANCH_TARGET==1);''',
                '''    localparam integer BTB_COMPACT_ACTIVE=(COMPACT_INDIRECT_BTB!=0) && (DIRECT_BRANCH_TARGET!=0);
    localparam integer BTB_TOTAL_ENTRIES=BTB_COMPACT_ACTIVE?COMPACT_BTB_ENTRIES:64;
    localparam integer BTB_ENTRIES=BTB_TOTAL_ENTRIES >> BANK_BITS;
    localparam integer BTB_TOTAL_INDEX_WIDTH=$clog2(BTB_TOTAL_ENTRIES);
    initial begin
        if(COMPACT_BTB_ENTRIES!=16 && COMPACT_BTB_ENTRIES!=32 && COMPACT_BTB_ENTRIES!=64)
            $fatal(1,"Compact BTB entries must be16/32/64");
    end''')
    text = once(text, '''        begin folded_btb_tag=pc[15:8] ^ pc[23:16] ^ pc[31:24];end''',
                '''        reg [31:0] identity;
        begin
            // Fold every PC bit above the chosen index. At64 entries this
            // reduces exactly to the original three-byte folded identity.
            identity=pc >> (BTB_TOTAL_INDEX_WIDTH+2);
            folded_btb_tag=identity[7:0] ^ identity[15:8] ^
                identity[23:16] ^ identity[31:24];
        end''')
    text = once(text, '    localparam integer BTB_INDEX_WIDTH=6-BANK_BITS;',
                '    localparam integer BTB_INDEX_WIDTH=BTB_TOTAL_INDEX_WIDTH-BANK_BITS;')
    text = once(text, '    wire [5-BANK_BITS:0] query_btb_index = query_pc_i[7:2+BANK_BITS];',
                '    wire [BTB_INDEX_WIDTH-1:0] query_btb_index = query_pc_i[2+BANK_BITS +: BTB_INDEX_WIDTH];')
    text = once(text, '    wire [5-BANK_BITS:0] feedback_btb_index = feedback_pc_i[7:2+BANK_BITS];',
                '    wire [BTB_INDEX_WIDTH-1:0] feedback_btb_index = feedback_pc_i[2+BANK_BITS +: BTB_INDEX_WIDTH];')
    changes[name] = text

    name = 'rtl/predictor/rv32_banked_predictor.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer COMPACT_INDIRECT_BTB = 0,',
                '    parameter integer COMPACT_INDIRECT_BTB = 0,\n    parameter integer COMPACT_BTB_ENTRIES = 64,')
    text = once(text, '    input wire [FEEDBACK_LANES*100-1:0] feedback_lane_packets_i,',
                '    input wire [FEEDBACK_LANES*100-1:0] feedback_lane_packets_i,\n    input wire [FEEDBACK_LANES*16-1:0] feedback_lane_metadata_i,')
    text = once(text, 'localparam integer MULTI_ACTIVE=(MULTI_FEEDBACK!=0) && (DIRECT_BRANCH_TARGET==1);',
                'localparam integer MULTI_ACTIVE=(MULTI_FEEDBACK!=0) && (DIRECT_BRANCH_TARGET!=0);')
    text = once(text, '                wire [99:0] packet;',
                '                wire [107:0] packet;\n                wire [FEEDBACK_LANES*108-1:0] packets;')
    text = once(text, '                    wire [31:0] lane_pc=feedback_lane_packets_i[feedback_lane*100+68 +: 32];',
                '''                    wire [31:0] lane_pc=feedback_lane_packets_i[feedback_lane*100+68 +: 32];
                    // This exact prediction-time index belongs to this lane,
                    // including when two branches resolve in distinct banks.
                    // Mode1 never consumes it and retains PC-indexed training.
                    assign packets[feedback_lane*108 +: 108]={
                        feedback_lane_metadata_i[feedback_lane*16 +: 8],
                        feedback_lane_packets_i[feedback_lane*100 +: 100]};''')
    text = once(text, '''                rv32_frequency_event_select #(.WIDTH(100),.EVENTS(FEEDBACK_LANES),.PRIORITY(0)) feedback_selector (
                    .events_i(grants),.values_i(feedback_lane_packets_i),
                    .write_o(update_valid),.value_o(packet));
                assign {update_pc,update_kind,update_taken,update_target,
                    update_pred_taken,update_pred_target}=packet;
                assign update_training_index=8'b0;''',
                '''                rv32_frequency_event_select #(.WIDTH(108),.EVENTS(FEEDBACK_LANES),.PRIORITY(0)) feedback_selector (
                    .events_i(grants),.values_i(packets),
                    .write_o(update_valid),.value_o(packet));
                assign {update_training_index,update_pc,update_kind,update_taken,update_target,
                    update_pred_taken,update_pred_target}=packet;''')
    text = once(text, '.HISTORY_BITS(HISTORY_BITS), .COMPACT_INDIRECT_BTB(COMPACT_INDIRECT_BTB)) predictor (',
                '.HISTORY_BITS(HISTORY_BITS), .COMPACT_INDIRECT_BTB(COMPACT_INDIRECT_BTB), .COMPACT_BTB_ENTRIES(COMPACT_BTB_ENTRIES)) predictor (')
    changes[name] = text

    name = 'rtl/backend/rv32_backend_joint.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    output wire [BE_WIDTH*100-1:0]      branch_feedback_lane_packets_o,',
                '    output wire [BE_WIDTH*100-1:0]      branch_feedback_lane_packets_o,\n    output wire [BE_WIDTH*16-1:0]       branch_feedback_lane_metadata_o,')
    text = once(text, 'generate if(EARLY_FRONT_REDIRECT!=0 && PREDICTOR_META==0) begin:g_early_front_redirect',
                'generate if(EARLY_FRONT_REDIRECT!=0) begin:g_early_front_redirect')
    text = once(text, '''            assign branch_feedback_lane_packets_o[feedback_source*100 +: 100]={
                pc,kind,alu_exec_branch_taken[feedback_source],
                alu_exec_branch_target[feedback_source*32 +: 32],pred_taken,full_pred_target};''',
                '''            assign branch_feedback_lane_packets_o[feedback_source*100 +: 100]={
                pc,kind,alu_exec_branch_taken[feedback_source],
                alu_exec_branch_target[feedback_source*32 +: 32],pred_taken,full_pred_target};
            if(PREDICTOR_META!=0) begin:g_indexed_training
                wire [ROB_ENTRIES*16-1:0] rows;
                for(genvar history_row=0;history_row<ROB_ENTRIES;history_row=history_row+1) begin:g_row
                    assign rows[history_row*16 +: 16]=rob_pred_metadata_mem[history_row];
                end
                rv32_frequency_array_read #(.WIDTH(16),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(ROB_SLOT_WIDTH)) history_read (
                    .rows_i(rows),.index_i(slot),
                    .value_o(branch_feedback_lane_metadata_o[feedback_source*16 +: 16]));
            end else begin:g_pc_indexed_training
                assign branch_feedback_lane_metadata_o[feedback_source*16 +: 16]=0;
            end''')
    text = once(text, '''        wire [7:0] history_next;
        for(capture_lane=0;capture_lane<BE_WIDTH;capture_lane=capture_lane+1) begin:g_lane''',
                '''        wire [7:0] history_next,history_saved;
        for(capture_lane=0;capture_lane<BE_WIDTH;capture_lane=capture_lane+1) begin:g_lane''')
    text = once(text, '''        rv32_frequency_word_bank #(.WIDTH(8)) history_owner (
            .clk_i(clk_i),.write_i(history_write),.data_i(history_next),.data_o(branch_recovery_history_o));''',
                '''        rv32_frequency_word_bank #(.WIDTH(8)) history_owner (
            .clk_i(clk_i),.write_i(history_write),.data_i(history_next),.data_o(history_saved));
        // Early redirect and GHR repair must use the same accepted branch on
        // the same edge. Waiting for history_saved adds a fetch bubble or
        // restores a previous branch's checkpoint. Preview mode uses saved.
        assign branch_recovery_history_o=(EARLY_FRONT_REDIRECT!=0 && branch_capture_write)?
            history_next:history_saved;''')
    changes[name] = text

    name = 'rtl/cpu_core.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_COMPACT_BTB = 0,',
                '    parameter integer PREDICTOR_COMPACT_BTB = 0,\n    parameter integer PREDICTOR_COMPACT_BTB_ENTRIES = 64,')
    text = once(text, '(SERIAL_BACKEND==0) && (PREDICTOR_DIRECT_BRANCH_TARGET==1);',
                '(SERIAL_BACKEND==0) && (PREDICTOR_DIRECT_BRANCH_TARGET!=0);')
    text = once(text, '    wire [BE_WIDTH*100-1:0] branch_feedback_lane_packets;',
                '    wire [BE_WIDTH*100-1:0] branch_feedback_lane_packets;\n    wire [BE_WIDTH*16-1:0] branch_feedback_lane_metadata;')
    text = once(text, '.COMPACT_INDIRECT_BTB(PREDICTOR_COMPACT_BTB), .HISTORY_BITS(PREDICTOR_HISTORY_BITS)',
                '.COMPACT_INDIRECT_BTB(PREDICTOR_COMPACT_BTB), .COMPACT_BTB_ENTRIES(PREDICTOR_COMPACT_BTB_ENTRIES), .HISTORY_BITS(PREDICTOR_HISTORY_BITS)')
    text = once(text, '.feedback_lane_packets_i(branch_feedback_lane_packets),',
                '.feedback_lane_packets_i(branch_feedback_lane_packets),\n                .feedback_lane_metadata_i(branch_feedback_lane_metadata),')
    text = once(text, '    assign branch_feedback_lane_packets=0;',
                '    assign branch_feedback_lane_packets=0;\n    assign branch_feedback_lane_metadata=0;')
    text = once(text, '.branch_feedback_lane_packets_o(branch_feedback_lane_packets),',
                '.branch_feedback_lane_packets_o(branch_feedback_lane_packets),\n         .branch_feedback_lane_metadata_o(branch_feedback_lane_metadata),')
    changes[name] = text

    name = 'rtl/course/student_top.v'
    text = (PARENT / name).read_text(encoding='utf-8')
    text = once(text, '    parameter integer PREDICTOR_DIRECT_BRANCH_TARGET = 1,',
                '    parameter integer PREDICTOR_DIRECT_BRANCH_TARGET = 2,')
    text = once(text, '    parameter integer PREDICTOR_COMPACT_BTB = 1,',
                '    parameter integer PREDICTOR_COMPACT_BTB = 1,\n    parameter integer PREDICTOR_COMPACT_BTB_ENTRIES = 32,')
    text = once(text, '.PREDICTOR_COMPACT_BTB(PREDICTOR_COMPACT_BTB),',
                '.PREDICTOR_COMPACT_BTB(PREDICTOR_COMPACT_BTB), .PREDICTOR_COMPACT_BTB_ENTRIES(PREDICTOR_COMPACT_BTB_ENTRIES),')
    changes[name] = text

    # No changes to speculative history generation, metadata checkpoint layout,
    # FQ acceptance or branch recovery descriptor/ROB lifetime authority.
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
    record['parameter_overrides'] = dict(parent['parameter_overrides'],
        PREDICTOR_DIRECT_BRANCH_TARGET=2, PREDICTOR_COMPACT_BTB_ENTRIES=32)
    record['enabled_profile'] = dict(parent['enabled_profile'], compact_gshare=True,
        indexed_bank_parallel_training=True, same_edge_early_history_repair=True,
        compact_btb_entries=32, gshare_bht_entries=256, speculative_history_bits=6)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Retain compact frontend/dispatch/RS JALR target and indirect BTB representation in gshare mode2. Export each accepted branch lane prediction-time ROB metadata for bank-parallel training instead of forcing zero gshare indices.',
        'Repair speculative GHR with the selected branch checkpoint and actual conditional outcome on the same edge as early frontend redirect; original registered history remains available for preview redirect mode.',
        'Parameterize compact indirect-only BTB16/32/64. This profile uses32 rows; reduce1280 payload+valid state bits without reducing BHT256 or GHR6. Full legacy BTB remains64 and all table aliases are checked by original full actual-target recovery.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        a36_three_case_profile_sha256=sha(PROFILE),
        direction_predictor_gain_unmeasured=True,
        compact_btb_removed_ff_bits=1280,
        gshare_metadata_bits_per_instruction_effective=12,
        gshare_metadata_instruction_owners={'frontend_queue': 16, 'decode_queue_rows': 4, 'rob_rows': 32},
        gshare_nominal_effective_metadata_ff_bits=624,
        gshare_history_register_ff_bits=6,
        gshare_registered_recovery_history_effective_ff_bits=6,
        gshare_declared_metadata_and_history_upper_bound_bits=848,
        ff_component_unpruned_delta_bits=-432,
        ff_component_nominal_delta_bits=-644,
        ff_component_nominal_delta_um2=-644*0.2916,
        mapped_area_and_ipc_and_timing_unmeasured=True)
    write(TARGET / 'candidate.json', record)
    proof = dict(status='SOURCE_COMPACT_GSHARE_PARALLEL_FEEDBACK_UNTESTED', candidate=str(TARGET),
        candidate_sha256=sha(TARGET / 'candidate.json'), changed_files=list(changes),
        compact_btb_removed_state_bits=1280, bht_capacity_unchanged=256, history_bits=6,
        new_pipeline_edges=0, tests_started=False, adopted=False,
        source_arguments=[
            'Observed A36 accepted predictor feedback correctness: median2629/3183, qsort36196/46059, towers302/391. They are bank-selected branch/JAL/JALR feedback, not an isolated conditional-direction accuracy; gshare gain remains unmeasured.',
            'Existing mode2 preserves speculative pre-bundle query history, exact saved query index, per-instruction history checkpoint, accepted-prefix advancement and full-generation accepted branch recovery. A40 retains those equations and checkpoint layout.',
            'Every bank still accepts at most one feedback packet. Lowest lane wins a same-bank conflict; different banks can train in parallel. The eight-bit training index is selected from the same full-generation accepted lane as its PC/kind/taken/target packet, never recomputed from current GHR or borrowed from another lane.',
            'Mode2 indirect BTB writes are already JALR-only, identical to mode1; direct conditional/JAL targets remain exact PC+decoded immediate. Therefore the compact39-bit payload (hash8,target31) is valid in both modes. A hash alias or reduced capacity changes only prediction and original full actual-target comparison forces recovery.',
            'Compact target page qualification remains the original logic: only same-page JALR keeps taken metadata and low12 target, while out-of-page JALR is forced to recover. Direct conditional/JAL target equality uses original exact actual target. No architectural target is shortened.',
            'At an early redirect, recovery history must use combinational history_next selected by the same branch_capture_grant as the redirect. Its conditional form appends actual direction to the saved pre-instruction checkpoint; JAL/JALR preserve that checkpoint. Preview mode uses the original captured history. No extra fetch recovery edge is introduced.',
            'Compact BTB index width follows entries per bank. Identity folds all remaining PC bits including bit7 at32 entries, preventing omission of the newly unindexed bit. At64 entries the fold equals the parent three-byte fold exactly. Legacy full BTB stays64.',
            'With FE4/BE2/FQ16/decodeCAPACITY4/ROB32, effective gshare metadata is six history bits and six training-row bits:624 data bits for FQ, decode and ROB, plus GHR6 and captured recovery history6. No metadata is added to dispatch, RS, ALU or MDU payload owners. Removing32 compact BTB rows deletes1280 state bits; nominal FF component delta is-644bits/-187.79um2. Even counting all declared16-bit metadata and8-bit history owners gives848 added bits and432 fewer state bits overall. This is structural accounting, not a mapped area prediction: metadata readers, XORs, control buffers and synthesis pruning must be measured.',
            'A36 primary frontend already chains response/new request on the same edge. This candidate does not claim request chaining as new performance work.',
            'No HDL/lint/simulation/synthesis/STA/unit tests. Meaningful later coverage includes multiple branches in one bundle, exact prediction-time feedback index after GHR changes, same-bank conflict, different-bank concurrent feedback, early/preview redirect history repair, ROB wrap/generation, compact indirect aliases/pages, RAS override and optional parameter fallbacks.'
        ])
    write(BASE / 'A40_source_review.json', proof)
    print({k: proof[k] for k in ('status', 'candidate', 'candidate_sha256', 'compact_btb_removed_state_bits', 'tests_started')})


if __name__ == '__main__':
    main()
