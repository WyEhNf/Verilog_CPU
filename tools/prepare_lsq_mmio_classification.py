"""Prepare conditional EQ off-tree; leave the running EP inputs untouched."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def lsq(text):
    text=change(text,'    output wire                         dcache_req_is_store_o,',
        '''    output wire                         dcache_req_is_store_o,
    output wire                         dcache_req_mmio_exit_o,''')
    text=change(text,'    wire selection_load,selection_unsigned;',
        '    wire selection_load,selection_unsigned,selection_mmio_exit;')
    text=change(text,'    localparam integer SELECTION_PAYLOAD_WIDTH=SLOT_WIDTH+TAG_WIDTH+ROB_TAG_WIDTH+72;',
        '''    // Move transaction classification across the existing selection
    // edge, before request-valid gating and the wide line mask formatter.
    wire pick_mmio_exit=!pick_load && pick_addr[1]==32'h80000000 && pick_store_mask==4'hf;
    wire selected_mmio_exit=(REQUEST_PIPELINE!=0)?selection_mmio_exit:pick_mmio_exit;
    localparam integer SELECTION_PAYLOAD_WIDTH=SLOT_WIDTH+TAG_WIDTH+ROB_TAG_WIDTH+73;''')
    text=change(text,'        .data_i({pick_slot[1],make_lsq_tag(pick_slot[1],pick_generation),pick_rob_tag,',
        '        .data_i({pick_mmio_exit,pick_slot[1],make_lsq_tag(pick_slot[1],pick_generation),pick_rob_tag,')
    text=change(text,'        .data_o({selection_slot,selection_lsq_tag,selection_rob_tag,selection_addr,',
        '        .data_o({selection_mmio_exit,selection_slot,selection_lsq_tag,selection_rob_tag,selection_addr,')
    text=change(text,'    assign dcache_req_addr_o=selected_addr;',
        '''    assign dcache_req_addr_o=selected_addr;
    // Retain the original full live/generation/commit/request admission.
    // Address 80000000 has offset zero; store_mask f is exactly line mask000f.
    assign dcache_req_mmio_exit_o=dcache_req_valid_o && selected_mmio_exit;''')
    return text


def backend(text):
    text=change(text,'    output wire                         dcache_req_is_store_o,',
        '''    output wire                         dcache_req_is_store_o,
    output wire                         dcache_req_mmio_exit_o,''')
    return change(text,'.dcache_req_is_store_o(dcache_req_is_store_o),',
        '.dcache_req_is_store_o(dcache_req_is_store_o), .dcache_req_mmio_exit_o(dcache_req_mmio_exit_o),')


def core(text):
    text=change(text,'    wire memory_dreq_unsigned;',
        '    wire memory_dreq_unsigned, memory_dreq_mmio_exit;\n    wire dcache_req_mmio_exit;')
    text=change(text,'    localparam integer DREQ_PAYLOAD_WIDTH = 181 + 2*ROB_TAG_WIDTH;',
        '''    // Carry the classification beside the complete original packet
    // when the optional CPU request register is enabled. The active course
    // profile is direct here; LSQ already captures classification and fields.
    generate if(SERIAL_BACKEND!=0) begin:g_serial_mmio_classification
        assign dcache_req_mmio_exit=dcache_req_store &&
            dcache_req_addr==32'h80000000 && dcache_req_mask==16'h000f;
    end endgenerate
    localparam integer DREQ_PAYLOAD_WIDTH = 182 + 2*ROB_TAG_WIDTH;''')
    text=change(text,'    wire [DREQ_PAYLOAD_WIDTH-1:0] dreq_payload_in = {\n        dcache_req_load,',
        '    wire [DREQ_PAYLOAD_WIDTH-1:0] dreq_payload_in = {\n        dcache_req_mmio_exit, dcache_req_load,')
    text=change(text,'    assign {memory_dreq_load, memory_dreq_store, memory_dreq_addr, memory_dreq_size,',
        '    assign {memory_dreq_mmio_exit, memory_dreq_load, memory_dreq_store, memory_dreq_addr, memory_dreq_size,')
    text=change(text,'''    wire mmio_exit_request = memory_dreq_valid && memory_dreq_store &&
                             (memory_dreq_addr == 32'h80000000) &&
                             (memory_dreq_mask == 16'h000f);''',
        '''    wire mmio_exit_request = memory_dreq_valid && memory_dreq_mmio_exit;''')
    # Only the joint backend owns the new port; the legacy serial instance
    # remains unchanged and uses the direct full-predicate fallback above.
    anchor='    rv32_backend_joint #('
    assert text.count(anchor)==1
    head,tail=text.split(anchor,1)
    tail=change(tail,'.dcache_req_is_store_o(dcache_req_store),',
        '.dcache_req_is_store_o(dcache_req_store), .dcache_req_mmio_exit_o(dcache_req_mmio_exit),')
    return head+anchor+tail


def main():
    parent=ROOT/'EP_lsq_selection_payload_word_owners'
    verify_parent(parent)
    transforms={'rtl/backend/rv32_lsq.v':lsq,'rtl/backend/rv32_backend_joint.v':backend,'rtl/cpu_core.v':core}
    for n,f in transforms.items():
        f((parent/n).read_text(encoding='utf-8'))
    out=prepare('EQ_lsq_registered_mmio_classification',parent,transforms,
        'Conditional existing-selection-edge MMIO classification sideband. Cut formatted mask/store/32-bit address decode after request-valid. Keep full request authority and complete packet; active profile +1 state bit/no cycle. Source only, not adopted/tested.')
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    record_delta(out,parent,groups+['lsq_existing_edge_mmio_classification'])
    path=out/'candidate.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    data.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        new_declared_sequential_state_bits=1,declared_additional_state_bits_vs_parent=1,
        active_profile_additional_state_bits=1,
        optional_CPU_request_register_additional_state_bits=1,
        active_profile_CPU_request_register_enabled=False,
        ordinary_integer_pipeline_depth=10,extra_transaction_latency_cycles=0,
        behavior='Inherits EP including intentional +1 empty-slot load-hit reply. Add one LSQ selection payload bit for the exact unqualified exit classification; request-valid/live/commit/gen/reset/recovery still qualify. Carry classifier with original packet in optional CPU skid; serial backend retains full original predicate. Active profile1 additional LSQ bit, no CPU request skid, no added stage.',
        preparation_relation='Post-dispatch conditional research off-tree. No running EP/main/frozen input modified.',
        selection_payload_width_expression='SLOT_WIDTH+TAG_WIDTH+ROB_TAG_WIDTH+73',
        active_profile_selection_payload_bits=111,
        measured_reference_run='F:/CPU2026CourseRuns/architecture_EL1_20261005',
        adoption_condition='Only reconsider if completed EP timing still limits through MMIO classification/request-mask qualification. Review source and report before any new measurement; no EQ test now.')
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_groups=len(data['implemented_groups']),active_profile_additional_state_bits=1,
        tests_started=False,adopted=False)))


if __name__=='__main__':
    main()
