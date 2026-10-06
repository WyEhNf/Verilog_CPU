"""Add the decoder-contracted store AGU to DX; source edits only."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, prepare, change
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def backend(t):
    return change(t, '''        rv32_frequency_add32_select address_adder (
            .lhs_i(selected_base),.rhs_i(selected_imm),.sum_o(shared_store_addr));''', '''        if(STORE_ALLOC_IMM12!=0) begin:g_decoder_store_offset
            // The CPU enables this signed-12-bit contract for all decoded
            // stores, including the shared probe. Standalone trace backends
            // retain full-width arithmetic with the default-disabled option.
            rv32_frequency_add_simm12 address_adder (
                .base_i(selected_base),.immediate_i(selected_imm[11:0]),
                .sum_o(shared_store_addr));
        end else begin:g_generic_store_offset
            rv32_frequency_add32_select address_adder (
                .lhs_i(selected_base),.rhs_i(selected_imm),.sum_o(shared_store_addr));
        end''')


def main():
    parent=ROOT/'DX_dm1_request_locality_and_predecode'
    verify_parent(parent)
    out=prepare('DY_dm1_locality_and_store_simm12',parent,
        {'rtl/backend/rv32_backend_joint.v':backend},
        'Combine DX locality/predecode/negative-polarity distribution and allocation signed-12-bit arithmetic with the same specialized arithmetic on the shared store AGU. CPU-decoded stores use a signed 12-bit displacement; standalone trace default remains full-width. No new clock edge or state; source only.')
    record_delta(out,parent,['allocation_store_signed_12bit_adder','shared_store_signed_12bit_adder',
        'negative_polarity_distribution','local_lsq_request_and_forwarding_owner',
        'lsq_report_rob_slot_predecode'])
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        mapped_gain_proven=False,new_declared_sequential_state_bits=0,
        signed_immediate_contract='STORE_ALLOC_IMM12=1 applies the CPU signed-12-bit store displacement contract to allocation and shared store-address arithmetic. Default 0 retains full-width trace arithmetic.')
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'candidate':str(out),'manifest_sha256':hashlib.sha256((out/'candidate.json').read_bytes()).hexdigest(),
                      'tests_started':False,'adopted':False}))


if __name__=='__main__':main()
