"""Prepare EA alternative removing allocation-edge store-address arithmetic."""
import hashlib
import json
from pathlib import Path
from prepare_staged_frequency_candidate import ROOT, change, prepare
from prepare_prf_precompare_and_store_imm12 import verify_parent, record_delta


def backend(text):
    text=change(text, '    parameter integer STORE_ALLOC_IMM12 = 0,', '''    parameter integer STORE_ALLOC_IMM12 = 0,
    // Independent control of the opportunistic allocation-edge address.
    // Ordinary AGU and EARLY_STORE_ADDRESS=2 shared probing remain available.
    parameter integer STORE_ALLOC_EARLY_ADDRESS = 1,''')
    start=text.index('            // Publish only an already-ready store base at allocation.')
    end=text.index('            assign prf_read_phys[(2*io_lane)*PAW +: PAW] =',start)
    old=text[start:end]
    body=old[old.index('            assign lsq_alloc_addr_valid'):]
    indented=''.join('    '+line if line.strip() else line for line in body.splitlines(keepends=True))
    replacement='''            // An allocation may advertise an address only when this
            // optional path is enabled. Disabled payload is constant as well,
            // so an unused PRF -> adder -> LSQ write cone can be removed.
            if(STORE_ALLOC_EARLY_ADDRESS!=0) begin:g_alloc_address_enabled
'''+indented+'''            end else begin:g_shared_or_ordinary_address
                assign lsq_alloc_addr_valid[io_lane]=1'b0;
                assign lsq_alloc_addr[io_lane*32 +: 32]=32'b0;
            end
'''
    return text[:start]+replacement+text[end:]


def core(text):
    return change(text, '    rv32_backend_joint #(.LSQ_ROB_QUERY_PREDECODE(1), .STORE_ALLOC_IMM12(1),',
                  '    rv32_backend_joint #(.STORE_ALLOC_EARLY_ADDRESS(0), .LSQ_ROB_QUERY_PREDECODE(1), .STORE_ALLOC_IMM12(1),')


def main():
    parent=ROOT/'EA_combined_control_locality'
    verify_parent(parent)
    out=prepare('ED_ea_shared_only_store_address',parent,
        {'rtl/backend/rv32_backend_joint.v':backend,'rtl/cpu_core.v':core},
        'Conditional EA alternative: disable only allocation-edge early store address and constant its payload, eliminating that optional PRF-to-four-adders-to-LSQ cone. Retain linked shared early-address probe, normal RS wake/issue, ordinary AGU, full tags and store commit. Zero added state; possible address availability / younger-load delay. Unadopted and unmeasured.')
    groups=json.loads((parent/'candidate.json').read_text(encoding='utf-8'))['implemented_groups']
    groups=[g for g in groups if g!='allocation_store_signed_12bit_adder']
    record_delta(out,parent,groups+['shared_or_ordinary_store_address_without_allocation_adder'])
    path=out/'candidate.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    manifest.update(actual_preparation_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        declared_additional_state_bits_vs_parent=0,new_declared_sequential_state_bits=0,
        behavior='CPU disables allocation-time early store address; shared EARLY_STORE_ADDRESS=2 probe and normal tagged ALU address updates remain. Ordinary integer pipeline remains 10 stages.',
        measured_parent_run=None,measured_reference_run='F:/CPU2026CourseRuns/architecture_DM1_20261005',
        timing_tradeoff='Cuts allocation PRF-to-address addition. Already-ready new stores lose allocation-edge publication, shared probing serves at most one store per cycle; no bound on IPC loss is claimed.',
        adoption_condition='Inspect actual EA critical endpoints/aliases first. Adopt only if allocation store-address arithmetic is a material limiter, then review address readiness tradeoff and report combined scope before measurement.')
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(candidate=str(out),manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         adopted=False,tests_started=False,new_declared_state_bits=0)))


if __name__=='__main__':
    main()
