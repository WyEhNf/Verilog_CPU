"""Route simultaneous live branch resolutions to independent predictor banks."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A28_alloc_load_selection_bypass'
TARGET=BASE/'A29_multibank_branch_feedback'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/backend/rv32_backend_joint.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    output wire [15:0]                  branch_feedback_metadata_o,','''    output wire [15:0]                  branch_feedback_metadata_o,
    // Per-lane accepted resolution: {pc,kind,taken,target,pred_taken,pred_target}.
    output wire [BE_WIDTH-1:0]          branch_feedback_lane_valid_o,
    output wire [BE_WIDTH*100-1:0]      branch_feedback_lane_packets_o,''')
    text=once(text,'            assign feedback_grants[feedback_source]=branch_feedback_valid_r && feedback_lane==feedback_source;','''            assign feedback_grants[feedback_source]=branch_feedback_valid_r && feedback_lane==feedback_source;
            // Every exported lane has its own complete ROB lifetime check.
            // No new execution-ready/backpressure condition is introduced.
            assign branch_feedback_lane_valid_o[feedback_source]=
                feedback_candidates[feedback_source] && branch_training_live[feedback_source];''')
    text=once(text,'''                alu_exec_branch_target[feedback_source*32 +: 32],pred_taken,full_pred_target};''','''                alu_exec_branch_target[feedback_source*32 +: 32],pred_taken,full_pred_target};
            assign branch_feedback_lane_packets_o[feedback_source*100 +: 100]={
                pc,kind,alu_exec_branch_taken[feedback_source],
                alu_exec_branch_target[feedback_source*32 +: 32],pred_taken,full_pred_target};''')
    # All backend clocked state and execution/commit/recovery interfaces stay
    # unchanged; the added exports only tap the original resolution signals.
    marker='    // One shared MDU accepts'
    assert text[text.index(marker):]==original[original.index(marker):]
    changes[name]=text
    name='rtl/predictor/rv32_banked_predictor.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer COMPACT_INDIRECT_BTB = 0,',
        '    parameter integer COMPACT_INDIRECT_BTB = 0,\n    parameter integer FEEDBACK_LANES = 1, MULTI_FEEDBACK = 0,')
    text=once(text,'    input wire [15:0] feedback_metadata_i,','''    input wire [15:0] feedback_metadata_i,
    input wire [FEEDBACK_LANES-1:0] feedback_lane_valid_i,
    input wire [FEEDBACK_LANES*100-1:0] feedback_lane_packets_i,''')
    text=once(text,'    wire [FE_WIDTH-1:0] bank_taken, bank_hit;','''    localparam integer MULTI_ACTIVE=(MULTI_FEEDBACK!=0) && (DIRECT_BRANCH_TARGET==1);
    wire [FE_WIDTH-1:0] bank_feedback_valid,bank_feedback_correct;
    wire [FE_WIDTH-1:0] bank_taken, bank_hit;''')
    text=once(text,'            wire [31:0] inst;','''            wire [31:0] inst;
            wire update_valid,update_taken,update_pred_taken;
            wire [31:0] update_pc,update_target,update_pred_target;
            wire [1:0] update_kind;
            wire [7:0] update_training_index;
            if(MULTI_ACTIVE) begin:g_parallel_feedback
                wire [FEEDBACK_LANES-1:0] candidates,grants;
                wire [99:0] packet;
                for(genvar feedback_lane=0;feedback_lane<FEEDBACK_LANES;feedback_lane=feedback_lane+1) begin:g_lane
                    wire [31:0] lane_pc=feedback_lane_packets_i[feedback_lane*100+68 +: 32];
                    assign candidates[feedback_lane]=feedback_lane_valid_i[feedback_lane] &&
                        ((lane_pc[3:2] & BANK_MASK)==BANK_NUMBER);
                    if(feedback_lane==0) begin:g_first
                        assign grants[feedback_lane]=candidates[feedback_lane];
                    end else begin:g_later
                        assign grants[feedback_lane]=candidates[feedback_lane] &&
                            !(|candidates[feedback_lane-1:0]);
                    end
                end
                // Each existing table bank still has exactly one update.
                // Different banks accept different resolved lanes together.
                rv32_frequency_event_select #(.WIDTH(100),.EVENTS(FEEDBACK_LANES),.PRIORITY(0)) feedback_selector (
                    .events_i(grants),.values_i(feedback_lane_packets_i),
                    .write_o(update_valid),.value_o(packet));
                assign {update_pc,update_kind,update_taken,update_target,
                    update_pred_taken,update_pred_target}=packet;
                assign update_training_index=8'b0;
            end else begin:g_single_feedback
                assign update_valid=feedback_valid_i && feedback_bank==BANK_NUMBER;
                assign update_pc=feedback_pc_i;
                assign update_kind=feedback_kind_i;
                assign update_taken=feedback_taken_i;
                assign update_target=feedback_target_i;
                assign update_pred_taken=feedback_pred_taken_i;
                assign update_pred_target=feedback_pred_target_i;
                assign update_training_index=feedback_metadata_i[7:0];
            end
            assign bank_feedback_valid[bank]=update_valid;
            assign bank_feedback_correct[bank]=update_valid && update_pred_taken==update_taken &&
                (!update_taken || update_pred_target==update_target);''')
    text=once(text,'''                .feedback_valid_i(feedback_valid_i && feedback_bank == BANK_NUMBER),
                .feedback_pc_i(feedback_pc_i), .feedback_kind_i(feedback_kind_i),
                .feedback_taken_i(feedback_taken_i), .feedback_target_i(feedback_target_i),
                .feedback_pred_taken_i(feedback_pred_taken_i),
                .feedback_pred_target_i(feedback_pred_target_i),
                .feedback_training_index_i(feedback_metadata_i[7:0]),''','''                .feedback_valid_i(update_valid),
                .feedback_pc_i(update_pc), .feedback_kind_i(update_kind),
                .feedback_taken_i(update_taken), .feedback_target_i(update_target),
                .feedback_pred_taken_i(update_pred_taken),
                .feedback_pred_target_i(update_pred_target),
                .feedback_training_index_i(update_training_index),''')
    old='''    // Count accepted resolution feedback once, including non-allocating kinds.
    always @(posedge clk_i) begin
        if (reset_i) begin
            prediction_count_o <= 0;
            correct_count_o <= 0;
        end else if (feedback_valid_i) begin
            prediction_count_o <= prediction_count_o + 1;
            if (feedback_pred_taken_i == feedback_taken_i &&
                (!feedback_taken_i || feedback_pred_target_i == feedback_target_i))
                correct_count_o <= correct_count_o + 1;
        end
    end'''
    new='''    // Count table-bank accepted resolutions, including non-allocating JAL.
    // Same-bank conflicts retain lowest-lane priority and are counted once.
    integer count_bank;
    reg [2:0] feedback_count,feedback_correct_count;
    always @* begin
        feedback_count=0;feedback_correct_count=0;
        for(count_bank=0;count_bank<FE_WIDTH;count_bank=count_bank+1) begin
            feedback_count=feedback_count+{2'b0,bank_feedback_valid[count_bank]};
            feedback_correct_count=feedback_correct_count+{2'b0,bank_feedback_correct[count_bank]};
        end
    end
    always @(posedge clk_i) begin
        if (reset_i) begin
            prediction_count_o <= 0;
            correct_count_o <= 0;
        end else if(MULTI_ACTIVE) begin
            prediction_count_o<=prediction_count_o+{29'b0,feedback_count};
            correct_count_o<=correct_count_o+{29'b0,feedback_correct_count};
        end else if (feedback_valid_i) begin
            prediction_count_o <= prediction_count_o + 1;
            if (feedback_pred_taken_i == feedback_taken_i &&
                (!feedback_taken_i || feedback_pred_target_i == feedback_target_i))
                correct_count_o <= correct_count_o + 1;
        end
    end'''
    text=once(text,old,new)
    text=once(text,'    generate\n        for (bank', '''    initial begin
        if(FEEDBACK_LANES!=1 && FEEDBACK_LANES!=2 && FEEDBACK_LANES!=4)
            $fatal(1,"Predictor feedback lane count must be1/2/4");
    end
    generate
        for (bank''')
    changes[name]=text
    name='rtl/cpu_core.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer PREDICTOR_COMPACT_BTB = 0,',
        '    parameter integer PREDICTOR_COMPACT_BTB = 0,\n    parameter integer PREDICTOR_MULTI_FEEDBACK = 0,')
    text=once(text,'    wire [15:0] branch_feedback_metadata;','''    wire [15:0] branch_feedback_metadata;
    wire [BE_WIDTH-1:0] branch_feedback_lane_valid;
    wire [BE_WIDTH*100-1:0] branch_feedback_lane_packets;''')
    text=once(text,'.COMPACT_INDIRECT_BTB(PREDICTOR_COMPACT_BTB), .HISTORY_BITS',
        '.FEEDBACK_LANES(BE_WIDTH), .MULTI_FEEDBACK(PREDICTOR_MULTI_FEEDBACK && !SERIAL_BACKEND), .COMPACT_INDIRECT_BTB(PREDICTOR_COMPACT_BTB), .HISTORY_BITS')
    text=once(text,'.feedback_metadata_i(branch_feedback_metadata),', '''.feedback_metadata_i(branch_feedback_metadata),
                .feedback_lane_valid_i(branch_feedback_lane_valid),
                .feedback_lane_packets_i(branch_feedback_lane_packets),''')
    text=once(text,'    assign branch_feedback_metadata = 16\'b0;', '''    assign branch_feedback_metadata = 16'b0;
    assign branch_feedback_lane_valid=0;
    assign branch_feedback_lane_packets=0;''')
    text=once(text,'.trace_pred_metadata_i(trace_pred_metadata), .branch_feedback_metadata_o(branch_feedback_metadata),','''.branch_feedback_lane_valid_o(branch_feedback_lane_valid),
         .branch_feedback_lane_packets_o(branch_feedback_lane_packets),
         .trace_pred_metadata_i(trace_pred_metadata), .branch_feedback_metadata_o(branch_feedback_metadata),''')
    changes[name]=text
    name='rtl/course/student_top.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer PREDICTOR_COMPACT_BTB = 1,',
        '    parameter integer PREDICTOR_COMPACT_BTB = 1,\n    parameter integer PREDICTOR_MULTI_FEEDBACK = 1,')
    text=once(text,'.PREDICTOR_COMPACT_BTB(PREDICTOR_COMPACT_BTB),',
        '.PREDICTOR_COMPACT_BTB(PREDICTOR_COMPACT_BTB), .PREDICTOR_MULTI_FEEDBACK(PREDICTOR_MULTI_FEEDBACK),')
    changes[name]=text
    for name in parent['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():(TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['parameter_overrides']=dict(parent['parameter_overrides'],PREDICTOR_MULTI_FEEDBACK=1)
    record['enabled_profile']=dict(parent['enabled_profile'],PREDICTOR_MULTI_FEEDBACK=1,
        accepted_branch_training_lanes=2,predictor_bank_update_ports_each=1,
        branch_training_added_predictor_entries=0,branch_training_added_pipeline_edges=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Route both accepted full-ROB-generation-live branch resolutions to their independent existing BHT/BTB banks; same-bank conflict keeps lowest lane, with unchanged execution/commit/recovery.'
    ]
    # Correct the inherited accounting label without mutating parent manifests.
    evidence=dict(parent['material_gain_evidence'])
    estimate=evidence.pop('prediction_target_removed_declared_ff_bits_lower_bound',None)
    if estimate is not None:evidence['prediction_target_made_constant_bits_lower_bound']=estimate
    record['material_gain_evidence']=dict(evidence,
        branch_resolutions_trainable_per_edge_before=1,branch_resolutions_trainable_per_edge_after=2,
        second_resolution_requires_distinct_table_bank=True,
        multibank_feedback_added_functional_state_bits=0,branch_training_dynamic_trigger_rate_unknown=True,
        branch_training_ipc_area_frequency_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_TWO_BRANCH_RESOLUTIONS_EXISTING_DISTINCT_BANKS_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),
        tests_started=False,source_arguments=[
            'Existing feedback_selector globally exports only first accepted branch. New lanes tap each original accepted/valid branch and apply its own full ROB generation/valid authority; no extra execution-ready/backpressure or architectural state update.',
            'Each existing predictor bank gets at most one lowest-lane grant matching PC low word-index bits. Distinct banks may train both resolved branches on the same edge; same-bank conflicts keep prior first-lane priority.',
            'No extra BHT/BTB entries or table ports, pipeline stage or result holding state. BHT updates still saturate original counters; BTB writes still use actual accepted JALR target and original valid ownership.',
            'Only mode1 OoO uses parallel packets. Disabled feature, serial backend, mode0 and history mode2 retain the original single-feedback interface and history snapshot.',
            'Diagnostic counters in multi mode count selected bank updates, including nonallocating JAL; same-bank dropped lanes are not counted. Correctness compares saved direction/expanded full target exactly as original metadata policy.',
            'Source export packet is100 bits with PC bits99:68, kind67:66, taken65, target64:33, predicted-taken32 and predicted-target31:0. All fields reuse existing per-lane source metadata/registered results.',
            'Benefit requires simultaneous accepted branches in different banks; static potential is not dynamic IPC proof. Added bank selection logic and late ROB authority can affect area/timing, still unmeasured.',
            'No HDL build, lint, simulation, synthesis, STA, performance or unit tests. Later relevant coverage includes both banks/same-bank conflict, reset/recovery/killed generations, saturation and indirect target updates.'
        ])
    write(BASE/'A29_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':main()
