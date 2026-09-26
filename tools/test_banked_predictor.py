"""Check sharded predictor behavior and total inferred storage at widths 1/2/4."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite/bin'
SOURCES = ['rtl/predictor/rv32_branch_predictor.v', 'rtl/predictor/rv32_banked_predictor.v']


@unittest.skipUnless((BIN / 'yosys.exe').is_file(), 'bundled tools unavailable')
class BankedTests(unittest.TestCase):
    def run_tool(self, command):
        env = os.environ.copy()
        env['PATH'] = str(BIN) + os.pathsep + str(BIN.parent / 'lib') + os.pathsep + env['PATH']
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_all_widths_exact_reference(self):
        with tempfile.TemporaryDirectory(prefix='banked_sim_') as directory:
            for width in (1, 2, 4):
                with self.subTest(width=width):
                    output = Path(directory) / f'w{width}.vvp'
                    self.run_tool([str(BIN / 'iverilog.exe'), '-g2005', '-I', 'rtl', '-s',
                        'rv32_banked_predictor_tb', f'-Prv32_banked_predictor_tb.WIDTH={width}',
                        '-o', str(output), *SOURCES, 'tb/unit/rv32_banked_predictor_tb.v'])
                    text = self.run_tool([str(BIN / 'vvp.exe'), '-N', str(output)])
                    self.assertIn(f'PASS: banked predictor width={width} 4000 cycles', text)
                    self.assertNotIn('FAIL:', text)
                    print(text.strip())

    def test_all_widths_storage_geometry(self):
        with tempfile.TemporaryDirectory(prefix='banked_ports_') as directory:
            for width in (1, 2, 4):
                with self.subTest(width=width):
                    output = Path(directory) / f'w{width}.json'
                    self.run_tool([str(BIN / 'yosys.exe'), '-Q', '-T', '-q', '-p',
                        'read_verilog -I rtl ' + ' '.join(SOURCES) + '; '
                        f'chparam -set FE_WIDTH {width} rv32_banked_predictor; '
                        'hierarchy -check -top rv32_banked_predictor; proc; opt; memory_dff; '
                        'memory_collect; flatten; opt_clean; check; write_json "' + output.as_posix() + '"'])
                    cells = json.loads(output.read_text())['modules']['rv32_banked_predictor']['cells']
                    memories = {name: cell for name, cell in cells.items() if cell['type'] == '$mem_v2'}
                    self.assertEqual(len(memories), 5 * width)
                    total = 0
                    for name, cell in memories.items():
                        p = {key: int(cell['parameters'][key], 2)
                             for key in ('WIDTH', 'SIZE', 'RD_PORTS', 'WR_PORTS')}
                        total += p['WIDTH'] * p['SIZE']
                        if name.endswith(('btb_tag', 'btb_target', 'btb_kind')):
                            self.assertEqual(p['SIZE'], 64 // width)
                            self.assertEqual((p['RD_PORTS'], p['WR_PORTS']), (1, 1))
                        elif name.endswith('bht'):
                            self.assertEqual(p['SIZE'], 256 // width)
                    self.assertEqual(total, 4288)
                    print(f'width={width}: {len(memories)} memory banks, total bits={total}, payload 1R1W')


if __name__ == '__main__':
    unittest.main()
