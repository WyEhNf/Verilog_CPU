"""Isolated EG child: split same-cycle ALU wake from registered slow results."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def rs(text):
    text=change(text,'    parameter integer WAKE_WIDTH = BE_WIDTH,', '''    parameter integer WAKE_WIDTH = BE_WIDTH,
    // Only this low-index prefix may feed combinational issue/base probing.
    // All ports still update the original operand/ready state on the edge.
    parameter integer SAME_CYCLE_WAKE_PORTS = WAKE_WIDTH,''')
    text=change(text,'    genvar wr, wl;', '''    wire [31:0] wake1_issue [0:ENTRIES-1],wake2_issue [0:ENTRIES-1];
    localparam [WAKE_WIDTH-1:0] SAME_CYCLE_WAKE_MASK=
        {{(WAKE_WIDTH-SAME_CYCLE_WAKE_PORTS){1'b0}},{SAME_CYCLE_WAKE_PORTS{1'b1}}};
    genvar wr, wl;''')
    original='''            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH),.PRIORITY(0)) first1_selector (
                .events_i(first1),.values_i(local_values),.write_o(),.value_o(wake1_first[wr]));

            rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH),.PRIORITY(0)) first2_selector (
                .events_i(first2),.values_i(local_values),.write_o(),.value_o(wake2_first[wr]));'''
    replacement='''            if(SAME_CYCLE_WAKE_PORTS>0 && SAME_CYCLE_WAKE_PORTS<WAKE_WIDTH) begin:g_split_issue_word
                // First-lane priority already resides in first1/first2. The
                // low prefix never depends on higher-index slow matches.
                // Merge both partitions for the ORIGINAL sequential value.
                wire [31:0] slow1,slow2;
                rv32_frequency_event_select #(.WIDTH(32),.EVENTS(SAME_CYCLE_WAKE_PORTS),.PRIORITY(0)) fast1_selector (
                    .events_i(first1[0 +: SAME_CYCLE_WAKE_PORTS]),
                    .values_i(local_values[0 +: SAME_CYCLE_WAKE_PORTS*32]),
                    .write_o(),.value_o(wake1_issue[wr]));
                rv32_frequency_event_select #(.WIDTH(32),.EVENTS(SAME_CYCLE_WAKE_PORTS),.PRIORITY(0)) fast2_selector (
                    .events_i(first2[0 +: SAME_CYCLE_WAKE_PORTS]),
                    .values_i(local_values[0 +: SAME_CYCLE_WAKE_PORTS*32]),
                    .write_o(),.value_o(wake2_issue[wr]));
                rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH-SAME_CYCLE_WAKE_PORTS),.PRIORITY(0)) slow1_selector (
                    .events_i(first1[SAME_CYCLE_WAKE_PORTS +: WAKE_WIDTH-SAME_CYCLE_WAKE_PORTS]),
                    .values_i(local_values[SAME_CYCLE_WAKE_PORTS*32 +: (WAKE_WIDTH-SAME_CYCLE_WAKE_PORTS)*32]),
                    .write_o(),.value_o(slow1));
                rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH-SAME_CYCLE_WAKE_PORTS),.PRIORITY(0)) slow2_selector (
                    .events_i(first2[SAME_CYCLE_WAKE_PORTS +: WAKE_WIDTH-SAME_CYCLE_WAKE_PORTS]),
                    .values_i(local_values[SAME_CYCLE_WAKE_PORTS*32 +: (WAKE_WIDTH-SAME_CYCLE_WAKE_PORTS)*32]),
                    .write_o(),.value_o(slow2));
                assign wake1_first[wr]=wake1_issue[wr] | slow1;
                assign wake2_first[wr]=wake2_issue[wr] | slow2;
            end else begin:g_original_issue_word
                rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH),.PRIORITY(0)) first1_selector (
                    .events_i(first1),.values_i(local_values),.write_o(),.value_o(wake1_first[wr]));
                rv32_frequency_event_select #(.WIDTH(32),.EVENTS(WAKE_WIDTH),.PRIORITY(0)) first2_selector (
                    .events_i(first2),.values_i(local_values),.write_o(),.value_o(wake2_first[wr]));
                assign wake1_issue[wr]=(SAME_CYCLE_WAKE_PORTS==0)?32'b0:wake1_first[wr];
                assign wake2_issue[wr]=(SAME_CYCLE_WAKE_PORTS==0)?32'b0:wake2_first[wr];
            end'''
    text=change(text,original,replacement)
    text=change(text,'''            wire wake1=(|wake1_match[effective_row]);
            wire wake2=(|wake2_match[effective_row]);''', '''            wire wake1=(|(wake1_match[effective_row] & SAME_CYCLE_WAKE_MASK));
            wire wake2=(|(wake2_match[effective_row] & SAME_CYCLE_WAKE_MASK));''')
    for operand in (1,2):
        text=change(text,f'                    wake{operand}_first[effective_row][effective_word*16 +: 16]:src{operand}_value_mem[effective_row][effective_word*16 +: 16];',
            f'                    wake{operand}_issue[effective_row][effective_word*16 +: 16]:src{operand}_value_mem[effective_row][effective_word*16 +: 16];')
    text=change(text,'                for(source=0;source<WAKE_WIDTH;source=source+1) begin',
        '                for(source=0;source<SAME_CYCLE_WAKE_PORTS;source=source+1) begin')
    return change(text,'''    // each issue lane.  Fold current-cycle CDB wakeups into selection and the
    // operand mux.''', '''    // each issue lane. Fold the configured fast wake prefix into selection
    // and the operand mux. Slow ports first update the existing row state.''')


def backend(text):
    text=change(text,'    parameter integer RS_PHYSICAL_WAKEUP = 0,', '''    parameter integer RS_PHYSICAL_WAKEUP = 0,
    // With direct producer wake, retain ALU same-cycle issue and let MDU/LSQ
    // wake flow through the existing operand/ready registers first.
    parameter integer RS_REGISTER_SLOW_WAKE = 0,''')
    text=change(text,'    localparam integer RS_WAKE_WIDTH = RS_DIRECT_WAKE ? PRODUCERS : BE_WIDTH+PRODUCERS;', '''    localparam integer RS_WAKE_WIDTH = RS_DIRECT_WAKE ? PRODUCERS : BE_WIDTH+PRODUCERS;
    localparam integer RS_SAME_CYCLE_WAKE_PORTS=(RS_REGISTER_SLOW_WAKE!=0 && RS_DIRECT_WAKE!=0)?BE_WIDTH:RS_WAKE_WIDTH;''')
    return change(text,'.WAKE_WIDTH(RS_WAKE_WIDTH), .STORE_DATA_WIDTH(32),',
        '.WAKE_WIDTH(RS_WAKE_WIDTH), .SAME_CYCLE_WAKE_PORTS(RS_SAME_CYCLE_WAKE_PORTS), .STORE_DATA_WIDTH(32),')


def core(text):
    return change(text,'    rv32_backend_joint #(.STORE_ALLOC_EARLY_ADDRESS(2),',
        '    rv32_backend_joint #(.RS_REGISTER_SLOW_WAKE(1), .STORE_ALLOC_EARLY_ADDRESS(2),')


def main():
    parent=ROOT/'EG_prf_parallel_store_address'
    verify_parent(parent)
    out=prepare('EH_rs_fast_slow_wake',parent,
        {'rtl/backend/rv32_reservation_station.v':rs,
         'rtl/backend/rv32_backend_joint.v':backend,'rtl/cpu_core.v':core},
        'Conditional EG child: separate ALU combinational wake operands from MDU/LSQ slow operands, which still update all existing row state and participate from the following cycle. Recombine split first-priority words for original sequential write semantics. No new FF or normal integer stage. Source-only, unadopted/unmeasured.')
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    record_delta(out,parent,groups+['rs_alu_fast_and_registered_mdu_lsq_wake'])
    path=out/'candidate.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        declared_additional_state_bits_vs_parent=0,new_declared_sequential_state_bits=0,
        measured_parent_run=None,measured_reference_run='F:/CPU2026CourseRuns/architecture_EA_20261005',
        behavior='Original all-port clocked operand/ready updates retained. ALU held-result same-cycle bypass preserved; MDU/LSQ dependent issue and shared base probe wait for existing row registers. PRF/data/complete authority unchanged from EG.',
        timing_tradeoff='Removes slow MDU/LSQ matches/data from combinational RS effective readiness, operand values, and early base-probe output. Does not remove slow writes into RS rows or normal completion/PRF paths. Slow dependent readiness can add one issue opportunity cycle; IPC impact unmeasured.',
        existing_clocked_payload_refactor='Original clocked text and all-port last-priority values retained. Split first-priority words recombine by masked OR.',
        current_wake_ports=dict(total=6,same_cycle_ALU=4,registered_MDU_LSQ=2),
        source_basis=[
            'https://docs.boom-core.org/en/latest/sections/issue-units.html',
            'https://docs.boom-core.org/en/latest/sections/reg-file-bypass-network.html'],
        distinction_from_speculative_fast_wakeup='Uses original already-valid held ALU result broadcasts; does not announce future issue-time results or require speculative replay.',
        adoption_condition='First inspect completed EF paths and area. EG/EH are separate source-only alternatives. Report final selected combination and cycle/IPC risks before any new measurement.')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        adopted=False,tests_started=False,new_declared_state_bits=0)))


if __name__=='__main__':
    main()
