import tempfile
import unittest
from pathlib import Path

from ppa_audit import timing_summary


class TimingUnitsTests(unittest.TestCase):
    def check_report(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "timing.rpt"
            path.write_text(text)
            return timing_summary(path)

    def test_verified_ps_report(self):
        result = self.check_report(
            "AUDIT time_unit=ps capacitance_unit=fF clock_period_ps=3333.3333333333335 uncertainty_ps=100\n"
            "core_clk period_min = 24832.51 fmax = 40.27\nwns max -21499.18\n")
        self.assertAlmostEqual(result["minimum_period_ns"], 24.83251)
        self.assertAlmostEqual(result["wns_ns"], -21.49918)
        self.assertAlmostEqual(result["clock_period_ns"], 10 / 3)

    def test_reject_legacy_or_wrong_clock(self):
        for header in ("", "AUDIT time_unit=ps capacitance_unit=fF clock_period_ps=3.333 uncertainty_ps=0.1\n"):
            with self.assertRaises(RuntimeError):
                self.check_report(header + "core_clk period_min = 24732.61 fmax = 40.43\n")


if __name__ == "__main__":
    unittest.main()
