"""Verify BTB payload inference is a single-write, non-reset SRAM boundary."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite/bin'


@unittest.skipUnless((BIN / 'yosys.exe').is_file(), 'bundled Yosys not installed')
class PayloadPortsTests(unittest.TestCase):
    def test_random_reference_model(self):
        env = os.environ.copy()
        env['PATH'] = str(BIN) + os.pathsep + str(BIN.parent / 'lib') + os.pathsep + env['PATH']
        with tempfile.TemporaryDirectory(prefix='btb_random_') as directory:
            output = Path(directory) / 'random.vvp'
            compile_result = subprocess.run([str(BIN / 'iverilog.exe'), '-g2005', '-I', 'rtl',
                '-s', 'rv32_branch_predictor_random_tb', '-o', str(output),
                'rtl/predictor/rv32_branch_predictor.v', 'tb/unit/rv32_branch_predictor_random_tb.v'],
                cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            result = subprocess.run([str(BIN / 'vvp.exe'), '-N', str(output)],
                                    cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS: predictor random oracle 4000 cycles', result.stdout)
            self.assertNotIn('FAIL:', result.stdout)

    def test_payload_has_one_read_and_one_write(self):
        env = os.environ.copy()
        env['PATH'] = str(BIN) + os.pathsep + str(BIN.parent / 'lib') + os.pathsep + env['PATH']
        with tempfile.TemporaryDirectory(prefix='btb_ports_') as directory:
            output = Path(directory) / 'predictor.json'
            commands = ('read_verilog -I rtl rtl/predictor/rv32_branch_predictor.v; '
                        'hierarchy -check -top rv32_branch_predictor; proc; opt; '
                        'memory_dff; memory_collect; check; write_json "' +
                        output.as_posix() + '"')
            result = subprocess.run([str(BIN / 'yosys.exe'), '-Q', '-T', '-q', '-p', commands],
                                    cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            cells = json.loads(output.read_text())['modules']['rv32_branch_predictor']['cells']
            for name, width in (('btb_tag', 24), ('btb_target', 32), ('btb_kind', 2)):
                cell = cells[name]
                self.assertEqual(cell['type'], '$mem_v2')
                params = cell['parameters']
                actual = {key: int(params[key], 2) for key in ('WIDTH', 'SIZE', 'RD_PORTS', 'WR_PORTS')}
                self.assertEqual(actual, dict(WIDTH=width, SIZE=64, RD_PORTS=1, WR_PORTS=1))
                self.assertEqual(set(params['INIT']), {'x'})
                self.assertEqual(int(params['WR_CLK_ENABLE'], 2), 1)
                print(f'{name}: {actual}, uninitialized payload, synchronous single write')


if __name__ == '__main__':
    unittest.main()
