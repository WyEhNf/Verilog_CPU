"""Prepare atomic elastic R-to-D admission; do not run CPU/EDA tests."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A14_two_wide_backend_er1_dcache'
TARGET=BASE/'A15_atomic_elastic_dispatch'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


QUEUE=r'''
// Two bundle entries break the D-resource/PRF path from R acceptance.
// R allocates ROB/physical destinations once. D emits the entire oldest
// bundle only when both its actual RS and LSQ demands fit the saved free
// counts. Recovery retains only full-generation-live, older ROB tags.
module rv32_elastic_dispatch_packet #(
    parameter integer LANES=2,PAYLOAD_WIDTH=160,TAG_WIDTH=16,ROB_ENTRIES=32,
    parameter integer SW=(ROB_ENTRIES<=1)?1:$clog2(ROB_ENTRIES),
    parameter integer GW=TAG_WIDTH-SW-3
) (
    input wire clk_i,reset_i,flush_i,hold_i,recovery_i,
    input wire [SW-1:0] recovery_head_i,
    input wire [TAG_WIDTH-1:0] recovery_tag_i,
    input wire [15:0] recovery_occupancy_i,
    input wire [ROB_ENTRIES-1:0] rob_valid_i,
    input wire [ROB_ENTRIES*GW-1:0] rob_generation_i,
    input wire [LANES-1:0] valid_i,
    input wire [LANES*TAG_WIDTH-1:0] tag_i,
    input wire [LANES*PAYLOAD_WIDTH-1:0] data_i,
    output wire ready_o,
    output wire [LANES-1:0] valid_o,
    output wire [LANES*TAG_WIDTH-1:0] tag_o,
    output wire [LANES*PAYLOAD_WIDTH-1:0] data_o,
    input wire consume_i
);
    reg [1:0] count;
    reg read_slot,write_slot;
    reg [LANES-1:0] valids [0:1];
    wire [TAG_WIDTH-1:0] tags [0:2*LANES-1];
    wire [PAYLOAD_WIDTH-1:0] payloads [0:2*LANES-1];
    wire [LANES-1:0] recovery_keep [0:1];
    wire [ROB_ENTRIES*(GW+1)-1:0] live_rows;
    wire normal=!reset_i && !flush_i && !hold_i && !recovery_i;
    assign ready_o=normal && count<2;
    wire push=(|valid_i) && ready_o;
    wire pop=normal && count!=0 && consume_i;
    wire [SW-1:0] branch_age=recovery_tag_i[3 +: SW]-recovery_head_i;
    genvar rob_row,row,lane,word;
    generate for(rob_row=0;rob_row<ROB_ENTRIES;rob_row=rob_row+1) begin:g_live_row
        assign live_rows[rob_row*(GW+1) +: GW+1]={rob_valid_i[rob_row],rob_generation_i[rob_row*GW +: GW]};
    end endgenerate
    localparam integer OUTPUT_WORDS=(PAYLOAD_WIDTH+TAG_WIDTH+15)/16;
    wire [LANES*OUTPUT_WORDS-1:0] read_views;
    rv32_frequency_control_tree #(.LEAVES(LANES*OUTPUT_WORDS)) read_tree (
        .signal_i(read_slot),.views_o(read_views));
    generate
        for(row=0;row<2;row=row+1) begin:g_row
            for(lane=0;lane<LANES;lane=lane+1) begin:g_lane
                wire [TAG_WIDTH-1:0] tag=tags[row*LANES+lane];
                wire [SW-1:0] slot=tag[3 +: SW];
                wire [SW-1:0] age=slot-recovery_head_i;
                wire [GW:0] live;
                rv32_frequency_array_read #(.WIDTH(GW+1),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SW)) live_reader (
                    .rows_i(live_rows),.index_i(slot),.value_o(live));
                assign recovery_keep[row][lane]=valids[row][lane] && tag[0] &&
                    live[GW] && tag[3+SW +: GW]==live[0 +: GW] &&
                    age<branch_age && age<recovery_occupancy_i;
                rv32_frequency_word_bank #(.WIDTH(TAG_WIDTH+PAYLOAD_WIDTH)) packet_owner (
                    .clk_i(clk_i),.write_i(push && write_slot==row && valid_i[lane]),
                    .data_i({tag_i[lane*TAG_WIDTH +: TAG_WIDTH],data_i[lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]}),
                    .data_o({tags[row*LANES+lane],payloads[row*LANES+lane]}));
            end
        end
        for(lane=0;lane<LANES;lane=lane+1) begin:g_output
            wire [TAG_WIDTH+PAYLOAD_WIDTH-1:0] selected;
            wire [TAG_WIDTH+PAYLOAD_WIDTH-1:0] first={tags[lane],payloads[lane]};
            wire [TAG_WIDTH+PAYLOAD_WIDTH-1:0] second={tags[LANES+lane],payloads[LANES+lane]};
            for(word=0;word<OUTPUT_WORDS;word=word+1) begin:g_word
                localparam integer LOW=16*word;
                localparam integer BITS=TAG_WIDTH+PAYLOAD_WIDTH-LOW>=16?16:TAG_WIDTH+PAYLOAD_WIDTH-LOW;
                assign selected[LOW +: BITS]=read_views[lane*OUTPUT_WORDS+word]?
                    second[LOW +: BITS]:first[LOW +: BITS];
            end
            assign {tag_o[lane*TAG_WIDTH +: TAG_WIDTH],data_o[lane*PAYLOAD_WIDTH +: PAYLOAD_WIDTH]}=selected;
            assign valid_o[lane]=normal && count!=0 && (read_slot?valids[1][lane]:valids[0][lane]);
        end
    endgenerate
    wire keep_first=|recovery_keep[read_slot];
    wire keep_second=(count==2) && (|recovery_keep[!read_slot]);
    always @(posedge clk_i) begin
        if(reset_i || flush_i) begin
            count<=0;read_slot<=0;write_slot<=0;valids[0]<=0;valids[1]<=0;
        end else if(recovery_i) begin
            valids[0]<=recovery_keep[0];valids[1]<=recovery_keep[1];
            if(count==0 || (!keep_first && !keep_second)) begin
                count<=0;read_slot<=0;write_slot<=0;valids[0]<=0;valids[1]<=0;
            end else if(keep_first && keep_second) begin
                count<=2;
            end else if(keep_first) begin
                count<=1;write_slot<=!read_slot;valids[!read_slot]<=0;
            end else begin
                count<=1;read_slot<=!read_slot;write_slot<=read_slot;valids[read_slot]<=0;
            end
        end else if(!hold_i) begin
            case({push,pop})
                2'b10:count<=count+1'b1;
                2'b01:count<=count-1'b1;
                default:count<=count;
            endcase
            if(pop) begin valids[read_slot]<=0;read_slot<=!read_slot;end
            if(push) begin valids[write_slot]<=valid_i;write_slot<=!write_slot;end
        end
    end
endmodule
'''


ADMISSION='''
    // Count raw D demand before gating either allocator, avoiding an
    // alloc_fire -> valid -> alloc_fire combinational readiness loop.
    // Only saved occupancy/free counts determine atomic acceptance.
    wire [BE_WIDTH-1:0] d_rs_need=d_valid & ~load_without_agu;
    wire [BE_WIDTH-1:0] d_lsq_need=d_valid & (d_is_load | d_is_store);
    reg [CREDIT_WIDTH-1:0] d_rs_demand,d_lsq_demand;
    integer demand_lane;
    always @* begin
        d_rs_demand=0;d_lsq_demand=0;
        for(demand_lane=0;demand_lane<BE_WIDTH;demand_lane=demand_lane+1) begin
            d_rs_demand=d_rs_demand+d_rs_need[demand_lane];
            d_lsq_demand=d_lsq_demand+d_lsq_need[demand_lane];
        end
    end
    assign d_admit=(DISPATCH_ELASTIC==0) ||
        (!reset_i && !flush_i && !branch_busy_domains[3] &&
         (d_rs_demand<=rs_free_count) && (d_lsq_demand<=lsq_free_count));
    assign rs_alloc_valid=d_rs_need & {BE_WIDTH{d_admit}};
    assign lsq_alloc_valid=d_lsq_need & {BE_WIDTH{d_admit}};
'''


def main():
    assert not TARGET.exists(),TARGET
    pm=read(PARENT/'candidate.json')
    for name,digest in pm['source_sha256'].items():assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/backend/rv32_backend_joint.v';old=(PARENT/name).read_text(encoding='utf-8');text=old
    text=once(text,'    parameter integer EARLY_LOAD_ADDRESS = 0,',
        '    parameter integer EARLY_LOAD_ADDRESS = 0,\n    parameter integer DISPATCH_ELASTIC = 0,')
    text=once(text,'    wire [BE_WIDTH-1:0] d_valid;',
        '    wire [BE_WIDTH-1:0] d_valid;\n    wire dispatch_packet_ready,d_admit;')
    text=once(text,'if (!halted_o && !flush_i && !branch_busy_domains[0] &&',
        'if (!halted_o && !flush_i && !branch_busy_domains[0] && dispatch_packet_ready &&')
    text=once(text,'(ready_rs_used <= rs_credit) &&','((DISPATCH_ELASTIC!=0) || (ready_rs_used <= rs_credit)) &&')
    text=once(text,'(ready_lsq_used <= lsq_credit) &&','((DISPATCH_ELASTIC!=0) || (ready_lsq_used <= lsq_credit)) &&')
    text=once(text,'.rename_ready_i(!halted_o && !flush_i && !branch_busy_domains[1]),',
        '.rename_ready_i(!halted_o && !flush_i && !branch_busy_domains[1] && dispatch_packet_ready),')
    text=once(text,'.rs_free_count_i({{(16-CREDIT_WIDTH){1\'b0}},rs_credit}),',
        ".rs_free_count_i((DISPATCH_ELASTIC!=0)?16'hffff:{{(16-CREDIT_WIDTH){1'b0}},rs_credit}),")
    text=once(text,'.lsq_free_count_i({{(16-CREDIT_WIDTH){1\'b0}},lsq_credit}),',
        ".lsq_free_count_i((DISPATCH_ELASTIC!=0)?16'hffff:{{(16-CREDIT_WIDTH){1'b0}},lsq_credit}),")
    text=once(text,'        if(DISPATCH_PIPELINE!=0) begin:g_reserved_dispatch',
        '''        if(DISPATCH_PIPELINE!=0 && DISPATCH_ELASTIC!=0) begin:g_elastic_dispatch
            rv32_elastic_dispatch_packet #(.LANES(BE_WIDTH),.PAYLOAD_WIDTH(DISPATCH_PAYLOAD_WIDTH),
                .TAG_WIDTH(TAG_WIDTH),.ROB_ENTRIES(ROB_ENTRIES)) packet (
                .clk_i(clk_i),.reset_i(reset_i),.flush_i(flush_i),.hold_i(branch_busy_domains[3]),
                .recovery_i(recovery_domains[7]),
                .recovery_head_i(recovery_head_views[0 +: ROB_SLOT_WIDTH]),
                .recovery_tag_i(recovery_tag_views[0 +: TAG_WIDTH]),
                .recovery_occupancy_i({{(16-ROB_COUNT_WIDTH){1'b0}},recovery_descriptor_occupancy}),
                .rob_valid_i(rob_entry_valid),.rob_generation_i(rob_entry_generation),
                .valid_i(dispatch_valid & rob_alloc_fire),.tag_i(rob_alloc_tag),.data_i(d_payload_in),
                .ready_o(dispatch_packet_ready),.valid_o(d_valid),.tag_o(d_tag),.data_o(d_payload_out),
                .consume_i(d_admit));
            assign d_reserved_rs=0;assign d_reserved_lsq=0;
        end else if(DISPATCH_PIPELINE!=0) begin:g_reserved_dispatch
            assign dispatch_packet_ready=1'b1;''')
    text=once(text,'        end else begin:g_direct_dispatch\n            assign d_valid=dispatch_valid;',
        "        end else begin:g_direct_dispatch\n            assign dispatch_packet_ready=1'b1;\n            assign d_valid=dispatch_valid;")
    text=once(text,'    assign rs_alloc_valid = d_valid & ~load_without_agu;\n    assign lsq_alloc_valid = d_valid & (d_is_load | d_is_store);',ADMISSION)
    text=text.replace('    // producer. Keep conservative rename/dispatch RS reservations unchanged.',
        '    // producer. Elastic mode admits only its actual D resource demand.')
    text+=QUEUE
    # Elastic mode requires the existing registered D boundary.
    assert 'parameter integer DISPATCH_PIPELINE = 0' in text
    changes[name]=text
    name='rtl/cpu_core.v';text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer EARLY_LOAD_ADDRESS = 0,',
        '    parameter integer EARLY_LOAD_ADDRESS = 0,\n    parameter integer DISPATCH_ELASTIC = 0,')
    text=once(text,'.DISPATCH_PIPELINE(1),','.DISPATCH_PIPELINE(1), .DISPATCH_ELASTIC(DISPATCH_ELASTIC),')
    changes[name]=text
    name='rtl/course/student_top.v';text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer EARLY_LOAD_ADDRESS = 3,',
        '    parameter integer EARLY_LOAD_ADDRESS = 3,\n    parameter integer DISPATCH_ELASTIC = 1,')
    text=once(text,'.EARLY_LOAD_ADDRESS(EARLY_LOAD_ADDRESS),',
        '.EARLY_LOAD_ADDRESS(EARLY_LOAD_ADDRESS), .DISPATCH_ELASTIC(DISPATCH_ELASTIC),')
    changes[name]=text
    for name in pm['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():(TARGET/name).write_text(text,encoding='utf-8')
    record=dict(pm)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={n:sha(TARGET/n) for n in pm['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)))
    record['parameter_overrides']=dict(pm['parameter_overrides'],DISPATCH_ELASTIC=1)
    record['enabled_profile']=dict(pm['enabled_profile'],DISPATCH_ELASTIC=1,dispatch_bundle_entries=2)
    record['implemented_changes']=list(pm['implemented_changes'])+[
        'Replace one reserved D packet by two elastic bundle entries; R reserves only ROB/PRF and queue capacity, D atomically allocates its actual RS/LSQ demand.'
    ]
    record['material_gain_evidence']=dict(pm['material_gain_evidence'],
        actual_ready_base_load_rs_demand=0,
        old_rename_ready_base_load_rs_reservation_per_instruction=1,
        dispatch_elastic_declared_extra_state_bits=358,
        dispatch_elastic_added_pipeline_edges=0,
        new_comb_ready_feedback_to_rename=False)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_PROTOCOL_REVIEW_UNTESTED_NOT_FULL_CORE_PROOF',candidate=str(TARGET),
        candidate_sha256=sha(TARGET/'candidate.json'),parent_sha256=sha(PARENT/'candidate.json'),
        changed_files=list(changes),tests_started=False,adopted=False,
        source_argument=[
            'The original D packet has no ready input and must reserve RS/LSQ capacity upstream; ignoring its credits alone is unsafe and is not implemented.',
            'The replacement queue accepts only complete renamed/ROB-allocated bundles and advertises capacity from a registered two-entry count, without D PRF/capacity feedback to R.',
            'D demand is computed from raw queued valid lanes and authoritative early-load address readiness, before gating either allocator.',
            'Saved RS/LSQ free counts must each cover the entire sparse demand. RS and LSQ valid masks share one admit event; a held bundle is not allocated partially or repeated.',
            'A ready-base load-only bundle has zero RS demand, so RS-full does not prevent its LSQ allocation. Missing-base loads and all other instructions still require RS.',
            'ROB/PRF destinations and speculative RAT writes still allocate only once at R. Outstanding queued consumers protect their source physical versions through in-order retirement.',
            'Recovery uses valid/full generation checks and the original strict older-than-branch age condition. It retains nonempty entries in order, drops wrong-path rows and resets queue pointers/count on empty.',
            'Branch-pending hold, reset, flush and recovery prohibit push/pop and ordinary allocation; retained older entries resume afterwards.',
            'Nominal R-to-D delay remains one edge. Additional queue storage, front read mux and D admission gates are explicit area/timing costs; real gain is not measured.',
            'Default DISPATCH_ELASTIC=0 retains the old reserved packet and conservative credits. The course core always enables the registered D boundary.',
            'No functional, equivalence, IPC, area, timing or hardware testing is claimed by this source review.'
        ])
    write(BASE/'A15_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':main()
