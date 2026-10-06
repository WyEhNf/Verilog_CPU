"""Decode demand/prefetch tag read indices once before selecting tag bits.

Preserve all cache state, SRAM ports, control-target reads and cycle timing.
This candidate is independent of the local tag-write banks.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace(code, old, new):
    assert code.count(old) == 1, 'Ambiguous anchor: '+old[:100]
    return code.replace(old, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--tag-bank-candidate', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root.resolve()/'rtl/cache/rv32_icache_nonblocking.v'
    out = args.outdir.resolve()
    assert not out.exists()
    code = source.read_text()
    code = replace(code, '    parameter integer NEXT_LINE_PREFETCH = 1,',
                   '    parameter integer TAG_READ_MUX_IMPL = 0,\n    parameter integer NEXT_LINE_PREFETCH = 1,')
    code = replace(code, '    reg lru_mem [0:CACHE_SETS-1];', '''    reg lru_mem [0:CACHE_SETS-1];
    wire [CACHE_TAG_WIDTH-1:0] lookup_tag [0:3];
    wire [3:0] lookup_valid;''')
    for index, name in enumerate(['request_way0', 'request_way1', 'prefetch_way0', 'prefetch_way1']):
        code = replace(code, f'valid_bits[{name}]', f'lookup_valid[{index}]')
        code = replace(code, f'tag_mem[{name}]', f'lookup_tag[{index}]')
    banks = '''    wire [CACHE_SET_WIDTH-1:0] lookup_set [0:1];
    assign lookup_set[0] = request_set;
    assign lookup_set[1] = prefetch_set;
    genvar lookup_query, lookup_way, lookup_row;
    generate
        for (lookup_query=0; lookup_query<2; lookup_query=lookup_query+1) begin:g_tag_query
            wire [CACHE_SETS-1:0] row_select;
            for (lookup_row=0; lookup_row<CACHE_SETS; lookup_row=lookup_row+1) begin:g_decode
                assign row_select[lookup_row] = lookup_set[lookup_query] == lookup_row;
            end
            for (lookup_way=0; lookup_way<2; lookup_way=lookup_way+1) begin:g_way
                if (TAG_READ_MUX_IMPL != 0) begin:g_parallel
                    reg [CACHE_TAG_WIDTH-1:0] tag_value;
                    reg valid_value;
                    integer read_row;
                    always @* begin
                        tag_value = 0;
                        valid_value = 0;
                        for (read_row=0; read_row<CACHE_SETS; read_row=read_row+1) begin
                            tag_value = tag_value | ({CACHE_TAG_WIDTH{row_select[read_row]}} &
                                tag_mem[cache_entry(read_row,lookup_way)]);
                            valid_value = valid_value | (row_select[read_row] &
                                valid_bits[cache_entry(read_row,lookup_way)]);
                        end
                    end
                    assign lookup_tag[lookup_query*2+lookup_way] = tag_value;
                    assign lookup_valid[lookup_query*2+lookup_way] = valid_value;
                end else begin:g_original
                    assign lookup_tag[lookup_query*2+lookup_way] =
                        tag_mem[cache_entry(lookup_set[lookup_query],lookup_way)];
                    assign lookup_valid[lookup_query*2+lookup_way] =
                        valid_bits[cache_entry(lookup_set[lookup_query],lookup_way)];
                end
            end
        end
    endgenerate
'''
    code = replace(code, '    wire prefetch_line_resident =', banks+'    wire prefetch_line_resident =')
    code = replace(code, '    initial begin\n', '    initial begin\n'
                   '        if (TAG_READ_MUX_IMPL != 0 && TAG_READ_MUX_IMPL != 1)\n'
                   '            $fatal(1, "Invalid I-cache tag read mux implementation");\n')
    helper = args.tag_bank_candidate.resolve()
    manifest = json.loads((helper/'candidate_manifest.json').read_text())
    assert manifest['baseline_sha256'] == sha(source)
    for name in ['tb/unit/rv32_icache_sram_tb.v', 'tools/probe_localized_component.py']:
        assert sha(helper/name) == manifest['files_sha256'][name]
    tb = (helper/'tb/unit/rv32_icache_sram_tb.v').read_text().replace('TAG_REGISTER_BANKS', 'TAG_READ_MUX_IMPL')
    probe = (helper/'tools/probe_localized_component.py').read_text().replace('TAG_REGISTER_BANKS', 'TAG_READ_MUX_IMPL')
    probe = probe.replace("case = out/f'tag_banks{variant}'", "case = out/f'tag_read{variant}'")
    files = {'rtl/cache/rv32_icache_nonblocking.v': code,
             'tb/unit/rv32_icache_sram_tb.v': tb, 'tools/probe_localized_component.py': probe}
    for name, text in files.items():
        target = out/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    baseline = out/'baseline/rv32_icache_nonblocking.v'
    baseline.parent.mkdir(parents=True)
    baseline.write_bytes(source.read_bytes())
    report = dict(status='PREPARED', source=str(source), baseline_sha256=sha(source),
                  candidate_sha256=sha(out/'rtl/cache/rv32_icache_nonblocking.v'),
                  files_sha256={name:sha(out/name) for name in files},
                  data_sram_unchanged=True, all_state_unchanged=True,
                  extra_cycles=0, cpu_integrated=False, tag_write_banks_included=False)
    (out/'candidate_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
