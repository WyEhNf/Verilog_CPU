"""Factor direct-mode write-enable alongside grants; no EDA or tests."""
import hashlib
import json
from pathlib import Path

from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def completion(t):
    t=change(t, '    parameter integer READ_DIRECT_VALUE = 0\n) (', '''    parameter integer READ_DIRECT_VALUE = 0,
    parameter integer DIRECT_PRF_ENABLE = 0
) (''')
    return change(t, '    assign prf_write_valid_o = cdb_valid_o & cdb_rd_we_o;', '''    // In direct mode the same write-enable is the OR of selected writable
    // sources. Resolve this single-bit field beside arbitration instead of
    // waiting for the wide metadata payload's distribution/readback.
    genvar write_enable_lane,write_enable_source;
    generate if(BYPASS==2 && DIRECT_PRF_ENABLE!=0) begin:g_local_prf_write_enable
        for(write_enable_lane=0;write_enable_lane<BE_WIDTH;write_enable_lane=write_enable_lane+1) begin:g_lane
            if(write_enable_lane<CDB_WIDTH) begin:g_active
                wire [SOURCES-1:0] writing_sources;
                for(write_enable_source=0;write_enable_source<SOURCES;write_enable_source=write_enable_source+1) begin:g_source
                    assign writing_sources[write_enable_source]=selected_mask[write_enable_lane][write_enable_source] &&
                        producer_rd_we_i[write_enable_source] && !producer_is_store_i[write_enable_source];
                end
                assign prf_write_valid_o[write_enable_lane]=!reset_i && !flush_i && (|writing_sources);
            end else begin:g_unused
                assign prf_write_valid_o[write_enable_lane]=1'b0;
            end
        end
    end else begin:g_original_prf_write_enable
        assign prf_write_valid_o = cdb_valid_o & cdb_rd_we_o;
    end endgenerate''')


def backend(t):
    return change(t, ' .READ_DIRECT_VALUE(PRF_VALUE_BYPASS_ENABLED)) completion (',
                 ' .READ_DIRECT_VALUE(PRF_VALUE_BYPASS_ENABLED), .DIRECT_PRF_ENABLE(PRF_VALUE_BYPASS_ENABLED)) completion (')


if __name__=='__main__':
    parent=ROOT/'DS_direct_prf_operand_bypass'
    verify_parent(parent)
    out=prepare('DT_completion_local_prf_enable',parent,
        {'rtl/backend/rv32_completion_network.v':completion,
         'rtl/backend/rv32_backend_joint.v':backend},
        'Combine DP/DQ/DR/DS with direct-mode PRF write-enable factored from the identical selected writable sources, retaining full eligibility, reset/flush and actual write-valid qualification of fused operand routing. No new state or cycles.')
    record_delta(out,parent,['allocation_store_signed_12bit_adder','prf_compare_before_completion',
                            'late_lsq_completion_grants','fused_producer_to_prf_operand_bypass',
                            'completion_local_prf_write_enable'])
    manifest=json.loads((out/'candidate.json').read_text(encoding='utf-8'))
    manifest['actual_preparation_script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    manifest['source_review']='Source equations and manual one-hot/priority algebra only; no HDL compiler, lint, simulation, synthesis, STA or formal run.'
    (out/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'candidate':str(out),
        'manifest_sha256':hashlib.sha256((out/'candidate.json').read_bytes()).hexdigest(),
        'tests_started':False,'adopted':False},ensure_ascii=False))
