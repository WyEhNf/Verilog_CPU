"""Stage fixed-slot I-cache MSHR writes, preserving every write priority.

The default retains the old indexed assignments. The trial gives each existing
MSHR row one sequential process. No extra registers, cycles, SRAM, assumptions,
or synthesis exemptions are introduced. This is an isolated component trial.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

BASE = Path('F:/CPU2026Candidates/icache_parallel_match_20261003')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


STATIC = '''    // Constant row indices avoid steering wide update payloads through
    // variable memory write ports. Later clauses retain the original priority:
    // cleanup, demand, sequential prefetch, send, response, control prefetch.
    genvar mshr_row;
    generate if (MSHR_STATIC_WRITES != 0) begin:g_static_mshr
        for (mshr_row=0; mshr_row<MSHR_ENTRIES; mshr_row=mshr_row+1) begin:g_row
            always @(posedge clk_i) begin
                if (reset_i) begin
                    mshr_valid[mshr_row] <= 1'b0;
                    mshr_sent[mshr_row] <= 1'b0;
                    mshr_prefetch[mshr_row] <= 1'b0;
                    mshr_control_prefetch[mshr_row] <= 1'b0;
                    mshr_pc[mshr_row] <= 32'd0;
                    mshr_line[mshr_row] <= 32'd0;
                    mshr_demand_epoch[mshr_row] <= {EPOCH_WIDTH{1'b0}};
                    mshr_txn_epoch[mshr_row] <= {EPOCH_WIDTH{1'b0}};
                end else begin
                    if (mshr_valid[mshr_row] &&
                        (mshr_txn_epoch[mshr_row] != current_epoch_i) &&
                        !mshr_control_prefetch[mshr_row]) begin
                        mshr_valid[mshr_row] <= 1'b0;
                        mshr_sent[mshr_row] <= 1'b0;
                        mshr_control_prefetch[mshr_row] <= 1'b0;
                    end
                    if (request_fire && !request_hit) begin
                        if (request_match_found) begin
                            if (request_match_index == mshr_row) begin
                                mshr_prefetch[mshr_row] <= 1'b0;
                                mshr_pc[mshr_row] <= if_req_pc_i;
                                mshr_demand_epoch[mshr_row] <= if_req_epoch_i;
                            end
                        end else if (free_index == mshr_row) begin
                            mshr_valid[mshr_row] <= 1'b1;
                            mshr_sent[mshr_row] <= 1'b0;
                            mshr_prefetch[mshr_row] <= 1'b0;
                            mshr_control_prefetch[mshr_row] <= 1'b0;
                            mshr_pc[mshr_row] <= if_req_pc_i;
                            mshr_line[mshr_row] <= request_line;
                            mshr_demand_epoch[mshr_row] <= if_req_epoch_i;
                            mshr_txn_epoch[mshr_row] <= if_req_epoch_i;
                        end
                    end
                    if (prefetch_step_allocates && (free_index == mshr_row)) begin
                        mshr_valid[mshr_row] <= 1'b1;
                        mshr_sent[mshr_row] <= 1'b0;
                        mshr_prefetch[mshr_row] <= 1'b1;
                        mshr_control_prefetch[mshr_row] <= prefetch_control_stream;
                        mshr_pc[mshr_row] <= prefetch_next_line;
                        mshr_line[mshr_row] <= prefetch_next_line;
                        mshr_demand_epoch[mshr_row] <= prefetch_epoch;
                        mshr_txn_epoch[mshr_row] <= prefetch_epoch;
                    end
                    if (mem_req_valid_o && mem_req_ready_i && (send_index == mshr_row))
                        mshr_sent[mshr_row] <= 1'b1;
                    if (mem_resp_valid_i && mem_resp_ready_o &&
                        response_target_found && (response_index == mshr_row)) begin
                        mshr_valid[mshr_row] <= 1'b0;
                        mshr_sent[mshr_row] <= 1'b0;
                        mshr_control_prefetch[mshr_row] <= 1'b0;
                    end
                    if (control_target_allocate && (response_index == mshr_row)) begin
                        mshr_valid[mshr_row] <= 1'b1;
                        mshr_sent[mshr_row] <= 1'b0;
                        mshr_prefetch[mshr_row] <= 1'b1;
                        mshr_control_prefetch[mshr_row] <= 1'b1;
                        mshr_pc[mshr_row] <= control_target;
                        mshr_line[mshr_row] <= {control_target[31:4], 4'b0};
                        mshr_demand_epoch[mshr_row] <= current_epoch_i;
                        mshr_txn_epoch[mshr_row] <= current_epoch_i;
                    end
                end
            end
        end
    end endgenerate

'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--outdir', type=Path, required=True)
    out = ap.parse_args().outdir.resolve()
    assert not out.exists(), 'Preserve earlier candidate'
    source = BASE/'rtl/cache/rv32_icache_nonblocking.v'
    assert sha(source) == '2af76a9644d54879974411edea411058ae173beca7fcc9b213458bb0f9016bb0'
    original = source.read_text()
    pattern = re.compile(r'^( +)(mshr_\w+\[[^\]\n]+\]\s*<=[\s\S]*?;\n(?:\1mshr_\w+\[[^\]\n]+\]\s*<=[\s\S]*?;\n)*)', re.M)
    groups = []

    def wrap(match):
        old = match[0]
        indent = match[1]
        new = indent+'if (MSHR_STATIC_WRITES == 0) begin\n'+''.join('    '+line+'\n' for line in old.splitlines())+indent+'end\n'
        groups.append((old,new))
        return new

    code = pattern.sub(wrap, original)
    assert len(groups) == 8, len(groups)
    assignments = sum(len(re.findall(r'\bmshr_\w+\[.*?\]\s*<=', old)) for old,_ in groups)
    assert assignments == 42, assignments
    restored = code
    for old,new in groups:
        restored = replace(restored,new,old)
    assert restored == original
    code = replace(code,'    parameter integer TAG_MATCH_PARALLEL = 0,',
        '    parameter integer MSHR_STATIC_WRITES = 0,\n    parameter integer TAG_MATCH_PARALLEL = 0,')
    code = replace(code,'    initial begin\n',STATIC+'    initial begin\n')
    files = {'rtl/cache/rv32_icache_nonblocking.v':code}
    for name in ('tb/unit/rv32_icache_sram_tb.v','tb/unit/rv32_icache_refill_policy_tb.v'):
        files[name] = replace((BASE/name).read_text(),'.TAG_MATCH_PARALLEL(1)',
                              '.TAG_MATCH_PARALLEL(1), .MSHR_STATIC_WRITES(1)')
    protocol = BASE/'tools/test_icache_parallel_match_protocol.py'
    files['tools/test_icache_static_mshr_protocol.py'] = protocol.read_text().replace('test_icache_parallel_match_protocol','test_icache_static_mshr_protocol')
    formal_source = BASE/'tools/test_icache_parallel_match_formal.py'
    formal = formal_source.read_text().replace('test_icache_parallel_match_formal','test_icache_static_mshr_formal')
    formal = replace(formal,"(' -set TAG_MATCH_PARALLEL 1' if label == 'gate' else '')",
                     "(f' -set MSHR_STATIC_WRITES {static}' if label == 'gate' else '')")
    formal = replace(formal,'''    for lines, ways, mshrs, epoch, ready in [(16,1,2,2,1), (16,2,4,2,1),
                                      (64,2,4,4,1), (128,2,8,4,1),
                                      (16,2,4,2,0), (256,2,16,4,1)]:''',
        '''    for lines, ways, mshrs, epoch, ready, parallel, static in [
            (16,1,2,2,1,1,1), (16,2,4,2,1,1,1),
            (64,2,4,4,1,1,1), (128,2,8,4,1,1,1),
            (16,2,4,2,0,1,1), (256,2,16,4,1,1,1),
            (16,2,4,2,1,0,1), (16,2,4,2,1,1,0)]:''')
    formal = replace(formal,"stem = f'formal_l{lines}_w{ways}_m{mshrs}_e{epoch}_ready{ready}'",
                     "stem = f'formal_l{lines}_w{ways}_m{mshrs}_e{epoch}_ready{ready}_parallel{parallel}_static{static}'")
    formal = replace(formal,'LOCAL_RESPONSE_READY=ready, REFILL_PROTECT_PENDING_HIT=1)',
                     'LOCAL_RESPONSE_READY=ready, REFILL_PROTECT_PENDING_HIT=1, TAG_MATCH_PARALLEL=parallel)')
    anchor = "        pins = ('clk','en','we','wmask','addr','wdata','rdata')"
    formal = replace(formal,anchor,'''        mshr_fields = ('valid','sent','prefetch','control_prefetch','pc','line','demand_epoch','txn_epoch')
        for field in mshr_fields:
            for row in range(mshrs):
                name = f'mshr_{field}[{row}]'
                assert name in models['gold']['netnames'] and name in models['gate']['netnames'], name
                assert len(models['gold']['netnames'][name]['bits']) == len(models['gate']['netnames'][name]['bits']), name
'''+anchor)
    formal = replace(formal,'tag_rows_preserved=len(state_names),',
                     'tag_rows_preserved=len(state_names), mshr_rows_preserved=mshrs, mshr_fields_preserved=list(mshr_fields), static_write_mode=static,')
    formal = formal.replace('six fullcontroller','eight fullcontroller')
    files['tools/test_icache_static_mshr_formal.py'] = formal
    probe_source = BASE/'tools/probe_localized_component.py'
    probe = replace(probe_source.read_text(),"case = out/f'parallel_match{variant}'", "case = out/f'static_mshr{variant}'")
    probe = replace(probe,'LOCAL_RESPONSE_READY=1, TAG_MATCH_PARALLEL=variant)',
                     'LOCAL_RESPONSE_READY=1, TAG_MATCH_PARALLEL=1, MSHR_STATIC_WRITES=variant)')
    files['tools/probe_localized_component.py'] = probe
    for name,text in files.items():
        target=out/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(text,encoding='utf-8')
    baseline = out/'baseline/rv32_icache_nonblocking.v'
    baseline.parent.mkdir(parents=True)
    baseline.write_bytes(source.read_bytes())
    result=dict(status='PREPARED',baseline_sha256=sha(source),candidate_sha256=sha(out/'rtl/cache/rv32_icache_nonblocking.v'),
        files_sha256={n:sha(out/n) for n in files},default_static_writes=0,guarded_original_groups=len(groups),guarded_original_assignments=assignments,
        guarded_original_removal_exact=True,extra_state_bits=0,extra_cycles=0,all_original_state_preserved=True,raw_data_sram_unchanged=True,
        cpu_integrated=False,measured_parallel_match=1,measured_ready=1,measured_protect=1,
        preparer_inputs_sha256={str(p):sha(p) for p in [Path(__file__),source,protocol,formal_source,probe_source]})
    (out/'candidate_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='PREPARED',candidate=str(out),candidate_sha256=result['candidate_sha256'])))


if __name__ == '__main__':
    main()
