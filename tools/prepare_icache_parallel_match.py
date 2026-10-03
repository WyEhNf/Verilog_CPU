"""Compare actual I-cache tags in place before reducing row hit bits.

This removes wide binary-indexed tag reads for demand, prefetch, and direct
jump target checks. Keep all real state, replacement policy, raw SRAM pins,
response timing, and default behavior. Prove before claiming any PPA benefit.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir',type=Path,required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    assert not out.exists()
    base = Path('F:/CPU2026Candidates/icache_local_response_ready_20261003')
    source = base/'rtl/cache/rv32_icache_nonblocking.v'
    assert sha(source) == '5c9f6adfa7dfec13f39fe93cb51a59997531c19b949f704d78ba151b0b664d59'
    original = source.read_text()
    code = replace(original,'    parameter integer LOCAL_RESPONSE_READY = 0,',
        '    parameter integer TAG_MATCH_PARALLEL = 0,\n    parameter integer LOCAL_RESPONSE_READY = 0,')
    code = replace(code,'''    wire request_hit_way0 = valid_bits[request_way0] &&
                            (tag_mem[request_way0] == request_tag);
    wire request_hit_way1 = (CACHE_WAYS == 2) && valid_bits[request_way1] &&
                            (tag_mem[request_way1] == request_tag);''', '''    wire [CACHE_LINES-1:0] demand_match_way0, demand_match_way1;
    wire [CACHE_LINES-1:0] prefetch_match_rows, control_match_rows;
    wire request_hit_way0 = (TAG_MATCH_PARALLEL != 0) ? (|demand_match_way0) :
                            (valid_bits[request_way0] &&
                             (tag_mem[request_way0] == request_tag));
    wire request_hit_way1 = (CACHE_WAYS == 2) && ((TAG_MATCH_PARALLEL != 0) ?
                            (|demand_match_way1) : (valid_bits[request_way1] &&
                             (tag_mem[request_way1] == request_tag)));''')
    old = '''            for (control_way = 0; control_way < CACHE_WAYS;
                 control_way = control_way + 1)
                if (valid_bits[cache_entry(
                        control_target[CACHE_SET_WIDTH+3:4], control_way)] &&
                    (tag_mem[cache_entry(
                        control_target[CACHE_SET_WIDTH+3:4], control_way)] ==
                     control_target[31:CACHE_SET_WIDTH+4]))
                    control_target_present = 1'b1;'''
    code = replace(code,old,'''            if (TAG_MATCH_PARALLEL != 0) begin
                if (|control_match_rows)
                    control_target_present = 1'b1;
            end else begin
'''+''.join('    '+line+'\n' for line in old.splitlines())+'''            end''')
    old = '''    wire prefetch_line_resident =
        (valid_bits[prefetch_way0] &&
         (tag_mem[prefetch_way0] == prefetch_tag)) ||
        ((CACHE_WAYS == 2) && valid_bits[prefetch_way1] &&
         (tag_mem[prefetch_way1] == prefetch_tag));'''
    code = replace(code,old,'''    // Each row owns a fixed stored tag. Query indices qualify a one-bit
    // match instead of steering every stored tag bit through a large mux.
    // This changes only combinational layout, with no additional state.
    genvar match_row;
    generate for (match_row=0; match_row<CACHE_LINES; match_row=match_row+1) begin:g_match_row
        if (TAG_MATCH_PARALLEL != 0) begin:g_parallel
            wire demand_hit = valid_bits[match_row] &&
                (request_set == (match_row / CACHE_WAYS)) &&
                (tag_mem[match_row] == request_tag);
            assign demand_match_way0[match_row] = (match_row % CACHE_WAYS == 0) && demand_hit;
            assign demand_match_way1[match_row] = (match_row % CACHE_WAYS == 1) && demand_hit;
            assign prefetch_match_rows[match_row] = valid_bits[match_row] &&
                (prefetch_set == (match_row / CACHE_WAYS)) &&
                (tag_mem[match_row] == prefetch_tag);
            assign control_match_rows[match_row] = valid_bits[match_row] &&
                (control_target[CACHE_SET_WIDTH+3:4] == (match_row / CACHE_WAYS)) &&
                (tag_mem[match_row] == control_target[31:CACHE_SET_WIDTH+4]);
        end else begin:g_disabled
            assign demand_match_way0[match_row] = 1'b0;
            assign demand_match_way1[match_row] = 1'b0;
            assign prefetch_match_rows[match_row] = 1'b0;
            assign control_match_rows[match_row] = 1'b0;
        end
    end endgenerate
    wire prefetch_line_resident = (TAG_MATCH_PARALLEL != 0) ? (|prefetch_match_rows) :
        ((valid_bits[prefetch_way0] &&
          (tag_mem[prefetch_way0] == prefetch_tag)) ||
         ((CACHE_WAYS == 2) && valid_bits[prefetch_way1] &&
          (tag_mem[prefetch_way1] == prefetch_tag)));''')
    files = {'rtl/cache/rv32_icache_nonblocking.v':code}
    for name in ('tb/unit/rv32_icache_sram_tb.v','tb/unit/rv32_icache_refill_policy_tb.v'):
        files[name] = replace((base/name).read_text(),'.LOCAL_RESPONSE_READY(1)',
                              '.LOCAL_RESPONSE_READY(1), .TAG_MATCH_PARALLEL(1)')
    protocol_path = base/'tools/test_icache_local_response_ready_protocol.py'
    files['tools/test_icache_parallel_match_protocol.py'] = protocol_path.read_text().replace('test_icache_local_response_ready_protocol','test_icache_parallel_match_protocol')
    formal_path = base/'tools/test_icache_local_response_ready_formal.py'
    formal = formal_path.read_text().replace('test_icache_local_response_ready_formal','test_icache_parallel_match_formal')
    formal = replace(formal,"(' -set LOCAL_RESPONSE_READY 1' if label == 'gate' else '')",
                            "(' -set TAG_MATCH_PARALLEL 1' if label == 'gate' else '')")
    formal = replace(formal,'''    for lines, ways, mshrs, epoch in [(16, 1, 2, 2), (16, 2, 4, 2),
                                      (64, 2, 4, 4), (128, 2, 8, 4)]:''',
                     '''    for lines, ways, mshrs, epoch, ready in [(16,1,2,2,1), (16,2,4,2,1),
                                      (64,2,4,4,1), (128,2,8,4,1),
                                      (16,2,4,2,0), (256,2,16,4,1)]:''')
    formal = replace(formal,"stem = f'formal_l{lines}_w{ways}_m{mshrs}_e{epoch}'",
                            "stem = f'formal_l{lines}_w{ways}_m{mshrs}_e{epoch}_ready{ready}'")
    formal = replace(formal,'EPOCH_WIDTH=epoch, PREFETCH_DISTANCE=7, NEXT_LINE_PREFETCH=1)',
                            'EPOCH_WIDTH=epoch, PREFETCH_DISTANCE=7, NEXT_LINE_PREFETCH=1, LOCAL_RESPONSE_READY=ready, REFILL_PROTECT_PENDING_HIT=1)')
    formal = formal.replace('and four fullcontroller','and six fullcontroller')
    files['tools/test_icache_parallel_match_formal.py'] = formal
    probe_path = base/'tools/probe_localized_component.py'
    probe = probe_path.read_text()
    probe = replace(probe,"case = out/f'ready{variant}'", "case = out/f'parallel_match{variant}'")
    probe = replace(probe,'REFILL_PROTECT_PENDING_HIT=args.protect, LOCAL_RESPONSE_READY=variant)',
                           'REFILL_PROTECT_PENDING_HIT=args.protect, LOCAL_RESPONSE_READY=1, TAG_MATCH_PARALLEL=variant)')
    files['tools/probe_localized_component.py'] = probe
    for name,text in files.items():
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
    baseline=out/'baseline/rv32_icache_nonblocking.v'
    baseline.parent.mkdir(parents=True);baseline.write_bytes(source.read_bytes())
    result=dict(status='PREPARED',baseline_sha256=sha(source),candidate_sha256=sha(out/'rtl/cache/rv32_icache_nonblocking.v'),
                files_sha256={n:sha(out/n) for n in files},default_parallel_match=0,
                data_sram_unchanged=True,all_state_unchanged=True,extra_cycles=0,cpu_integrated=False,
                measured_ready=1,measured_protect=1,measured_prefetch_distance=7,
                scope=__doc__,preparer_inputs_sha256={str(p):sha(p) for p in [Path(__file__),source,protocol_path,formal_path,probe_path]})
    (out/'candidate_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='PREPARED',candidate=str(out),candidate_sha256=result['candidate_sha256'])))


if __name__ == '__main__':
    main()
