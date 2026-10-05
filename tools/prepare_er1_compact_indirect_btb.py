"""Keep BTB64, compress indirect-only payload; no HDL or EDA execution."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A26_compact_prediction_target'
TARGET=BASE/'A27_compact_indirect_btb'


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
    text=once(original,'    parameter integer DIRECT_BRANCH_TARGET = 0,',
        '    parameter integer DIRECT_BRANCH_TARGET = 0,\n    parameter integer COMPACT_INDIRECT_BTB = 0,')
    text=once(text,'    localparam integer BTB_ENTRIES = 64 >> BANK_BITS;', '''    localparam integer BTB_ENTRIES = 64 >> BANK_BITS;
    localparam integer BTB_COMPACT_ACTIVE=(COMPACT_INDIRECT_BTB!=0) && (DIRECT_BRANCH_TARGET==1);
    localparam integer BTB_PAYLOAD_WIDTH=BTB_COMPACT_ACTIVE?39:58;
    // A predictor tag may alias; execution still compares the full resolved
    // target before retirement. Keep all entries, with an eight-bit folded
    // identity instead of twenty-four exact bits in indirect-only mode.
    function [7:0] folded_btb_tag;
        input [31:0] pc;
        begin folded_btb_tag=pc[15:8] ^ pc[23:16] ^ pc[31:24];end
    endfunction
    wire [BTB_PAYLOAD_WIDTH-1:0] btb_update_payload=BTB_COMPACT_ACTIVE?
        {folded_btb_tag(feedback_pc_i),feedback_btb_target[31:1]}:
        {feedback_pc_i[31:8],feedback_btb_target,feedback_kind_i};
    wire [23:0] query_btb_identity=BTB_COMPACT_ACTIVE?
        {16'b0,folded_btb_tag(query_pc_i)}:query_pc_i[31:8];''')
    text=once(text,'    wire [BTB_DOMAINS*58-1:0] btb_write_payloads;',
        '    wire [BTB_DOMAINS*BTB_PAYLOAD_WIDTH-1:0] btb_write_payloads;')
    text=once(text,'''    rv32_frequency_control_tree #(.WIDTH(58),.LEAVES(BTB_DOMAINS)) btb_payload_tree (
        .signal_i({feedback_pc_i[31:8],feedback_btb_target,feedback_kind_i}),.views_o(btb_write_payloads));''','''    rv32_frequency_control_tree #(.WIDTH(BTB_PAYLOAD_WIDTH),.LEAVES(BTB_DOMAINS)) btb_payload_tree (
        .signal_i(btb_update_payload),.views_o(btb_write_payloads));''')
    text=once(text,'''            rv32_predictor_btb_row row (
                .clk_i(clk_i),.reset_i(reset_views[BHT_ENTRIES+predictor_row]),.update_i(update),
                .payload_i(btb_write_payloads[DOMAIN*58 +: 58]),.valid_o(btb_valid[predictor_row]),
                .tag_o(btb_tag[predictor_row]),.target_o(btb_target[predictor_row]),.kind_o(btb_kind[predictor_row]));''','''            if(BTB_COMPACT_ACTIVE) begin:g_compact
                rv32_predictor_indirect_btb_row row (
                    .clk_i(clk_i),.reset_i(reset_views[BHT_ENTRIES+predictor_row]),.update_i(update),
                    .payload_i(btb_write_payloads[DOMAIN*BTB_PAYLOAD_WIDTH +: BTB_PAYLOAD_WIDTH]),
                    .valid_o(btb_valid[predictor_row]),.tag_o(btb_tag[predictor_row][7:0]),
                    .target_o(btb_target[predictor_row]));
                assign btb_tag[predictor_row][23:8]=16'b0;
                assign btb_kind[predictor_row]=`RV32IM_PRED_JALR;
            end else begin:g_full
                rv32_predictor_btb_row row (
                    .clk_i(clk_i),.reset_i(reset_views[BHT_ENTRIES+predictor_row]),.update_i(update),
                    .payload_i(btb_write_payloads[DOMAIN*BTB_PAYLOAD_WIDTH +: BTB_PAYLOAD_WIDTH]),
                    .valid_o(btb_valid[predictor_row]),.tag_o(btb_tag[predictor_row]),
                    .target_o(btb_target[predictor_row]),.kind_o(btb_kind[predictor_row]));
            end''')
    text=once(text,'(query_btb_word[57:34] == query_pc_i[31:8]);',
        '(query_btb_word[57:34] == query_btb_identity);')
    text+='''

// In direct-target mode only JALR allocates the BTB. Its kind and target bit0
// are constants; the hash is predictor metadata, never architectural identity.
module rv32_predictor_indirect_btb_row (
    input wire clk_i,reset_i,update_i,
    input wire [38:0] payload_i,
    output reg valid_o,
    output wire [7:0] tag_o,
    output wire [31:0] target_o
);
    wire [38:0] payload;
    rv32_frequency_word_bank #(.WIDTH(39)) payload_owner (
        .clk_i(clk_i),.write_i(!reset_i && update_i),.data_i(payload_i),.data_o(payload));
    assign tag_o=payload[38:31];
    assign target_o={payload[30:0],1'b0};
    always @(posedge clk_i) begin
        if(reset_i) valid_o<=0;
        else if(update_i) valid_o<=1;
    end
endmodule
'''
    # Saturating BHT rows and old BTB implementation remain unchanged.
    marker='// Saturating direction counter preserves'
    assert text[text.index(marker):].startswith(original[original.index(marker):])
    changes[name]=text
    name='rtl/predictor/rv32_banked_predictor.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer DIRECT_BRANCH_TARGET = 0,',
        '    parameter integer DIRECT_BRANCH_TARGET = 0,\n    parameter integer COMPACT_INDIRECT_BTB = 0,')
    text=once(text,'.HISTORY_BITS(HISTORY_BITS)) predictor (',
        '.HISTORY_BITS(HISTORY_BITS), .COMPACT_INDIRECT_BTB(COMPACT_INDIRECT_BTB)) predictor (')
    changes[name]=text
    name='rtl/cpu_core.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer PREDICTOR_COMPACT_TARGET = 0,',
        '    parameter integer PREDICTOR_COMPACT_TARGET = 0,\n    parameter integer PREDICTOR_COMPACT_BTB = 0,')
    text=once(text,'.HISTORY_BITS(PREDICTOR_HISTORY_BITS), .LEGACY_SENTINEL_HALT',
        '.COMPACT_INDIRECT_BTB(PREDICTOR_COMPACT_BTB), .HISTORY_BITS(PREDICTOR_HISTORY_BITS), .LEGACY_SENTINEL_HALT')
    changes[name]=text
    name='rtl/course/student_top.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer PREDICTOR_COMPACT_TARGET = 1,',
        '    parameter integer PREDICTOR_COMPACT_TARGET = 1,\n    parameter integer PREDICTOR_COMPACT_BTB = 1,')
    text=once(text,'.PREDICTOR_COMPACT_TARGET(PREDICTOR_COMPACT_TARGET),',
        '.PREDICTOR_COMPACT_TARGET(PREDICTOR_COMPACT_TARGET), .PREDICTOR_COMPACT_BTB(PREDICTOR_COMPACT_BTB),')
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
    record['parameter_overrides']=dict(parent['parameter_overrides'],PREDICTOR_COMPACT_BTB=1)
    record['enabled_profile']=dict(parent['enabled_profile'],PREDICTOR_COMPACT_BTB=1,
        btb_entries=64,btb_payload_bits_per_entry=39,btb_tag_hash_bits=8,
        btb_removed_declared_ff_bits=64*19,bht_entries=256)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Keep64 BTB entries and256 BHT entries; direct mode1 BTB stores39-bit indirect-only payload: eight-bit folded tag and31-bit aligned target, with full target resolution protecting architectural correctness.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        btb_payload_bits_before=58,btb_payload_bits_after=39,
        btb_removed_declared_ff_bits=64*19,btb_removed_ff_area_component_um2=64*19*.2916,
        btb_hash_can_increase_false_predictions=True,btb_new_ipc_area_fmax_unmeasured=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_INDIRECT_BTB_HASH39BIT_PAYLOAD_CAPACITY_RETAINED_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),changed_files=list(changes),
        tests_started=False,source_arguments=[
            'DIRECT_BRANCH_TARGET==1 writes BTB only for accepted/taken JALR feedback. Therefore kind==JALR and target bit0==0 are constants, represented explicitly rather than inferred through an update condition.',
            'All64 BTB entries, their index/bank ownership and valid bits remain. Hash tag foldsPC31:8 into eight bits; BHT256, saturating updates, direct conditional/JAL prediction and RAS remain unchanged.',
            'Prediction tags can alias but never validate architectural state. Legal JALR resolution still compares full32-bit actual target with full original prediction (or page-qualified offset with mandatory cross-page recovery in A26), and in-order commit prevents a wrong predicted suffix from retiring.',
            'Mode0/2 or disabled parameter retains original58-bit payload/full tag. Enabled39-bit payload removes1216 declared FF bits and nineteen write-distribution/read-mux bits per entry; 354.5856um2 FF component excludes hash/mux costs and is not actual total-area gain.',
            'All six frozen performance linked texts reside wholly in page0 (max PC0x508). Within that text set the folded identity equals the original low tag byte, with no additional static text aliases. This is static evidence only, not dynamic confinement/IPC proof.',
            'No HDL build, lint, simulation, synthesis, STA, perf or unit tests. Final verification must include high-address hash aliases and full JALR target mismatch recovery, not only course programs.'
        ])
    write(BASE/'A27_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':
    main()
