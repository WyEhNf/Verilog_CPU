"""Prepare polarity-aware bounded distribution, without any HDL/EDA run."""
import hashlib
import json
from pathlib import Path

from prepare_staged_frequency_candidate import ROOT, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


NEGATIVE_TREE='''// Internal distribution receives a NEGATIVE representation and returns
// positive leaves. Every leaf has its own inverter; internal nodes retain a
// negative representation using two real inverters and at most four children.
// Thus no alias leaf can expose a parent directly to its payload consumer load.
module rv32_frequency_negative_subtree #(
    parameter integer WIDTH=1,LEAVES=1
) (
    input wire [WIDTH-1:0] negative_i,
    output wire [WIDTH*LEAVES-1:0] views_o
);
    localparam integer CHILDREN=LEAVES>4?4:LEAVES;
    localparam integer BASE_COUNT=LEAVES/CHILDREN;
    localparam integer EXTRA_COUNT=LEAVES%CHILDREN;
    genvar bit_id,child;
    generate if(LEAVES==1) begin:g_leaf
        for(bit_id=0;bit_id<WIDTH;bit_id=bit_id+1) begin:g_driver
            (* keep=1,keep_hierarchy=1 *)
            rv32_frequency_inversion restore_positive (
                .signal_i(negative_i[bit_id]),.signal_o(views_o[bit_id]));
        end
    end else begin:g_internal
        wire [WIDTH-1:0] positive,distributed_negative;
        for(bit_id=0;bit_id<WIDTH;bit_id=bit_id+1) begin:g_driver
            (* keep=1,keep_hierarchy=1 *)
            rv32_frequency_inversion invert_root (
                .signal_i(negative_i[bit_id]),.signal_o(positive[bit_id]));
            (* keep=1,keep_hierarchy=1 *)
            rv32_frequency_inversion invert_output (
                .signal_i(positive[bit_id]),.signal_o(distributed_negative[bit_id]));
        end
        for(child=0;child<CHILDREN;child=child+1) begin:g_child
            localparam integer COUNT=BASE_COUNT+(child<EXTRA_COUNT);
            localparam integer OFFSET=child*BASE_COUNT+
                (child<EXTRA_COUNT?child:EXTRA_COUNT);
            rv32_frequency_negative_subtree #(.WIDTH(WIDTH),.LEAVES(COUNT)) subtree (
                .negative_i(distributed_negative),
                .views_o(views_o[OFFSET*WIDTH +: COUNT*WIDTH]));
        end
    end endgenerate
endmodule

// One inversion produces a negative representation at the root. Negative
// internal nodes distribute it; individual leaf inverters restore the original
// positive signal. For LEAVES>1 this removes two serial inversions on every
// path and LEAVES+1 inverter instances per bit versus the old positive-node
// tree. Each internal driver still owns at most four child gate inputs.
// LEAVES=1 remains a two-inverter, positive-output leaf.
module rv32_frequency_control_tree #(
    parameter integer WIDTH=1,
    parameter integer LEAVES=4
) (
    input wire [WIDTH-1:0] signal_i,
    output wire [WIDTH*LEAVES-1:0] views_o
);
    localparam integer CHILDREN=LEAVES>4?4:LEAVES;
    localparam integer BASE_COUNT=LEAVES/CHILDREN;
    localparam integer EXTRA_COUNT=LEAVES%CHILDREN;
    wire [WIDTH-1:0] negative;
    genvar bit_id,child;
    generate
        for(bit_id=0;bit_id<WIDTH;bit_id=bit_id+1) begin:g_driver
            (* keep=1,keep_hierarchy=1 *)
            rv32_frequency_inversion invert_root (
                .signal_i(signal_i[bit_id]),.signal_o(negative[bit_id]));
        end
        if(LEAVES==1) begin:g_leaf
            rv32_frequency_negative_subtree #(.WIDTH(WIDTH),.LEAVES(1)) subtree (
                .negative_i(negative),.views_o(views_o));
        end else begin:g_branches
            for(child=0;child<CHILDREN;child=child+1) begin:g_child
                localparam integer COUNT=BASE_COUNT+(child<EXTRA_COUNT);
                localparam integer OFFSET=child*BASE_COUNT+
                    (child<EXTRA_COUNT?child:EXTRA_COUNT);
                rv32_frequency_negative_subtree #(.WIDTH(WIDTH),.LEAVES(COUNT)) subtree (
                    .negative_i(negative),
                    .views_o(views_o[OFFSET*WIDTH +: COUNT*WIDTH]));
            end
        end
    endgenerate
endmodule
'''


def distribution(t):
    start=t.index('// Four-way recursive distribution with a pair of real inversions at each')
    end=t.index('// Preserve the legacy optional interface without importing external cells.',start)
    return t[:start]+NEGATIVE_TREE+'\n'+t[end:]


if __name__=='__main__':
    parent=ROOT/'DT_completion_local_prf_enable'
    verify_parent(parent)
    out=prepare('DV_negative_polarity_distribution',parent,
        {'rtl/common/rv32_asap7_fanout.v':distribution},
        'Post-DT alternative: share a negative representation through the bounded fanout tree and restore positive polarity at each isolated consumer leaf. Root one inversion, negative internal node two inversions, leaf one inversion. No bypassed leaf driver, blackbox, library change, new state or clock edge. Source-only and unadopted.')
    record_delta(out,parent,['allocation_store_signed_12bit_adder','prf_compare_before_completion',
        'late_lsq_completion_grants','fused_producer_to_prf_operand_bypass','completion_local_prf_write_enable',
        'negative_polarity_distribution'])
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    manifest['actual_preparation_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest['internal_driver_child_gate_bound']=4
    manifest['preserves_individual_payload_leaf_driver']=True
    manifest['source_inverter_saving_per_bit']='LEAVES+1 for LEAVES>1; zero for LEAVES=1'
    manifest['source_path_inverter_depth_reduction']='two for every path in a tree with LEAVES>1; zero for LEAVES=1'
    manifest['mapped_gain_proven']=False
    manifest['new_declared_sequential_state_bits']=0
    manifest['adoption_condition']='Review DT first, then complete source review and deliver a concrete next-batch report before any measurement. Do not reuse DT measured metrics for this alternative.'
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'candidate':str(out),'manifest_sha256':hashlib.sha256((out/'candidate.json').read_bytes()).hexdigest(),
                      'tests_started':False,'adopted':False},ensure_ascii=False))
