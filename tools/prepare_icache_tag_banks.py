"""Keep actual I-cache tag state in functional row modules with local enables.

Preserve every tag bit, all asynchronous read ports, the real data SRAM,
reset behavior and cycle timing. Do not replace SRAM or add buffer stubs.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace(code, old, new):
    assert code.count(old) == 1, 'Ambiguous anchor: ' + old[:100]
    return code.replace(old, new)


HELPER = r'''
// Own a real tag register and the original refill write predicate locally.
(* keep_hierarchy = 1 *)
module rv32_icache_tag_row #(
    parameter integer TAG_WIDTH = 22,
    parameter integer ENTRY_WIDTH = 7,
    parameter integer ROW_ID = 0
) (
    input wire clk_i, reset_i,
    input wire response_valid_i, response_ready_i, response_target_i,
    input wire response_error_i, response_matches_i,
    input wire [ENTRY_WIDTH-1:0] entry_i,
    input wire [TAG_WIDTH-1:0] tag_i,
    output reg [TAG_WIDTH-1:0] tag_o
);
    // Tags intentionally have no reset, exactly as in the baseline.
    always @(posedge clk_i) begin
        if (!reset_i && response_valid_i && response_ready_i &&
            response_target_i && !response_error_i && response_matches_i &&
            entry_i == ROW_ID)
            tag_o <= tag_i;
    end
endmodule
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root.resolve()/'rtl/cache/rv32_icache_nonblocking.v'
    out = args.outdir.resolve()
    assert not out.exists()
    original = source.read_text()
    code = replace(original, '    parameter integer NEXT_LINE_PREFETCH = 1,',
                   '    parameter integer TAG_REGISTER_BANKS = 0,\n    parameter integer NEXT_LINE_PREFETCH = 1,')
    code = replace(code, '    reg [CACHE_TAG_WIDTH-1:0] tag_mem [0:CACHE_LINES-1];',
                   '    wire [CACHE_TAG_WIDTH-1:0] tag_mem [0:CACHE_LINES-1];\n'
                   '    reg [CACHE_TAG_WIDTH-1:0] legacy_tag_mem [0:CACHE_LINES-1];')
    code = replace(code, '                    tag_mem[refill_entry] <=\n                        mem_resp_line_addr_i[31:CACHE_SET_WIDTH+4];',
                   '                    if (TAG_REGISTER_BANKS == 0)\n'
                   '                        legacy_tag_mem[refill_entry] <=\n'
                   '                            mem_resp_line_addr_i[31:CACHE_SET_WIDTH+4];')
    banks = r'''
    genvar tag_row;
    generate for (tag_row=0; tag_row<CACHE_LINES; tag_row=tag_row+1) begin:g_tag_row
        if (TAG_REGISTER_BANKS != 0) begin:g_bank
            rv32_icache_tag_row #(.TAG_WIDTH(CACHE_TAG_WIDTH),
                .ENTRY_WIDTH(CACHE_ENTRY_WIDTH), .ROW_ID(tag_row)) bank (
                .clk_i(clk_i), .reset_i(reset_i),
                .response_valid_i(mem_resp_valid_i), .response_ready_i(mem_resp_ready_o),
                .response_target_i(response_target_found), .response_error_i(mem_resp_error_i),
                .response_matches_i(response_matches), .entry_i(refill_entry),
                .tag_i(mem_resp_line_addr_i[31:CACHE_SET_WIDTH+4]), .tag_o(tag_mem[tag_row]));
        end else begin:g_legacy
            assign tag_mem[tag_row] = legacy_tag_mem[tag_row];
        end
    end endgenerate

'''
    code = replace(code, '    // Do not derive arbitration from mem_resp_ready_o:',
                   banks + '    // Do not derive arbitration from mem_resp_ready_o:')
    code = replace(code, '    initial begin\n',
                   '    initial begin\n        if (TAG_REGISTER_BANKS != 0 && TAG_REGISTER_BANKS != 1)\n'
                   '            $fatal(1, "Invalid I-cache tag register bank mode");\n')
    code += HELPER
    tb = (ROOT/'tb/unit/rv32_icache_sram_tb.v').read_text()
    tb = replace(tb, '    parameter integer LINES = 16, WAYS = 2;',
                 '    parameter integer LINES = 16, WAYS = 2, MSHRS = 4;')
    tb = replace(tb, '.EPOCH_WIDTH(2), .MSHR_ENTRIES(4),',
                 '.EPOCH_WIDTH(2), .MSHR_ENTRIES(MSHRS), .TAG_REGISTER_BANKS(1),')
    tb = replace(tb, '    always @(posedge clk) begin',
                 '    initial if (dut.TAG_REGISTER_BANKS != 1) $fatal(1, "Tag banks disabled");\n'
                 '    always @(posedge clk) begin')
    probe = (ROOT/'tools/probe_localized_component.py').read_text()
    probe = replace(probe, "choices=('dcache','rob','rs')", "choices=('dcache','rob','rs','icache')")
    probe = replace(probe, "('rtl/backend/rv32_reservation_station.v',) if args.component == 'rs' else",
                    "('rtl/backend/rv32_reservation_station.v',) if args.component == 'rs' else\n"
                    "        ('rtl/cache/rv32_icache_nonblocking.v',) if args.component == 'icache' else")
    probe = replace(probe, '        case.mkdir()',
                    "        if args.component == 'icache':\n            case = out/f'tag_banks{variant}'\n        case.mkdir()")
    probe = replace(probe, "        else:\n            root_module = 'rv32_rob'",
                    "        elif args.component == 'icache':\n"
                    "            root_module = 'rv32_icache_nonblocking'\n"
                    "            parameters = dict(EPOCH_WIDTH=4, MSHR_ENTRIES=8, NEXT_LINE_PREFETCH=1,\n"
                    "                PREFETCH_DISTANCE=3, CACHE_LINES=128, CACHE_WAYS=2, TAG_REGISTER_BANKS=variant)\n"
                    "        else:\n            root_module = 'rv32_rob'")
    files = {'rtl/cache/rv32_icache_nonblocking.v': code,
             'tb/unit/rv32_icache_sram_tb.v': tb, 'tools/probe_localized_component.py': probe}
    for name, text in files.items():
        target = out/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    baseline = out/'baseline/rv32_icache_nonblocking.v'
    baseline.parent.mkdir(parents=True)
    baseline.write_bytes(source.read_bytes())
    assert sha(source) == sha(baseline)
    report = dict(status='PREPARED', source=str(source), baseline_sha256=sha(source),
                  candidate_sha256=sha(out/'rtl/cache/rv32_icache_nonblocking.v'),
                  files_sha256={name: sha(out/name) for name in files},
                  extra_cycles=0, data_sram_unchanged=True, no_tag_reset_added=True,
                  cpu_integrated=False)
    (out/'candidate_manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
