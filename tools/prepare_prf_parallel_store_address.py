"""Isolated EF alternative: commute signed-12 address addition with PRF bypass."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def prf(text):
    text=change(text,'    parameter integer LOCAL_VALUE_ROWS = 0,', '''    parameter integer LOCAL_VALUE_ROWS = 0,
    // Optional combination output for even allocation read ports only.
    // The original read data/ready and storage updates remain independent.
    parameter integer STORE_ADDRESS_READ = 0,''')
    text=change(text,'    input  wire [BE_WIDTH-1:0]           write_valid_i\n);', '''    input  wire [BE_WIDTH-1:0]           write_valid_i,
    input  wire [BE_WIDTH*12-1:0]        store_offset_i,
    output wire [BE_WIDTH*32-1:0]       store_address_o
);''')
    text=change(text, '''            rv32_frequency_control_tree #(.LEAVES(2)) bypass_choice_tree (
                .signal_i(bypass_write),.views_o(bypass_select));''', '''            rv32_frequency_control_tree #(.LEAVES(2)) bypass_choice_tree (
                .signal_i(bypass_write),.views_o(bypass_select));
            if((rp%2)==0) begin:g_store_address_output
                if(STORE_ADDRESS_READ!=0) begin:g_parallel_calculation
                    wire [BE_WIDTH:0] address_events;
                    wire [(BE_WIDTH+1)*32-1:0] address_values;
                    // The fallback is the SAME un-bypassed read-tree value.
                    // P0 and out-of-range rows already read zero from this tree.
                    assign address_events[0]=!bypass_write;
                    rv32_frequency_add_simm12 stored_address (
                        .base_i(stored_tree[1]),
                        .immediate_i(store_offset_i[(rp/2)*12 +: 12]),
                        .sum_o(address_values[0 +: 32]));
                    for(genvar address_lane=0;address_lane<BE_WIDTH;address_lane=address_lane+1) begin:g_write_address
                        // Reuse legal/write-valid/phys equality. Highest write
                        // lane still wins, including the branch-link lane.
                        assign address_events[address_lane+1]=bypass_match[address_lane];
                        rv32_frequency_add_simm12 write_address (
                            .base_i(write_data_i[address_lane*32 +: 32]),
                            .immediate_i(store_offset_i[(rp/2)*12 +: 12]),
                            .sum_o(address_values[(address_lane+1)*32 +: 32]));
                    end
                    rv32_frequency_event_select #(.WIDTH(32),.EVENTS(BE_WIDTH+1),.PRIORITY(1)) address_selector (
                        .events_i(address_events),.values_i(address_values),.write_o(),
                        .value_o(store_address_o[(rp/2)*32 +: 32]));
                end else begin:g_disabled
                    assign store_address_o[(rp/2)*32 +: 32]=0;
                end
            end''')
    return change(text, '    end else begin : g_original_read\n', '''    end else begin : g_original_read
    // The backend only selects this extra output with parallel read enabled.
    assign store_address_o=0;
''')


def backend(text):
    text=change(text, '''    parameter integer STORE_ALLOC_EARLY_ADDRESS = 1,''', '''    // 0 removes the optional allocation-edge address, 1 uses the original
    // post-read adder, 2 selects parallel PRF address candidates when supported.
    parameter integer STORE_ALLOC_EARLY_ADDRESS = 1,''')
    text=change(text, '            if(STORE_ALLOC_EARLY_ADDRESS!=0) begin:g_alloc_address_enabled', '''            if(STORE_ALLOC_EARLY_ADDRESS!=0) begin:g_alloc_address_enabled''')
    text=change(text, '                if(STORE_ALLOC_IMM12!=0) begin:g_store_alloc_simm12', '''                if(STORE_ALLOC_EARLY_ADDRESS==2 && STORE_ALLOC_IMM12!=0 && PRF_READ_MUX_IMPL!=0) begin:g_parallel_prf_address
                    assign lsq_alloc_addr[io_lane*32 +: 32]=prf_store_address[io_lane*32 +: 32];
                end else if(STORE_ALLOC_IMM12!=0) begin:g_store_alloc_simm12''')
    anchor='    rv32_physical_register_file #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS), .READ_MUX_IMPL(PRF_READ_MUX_IMPL), .LOCAL_VALUE_ROWS(1)) prf ('
    text=change(text,anchor, '''    localparam integer PARALLEL_STORE_ADDRESS=(STORE_ALLOC_EARLY_ADDRESS==2) &&
        (STORE_ALLOC_IMM12!=0) && (PRF_READ_MUX_IMPL!=0);
    wire [BE_WIDTH*12-1:0] prf_store_offsets;
    wire [BE_WIDTH*32-1:0] prf_store_address;
    generate for(genvar store_offset_lane=0;store_offset_lane<BE_WIDTH;store_offset_lane=store_offset_lane+1) begin:g_store_offset
        assign prf_store_offsets[store_offset_lane*12 +: 12]=d_imm[store_offset_lane*32 +: 12];
    end endgenerate
    rv32_physical_register_file #(.BE_WIDTH(BE_WIDTH), .PHYS_REGS(PHYS_REGS), .READ_MUX_IMPL(PRF_READ_MUX_IMPL), .LOCAL_VALUE_ROWS(1), .STORE_ADDRESS_READ(PARALLEL_STORE_ADDRESS)) prf (''')
    return change(text, '''        .clk_i(clk_i), .reset_i(reset_i), .read_phys_i(prf_read_phys), .read_data_o(prf_read_data), .read_ready_o(prf_read_ready),''', '''        .clk_i(clk_i), .reset_i(reset_i), .read_phys_i(prf_read_phys), .read_data_o(prf_read_data), .read_ready_o(prf_read_ready),
        .store_offset_i(prf_store_offsets), .store_address_o(prf_store_address),''')


def core(text):
    return change(text, '    rv32_backend_joint #(.STORE_ALLOC_EARLY_ADDRESS(0),',
                  '    rv32_backend_joint #(.STORE_ALLOC_EARLY_ADDRESS(2),')


def main():
    parent=ROOT/'EF_rob_commit_packet_domains'
    verify_parent(parent)
    out=prepare('EG_prf_parallel_store_address',parent,
        {'rtl/rv32_physical_register_file.v':prf,
         'rtl/backend/rv32_backend_joint.v':backend,'rtl/cpu_core.v':core},
        'Conditional EF alternative: restore allocation-edge early store addresses with addition computed in parallel for stored PRF data and all original writeback candidates, then reuse original legal/phys/write-valid highest-lane priority. No new state or cycles, no new normal ROB authority bypass. Trades more adders for eliminating addition after PRF bypass selection. Source-only, unadopted/unmeasured.')
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    groups=[g for g in groups if g!='shared_or_ordinary_store_address_without_allocation_adder']
    record_delta(out,parent,groups+['parallel_prf_allocation_store_address_candidates'])
    path=out/'candidate.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        declared_additional_state_bits_vs_parent=0,new_declared_sequential_state_bits=0,
        existing_clocked_payload_refactor='Inherited EF forwarding hold owner, no new clocked logic.',
        measured_parent_run=None,measured_reference_run='F:/CPU2026CourseRuns/architecture_EA_20261005',
        behavior='Allocation early address timing behavior restored to EA: same original ready/valid guard and address function. Ordinary PRF data/ready, normal RS issue, complete identity authority and store commit retained. No additional pipeline cycle.',
        address_adder_formula='BE_WIDTH*(1+BE_WIDTH) with enabled parallel signed-12 allocation address; current 20 versus EA 4 or EF 0 allocation adders.',
        timing_tradeoff='Addresses from stored data and each original PRF writeback data run alongside bypass control. CDB value mux itself remains. Additional adders and data/offset loads may introduce new delay/area; no gain claimed.',
        area_scale_evidence='EA measured signed-12 adder 14.215500 um2; extra 16 vs EA about 227.448 um2, complete 20 vs EF about 284.310 um2 before new selectors/buffers/re-mapping.',
        adoption_condition='First inspect completed EF frequency/area/path evidence. Review potential allocation-ready IPC tradeoff versus EG extra logic; report full chosen scope before any new measurement.')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         adopted=False,tests_started=False,new_declared_state_bits=0)))


if __name__=='__main__':
    main()
