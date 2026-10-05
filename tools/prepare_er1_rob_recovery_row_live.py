"""Prepare full-generation qualification per ROB row before recovery selection."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import ROOT, read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A104_lsq_alloc_fire_distribution'
TARGET=BASE/'A105_rob_recovery_row_live'
REVIEW=BASE/'A105_source_review.json'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    assert sha(PARENT/'candidate.json')=='cb856713cc7cf7c228cca32a4a69238084ecefc91f685db2fa9a9c74c4ef6b04'
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/backend/rv32_rob.v';original=(PARENT/name).read_text(encoding='utf-8')
    marker='    parameter integer STORE_PREFIX_ADMISSION = 0,'
    text=once(original,marker,marker+'\n    parameter integer RECOVERY_ROW_LIVE_QUALIFY = 0,')
    old='''            wire [RECOVERY_LIVE_WIDTH-1:0] live_state;
            rv32_frequency_array_read #(.WIDTH(RECOVERY_LIVE_WIDTH),.ENTRIES(ROB_ENTRIES),.INDEX_WIDTH(SLOT_WIDTH)) live_reader (
                .rows_i(recovery_live_rows),.index_i(tag[SLOT_LSB +: SLOT_WIDTH]),.value_o(live_state));
            assign recovery_lane_live[recovery_query_lane]=tag[VALID_LSB] && live_state[GENERATION_WIDTH] &&
                tag[GEN_LSB +: GENERATION_WIDTH]==live_state[0 +: GENERATION_WIDTH];'''
    new='''            if(RECOVERY_ROW_LIVE_QUALIFY!=0) begin:g_row_live
                localparam integer QUERY_WIDTH=SLOT_WIDTH+GENERATION_WIDTH;
                localparam integer DOMAINS=(ROB_ENTRIES+3)/4;
                localparam integer LEAVES=1<<$clog2(ROB_ENTRIES);
                wire [DOMAINS*QUERY_WIDTH-1:0] query_views;
                wire live_tree [1:2*LEAVES-1];
                // Compare every saved row's complete GEN before selecting it.
                // No selected GEN bus followed by a late equality comparison.
                rv32_frequency_control_tree #(.WIDTH(QUERY_WIDTH),.LEAVES(DOMAINS)) query_tree (
                    .signal_i({tag[GEN_LSB +: GENERATION_WIDTH],tag[SLOT_LSB +: SLOT_WIDTH]}),
                    .views_o(query_views));
                for(genvar live_row=0;live_row<LEAVES;live_row=live_row+1) begin:g_row
                    if(live_row<ROB_ENTRIES) begin:g_present
                        wire [QUERY_WIDTH-1:0] query=query_views[(live_row/4)*QUERY_WIDTH +: QUERY_WIDTH];
                        wire [RECOVERY_LIVE_WIDTH-1:0] state=recovery_live_rows[live_row*RECOVERY_LIVE_WIDTH +: RECOVERY_LIVE_WIDTH];
                        wire generation_matches=query[SLOT_WIDTH +: GENERATION_WIDTH]==state[0 +: GENERATION_WIDTH];
                        wire slot_matches=query[0 +: SLOT_WIDTH]==live_row;
                        assign live_tree[LEAVES+live_row]=slot_matches && state[GENERATION_WIDTH] && generation_matches;
                    end else begin:g_padding
                        assign live_tree[LEAVES+live_row]=1'b0;
                    end
                end
                for(genvar live_node=1;live_node<LEAVES;live_node=live_node+1) begin:g_reduce
                    rv32_rob_recovery_live_or pair (
                        .left_i(live_tree[2*live_node]),.right_i(live_tree[2*live_node+1]),
                        .value_o(live_tree[live_node]));
                end
                assign recovery_lane_live[recovery_query_lane]=tag[VALID_LSB] && live_tree[1];
            end else begin:g_original_live_read
'''+old+'''
            end'''
    text=once(text,old,new)
    marker='    localparam integer STORE_PREFIX_ADMISSION_ACTIVE='
    assert text[text.index(marker):]==original[original.index(marker):]
    text+='''

// Pure single-bit OR. Keep binary reduction levels separate from GEN/slot
// predicates; all functional cells remain priced by the original course flow.
(* keep_hierarchy = 1 *)
module rv32_rob_recovery_live_or (
    input wire left_i,right_i,
    output wire value_o
);
    assign value_o=left_i | right_i;
endmodule
'''
    changes[name]=text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original=(PARENT/name).read_text(encoding='utf-8');default=1 if name.endswith('student_top.v') else 0
        marker='    parameter integer ROB_STORE_PREFIX_ADMISSION = '+str(default)+','
        text=once(original,marker,marker+'\n    parameter integer ROB_RECOVERY_ROW_LIVE_QUALIFY = '+str(default)+',')
        if '/backend/' in name:
            text=once(text,'.STORE_PREFIX_ADMISSION(ROB_STORE_PREFIX_ADMISSION)',
                '.STORE_PREFIX_ADMISSION(ROB_STORE_PREFIX_ADMISSION), .RECOVERY_ROW_LIVE_QUALIFY(ROB_RECOVERY_ROW_LIVE_QUALIFY)')
        else:
            text=once(text,'.ROB_STORE_PREFIX_ADMISSION(ROB_STORE_PREFIX_ADMISSION)',
                '.ROB_STORE_PREFIX_ADMISSION(ROB_STORE_PREFIX_ADMISSION), .ROB_RECOVERY_ROW_LIVE_QUALIFY(ROB_RECOVERY_ROW_LIVE_QUALIFY)')
        changes[name]=text
    for name in parent['source_sha256']:
        dest=TARGET/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PARENT/name,dest)
    for name,text in changes.items():(TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(status='SOURCE_COMPLETE_ROB_GEN_ROW_QUALIFICATION_BEFORE_RECOVERY_SELECTION_UNTESTED',
        created_at=datetime.now(timezone.utc).isoformat(),source_root=str(TARGET),parent_candidate=str(PARENT),
        parent_candidate_sha256=sha(PARENT/'candidate.json'),changed_from_parent_files=list(changes),
        source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),
        tests_started=False,synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides']=dict(parent['parameter_overrides'],ROB_RECOVERY_ROW_LIVE_QUALIFY=1)
    record['enabled_profile']=dict(parent['enabled_profile'],ROB_RECOVERY_ROW_LIVE_QUALIFY=1,recovery_live_rows_per_domain=4,
        recovery_row_live_new_ff_bits=0,recovery_row_live_new_sram_bits=0,recovery_row_live_new_pipeline_edges=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Original ROB recovery_lane_live reads9-bit current valid/GEN by selectedslot then compares all8GEN. New mode independently compares complete saved GEN for each currentROBrow with original candidateGEN, applies exactslot/valid, and binaryORs a1-bit answer; candidatevalid still gatesroot. Realcontroltree distributes13bit slot+GEN to8four-row domains forROB32, preservingfullgeneration and out-of-range semantics. No state/protocol/age/priority/descriptor changes. Old recoverydest payload selection remains original. Removes selectedGENread->GENcompare serial work at cost of32parallel comparisons, tradedagainstremoved9bit readmux. Keep original option0.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        recovery_row_live_limit='A99 top5 begin branchcapture metadata -> ROB g_recovery_lane_query[0] live_reader rowselect0.2694/leaf0.2935 -> recovery_preview0.6154 -> applydistribution0.7736 -> later LSQ/CDB/admission/FF3.414. Perrow fullGEN equality depends only capturedtag/currentrowstate, can occur concurrently withslotqualification, then onlyboolOR beforeoriginalrecovery_lane_live. Original9bit currentGENmux and postmux8bit equality eliminated. Queryfanout/distribution/binaryOR area/timing mayoffsetgain, actual84um2 budget tight. TogetherwithA103lateLSQrecoverybool/A104allocationfanout targetsroot,middle,tail ofsamepath; no measured guarantee.')
    write(TARGET/'candidate.json',record)
    proof=dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,
        added_declared_ff_bits=0,added_sram_bits=0,added_pipeline_edges=0,
        source_arguments=[
            'Original array_read uses binaryslotindex and a rowhit equality for every realrow. For an in-range index r exactly onehit exists, so originallive_state equals{valid[r],fullGEN[r]}. Originaltagvalid &&valid[r]&&tagGEN==GEN[r] therefore equals tagvalid&&OR_i(index==i&&valid[i]&&tagGEN==GEN[i]). New rowloop is precisely this expression. For out-of-range binary index no realhit exists; originalreaderreturnszero valid and newORzero, bothfalse. Tagvalid0 also makesbothfalse regardlessrowdata. Exact for all binary input/row states, no onehot-private-query or reachable-state assumption.',
            'AllGENERATION_WIDTH bits are compared, allSLOT_WIDTH bits are matched against same rowinteger constants; padding rows arezero, non-power-of-two indices beyondROBentries fail, entries1 has1leaf/rootandnoORinternalnodes. Narrowquerypacket containsonlyGEN+slot; originaltagvalidgatesroot. Control_treeviewidentity preserves eachbit. Kept1bitbinaryOR modules arepurefunctional logic withoutstate/clock/priority/assumptions.',
            'Only recovery_lane_live implementation changes. Originalrecovery_valid gating, unsignedage/occupancy, oldestcandidate/lanepriority, selecteddest/checkpointreader, chosenROBslot/descriptor, redirect/epoch, GENupdates/recoverytruncation, commit/store/ACK/allocation/sourceevents and state/body from STORE_PREFIX_ADMISSION_ACTIVE to originalendmodule remainbyte-identical. Mainbackend/sourcegenerations/dimensionsunchanged exceptflagpropagation.',
            'Core/backend/ROBnewflag0/course1 retains originalreadqueryfallback. Newcourse32rows domains8/candidate13bits, originalwidth9currentGENreadmux eliminated and replaced32full8bitcomparators+1bitORtree. State/queryfanout/gatemapping/area canincreaseorcreateotherpath; noFF/SRAM/pipelineincrease, nofrequencyguarantee. AllhelpersfullypricedoriginalASAP7/idealclockconstraints unchanged.',
            'NoHDL/lint/formal/sim/synthesis/STA/unit tests ornewCPUbuild. ExistingA99terminalPPAandA104sourcefrozen, mainEsourceunadopted. NextcoherentbatchA103/A104/A105 addressesnewcriticalroot,middle,tail; remainingunsupporteddirectionsbeforetestreview, pre-report beforeonePPA, numericdualPPAgatebefore6perf, then19official+minimal4existingedge andparametercoveragebeforeadoption. FullRV32IM/OoO/inordercommit/MMIO and threegoals preserved.'
        ],goal_complete=False,adopted=False)
    write(REVIEW,proof)
    print({k:proof[k] for k in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__=='__main__':
    main()
