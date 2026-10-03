"""Stage real per-MSHR state ownership and local update decoding.

Each child owns the existing 76 bits at the actual EPOCH_WIDTH4 configuration.
Its next-state clauses are taken verbatim from the fixed-slot candidate,
renaming only signals/row references. Functional hierarchy remains priced and
timed; this is not a buffer cell, empty wrapper or synthesis exemption.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from prepare_icache_static_mshr import STATIC

BASE=Path('F:/CPU2026Candidates/icache_static_mshr_20261003')
FIELDS={'valid':1,'sent':1,'prefetch':1,'control_prefetch':1,'pc':32,'line':32,
        'demand_epoch':'EPOCH_WIDTH','txn_epoch':'EPOCH_WIDTH'}
INPUTS={
    'clk_i':1,'reset_i':1,'current_epoch_i':'EPOCH_WIDTH',
    'request_fire':1,'request_hit':1,'request_match_found':1,'request_match_index':32,'free_index':32,
    'if_req_pc_i':32,'request_line':32,'if_req_epoch_i':'EPOCH_WIDTH',
    'prefetch_step_allocates':1,'prefetch_control_stream':1,'prefetch_next_line':32,'prefetch_epoch':'EPOCH_WIDTH',
    'mem_req_valid_o':1,'mem_req_ready_i':1,'send_index':32,
    'mem_resp_valid_i':1,'mem_resp_ready_o':1,'response_target_found':1,'response_index':32,
    'control_target_allocate':1,'control_target':32}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace(code,old,new):
    assert code.count(old)==1,old
    return code.replace(old,new)


def width(size):
    return '' if size==1 else f'[{size-1}:0] ' if isinstance(size,int) else f'[{size}-1:0] '


def port(name):
    return name if name.endswith('_i') else name.removesuffix('_o')+'_i'


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--outdir',type=Path,required=True)
    out=ap.parse_args().outdir.resolve();assert not out.exists()
    source=BASE/'rtl/cache/rv32_icache_nonblocking.v'
    assert sha(source)=='458b8734e1f4f04825af40247b787504aefa4dbd6cf158ee2df3172f7b5ea110'
    original=source.read_text();assert original.count(STATIC)==1
    start=STATIC.index('            always @(posedge clk_i) begin')
    end=STATIC.index('\n        end\n    end endgenerate')
    original_process=STATIC[start:end]
    body='\n'.join(line[8:] for line in original_process.splitlines())
    renamed=body
    for field in FIELDS:renamed=renamed.replace(f'mshr_{field}[mshr_row]',field+'_o')
    assert not re.search(r'\bmshr_\w+\[',renamed)
    mapping={name:port(name) for name in INPUTS}|{'mshr_row':'ROW'}
    renamed=re.sub(r'\b[a-zA-Z_]\w*\b',lambda m:mapping.get(m[0],m[0]),renamed)
    # Independently undo every rename and confirm the original next-state
    # process was retained, including all concurrent-write priorities.
    reverse={value:key for key,value in mapping.items()}
    assert len(reverse)==len(mapping)
    restored=re.sub(r'\b[a-zA-Z_]\w*\b',lambda m:reverse.get(m[0],m[0]),renamed)
    for field in FIELDS:restored=re.sub(r'\b'+field+'_o'+r'\b',f'mshr_{field}[mshr_row]',restored)
    assert restored==body
    decls=[f'    input wire {width(size)}{port(name)}' for name,size in INPUTS.items()]
    decls += [f'    output reg {width(size)}{field}_o' for field,size in FIELDS.items()]
    child='''
// Functional storage row: owns all MSHR state and decodes updates locally.
(* keep_hierarchy = 1 *)
module rv32_icache_mshr_state_bank #(
    parameter integer EPOCH_WIDTH = 4,
    parameter integer ROW = 0
) (
'''+',\n'.join(decls)+'\n);\n'+renamed+'\nendmodule\n'
    wires=''.join(f'                wire {width(size)}bank_{field};\n' for field,size in FIELDS.items())
    connections=[f'                    .{port(name)}({name})' for name in INPUTS]
    connections += [f'                    .{field}_o(bank_{field})' for field in FIELDS]
    owned='''            if (MSHR_STATE_BANKS != 0) begin:g_owned
'''+wires+'''                rv32_icache_mshr_state_bank #(.EPOCH_WIDTH(EPOCH_WIDTH), .ROW(mshr_row)) state_bank (
'''+',\n'.join(connections)+'''
                );
                always @* begin
'''+''.join(f'                    mshr_{field}[mshr_row] = bank_{field};\n' for field in FIELDS)+'''                end
            end else begin:g_flat
'''+''.join('    '+line+'\n' for line in original_process.splitlines())+'''            end'''
    new_static=replace(STATIC,original_process,owned)
    code=replace(original,STATIC,new_static)
    code=replace(code,'    parameter integer MSHR_STATIC_WRITES = 0,',
                 '    parameter integer MSHR_STATE_BANKS = 0,\n    parameter integer MSHR_STATIC_WRITES = 0,')
    code=replace(code,'    initial begin\n',
                 '    initial begin\n        if ((MSHR_STATE_BANKS != 0) && (MSHR_STATIC_WRITES == 0))\n            $fatal(1, "MSHR_STATE_BANKS requires fixed-slot writes");\n')
    code+=child
    files={'rtl/cache/rv32_icache_nonblocking.v':code}
    for name in ('tb/unit/rv32_icache_sram_tb.v','tb/unit/rv32_icache_refill_policy_tb.v'):
        files[name]=replace((BASE/name).read_text(),'.MSHR_STATIC_WRITES(1)',
                            '.MSHR_STATIC_WRITES(1), .MSHR_STATE_BANKS(1)')
    proto_source=BASE/'tools/test_icache_static_mshr_protocol.py'
    files['tools/test_icache_mshr_state_banks_protocol.py']=proto_source.read_text().replace('test_icache_static_mshr_protocol','test_icache_mshr_state_banks_protocol')
    formal_source=BASE/'tools/test_icache_static_mshr_formal.py'
    formal=formal_source.read_text().replace('test_icache_static_mshr_formal','test_icache_mshr_state_banks_formal')
    formal=replace(formal,"f' -set MSHR_STATIC_WRITES {static}'", "f' -set MSHR_STATE_BANKS {static}'")
    formal=replace(formal,'TAG_MATCH_PARALLEL=parallel)', 'TAG_MATCH_PARALLEL=parallel, MSHR_STATIC_WRITES=1)')
    formal=formal.replace('static_write_mode=static','state_bank_mode=static').replace('_static{static}','_bank{static}')
    files['tools/test_icache_mshr_state_banks_formal.py']=formal
    probe_source=BASE/'tools/probe_localized_component.py'
    probe=replace(probe_source.read_text(),"case = out/f'static_mshr{variant}'", "case = out/f'mshr_state_bank{variant}'")
    probe=replace(probe,'MSHR_STATIC_WRITES=variant)', 'MSHR_STATIC_WRITES=1, MSHR_STATE_BANKS=variant)')
    files['tools/probe_localized_component.py']=probe
    for name,text in files.items():
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
    baseline=out/'baseline/rv32_icache_nonblocking.v';baseline.parent.mkdir(parents=True);baseline.write_bytes(source.read_bytes())
    result=dict(status='PREPARED',baseline_sha256=sha(source),candidate_sha256=sha(out/'rtl/cache/rv32_icache_nonblocking.v'),
                files_sha256={n:sha(out/n) for n in files},default_state_banks=0,requires_static_writes=1,
                state_fields=list(FIELDS),actual_e4_bits_per_bank=76,next_state_rename_reversal_exact=True,
                extra_state_bits=0,extra_cycles=0,child_owns_existing_state=True,all_hierarchy_must_be_priced_and_timed=True,
                raw_data_sram_unchanged=True,cpu_integrated=False,no_ppa_claim=True,
                preparer_inputs_sha256={str(p):sha(p) for p in [Path(__file__),Path(__file__).with_name('prepare_icache_static_mshr.py'),source,proto_source,formal_source,probe_source]})
    (out/'candidate_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='PREPARED',candidate=str(out),candidate_sha256=result['candidate_sha256'],actual_bits_per_bank=76)))


if __name__=='__main__':main()
