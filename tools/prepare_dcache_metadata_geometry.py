"""Prepare an isolated 16-versus-64-row Cache metadata-bank experiment.

Only bank geometry changes; actual data/tag SRAM, request sequencing and bank
logic are preserved. Keep the main and already-measured CPU sources frozen.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace(text, old, new):
    assert text.count(old) == 1, 'Ambiguous patch anchor: '+old
    return text.replace(old, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', required=True, type=Path)
    args = parser.parse_args()
    out = args.outdir.resolve()
    assert not out.exists(), 'Preserve previous candidate'
    names = ['rtl/cache/rv32_dcache_nonblocking.v', 'rtl/cache/rv32_dcache_control_banks.v',
             'tb/unit/rv32_dcache_sram_tb.v', 'tb/unit/rv32_dcache_hash_tb.v',
             'tools/test_dcache_local_metadata.py', 'tools/probe_localized_component.py']
    baseline = {}
    for name in names:
        target = out/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
        backup = out/'baseline'/name
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, backup)
        baseline[name] = digest(ROOT/name)
    path = out/names[0]
    text = path.read_text()
    text = replace(text, '    parameter integer LOCAL_ACTION_DECODE = 0,',
        '    parameter integer LOCAL_ACTION_DECODE = 0,\n'
        '    // Actual metadata state rows per bank in STATIC_UPDATES=2 only.\n'
        '    // Small caches cap the requested geometry to their total rows.\n'
        '    parameter integer METADATA_GROUP_ROWS = 16,')
    text = replace(text, '    end else begin : g_banked_updates\n        localparam integer GROUP_ROWS = 16;',
        '    end else begin : g_banked_updates\n'
        '        localparam integer GROUP_ROWS = (METADATA_GROUP_ROWS < CACHE_LINES) ?\n'
        '                                            METADATA_GROUP_ROWS : CACHE_LINES;')
    text = replace(text, '            (LOCAL_ACTION_DECODE != 0 && LOCAL_ACTION_DECODE != 1) ||',
        '            (LOCAL_ACTION_DECODE != 0 && LOCAL_ACTION_DECODE != 1) ||\n'
        '            METADATA_GROUP_ROWS < 16 || METADATA_GROUP_ROWS > 128 ||\n'
        '            ((METADATA_GROUP_ROWS & (METADATA_GROUP_ROWS-1)) != 0) ||')
    path.write_text(text)
    for name in names[2:4]:
        path = out/name
        text = path.read_text()
        text = replace(text, '    parameter integer LOCAL_METADATA_QUERY = 0\n',
            '    parameter integer LOCAL_METADATA_QUERY = 0,\n'
            '    parameter integer LOCAL_ACTION_DECODE = 0,\n'
            '    parameter integer METADATA_GROUP_ROWS = 16\n')
        text = replace(text, '.LOCAL_METADATA_QUERY(LOCAL_METADATA_QUERY)) dut (',
            '.LOCAL_METADATA_QUERY(LOCAL_METADATA_QUERY),\n'
            '        .LOCAL_ACTION_DECODE(LOCAL_ACTION_DECODE),\n'
            '        .METADATA_GROUP_ROWS(METADATA_GROUP_ROWS)) dut (')
        rows = '16' if name.endswith('sram_tb.v') else 'CACHE_LINES'
        text = replace(text, '    integer registered_index_checks = 0;',
            '    initial if (dut.LOCAL_ACTION_DECODE != LOCAL_ACTION_DECODE ||\n'
            '                dut.METADATA_GROUP_ROWS != METADATA_GROUP_ROWS)\n'
            '        $fatal(1,"Action/geometry parameters did not reach actual Cache");\n'
            '    generate if (STATIC_UPDATES == 2) begin : g_geometry_check\n'
            f'        localparam integer EXPECT_ROWS = (METADATA_GROUP_ROWS < {rows}) ?\n'
            f'                                            METADATA_GROUP_ROWS : {rows};\n'
            '        initial if (dut.g_banked_updates.GROUP_ROWS != EXPECT_ROWS ||\n'
            f'                    dut.g_banked_updates.GROUP_COUNT != {rows}/EXPECT_ROWS)\n'
            '            $fatal(1,"Actual Cache metadata bank geometry mismatch");\n'
            '    end endgenerate\n'
            '    integer registered_index_checks = 0;')
        path.write_text(text)
    path = out/names[4]
    text = path.read_text()
    text = replace(text, "    args = parser.parse_args()", "    parser.add_argument('--group-rows', type=int, choices=(16,32,64,128), default=64)\n    args = parser.parse_args()")
    text = replace(text, '    for top, config in cases:\n', '    for top, config in cases:\n        config = config | dict(METADATA_GROUP_ROWS=args.group_rows)\n')
    path.write_text(text)
    path = out/names[5]
    text = path.read_text()
    text = replace(text, '    for variant in (0, 1):',
        "    assert args.component == 'dcache' and args.update_mode == 2\n    for variant in (16, 64):")
    text = replace(text, '        case.mkdir()', "        case = out/f'metadata_rows{variant}'\n        case.mkdir()")
    text = replace(text, '                          LOCAL_METADATA_QUERY=variant)',
        '                          LOCAL_METADATA_QUERY=1, LOCAL_ACTION_DECODE=1,\n'
        '                          METADATA_GROUP_ROWS=variant)')
    text = replace(text, "    args = parser.parse_args()", "    args = parser.parse_args()\n    assert args.cache_experiment == 'metadata', 'Geometry is the only experiment here'")
    path.write_text(text)
    manifest = dict(status='PREPARED', description=__doc__, source_root=str(ROOT),
                    baseline_sha256=baseline, candidate_sha256={n:digest(out/n) for n in names},
                    cpu_integrated=False, cpu_ppa_claim=False)
    (out/'candidate_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
