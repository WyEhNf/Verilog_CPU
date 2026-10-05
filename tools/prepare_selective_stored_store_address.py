"""Prepare EV off-tree: only stable stored bases publish allocation addresses."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def prf(text):
    text=change(text,'    parameter integer STORE_ADDRESS_PRECOMPUTED = 0,',
        '''    parameter integer STORE_ADDRESS_PRECOMPUTED = 0,
    // Independent optional stored-base address output. Ordinary data/ready
    // and all same-cycle wake/bypass/write storage behavior remain original.
    parameter integer STORE_ADDRESS_STORED_ONLY = 0,''')
    text=change(text,'    output wire [BE_WIDTH*32-1:0]       store_address_o\n);',
        '''    output wire [BE_WIDTH*32-1:0]       store_address_o,
    output wire [BE_WIDTH-1:0]          store_address_stored_valid_o
);''')
    text=change(text,'''            if((rp%2)==0) begin:g_store_address_output
                if(STORE_ADDRESS_READ!=0) begin:g_parallel_calculation''',
        '''            if((rp%2)==0) begin:g_store_address_output
                // A matching write always wins the ordinary value read.
                // Therefore do not advertise its old stored value as address,
                // even when the stored row was already marked ready.
                assign store_address_stored_valid_o[rp/2]=
                    (STORE_ADDRESS_READ!=0) && (STORE_ADDRESS_STORED_ONLY!=0) &&
                    ((address==0) || ready_tree[1]) && !bypass_write;
                if(STORE_ADDRESS_READ!=0 && STORE_ADDRESS_STORED_ONLY!=0) begin:g_stored_only
                    rv32_frequency_add_simm12 stored_address (
                        .base_i(stored_tree[1]),
                        .immediate_i(store_offset_i[(rp/2)*12 +: 12]),
                        .sum_o(store_address_o[(rp/2)*32 +: 32]));
                end else if(STORE_ADDRESS_READ!=0) begin:g_parallel_calculation''')
    return change(text,'    assign store_address_o=0;\n    // Reads are combinational.',
        '    assign store_address_o=0;\n    assign store_address_stored_valid_o=0;\n    // Reads are combinational.')


def backend(text):
    text=change(text,'    // post-read adder, 2 selects parallel PRF address candidates when supported.',
        '''    // post-read adder, 2 selects parallel PRF address candidates when supported,
    // 3 publishes only an already-stored ready base with no current WB override.
    // Deferred stores retain their ordinary RS/shared-probe/AGU transaction.''')
    text=change(text,'''                assign lsq_alloc_addr_valid[io_lane] = (EARLY_STORE_ADDRESS != 0) &&
                    d_valid[io_lane] && d_is_store[io_lane] && rs_src1_ready[io_lane];
                if(STORE_ALLOC_EARLY_ADDRESS==2 && STORE_ALLOC_IMM12!=0 && PRF_READ_MUX_IMPL!=0) begin:g_parallel_prf_address''',
        '''                assign lsq_alloc_addr_valid[io_lane] = (EARLY_STORE_ADDRESS != 0) &&
                    d_valid[io_lane] && d_is_store[io_lane] && rs_src1_ready[io_lane] &&
                    (!STORED_ONLY_ALLOC_ADDRESS || prf_store_address_stored_valid[io_lane]);
                if((STORE_ALLOC_EARLY_ADDRESS==2 || STORE_ALLOC_EARLY_ADDRESS==3) &&
                    STORE_ALLOC_IMM12!=0 && PRF_READ_MUX_IMPL!=0) begin:g_parallel_prf_address''')
    text=change(text,'''    localparam integer PARALLEL_STORE_ADDRESS=(STORE_ALLOC_EARLY_ADDRESS==2) &&
        (STORE_ALLOC_IMM12!=0) && (PRF_READ_MUX_IMPL!=0);''',
        '''    localparam integer PARALLEL_STORE_ADDRESS=(STORE_ALLOC_EARLY_ADDRESS==2) &&
        (STORE_ALLOC_IMM12!=0) && (PRF_READ_MUX_IMPL!=0);
    localparam integer STORED_ONLY_ALLOC_ADDRESS=(STORE_ALLOC_EARLY_ADDRESS==3) &&
        (STORE_ALLOC_IMM12!=0) && (PRF_READ_MUX_IMPL!=0);
    wire [BE_WIDTH-1:0] prf_store_address_stored_valid;''')
    text=change(text,'.STORE_ADDRESS_READ(PARALLEL_STORE_ADDRESS), .STORE_ADDRESS_PRECOMPUTED(SOURCE_STORE_ADDRESS)) prf (',
        '.STORE_ADDRESS_READ(PARALLEL_STORE_ADDRESS || STORED_ONLY_ALLOC_ADDRESS), .STORE_ADDRESS_PRECOMPUTED(SOURCE_STORE_ADDRESS), .STORE_ADDRESS_STORED_ONLY(STORED_ONLY_ALLOC_ADDRESS)) prf (')
    return change(text,'        .store_offset_i(prf_store_offsets), .store_precomputed_i(prf_precomputed_store_addresses), .store_address_o(prf_store_address),',
        '''        .store_offset_i(prf_store_offsets), .store_precomputed_i(prf_precomputed_store_addresses), .store_address_o(prf_store_address),
        .store_address_stored_valid_o(prf_store_address_stored_valid),''')


def core(text):
    return change(text,'.STORE_ALLOC_EARLY_ADDRESS(2), .LSQ_ROB_QUERY_PREDECODE(1)',
        '.STORE_ALLOC_EARLY_ADDRESS(3), .LSQ_ROB_QUERY_PREDECODE(1)')


def main():
    parent=ROOT/'EU_prefix_pick_and_prearbitration_store_addresses'
    verify_parent(parent)
    out=prepare('EV_selective_stored_store_allocation',parent,
        {'rtl/backend/rv32_backend_joint.v':backend,'rtl/rv32_physical_register_file.v':prf,'rtl/cpu_core.v':core},
        'Conditional source-only alternative: retain original ready/store/dispatch permission but publish allocation address only when stored PRF base is ready and no current WB overrides it. Current WB still supplies RS operand/ready; shared registered probe or ordinary AGU completes deferred address. Disable EU source-side address mesh statically, no new state. Store/load timing may change; not adopted/tested.')
    pm=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))
    record_delta(out,parent,pm['implemented_groups']+['selective_stored_only_allocation_address'])
    path=out/'candidate.json'
    cm=json.loads(path.read_text(encoding='utf-8'))
    cm.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_parent=str(parent),measured_parent_run=None,
        measured_reference_run='F:/CPU2026CourseRuns/architecture_ER1_20261005',
        new_declared_sequential_state_bits=0,declared_additional_state_bits_vs_parent=0,
        ordinary_integer_pipeline_depth=10,extra_transaction_latency_cycles=None,
        additional_store_address_opportunity_cycle_possible=True,
        behavior='Intentional address-availability tradeoff, not edge-for-edge equivalence. All ordinary PRF data/ready/bypass and RS allocation/wakeup, store links, full tag/generation/recovery, unknown-store-address hazard and commit permissions retained. Valid stable addresses are unchanged; deferred allocation payload is unobserved until tagged address update.',
        active_profile=dict(BE_WIDTH=4,CDB_WIDTH=3,EARLY_STORE_ADDRESS=2,STORE_ALLOC_EARLY_ADDRESS=3,
            SOURCE_STORE_ADDRESS=0,STORE_ADDRESS_STORED_ONLY=1,
            active_allocation_simm12_adders=4,previous_EU_allocation_simm12_adders=32,
            disabled_EU_producer_adders=24,disabled_EU_link_adders=4),
        implemented_groups_are_source_history_not_all_enabled_in_EV=True,
        disabled_source_group='prearbitration_producer_store_address_queries',
        adoption_condition='Source-review stable-address/PRF data and deferred RS/shared-probe/AGU lifecycle, masks/full tags/generation/recovery/commit. Adopt only after completed EU actual path/area and IPC tradeoff support. Report complete batch before any measurement; no EV test now.',
        limitations=['No HDL/elaboration/formal/simulation/synthesis/STA invoked.',
            'Clock block text identity does not imply identical addr_ready state transitions or program cycles.',
            'A newly WB-ready store can receive an address later; younger overlapping/unknown-address loads can wait. IPC loss unbounded/unmeasured.',
            'Ordinary same-cycle RS issue and source-value capture remain, but complete CPU correctness is not proved by source reading.',
            'Disabled RTL arithmetic removes the intended address data chain but late ready qualification may become limiting; no MHz/area prediction.'])
    path.write_text(json.dumps(cm,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_history_groups=len(cm['implemented_groups']),new_state_bits=0,
        address_timing_changed=True,tests_started=False,adopted=False)))


if __name__=='__main__':
    main()
