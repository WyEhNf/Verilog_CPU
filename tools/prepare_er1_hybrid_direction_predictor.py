"""Prepare exact prediction-time bimodal/gshare choice in the existing metadata."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A44_frontend_local_response_pc'
TARGET=BASE/'A45_hybrid_direction_predictor'
REFERENCE='https://ftp.zx.net.nz/pub/archive/ftp.digital.com/pub/compaq/WRL/research-reports/WRL-TN-36.pdf'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/predictor/rv32_branch_predictor.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer HISTORY_BITS = 6',
        '    parameter integer HYBRID_DIRECTION = 0,\n    parameter integer HISTORY_BITS = 6')
    text=once(text,'    output wire [1:0]  pred_counter_o,',
        '    output wire [1:0]  pred_counter_o,\n    output wire [1:0]  pred_component_directions_o,')
    text=once(text,'    input  wire [7:0]  feedback_training_index_i,',
        '    input  wire [7:0]  feedback_training_index_i,\n    input  wire [1:0]  feedback_component_directions_i,')
    text=once(text,'    localparam integer BHT_ENTRIES = 256 >> BANK_BITS;',
        '''    localparam integer BHT_ENTRIES = 256 >> BANK_BITS;
    // Two high metadata bits are available only with <=6 history bits.
    // Other modes retain the original predictor and full history encoding.
    localparam integer HYBRID_ACTIVE=(HYBRID_DIRECTION!=0) &&
        (DIRECT_BRANCH_TARGET==2) && (HISTORY_BITS<=6);''')
    text=once(text,'    assign pred_counter_o = query_bht_word[1:0];', '''    wire [2:0] query_bimodal_word;
    wire [1:0] query_choice;
    wire global_direction=query_bht_word[2]?query_bht_word[1]:branch_imm[31];
    wire bimodal_direction=query_bimodal_word[2]?query_bimodal_word[1]:branch_imm[31];
    wire hybrid_direction=query_choice[1]?global_direction:bimodal_direction;
    assign pred_component_directions_o=(HYBRID_ACTIVE && query_valid_i &&
        query_opcode==7'b1100011)?{global_direction,bimodal_direction}:2'b00;
    assign pred_counter_o=(HYBRID_ACTIVE && !query_choice[1])?
        query_bimodal_word[1:0]:query_bht_word[1:0];
    generate if(HYBRID_ACTIVE) begin:g_hybrid_direction
        localparam integer CHOICE_ENTRIES=64>>BANK_BITS;
        localparam integer CHOICE_INDEX_WIDTH=6-BANK_BITS;
        localparam integer CHOICE_DOMAINS=(CHOICE_ENTRIES+3)/4;
        wire [BHT_ENTRIES*3-1:0] bimodal_rows;
        wire [CHOICE_ENTRIES*2-1:0] choice_rows;
        wire [BHT_ENTRIES+CHOICE_ENTRIES-1:0] hybrid_reset_views;
        wire [BHT_DOMAINS*BHT_INDEX_WIDTH-1:0] bimodal_write_queries;
        wire [BHT_DOMAINS-1:0] bimodal_write_events,bimodal_directions;
        wire [CHOICE_DOMAINS*CHOICE_INDEX_WIDTH-1:0] choice_write_queries;
        wire [CHOICE_DOMAINS-1:0] choice_write_events,choice_global_correct;
        wire conditional_feedback=feedback_valid_i && feedback_kind_i==`RV32IM_PRED_BRANCH;
        wire choice_adjust=conditional_feedback &&
            (feedback_component_directions_i[1]!=feedback_component_directions_i[0]);
        wire global_correct=feedback_taken_i==feedback_component_directions_i[1];
        rv32_frequency_control_tree #(.LEAVES(BHT_ENTRIES+CHOICE_ENTRIES)) hybrid_reset_tree (
            .signal_i(reset_i),.views_o(hybrid_reset_views));
        rv32_frequency_control_tree #(.WIDTH(BHT_INDEX_WIDTH),.LEAVES(BHT_DOMAINS)) bimodal_address_tree (
            .signal_i(feedback_pc_i[9:2+BANK_BITS]),.views_o(bimodal_write_queries));
        rv32_frequency_control_tree #(.LEAVES(BHT_DOMAINS)) bimodal_event_tree (
            .signal_i(conditional_feedback),.views_o(bimodal_write_events));
        rv32_frequency_control_tree #(.LEAVES(BHT_DOMAINS)) bimodal_direction_tree (
            .signal_i(feedback_taken_i),.views_o(bimodal_directions));
        rv32_frequency_control_tree #(.WIDTH(CHOICE_INDEX_WIDTH),.LEAVES(CHOICE_DOMAINS)) choice_address_tree (
            .signal_i(feedback_pc_i[7:2+BANK_BITS]),.views_o(choice_write_queries));
        rv32_frequency_control_tree #(.LEAVES(CHOICE_DOMAINS)) choice_event_tree (
            .signal_i(choice_adjust),.views_o(choice_write_events));
        rv32_frequency_control_tree #(.LEAVES(CHOICE_DOMAINS)) choice_direction_tree (
            .signal_i(global_correct),.views_o(choice_global_correct));
        for(genvar bimodal_row=0;bimodal_row<BHT_ENTRIES;bimodal_row=bimodal_row+1) begin:g_bimodal_owner
            localparam integer DOMAIN=bimodal_row/4;
            wire [1:0] counter;
            wire trained;
            wire update=bimodal_write_events[DOMAIN] &&
                bimodal_write_queries[DOMAIN*BHT_INDEX_WIDTH +: BHT_INDEX_WIDTH]==bimodal_row;
            rv32_predictor_bht_row row (
                .clk_i(clk_i),.reset_i(hybrid_reset_views[bimodal_row]),.update_i(update),
                .taken_i(bimodal_directions[DOMAIN]),.counter_o(counter),.trained_o(trained));
            assign bimodal_rows[bimodal_row*3 +: 3]={trained,counter};
        end
        for(genvar choice_row=0;choice_row<CHOICE_ENTRIES;choice_row=choice_row+1) begin:g_choice_owner
            localparam integer DOMAIN=choice_row/4;
            wire update=choice_write_events[DOMAIN] &&
                choice_write_queries[DOMAIN*CHOICE_INDEX_WIDTH +: CHOICE_INDEX_WIDTH]==choice_row;
            rv32_predictor_choice_row row (
                .clk_i(clk_i),.reset_i(hybrid_reset_views[BHT_ENTRIES+choice_row]),
                .update_i(update),.global_correct_i(choice_global_correct[DOMAIN]),
                .counter_o(choice_rows[choice_row*2 +: 2]));
        end
        // All three tables query in parallel. Choice is a final direction mux,
        // never an extra serialized index lookup before either direction table.
        rv32_frequency_array_read #(.WIDTH(3),.ENTRIES(BHT_ENTRIES),.INDEX_WIDTH(BHT_INDEX_WIDTH)) bimodal_query (
            .rows_i(bimodal_rows),.index_i(query_pc_i[9:2+BANK_BITS]),.value_o(query_bimodal_word));
        rv32_frequency_array_read #(.WIDTH(2),.ENTRIES(CHOICE_ENTRIES),.INDEX_WIDTH(CHOICE_INDEX_WIDTH)) choice_query (
            .rows_i(choice_rows),.index_i(query_pc_i[7:2+BANK_BITS]),.value_o(query_choice));
    end else begin:g_no_hybrid_direction
        assign query_bimodal_word=3'b000;
        assign query_choice=2'b10;
    end endgenerate''')
    text=once(text,'                        if (query_bht_word[2] ? query_bht_word[1] : branch_imm[31]) begin',
        '                        if (HYBRID_ACTIVE ? hybrid_direction : global_direction) begin')
    target_marker='    wire [3:0] target_classes;'
    assert text[text.index(target_marker):]==original[original.index(target_marker):]
    bht_marker='        for(predictor_row=0;predictor_row<BHT_ENTRIES;predictor_row=predictor_row+1) begin:g_bht_owner'
    btb_marker='        for(predictor_row=0;predictor_row<BTB_ENTRIES;predictor_row=predictor_row+1) begin:g_btb_owner'
    assert text[text.index(bht_marker):text.index(btb_marker)]==original[original.index(bht_marker):original.index(btb_marker)]
    text+='''
// Preference saturates toward the predictor that was actually right at fetch.
// With equal predictions, the parent never updates this row. Cold preference
// is weakly bimodal; both direction tables still learn every accepted branch.
module rv32_predictor_choice_row (
    input wire clk_i,reset_i,update_i,global_correct_i,
    output reg [1:0] counter_o
);
    always @(posedge clk_i) begin
        if(reset_i) counter_o<=2'b01;
        else if(update_i) begin
            if(global_correct_i) begin
                if(counter_o!=2'b11) counter_o<=counter_o+2'b01;
            end else if(counter_o!=2'b00) counter_o<=counter_o-2'b01;
        end
    end
endmodule
'''
    changes[name]=text

    name='rtl/predictor/rv32_banked_predictor.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer HISTORY_BITS = 6',
        '    parameter integer HYBRID_DIRECTION = 0,\n    parameter integer HISTORY_BITS = 6')
    text=once(text,'    localparam integer MULTI_ACTIVE=(MULTI_FEEDBACK!=0) && (DIRECT_BRANCH_TARGET!=0);',
        '''    localparam integer MULTI_ACTIVE=(MULTI_FEEDBACK!=0) && (DIRECT_BRANCH_TARGET!=0);
    localparam integer HYBRID_ACTIVE=(HYBRID_DIRECTION!=0) &&
        (DIRECT_BRANCH_TARGET==2) && (HISTORY_BITS<=6);''')
    text=once(text,'    wire [FE_WIDTH*38-1:0] bank_query_packets;',
        '''    wire [FE_WIDTH*40-1:0] bank_query_packets;
    wire [FE_WIDTH*2-1:0] bank_component_directions,lane_component_directions;''')
    text=once(text,'            wire [7:0] update_training_index;',
        '            wire [7:0] update_training_index;\n            wire [1:0] update_component_directions;')
    text=once(text,'                wire [107:0] packet;', '                wire [109:0] packet;')
    text=once(text,'                wire [FEEDBACK_LANES*108-1:0] packets;',
        '                wire [FEEDBACK_LANES*110-1:0] packets;')
    text=once(text,'''                    assign packets[feedback_lane*108 +: 108]={
                        feedback_lane_metadata_i[feedback_lane*16 +: 8],''',
        '''                    assign packets[feedback_lane*110 +: 110]={
                        ((HYBRID_ACTIVE!=0)?feedback_lane_metadata_i[feedback_lane*16+14 +: 2]:2'b00),
                        feedback_lane_metadata_i[feedback_lane*16 +: 8],''')
    text=once(text,'rv32_frequency_event_select #(.WIDTH(108),.EVENTS(FEEDBACK_LANES),.PRIORITY(0)) feedback_selector',
        'rv32_frequency_event_select #(.WIDTH(110),.EVENTS(FEEDBACK_LANES),.PRIORITY(0)) feedback_selector')
    text=once(text,'                assign {update_training_index,update_pc,update_kind,update_taken,update_target,',
        '                assign {update_component_directions,update_training_index,update_pc,update_kind,update_taken,update_target,')
    text=once(text,'                assign update_training_index=feedback_metadata_i[7:0];',
        '''                assign update_training_index=feedback_metadata_i[7:0];
                assign update_component_directions=(HYBRID_ACTIVE!=0)?feedback_metadata_i[15:14]:2'b00;''')
    text=once(text,'            assign bank_query_packets[bank*38 +: 38]={bank_taken[bank],bank_hit[bank],',
        '''            assign bank_query_packets[bank*40 +: 40]={bank_component_directions[bank*2 +: 2],bank_taken[bank],bank_hit[bank],''')
    text=once(text,'.HISTORY_BITS(HISTORY_BITS), .COMPACT_INDIRECT_BTB(COMPACT_INDIRECT_BTB),',
        '.HISTORY_BITS(HISTORY_BITS), .HYBRID_DIRECTION(HYBRID_DIRECTION), .COMPACT_INDIRECT_BTB(COMPACT_INDIRECT_BTB),')
    text=once(text,'                .pred_counter_o(bank_counter[bank*2 +: 2]),',
        '''                .pred_counter_o(bank_counter[bank*2 +: 2]),
                .pred_component_directions_o(bank_component_directions[bank*2 +: 2]),''')
    text=once(text,'                .feedback_training_index_i(update_training_index),',
        '''                .feedback_training_index_i(update_training_index),
                .feedback_component_directions_i(update_component_directions),''')
    text=once(text,'            wire [37:0] selected_prediction;', '            wire [39:0] selected_prediction;')
    text=once(text,'rv32_frequency_array_read #(.WIDTH(38),.ENTRIES(FE_WIDTH),.INDEX_WIDTH(2)) bank_query',
        'rv32_frequency_array_read #(.WIDTH(40),.ENTRIES(FE_WIDTH),.INDEX_WIDTH(2)) bank_query')
    text=once(text,'            assign {pred_taken_o[lane],pred_btb_hit_o[lane],pred_target_o[lane*32 +: 32],',
        '            assign {lane_component_directions[lane*2 +: 2],pred_taken_o[lane],pred_btb_hit_o[lane],pred_target_o[lane*32 +: 32],')
    text=once(text,'''                if (pred_kind_o[history_lane*2 +: 2] == `RV32IM_PRED_BRANCH)
                    history_after_bundle''', '''                // Keep the exact low history checkpoint and global-table
                // query index. The two spare high bits carry both raw fetch
                // directions for resolution-time preference training.
                if (HYBRID_ACTIVE)
                    pred_metadata_o[history_lane*16+14 +: 2]=
                        lane_component_directions[history_lane*2 +: 2];
                if (pred_kind_o[history_lane*2 +: 2] == `RV32IM_PRED_BRANCH)
                    history_after_bundle''')
    clock_marker='    always @(posedge clk_i) begin'
    assert text[text.index(clock_marker):]==original[original.index(clock_marker):]
    assert text.count('pred_metadata_o = {FE_WIDTH*16{1\'b0}};')==1
    changes[name]=text

    name='rtl/cpu_core.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer PREDICTOR_HISTORY_BITS = 6,',
        '    parameter integer PREDICTOR_HISTORY_BITS = 6,\n    parameter integer PREDICTOR_HYBRID_DIRECTION = 0,')
    text=once(text,'.HISTORY_BITS(PREDICTOR_HISTORY_BITS), .LEGACY_SENTINEL_HALT(LEGACY_SENTINEL_HALT)) predictor',
        '.HISTORY_BITS(PREDICTOR_HISTORY_BITS), .HYBRID_DIRECTION(PREDICTOR_HYBRID_DIRECTION && !SERIAL_BACKEND), .LEGACY_SENTINEL_HALT(LEGACY_SENTINEL_HALT)) predictor')
    assert text[text.index('    wire ic_mem_req_valid,'):]==original[original.index('    wire ic_mem_req_valid,'):]
    changes[name]=text
    name='rtl/course/student_top.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer PREDICTOR_HISTORY_BITS = 6,',
        '    parameter integer PREDICTOR_HISTORY_BITS = 6,\n    parameter integer PREDICTOR_HYBRID_DIRECTION = 1,')
    text=once(text,'    parameter integer PREDICTOR_COMPACT_BTB_ENTRIES = 32,',
        '    parameter integer PREDICTOR_COMPACT_BTB_ENTRIES = 16,')
    text=once(text,'.PREDICTOR_HISTORY_BITS(PREDICTOR_HISTORY_BITS),',
        '.PREDICTOR_HISTORY_BITS(PREDICTOR_HISTORY_BITS), .PREDICTOR_HYBRID_DIRECTION(PREDICTOR_HYBRID_DIRECTION),')
    changes[name]=text
    for name in parent['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    assert sha(TARGET/'rtl/backend/rv32_backend_joint.v')==parent['source_sha256']['rtl/backend/rv32_backend_joint.v']
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['parameter_overrides']=dict(parent['parameter_overrides'],
        PREDICTOR_HYBRID_DIRECTION=1,PREDICTOR_COMPACT_BTB_ENTRIES=16)
    record['enabled_profile']=dict(parent['enabled_profile'],hybrid_direction_predictor=True,
        hybrid_gshare_entries=256,hybrid_bimodal_entries=256,hybrid_choice_entries=64,
        compact_indirect_btb_entries=16,hybrid_metadata_direction_bits=2,
        hybrid_metadata_bus_width_unchanged=16,hybrid_added_pipeline_edges=0,
        hybrid_table_added_state_bits=896,hybrid_btb_removed_state_bits=640,
        hybrid_metadata_added_effective_state_bits_estimate=104,
        hybrid_net_effective_state_bits_estimate=360)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Parallel256-entry gshare and256-entry bimodal direction tables plus64-entry2-bit PC chooser. Train both directions from full-generation accepted feedback, global row from saved query index, and preference only when the two saved fetch-time directions disagree. Reuse spare metadata bits15:14 when history<=6; exact checkpoint/index and all recovery logic retained. Compact indirect-only BTB32->16 funds most added state; no extra fetch edge.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],hybrid_direction_predictor={
        'a41_ipc':1.0116565072515666,'a41_area_um2':35559.51075799682,
        'a41_area_margin_um2':440.4892420031822,
        'mixed_a36_a41_benchmark_effect_not_single_change_causal_attribution':True,
        'mcfarling_original_paper':REFERENCE,
        'metadata_layout':'15:14 raw global/bimodal;13:8 history checkpoint;7:0 exact global query index',
        'new_direction_and_choice_state_bits':896,'btb_removed_state_bits':640,
        'effective_metadata_extra_bits_estimate':104,'net_state_bits_estimate':360,
        'net_state_area_component_estimate_um2':360*0.2916,
        'extra_logic_and_future_fmax_area_ipc_unmeasured':True})
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_HYBRID_DIRECTION_PREDICTOR_UNTESTED',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),tests_started=False,adopted=False,
        added_pipeline_edges=0,added_sram_bits=0,
        new_predictor_table_state_bits=896,removed_btb_state_bits=640,
        metadata_state_bits_estimate=104,net_state_bits_estimate=360,
        source_reference=REFERENCE,
        source_arguments=[
            'Both direction tables and the PC chooser query in parallel, with a final direction choice. The original gshare table indexing, cold BTFNT fallback, row reset/train behavior, full branch/JAL target formation and full JALR recovery comparisons are retained.',
            'Both predictors train every accepted conditional branch in that bank. Gshare uses exact prediction-time feedback_training_index_i, not resolution-time GHR; bimodal and chooser use saved feedback_pc_i. Choice saturates toward the raw predictor that was right only when saved raw directions disagree; initial preference is weakly bimodal.',
            'Metadata width stays16. Enabled history<=6 places raw{gshare,bimodal} in15:14, history checkpoint in13:8 and saved gshare row index in7:0. Core serial backend disables hybrid, and child/banked active guards disable it outside mode2/history<=6. Mode0/1 and larger legal history keep original metadata behavior.',
            'Every multi-feedback packet grows108->110, adding raw directions to the same lane packet as index, PC, kind, actual/predicted directions and targets. Original grants and full-generation backend feedback qualification remain unchanged; distinct banks can update together, same-bank conflict keeps original first lane.',
            'Only lower6 recovered history bits are used in this active profile. The original backend checkpoint capture/conditional shift may carry raw direction bits in upper recovery outputs, but banked recovery always masks HISTORY_MASK; they cannot enter a history<=6 register. Backend source is byte-exact parent.',
            'Added tables have768+128=896 state bits. Compact BTB32->16 removes16*40=640 bits. FQ16+decode4+ROB32 existing metadata owners may materialize2*52=104 previously constant high bits, estimating net360 bits, about104.976um2 FF area component. This excludes combinational/buffer/owner costs, is not a mapped area claim, and exact total pruning/storage cost must be measured later.',
            'Direct targets remain PC+immediate and never allocate compact BTB; shrinking indirect target capacity is an explicit prediction-capacity trade, not a correctness approximation. Capacity aliases/misses must still resolve against full architectural targets and may hurt IPC.',
            'A41 mixed median improvement and qsort regression motivate adaptive direction selection but do not prove gshare alone caused the changes. Paper results on other workloads are not this CPU results or a guaranteed IPC improvement.',
            'No HDL/lint/simulation/synthesis/STA/unit tests. Later coverage must include both preference directions/saturation, equal predictions, fetch-to-feedback intervening training, multiple branches/banks, same-bank conflict, cold rows, history recovery/accepted prefix/RAS override, wrong-path tags, all FE widths and disabled/history>6 fallbacks.'
        ])
    write(BASE/'A45_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','changed_files','net_state_bits_estimate','tests_started')})


if __name__=='__main__':
    main()
