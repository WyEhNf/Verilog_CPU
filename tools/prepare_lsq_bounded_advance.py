"""Stage an optional exact LSQ pointer simplification with isolated evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace(text, before, after):
    assert text.count(before) == 1, before
    return text.replace(before, after)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    out = args.outdir.resolve()
    assert not out.exists()
    source = Path('F:/CPU2026Candidates/legal_addi_fix_20261003')
    profile = json.loads((ROOT/'build/cpu2026/verified_legal_addi_profile_20261003.json').read_text())
    name = 'rtl/backend/rv32_lsq.v'
    assert sha(source/name) == profile['source_sha256'][name]
    original = (source/name).read_text()
    code = replace(original, '    parameter integer STORE_ADMISSION_BYPASS = 0,',
                   '    parameter integer DIRECT_ADVANCE = 0,\n    parameter integer STORE_ADMISSION_BYPASS = 0,')
    function = re.search(r'    function \[SLOT_WIDTH-1:0\] advance_slot;.*?    endfunction', code, re.S)[0]
    legacy = function.split('        begin\n',1)[1].rsplit('        end\n',1)[0]
    modified = '''    function [SLOT_WIDTH-1:0] advance_slot;
        input [SLOT_WIDTH-1:0] start;
        input integer amount;
        integer p;
        integer n;
        begin
            if (DIRECT_ADVANCE != 0) begin
                // The loop clamps increments to [0,LSQ_ENTRIES]. A full
                // traversal of a power-of-two queue returns to its start.
                // Depth1 has a spare representable start value; preserve
                // the literal loop even for that otherwise unused value.
                if (LSQ_ENTRIES == 1)
                    advance_slot = (amount > 0) ? {SLOT_WIDTH{1'b0}} : start;
                else if (amount <= 0 || amount >= LSQ_ENTRIES)
                    advance_slot = start;
                else
                    advance_slot = start + amount;
            end else begin
'''+''.join('    '+line+'\n' for line in legacy.splitlines())+'''            end
        end
    endfunction'''
    code = replace(code, function, modified)
    tb_path = ROOT/'tb/unit/rv32_lsq_tb.v'
    tb = replace(tb_path.read_text(), '.LSQ_ENTRIES(ENTRIES)', '.LSQ_ENTRIES(ENTRIES), .DIRECT_ADVANCE(1)')
    literal_path = ROOT/'tools/test_rob_advance.py'
    literal = literal_path.read_text().replace('ROB','LSQ').replace('rob','lsq')
    literal = replace(literal, 'ROOT = Path(__file__).resolve().parents[1]', "ROOT = Path('E:/Verilog_cpu')")
    literal = literal.replace('parameter integer SLOT_WIDTH=$clog2(LSQ_ENTRIES)',
                              'parameter integer DIRECT_ADVANCE=1,\n            parameter integer SLOT_WIDTH=(LSQ_ENTRIES<=1)?1:$clog2(LSQ_ENTRIES)')
    literal = replace(literal, 'for depth in (2,4,8,16,32,64,128):', 'for depth in (1,2,4,8,16,32,64,128):')
    literal = literal.replace('seven literal LSQ', 'eight literal LSQ')
    probe_path = Path('F:/CPU2026Candidates/frontend_bounded_count_20261003/tools/probe_localized_component.py')
    probe = probe_path.read_text()
    probe = re.sub(r'^""".*?"""', '"""Measure the complete actual LSQ16 with DIRECT_ADVANCE0 versus1.\n\nRetain every port and state field, original validator, raw five libraries,\ndefault ABC, all physical leaves, and complete original-flow timing.\nComponent measurements do not establish CPU IPC, area or frequency.\n"""', probe, count=1, flags=re.S)
    probe = replace(probe, "choices=('dcache','rob','rs','frontend'), default='dcache'", "choices=('lsq',), default='lsq'")
    start = probe.index('    component_sources = ')
    end = probe.index('    names = component_sources', start)
    probe = probe[:start]+"    component_sources = [Path('rtl/backend/rv32_lsq.v')]\n"+probe[end:]
    start = probe.index('        case = out/', probe.index('    for variant in (0, 1):'))
    end = probe.index("        run(case, 'elaborate'", start)
    probe = probe[:start]+'''        case = out/f'direct_advance{variant}'
        case.mkdir()
        root_module = 'rv32_lsq'
        parameters = dict(BE_WIDTH=4, LSQ_ENTRIES=16, ROB_ENTRIES=64,
                          TAG_WIDTH=17, ROB_TAG_WIDTH=17,
                          STORE_ADMISSION_BYPASS=0, STORE_ADDRESS_PROBE=1,
                          DIRECT_ADVANCE=variant)
'''+probe[end:]
    files = {name:code, 'tb/unit/rv32_lsq_tb.v':tb,
             'tools/test_lsq_advance.py':literal, 'tools/probe_localized_component.py':probe}
    for name, text in files.items():
        target = out/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    baseline = out/'baseline/rv32_lsq.v'
    baseline.parent.mkdir(parents=True)
    baseline.write_bytes((source/'rtl/backend/rv32_lsq.v').read_bytes())
    inputs = [Path(__file__).resolve(), tb_path, literal_path, probe_path]
    result = dict(status='PREPARED', default_direct_advance=0, cpu_integrated=False,
                  baseline_sha256=sha(baseline), candidate_sha256=sha(out/'rtl/backend/rv32_lsq.v'),
                  files_sha256={n:sha(out/n) for n in files},
                  preparer_inputs_sha256={str(p):sha(p) for p in inputs},
                  scope='Only default-off pointer function branch; arbitrary signed32 amount and every represented start require literal SAT; complete module proof and protocols follow.')
    (out/'candidate_manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='PREPARED',candidate=str(out))))


if __name__ == '__main__':
    main()
