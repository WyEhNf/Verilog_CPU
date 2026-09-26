"""Unit checks for selective buffering and fail-closed STA area accounting."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from yosys_json_to_sta_verilog import (
    expand_critical_bus_bits, insert_buffer_trees, select_critical_driver_bits)


class BufferTests(unittest.TestCase):
    def test_bus_expansion_is_bounded_and_nonrecursive(self):
        nets = {"word": {"bits": [10, 11, "0"]},
                "alias": {"bits": [11, 12]},
                "wide": {"bits": [10, 20, 21, 22, 23]}}
        self.assertEqual(expand_critical_bus_bits({10}, nets, 4), {10, 11})
        self.assertEqual(expand_critical_bus_bits({10}, nets, 0), {10})

    def records(self):
        records = [("driver", "INV", {"port_directions": {"A": "input", "Y": "output"},
                    "connections": {"A": [2], "Y": [10]}})]
        for index in range(10):
            records.append(("sink" + str(index), "INV", {
                "port_directions": {"A": "input", "Y": "output"},
                "connections": {"A": [10], "Y": [20 + index]}}))
        records.append(("clock_sink", "DFF", {
            "port_directions": {"CLK": "input", "QN": "output"},
            "connections": {"CLK": [10], "QN": [40]}}))
        return records

    def test_select_only_original_driver_outputs(self):
        records = self.records()
        selected = select_critical_driver_bits(records,
            "u_0/Y (INV) u_1/A (INV) u_100/Y (BUF) u_2/Y (INV)")
        self.assertEqual(selected, {10, 21})

    def test_selective_tree_preserves_roots_and_clock(self):
        records = self.records()
        result = insert_buffer_trees(records, {}, 64, "BUF", {10}, 3)
        self.assertEqual(result["inserted"], 6)
        self.assertEqual(result["critical_buffered_nets"], 1)
        self.assertEqual(records[11][2]["connections"]["CLK"], [10])
        parent = {cell["connections"]["Y"][0]: cell["connections"]["A"][0]
                  for _, kind, cell in records if kind == "BUF"}
        for _, _, cell in records[1:11]:
            bit = cell["connections"]["A"][0]
            visited = set()
            while bit in parent:
                self.assertNotIn(bit, visited)
                visited.add(bit)
                bit = parent[bit]
            self.assertEqual(bit, 10)
        fanout = {}
        for _, _, cell in records:
            for pin, direction in cell["port_directions"].items():
                if direction == "input" and pin != "CLK":
                    for bit in cell["connections"][pin]:
                        fanout[bit] = fanout.get(bit, 0) + 1
        self.assertLessEqual(max(fanout.values()), 3)

    def test_invalid_single_sink_limit_rejected(self):
        with self.assertRaises(ValueError):
            insert_buffer_trees(self.records(), {}, 1, "BUF")


class ExportTests(unittest.TestCase):
    def test_skip_maps_preserves_netlist_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = {"modules": {"cpu_core": {
                "ports": {"a": {"direction": "input", "bits": [2]},
                          "y": {"direction": "output", "bits": [3]}},
                "netnames": {"a": {"bits": [2]}, "y": {"bits": [3]}},
                "cells": {"inv": {"type": "INVx1_ASAP7_75t_R",
                    "port_directions": {"A": "input", "Y": "output"},
                    "connections": {"A": [2], "Y": [3]}}}}}}
            source = root / "input.json"
            source.write_text(json.dumps(fixture))
            for stem, extra in (("normal", []), ("compact", ["--skip-maps"])):
                result = subprocess.run([sys.executable,
                    str(Path(__file__).with_name("yosys_json_to_sta_verilog.py")),
                    str(source), str(root / (stem + ".v")), *extra],
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / "normal.v").read_text(),
                             (root / "compact.v").read_text())
            self.assertEqual(json.loads((root / "normal.memories.json").read_text()),
                             json.loads((root / "compact.memories.json").read_text()))
            for suffix in ("cells.tsv", "nets.tsv"):
                self.assertTrue((root / ("normal." + suffix)).exists())
                self.assertFalse((root / ("compact." + suffix)).exists())


class AreaTests(unittest.TestCase):
    def audit(self, with_memory, allow=False, unknown=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cells = {"dff": {"type": "DFFHQNx1_ASAP7_75t_R"},
                     "inv": {"type": "unknown_cell" if unknown else "INVx1_ASAP7_75t_R"}}
            if with_memory:
                cells["ram"] = {"type": "$mem_v2"}
            (root / "input.json").write_text(json.dumps({"modules": {"cpu_core": {"cells": cells}}}))
            (root / "manifest.json").write_text(json.dumps({
                "top": "cpu_core", "memory_boundaries": int(with_memory),
                "standard_or_known_cells": 2, "unhandled_generic_cell_types": {},
                "buffer_tree": {"cell": "BUFx8_ASAP7_75t_R", "inserted": 2}}))
            command = [sys.executable, str(Path(__file__).with_name("audit_sta_area.py")),
                       str(root / "input.json"), str(root / "manifest.json"), str(root / "output.json")]
            if allow:
                command.append("--allow-memory-boundaries")
            result = subprocess.run(command, capture_output=True, text=True)
            output = root / "output.json"
            return result, json.loads(output.read_text()) if output.exists() else None

    def test_memory_release_gate_rejects_by_default(self):
        result, data = self.audit(True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(data)

    def test_explicit_partial_audit_keeps_total_unknown(self):
        result, data = self.audit(True, allow=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(data["status"], "INCOMPLETE")
        self.assertIsNone(data["timed_netlist_total_area_um2"])
        self.assertIsNone(data["sram_area_um2"])
        self.assertGreater(data["sequential_standard_cell_area_um2"], 0)
        self.assertAlmostEqual(data["known_timed_standard_cell_area_um2"],
            data["combinational_standard_cell_area_um2"] + data["sequential_standard_cell_area_um2"])

    def test_memory_free_audit_complete(self):
        result, data = self.audit(False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(data["status"], "COMPLETE")
        self.assertEqual(data["unpriced_leaves"], 0)
        self.assertEqual(data["timed_netlist_total_area_um2"], data["known_timed_standard_cell_area_um2"])

    def test_unknown_logic_not_excused_by_memory_option(self):
        result, data = self.audit(True, allow=True, unknown=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(data)


if __name__ == "__main__":
    unittest.main()
