"""Prepare ET and EU off-tree, with source-side store address arithmetic."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


PRECALC = '''    // This is allocation-query arithmetic, not new producer state.
    // Current dispatch offsets may change while a direct lane is held; all
    // derived sums follow the same current offset as the original PRF output.
    localparam integer SOURCE_STORE_ADDRESS=PARALLEL_STORE_ADDRESS && (COMPLETION_BYPASS==2);
    wire [BE_WIDTH*PRODUCERS-1:0] completion_source_select;
    wire [BE_WIDTH*BE_WIDTH*32-1:0] prf_precomputed_store_addresses;
    generate if(SOURCE_STORE_ADDRESS!=0) begin:g_source_store_address
        wire [BE_WIDTH*PRODUCERS*32-1:0] producer_base_views;
        wire [BE_WIDTH*32-1:0] link_base_views;
        // A producer value gains one bounded distribution root rather than
        // directly driving the four new allocation adders in addition to CDB.
        rv32_frequency_control_tree #(.WIDTH(PRODUCERS*32),.LEAVES(BE_WIDTH)) producer_base_tree (
            .signal_i(producer_value),.views_o(producer_base_views));
        rv32_frequency_control_tree #(.WIDTH(32),.LEAVES(BE_WIDTH)) link_base_tree (
            .signal_i(branch_pending_value),.views_o(link_base_views));
        for(genvar allocation_lane=0;allocation_lane<BE_WIDTH;allocation_lane=allocation_lane+1) begin:g_allocation
            wire [PRODUCERS*32-1:0] source_addresses;
            wire [31:0] zero_address={{20{prf_store_offsets[allocation_lane*12+11]}},
                prf_store_offsets[allocation_lane*12 +: 12]};
            for(genvar producer_id=0;producer_id<PRODUCERS;producer_id=producer_id+1) begin:g_source
                rv32_frequency_add_simm12 address_adder (
                    .base_i(producer_base_views[(allocation_lane*PRODUCERS+producer_id)*32 +: 32]),
                    .immediate_i(prf_store_offsets[allocation_lane*12 +: 12]),
                    .sum_o(source_addresses[producer_id*32 +: 32]));
            end
            for(genvar write_lane=0;write_lane<BE_WIDTH;write_lane=write_lane+1) begin:g_write_lane
                wire [PRODUCERS-1:0] sources=
                    completion_source_select[write_lane*PRODUCERS +: PRODUCERS];
                wire [PRODUCERS:0] events={sources,!(|sources)};
                wire [(PRODUCERS+1)*32-1:0] values={source_addresses,zero_address};
                wire [31:0] normal_address;
                // The direct completion masks are one-hot. No source uses
                // the exact old zero CDB data plus the same signed immediate.
                rv32_frequency_event_select #(.WIDTH(32),.EVENTS(PRODUCERS+1),.PRIORITY(0)) source_selector (
                    .events_i(events),.values_i(values),.write_o(),.value_o(normal_address));
                if(write_lane==CDB_WIDTH-1) begin:g_branch_link
                    wire [31:0] link_address;
                    wire [1:0] link_views;
                    rv32_frequency_add_simm12 link_adder (
                        .base_i(link_base_views[allocation_lane*32 +: 32]),
                        .immediate_i(prf_store_offsets[allocation_lane*12 +: 12]),
                        .sum_o(link_address));
                    rv32_frequency_control_tree #(.LEAVES(2)) link_tree (
                        .signal_i(branch_pending && branch_pending_rd_we),.views_o(link_views));
                    for(genvar word_id=0;word_id<2;word_id=word_id+1) begin:g_word
                        assign prf_precomputed_store_addresses[(allocation_lane*BE_WIDTH+write_lane)*32+word_id*16 +: 16]=
                            link_views[word_id]?link_address[word_id*16 +: 16]:normal_address[word_id*16 +: 16];
                    end
                end else begin:g_normal
                    assign prf_precomputed_store_addresses[(allocation_lane*BE_WIDTH+write_lane)*32 +: 32]=normal_address;
                end
            end
        end
    end else begin:g_original_store_address
        assign prf_precomputed_store_addresses=0;
    end endgenerate
'''


def completion(text):
    text=change(text,'    output wire [COUNT_WIDTH-1:0]       occupancy_o\n);',
        '''    output wire [COUNT_WIDTH-1:0]       occupancy_o,
    // Same direct payload mask, including reset/flush and held-source rules.
    // This combinational query export does not grant a new transaction.
    output wire [BE_WIDTH*SOURCES-1:0]  source_select_o
);''')
    text=change(text,'''                rv32_frequency_control_tree #(.LEAVES(WORDS)) select_tree (
                    .signal_i(selected_mask[payload_lane][payload_source] && !reset_i && !flush_i),''',
        '''                assign source_select_o[payload_lane*SOURCES+payload_source]=
                    (BYPASS==2) && selected_mask[payload_lane][payload_source] && !reset_i && !flush_i;
                rv32_frequency_control_tree #(.LEAVES(WORDS)) select_tree (
                    .signal_i(selected_mask[payload_lane][payload_source] && !reset_i && !flush_i),''')
    return change(text,'''        assign direct_target[payload_lane]=target_tree[1];
    end endgenerate''',
        '''        assign direct_target[payload_lane]=target_tree[1];
    end
    for(genvar unused_lane=CDB_WIDTH;unused_lane<BE_WIDTH;unused_lane=unused_lane+1) begin:g_unused_source_query
        assign source_select_o[unused_lane*SOURCES +: SOURCES]=0;
    end endgenerate''')


def prf(text):
    text=change(text,'    parameter integer STORE_ADDRESS_READ = 0,',
        '''    parameter integer STORE_ADDRESS_READ = 0,
    // Optional query arithmetic supplied before producer/CDB selection.
    // Default retains the original standalone interface behavior.
    parameter integer STORE_ADDRESS_PRECOMPUTED = 0,''')
    text=change(text,'    input  wire [BE_WIDTH*12-1:0]        store_offset_i,',
        '''    input  wire [BE_WIDTH*12-1:0]        store_offset_i,
    input  wire [BE_WIDTH*BE_WIDTH*32-1:0] store_precomputed_i,''')
    return change(text,'''                        rv32_frequency_add_simm12 write_address (
                            .base_i(write_data_i[address_lane*32 +: 32]),
                            .immediate_i(store_offset_i[(rp/2)*12 +: 12]),
                            .sum_o(address_values[(address_lane+1)*32 +: 32]));''',
        '''                        if(STORE_ADDRESS_PRECOMPUTED!=0) begin:g_precomputed
                            assign address_values[(address_lane+1)*32 +: 32]=
                                store_precomputed_i[((rp/2)*BE_WIDTH+address_lane)*32 +: 32];
                        end else begin:g_original
                            rv32_frequency_add_simm12 write_address (
                                .base_i(write_data_i[address_lane*32 +: 32]),
                                .immediate_i(store_offset_i[(rp/2)*12 +: 12]),
                                .sum_o(address_values[(address_lane+1)*32 +: 32]));
                        end''')


def backend(text):
    text=change(text,'''    rv32_physical_register_file #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS), .READ_MUX_IMPL(PRF_READ_MUX_IMPL), .LOCAL_VALUE_ROWS(1), .STORE_ADDRESS_READ(PARALLEL_STORE_ADDRESS)) prf (''',
        PRECALC+'''    rv32_physical_register_file #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS), .READ_MUX_IMPL(PRF_READ_MUX_IMPL), .LOCAL_VALUE_ROWS(1), .STORE_ADDRESS_READ(PARALLEL_STORE_ADDRESS), .STORE_ADDRESS_PRECOMPUTED(SOURCE_STORE_ADDRESS)) prf (''')
    text=change(text,'        .store_offset_i(prf_store_offsets), .store_address_o(prf_store_address),',
        '        .store_offset_i(prf_store_offsets), .store_precomputed_i(prf_precomputed_store_addresses), .store_address_o(prf_store_address),')
    return change(text,'''        .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .kill_valid_i(recovery_domains[6]),''',
        '''        .source_select_o(completion_source_select),
        .clk_i(clk_i), .reset_i(reset_i), .flush_i(flush_i), .kill_valid_i(recovery_domains[6]),''')


def make(name,parent,role):
    verify_parent(parent)
    out=prepare(name,parent,{'rtl/backend/rv32_completion_network.v':completion,
        'rtl/backend/rv32_backend_joint.v':backend,'rtl/rv32_physical_register_file.v':prf},role)
    pm=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))
    record_delta(out,parent,pm['implemented_groups']+['prearbitration_producer_store_address_queries'])
    path=out/'candidate.json'
    cm=json.loads(path.read_text(encoding='utf-8'))
    cm.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        measured_parent_run='F:/CPU2026CourseRuns/architecture_ER1_20261005',
        measured_reference_run='F:/CPU2026CourseRuns/architecture_ER1_20261005',
        source_parent=str(parent),new_declared_sequential_state_bits=0,
        declared_additional_state_bits_vs_parent=0,ordinary_integer_pipeline_depth=10,
        extra_transaction_latency_cycles=0,
        active_profile=dict(BE_WIDTH=4,CDB_WIDTH=3,PRODUCERS=6,
            previous_simm12_adders=20,new_producer_adders=24,new_branch_link_adders=4,
            unchanged_stored_read_adders=4,total_allocation_simm12_adders=32,
            extra_adders_vs_ER1=12,source_query_bits=24,precomputed_bus_bits=512),
        behavior='Same direct completion masks, full live/tag/generation/hold/reset/flush authority, current dispatch offsets, branch link override and highest matching PRF write priority. Producer arithmetic moves before source arbitration. Optional standalone fallbacks retained; no extra state, edge, handshake or program cycle.',
        source_evidence=['F:/CPU2026Proofs/ER1_mapped_paths_20261005/saved_path_analysis.json',
            'F:/CPU2026Proofs/ER1_existing_reports_20261005/summary.json'],
        adoption_condition='Complete new source/one-hot/default/branch-link/offset/parameter/clock review and all justified batch changes; then freeze, report and one combined timing-only run. No ET/EU intermediate test.',
        limitations=['Binary source identity derivation only; no HDL or formal or CPU or EDA invoked.',
            'Extra parallel adders, masks and buffers may exceed area budget or expose another critical path; no MHz/area prediction.',
            'Inherits existing EP cache first-hit extra cycle; IPC/function remain unmeasured.'])
    path.write_text(json.dumps(cm,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_groups=len(cm['implemented_groups']),tests_started=False,adopted=False)))


def main():
    make('ET_prearbitration_producer_store_addresses',ROOT/'ER1_parallel_lsq_pick_slot_identity',
        'Conditional source-only extension of ER1: parallel producer-based allocation address queries before completion source selection; preserve direct masks, branch-link priority, defaults, PRF matching and current dispatch offsets.')
    make('EU_prefix_pick_and_prearbitration_store_addresses',ROOT/'ES_lsq_circular_prefix_packet',
        'Complete source-only combination: ES circular prefix packet plus producer-side allocation store sums before CDB arbitration. Address authority and zero/default/branch-link/current-offset behavior retained; zero new state or transaction cycles.')


if __name__=='__main__':
    main()
