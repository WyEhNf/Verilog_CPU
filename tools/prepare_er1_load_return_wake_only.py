"""Separate load speculative wake from formal completion; no HDL execution."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE=Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT=BASE/'A21_credit_guaranteed_dispatch_replace'
TARGET=BASE/'A22_load_return_wake_only'


def once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def main():
    assert not TARGET.exists()
    parent=read(PARENT/'candidate.json')
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name)==digest,name
    changes={}
    name='rtl/backend/rv32_lsq.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer LOAD_COMPLETION_BYPASS = 0,',
        '    parameter integer LOAD_COMPLETION_BYPASS = 0,\n    parameter integer LOAD_WAKE_BYPASS = 0,')
    text=once(text,'    output reg                          load_complete_error_o,', '''    output reg                          load_complete_error_o,
    // Early speculative wake is independent of CDB acceptance/completion.
    // The original row still captures the response for formal publication.
    output wire                         load_return_wake_valid_o,
    output wire [ROB_TAG_WIDTH-1:0]      load_return_wake_rob_tag_o,
    output wire [PHYS_ADDR_WIDTH-1:0]    load_return_wake_phys_o,
    output wire [31:0]                  load_return_wake_value_o,''')
    text=once(text,'    genvar report_row,report_word,report_node,report_decode;', '''    localparam integer RETURN_WAKE_META_WIDTH=ROB_TAG_WIDTH+PHYS_ADDR_WIDTH;
    wire [LSQ_ENTRIES-1:0] return_wake_rows;
    wire [LSQ_ENTRIES*RETURN_WAKE_META_WIDTH-1:0] return_wake_metadata;
    generate if(LOAD_WAKE_BYPASS!=0 && LOCAL_REPORT_CANCEL!=0) begin:g_return_wake_selector
        rv32_frequency_event_select #(.WIDTH(RETURN_WAKE_META_WIDTH),.EVENTS(LSQ_ENTRIES),.PRIORITY(0)) return_owner_selector (
            .events_i(return_wake_rows),.values_i(return_wake_metadata),
            .write_o(load_return_wake_valid_o),
            .value_o({load_return_wake_rob_tag_o,load_return_wake_phys_o}));
        // Exactly the value captured by the original selected response row:
        // line/word choice, byte forwarding merge, size and signed extension.
        assign load_return_wake_value_o=payload_response_value;
    end else begin:g_no_return_wake
        assign load_return_wake_valid_o=1'b0;
        assign load_return_wake_rob_tag_o=0;
        assign load_return_wake_phys_o=0;
        assign load_return_wake_value_o=0;
    end endgenerate

    genvar report_row,report_word,report_node,report_decode;''')
    text=once(text,'                // Reuse the exact existing LSQ response value: full byte', '''                // Full LSQ generation and live row ownership qualify wake.
                // A retired/stale/killed/store row cannot wake a reclaimed
                // physical register. No oldest-report arbitration or ROB
                // table lookup sits on this notification path.
                assign return_wake_rows[report_row]=(LOAD_WAKE_BYPASS!=0) &&
                    (LOCAL_REPORT_CANCEL!=0) && !reset_i && !flush_i && !recovery_valid_i &&
                    response_match_rows[report_row] && load_mem[report_row] && !store_mem[report_row] &&
                    request_sent_mem[report_row] && !complete_mem[report_row] &&
                    !load_reported_mem[report_row] && !retired_mem[report_row] &&
                    rob_tag_mem[report_row][0] && !row_cancel;
                assign return_wake_metadata[report_row*RETURN_WAKE_META_WIDTH +: RETURN_WAKE_META_WIDTH]={
                    rob_tag_mem[report_row],physical_destinations[report_row*PHYS_ADDR_WIDTH +: PHYS_ADDR_WIDTH]};
                // Reuse the exact existing LSQ response value: full byte''')
    marker='    // Wide payload fields have no reset state.'
    assert text.split(marker,1)[1]==original.split(marker,1)[1]
    changes[name]=text
    name='rtl/backend/rv32_backend_joint.v'
    original=(PARENT/name).read_text(encoding='utf-8')
    text=once(original,'    parameter integer LOAD_COMPLETION_BYPASS = 0,',
        '    parameter integer LOAD_COMPLETION_BYPASS = 0,\n    parameter integer LOAD_WAKE_BYPASS = 0,')
    text=once(text,'    localparam integer RS_WAKE_WIDTH = RS_DIRECT_WAKE ? PRODUCERS : BE_WIDTH+PRODUCERS;', '''    localparam integer RS_BASE_WAKE_WIDTH=RS_DIRECT_WAKE?PRODUCERS:BE_WIDTH+PRODUCERS;
    localparam integer RS_LOAD_RETURN_WAKE=(LOAD_WAKE_BYPASS!=0) && RS_DIRECT_WAKE && (LOCAL_EXEC_RECOVERY!=0);
    localparam integer RS_WAKE_WIDTH=RS_BASE_WAKE_WIDTH+RS_LOAD_RETURN_WAKE;
    wire [RS_BASE_WAKE_WIDTH-1:0] rs_base_wake_valid;
    wire [RS_BASE_WAKE_WIDTH*32-1:0] rs_base_wake_value;
    wire lsq_return_wake_valid;
    wire [TAG_WIDTH-1:0] lsq_return_wake_tag;
    wire [PAW-1:0] lsq_return_wake_phys;
    wire [31:0] lsq_return_wake_value;''')
    text=once(text,'.LOAD_COMPLETION_BYPASS(LOAD_COMPLETION_BYPASS),',
        '.LOAD_COMPLETION_BYPASS(LOAD_COMPLETION_BYPASS), .LOAD_WAKE_BYPASS(RS_LOAD_RETURN_WAKE),')
    text=once(text,'.load_complete_valid_o(lsq_load_complete_valid),', '''.load_return_wake_valid_o(lsq_return_wake_valid), .load_return_wake_rob_tag_o(lsq_return_wake_tag),
        .load_return_wake_phys_o(lsq_return_wake_phys), .load_return_wake_value_o(lsq_return_wake_value),
        .load_complete_valid_o(lsq_load_complete_valid),''')
    text=once(text,'        assign rs_wake_valid=producer_valid & producer_rd_we & producer_wake_live;',
        '        assign rs_base_wake_valid=producer_valid & producer_rd_we & producer_wake_live;')
    text=once(text,'        assign rs_wake_value=producer_value;',
        '        assign rs_base_wake_value=producer_value;')
    text=once(text,'        assign rs_wake_valid={producer_valid & producer_rd_we & producer_wake_live,wake_wb_valid};',
        '        assign rs_base_wake_valid={producer_valid & producer_rd_we & producer_wake_live,wake_wb_valid};')
    text=once(text,'        assign rs_wake_value={producer_value,wake_wb_value};',
        '        assign rs_base_wake_value={producer_value,wake_wb_value};')
    text=once(text,'    genvar wake_identity_lane;', '''    // Keep the saved LSQ completion wake and new response wake in separate
    // columns: simultaneous returns must not hide an accepted older result.
    generate if(RS_LOAD_RETURN_WAKE!=0) begin:g_early_load_wake
        assign rs_wake_valid={lsq_return_wake_valid,rs_base_wake_valid};
        assign rs_wake_value={lsq_return_wake_value,rs_base_wake_value};
    end else begin:g_original_load_wake
        assign rs_wake_valid=rs_base_wake_valid;
        assign rs_wake_value=rs_base_wake_value;
    end endgenerate

    genvar wake_identity_lane;''')
    text=once(text,'            if(RS_DIRECT_WAKE!=0) begin:g_direct_producer', '''            if(RS_LOAD_RETURN_WAKE!=0 && wake_identity_lane==RS_BASE_WAKE_WIDTH) begin:g_return_load
                assign phys=lsq_return_wake_phys;
            end else if(RS_DIRECT_WAKE!=0) begin:g_direct_producer''')
    # Formal completion source formation, ROB generation checks, CDB/PRF
    # routing, RS ownership and queue clock blocks are not altered.
    start='    always @* begin\n        producer_valid_r ='
    end='    genvar wake_identity_lane;'
    producer_old=original[original.index(start):original.index('    assign producer_valid =',original.index(start))]
    producer_new=text[text.index(start):text.index('    assign producer_valid =',text.index(start))]
    assert producer_new==producer_old
    changes[name]=text
    name='rtl/cpu_core.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer LOAD_COMPLETION_BYPASS = 0,',
        '    parameter integer LOAD_COMPLETION_BYPASS = 0,\n    parameter integer LOAD_WAKE_BYPASS = 0,')
    text=once(text,'.LOAD_COMPLETION_BYPASS(LOAD_COMPLETION_BYPASS),',
        '.LOAD_COMPLETION_BYPASS(LOAD_COMPLETION_BYPASS), .LOAD_WAKE_BYPASS(LOAD_WAKE_BYPASS),')
    changes[name]=text
    name='rtl/course/student_top.v'
    text=(PARENT/name).read_text(encoding='utf-8')
    text=once(text,'    parameter integer LOAD_COMPLETION_BYPASS = 1,',
        '    parameter integer LOAD_COMPLETION_BYPASS = 0,\n    parameter integer LOAD_WAKE_BYPASS = 1,')
    text=once(text,'.LOAD_COMPLETION_BYPASS(LOAD_COMPLETION_BYPASS),',
        '.LOAD_COMPLETION_BYPASS(LOAD_COMPLETION_BYPASS), .LOAD_WAKE_BYPASS(LOAD_WAKE_BYPASS),')
    changes[name]=text
    for name in parent['source_sha256']:
        target=TARGET/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,target)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record=dict(parent)
    record.update(source_root=str(TARGET),created_at=datetime.now(timezone.utc).isoformat(),
        parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={n:sha(TARGET/n) for n in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),tests_started=False,adopted=False)
    record['parameter_overrides']=dict(parent['parameter_overrides'],LOAD_COMPLETION_BYPASS=0,LOAD_WAKE_BYPASS=1)
    record['enabled_profile']=dict(parent['enabled_profile'],LOAD_COMPLETION_BYPASS=0,LOAD_WAKE_BYPASS=1,
        rs_wake_columns=5,load_report_hold_identity_bits=0,load_return_wake_added_state_bits=0)
    record['implemented_changes']=list(parent['implemented_changes'])+[
        'Disable formal load-return completion bypass; retain its one-edge dependency wake opportunity on a separate speculative RS column while ordinary CDB/ROB/PRF completion starts from saved LSQ state.'
    ]
    record['material_gain_evidence']=dict(parent['material_gain_evidence'],
        a21_measured_ipc=0.9615883182384856,a21_measured_fmax_mhz=247.40275428847548,
        a21_formal_load_return_chain_rejected=True,rs_saved_and_early_load_wake_columns_independent=True,
        wake_only_real_ipc_area_frequency_unknown=True)
    write(TARGET/'candidate.json',record)
    proof=dict(status='SOURCE_WAKE_ONLY_COMPLETION_REGISTER_BOUNDARY_RESTORED_UNTESTED',
        candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        changed_files=list(changes),tests_started=False,adopted=False,
        source_arguments=[
            'A21 measured only1.61% IPC gain and247.40MHz. Its top STA path runs from bus data response FIFO through Dcache/LSQ return publication and ROB lifetime authority; formal response publication is disabled in this candidate.',
            'LOAD_COMPLETION_BYPASS=0 makes formal report eligibility/payload use only saved complete/value/error, removing the incoming response from CDB/ROB/PRF completion on that edge. Original capture and all metadata clock logic remain exact parent bytes.',
            'A separate early wake requires complete LSQ generation match, request_sent/response_wait, live load-only row, not complete/reported/retired, a valid full ROB tag and local recovery cancellation. Reset/flush/apply suppress it. Ownership follows the same retained unretired LSQ lifetime used by the existing local direct wake.',
            'The early value is exactly payload_response_value captured by the original response owner, including byte forwarding and signed/unsigned formatting. Only ROBtag/physical destination are selected from matching row metadata; no oldest completion tournament or global ROB read is needed for this notification.',
            'Early wake is not retirement/PRF/ROB publication and has no backpressure handshake. Original row capture always retains it for formal completion later. Any wrong-path speculative consumer is still removed by original recovery; an older instruction cannot depend on a younger reclaimed destination.',
            'An additional RS wake column prevents a fresh response from replacing the existing saved LSQ wake when both occur. Unique physical owner still holds: new-return row requires !complete, whereas saved report requires complete; other live instructions cannot own the same physical destination.',
            'New path is enabled only for direct physical wake with local execution/recovery cancellation. Other profiles keep their original wake width/identity modes. No extra state or nominal ALU/MDU pipeline edge is introduced.',
            'Cost is one RS wake column and metadata selection logic; cache-to-wake/ALU timing still must be measured. No new IPC/area/Fmax, HDL build, simulation, synthesis or STA has been run.',
            'A21 and A16R2 runs, their terminal results, course dependency files and main EU source remain unchanged. Further IPC/area work is still needed before the next coherent measurement.'
        ])
    write(BASE/'A22_source_review.json',proof)
    print({k:proof[k] for k in ('status','candidate','candidate_sha256','tests_started')})


if __name__=='__main__':
    main()
