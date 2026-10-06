"""Stage a default-off bounded fetch-queue occupancy register.

Keep the original signed 32-bit count expression as an observable alias;
only its stored zero-extended representation becomes clog2(depth+1) bits.
Require complete sequential equivalence before drawing any PPA conclusion.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace(code, before, after):
    assert code.count(before) == 1, before
    return code.replace(before, after)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    assert not out.exists()
    source = Path('F:/CPU2026Candidates/legal_addi_fix_20261003')
    profile_path = ROOT/'build/cpu2026/verified_legal_addi_profile_20261003.json'
    profile = json.loads(profile_path.read_text())
    name = 'rtl/frontend/rv32_fetch_frontend.v'
    assert profile['status'] == 'VERIFIED_SOURCE_ADOPTED_FULL_PPA'
    assert sha(source/name) == profile['source_sha256'][name]
    original = (source/name).read_text()
    code = replace(original, '    parameter integer LEGACY_SENTINEL_HALT = 0,',
                   '    parameter integer NARROW_OCCUPANCY = 0,\n    parameter integer LEGACY_SENTINEL_HALT = 0,')
    code = replace(code, '    integer count_reg;', '''    localparam integer COUNT_WIDTH = (NARROW_OCCUPANCY != 0) ?
        ((FQ_DEPTH <= 1) ? 1 : $clog2(FQ_DEPTH + 1)) : 32;
    reg [COUNT_WIDTH-1:0] count_storage_reg;
    // Admission bounds occupancy by FQ_DEPTH. Preserve signed 32-bit
    // arithmetic and the public internal alias used by existing checks.
    wire signed [31:0] count_reg = {{(32-COUNT_WIDTH){1'b0}}, count_storage_reg};''')
    assert code.count('count_reg <=') == 3
    code = code.replace('count_reg <=', 'count_storage_reg <=')
    tb = (ROOT/'tb/unit/rv32_fetch_frontend_tb.v').read_text()
    tb = replace(tb, '.PREDICTOR_META(PREDICTOR_META)) dut (',
                 '.PREDICTOR_META(PREDICTOR_META), .NARROW_OCCUPANCY(1)) dut (')
    helper = (ROOT/'tools/test_frontend_payload_banks.py').read_text()
    helper = helper.replace('test_frontend_payload_banks', 'test_frontend_bounded_count')
    helper = helper.replace('ROOT=Path(__file__).resolve().parents[1]', "ROOT=Path('E:/Verilog_cpu')")
    helper = helper.replace('QUEUE_PAYLOAD_BANKS', 'NARROW_OCCUPANCY')
    helper = replace(helper,
        '    for width,depth,metadata in [(1,4,0),(2,8,0),(4,16,0),(4,16,1),(4,4,1),(4,32,0)]:',
        '    for width,depth,metadata,legacy in [(1,4,0,0),(2,8,0,0),(4,16,0,0),(4,16,1,0),(4,4,1,0),(4,32,0,0),(1,1,0,0),(2,2,1,0),(4,16,0,1)]:')
    helper = replace(helper, "stem=f'formal_fe{width}_fq{depth}_meta{metadata}'",
                     "stem=f'formal_fe{width}_fq{depth}_meta{metadata}_legacy{legacy}'")
    helper = replace(helper, 'config=dict(FE_WIDTH=width,FQ_DEPTH=depth,EPOCH_WIDTH=4,PREDICTOR_META=metadata)',
                     'config=dict(FE_WIDTH=width,FQ_DEPTH=depth,EPOCH_WIDTH=4,PREDICTOR_META=metadata,LEGACY_SENTINEL_HALT=legacy)')
    helper = replace(helper, "        state_names=[n for n in models['gold']['netnames'] if re.fullmatch(r'fq_\\w+\\[\\d+\\]',n)]", r"""        assert len(models['gold']['netnames']['count_reg']['bits']) == 32
        assert len(models['gate']['netnames']['count_reg']['bits']) == 32
        stored_width = max(1, depth.bit_length())
        assert len(models['gate']['netnames']['count_storage_reg']['bits']) == stored_width
        assert models['gate']['netnames']['count_reg']['bits'][stored_width:] == ['0']*(32-stored_width)
        state_names=[n for n in models['gold']['netnames'] if re.fullmatch(r'fq_\w+\[\d+\]',n)]""")
    helper = helper.replace('six complete frontend proofs', 'nine complete frontend proofs')
    probe = Path('F:/CPU2026Candidates/frontend_packed_banks_20261003/tools/probe_localized_component.py').read_text()
    probe = probe.replace('QUEUE_PAYLOAD_BANKS=variant', 'NARROW_OCCUPANCY=variant')
    probe = probe.replace("case = out/f'payload_banks{variant}'", "case = out/f'narrow_count{variant}'")
    files = {name: code, 'baseline/rv32_fetch_frontend.v': original,
             'tb/unit/rv32_fetch_frontend_tb.v': tb,
             'tools/test_frontend_bounded_count.py': helper,
             'tools/probe_localized_component.py': probe}
    for name, text in files.items():
        path = out/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    # Preserve exact baseline bytes independently of text newline normalization.
    (out/'baseline/rv32_fetch_frontend.v').write_bytes((source/'rtl/frontend/rv32_fetch_frontend.v').read_bytes())
    report = dict(status='PREPARED', source_root=str(source), profile=str(profile_path),
                  baseline_sha256=sha(out/'baseline/rv32_fetch_frontend.v'),
                  candidate_sha256=sha(out/'rtl/frontend/rv32_fetch_frontend.v'),
                  files_sha256={n:sha(out/n) for n in files}, default_narrow_occupancy=0,
                  actual_depth16_storage_bits=[32,5], all_count_expression_bits=32,
                  full_equivalence_required=True, cpu_integrated=False,
                  preparer_sha256=sha(__file__))
    (out/'candidate_manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(status='PREPARED', candidate=str(out), actual_counter_bits=[32,5])))


if __name__ == '__main__':
    main()
