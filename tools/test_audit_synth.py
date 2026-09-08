#!/usr/bin/env python3
"""Focused tests for tools/audit_synth.py."""

import tempfile
import unittest
from pathlib import Path

import audit_synth


class AuditSynthTests(unittest.TestCase):
    def test_parse_memory_dump(self):
        contents = """\
module \\top
  cell $mem_v2 \\data_mem
    parameter \\ABITS 3
    parameter \\RD_PORTS 2
    parameter \\SIZE 8
    parameter \\WIDTH 32
    parameter \\WR_PORTS 1
  end
end
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mem.il"
            path.write_text(contents, encoding="utf-8")
            memories = audit_synth.parse_memory_dump(path)
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["module"], "top")
        self.assertEqual(memories[0]["cell"], "data_mem")
        self.assertEqual(memories[0]["width"], 32)
        self.assertEqual(memories[0]["size"], 8)
        self.assertEqual(memories[0]["bits"], 256)
        self.assertEqual(memories[0]["rd_ports"], 2)

    def test_parse_final_hierarchy_and_unknown_counts(self):
        contents = """\
=== design hierarchy ===
  2 1.0 INVx1_ASAP7_75t_R
  Chip area for top module '\\cpu_core': 1.0
=== design hierarchy ===
  20 - $_MUX_
  10 6.9984 INVx1_ASAP7_75t_R
  Area for cell type $_MUX_ is unknown!
  Chip area for top module '\\cpu_core': 6.9984
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synth.log"
            path.write_text(contents, encoding="utf-8")
            report = audit_synth.parse_synth_log(path)
        self.assertEqual(report["top_area_um2_known_cells_only"], 6.9984)
        self.assertEqual(report["cell_counts"]["$_MUX_"], 20)
        self.assertEqual(report["unknown_area_cells"], [{"type": "$_MUX_", "count": 20}])


if __name__ == "__main__":
    unittest.main()
