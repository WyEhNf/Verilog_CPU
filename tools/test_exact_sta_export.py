"""Check that exact mapped export preserves cells; keep old Verilog fallback."""
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / '.deps/oss-cad-suite-install/oss-cad-suite/bin'
YOSYS = BIN / 'yosys.exe'


@unittest.skipUnless(YOSYS.is_file(), 'bundled Yosys not installed')
class ExactExportTests(unittest.TestCase):
    def run_yosys(self, commands):
        env = os.environ.copy()
        env['PATH'] = str(BIN) + os.pathsep + str(BIN.parent / 'lib') + os.pathsep + env['PATH']
        result = subprocess.run([str(YOSYS), '-Q', '-T', '-q', '-p', commands],
                                cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def test_exact_and_compatibility_paths(self):
        with tempfile.TemporaryDirectory(prefix='sta_export_') as temp:
            path = Path(temp)
            source = path / 'toy.v'
            source.write_text('module cpu_core(input clk_i, input disable, input [3:0] addr, '
                              'input [7:0] data, output [7:0] q); '
                              'reg [7:0] ram [0:15]; '
                              'always @(posedge clk_i) if (!disable) ram[addr] <= data; '
                              'assign q = ram[addr]; endmodule\n')
            prefix = path.as_posix()
            self.run_yosys(f'read_verilog {source.as_posix()}; hierarchy -top cpu_core; '
                           'proc; opt; memory_collect; techmap; opt; '
                           'abc -genlib _asap7_lib_filtered/asap7_comb.genlib; opt; '
                           f'write_json {prefix}/before.json; '
                           f'write_rtlil {prefix}/cpu_core_mapped.il; '
                           f'write_verilog -noattr {prefix}/cpu_core_synth.v')
            output = self.run_yosys(f'tcl synth/export_sta_json.tcl {prefix} {prefix}/exact')
            self.assertIn('input_mode=exact_mapped_rtlil', output)
            before = json.loads((path / 'before.json').read_text())['modules']['cpu_core']['cells']
            after = json.loads((path / 'exact/cpu_core_flat.json').read_text())['modules']['cpu_core']['cells']
            self.assertEqual(Counter(cell['type'] for cell in before.values()),
                             Counter(cell['type'] for cell in after.values()))
            before_mem = [cell['parameters'] for cell in before.values() if cell['type'] == '$mem_v2']
            after_mem = [cell['parameters'] for cell in after.values() if cell['type'] == '$mem_v2']
            self.assertEqual(before_mem, after_mem)
            (path / 'cpu_core_mapped.il').unlink()
            output = self.run_yosys(f'tcl synth/export_sta_json.tcl {prefix} {prefix}/compat')
            self.assertIn('input_mode=behavioral_verilog_compatibility', output)
            self.assertTrue((path / 'compat/cpu_core_flat.json').is_file())


if __name__ == '__main__':
    unittest.main()
