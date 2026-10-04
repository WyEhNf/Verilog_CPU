"""Combine two source-only post-DT alternatives; do not run tools/tests."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT,prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent,record_delta
from prepare_negative_polarity_distribution import distribution


if __name__=='__main__':
    parent=ROOT/'DU_lsq_report_rob_predecode'
    verify_parent(parent)
    out=prepare('DW_predecode_and_polarity',parent,
        {'rtl/common/rv32_asap7_fanout.v':distribution},
        'Combine DU early LSQ ROB-slot bank-mask decoding with DV negative-polarity bounded distribution. Retain DT full authority, ordinary tags and cycles. Main DT timing inputs remain untouched; unadopted and unmeasured until result review and a new pretest report.')
    record_delta(out,parent,['allocation_store_signed_12bit_adder','prf_compare_before_completion',
        'late_lsq_completion_grants','fused_producer_to_prf_operand_bypass','completion_local_prf_write_enable',
        'lsq_report_rob_slot_predecode','negative_polarity_distribution'])
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        adoption_condition='Review DT measurement before choosing DV alone or combined DW; deliver a new complete pretest report before any subsequent measurement.',
        new_declared_sequential_state_bits=0,report_payload_width_current_configuration=91,
        internal_driver_child_gate_bound=4,preserves_individual_payload_leaf_driver=True,
        mapped_gain_proven=False)
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'candidate':str(out),'manifest_sha256':hashlib.sha256((out/'candidate.json').read_bytes()).hexdigest(),
        'tests_started':False,'adopted':False},ensure_ascii=False))
