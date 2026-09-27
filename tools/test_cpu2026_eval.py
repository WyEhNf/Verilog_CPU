"""Reject benchmark results measured with a missing or incorrect memory setup."""
import unittest

from run_cpu2026 import BenchmarkError, evaluation_memory, performance_counters


class EvaluationMemoryTests(unittest.TestCase):
    def test_scoring_latency(self):
        line = "EVAL_MEMORY: unified=1 latency=20 i_outstanding=16 d_outstanding=8 line_bytes=16"
        self.assertEqual(evaluation_memory(line, 20)["latency_cycles"], 20)

    def test_reject_wrong_latency_or_split_store(self):
        for line in (
            "EVAL_MEMORY: unified=1 latency=50 i_outstanding=16 d_outstanding=8 line_bytes=16",
            "EVAL_MEMORY: unified=0 latency=20 i_outstanding=16 d_outstanding=8 line_bytes=16",
            "PASS: old runner without configuration",
        ):
            with self.assertRaises(BenchmarkError):
                evaluation_memory(line, 20)


class PerformanceCounterTests(unittest.TestCase):
    def test_all_groups_and_crlf(self):
        result = performance_counters(
            "noise\r\nPERF: rob_full=12 rs_full=8\r\n"
            "PERF_CACHE: d_req=42 d_hit=30\r\n"
            "PERF_PRED: correct=3 mispredict=1\r\n")
        self.assertEqual(result, {
            "PERF": {"rob_full": 12, "rs_full": 8},
            "PERF_CACHE": {"d_req": 42, "d_hit": 30},
            "PERF_PRED": {"correct": 3, "mispredict": 1},
        })

    def test_optional(self):
        self.assertEqual(performance_counters("PASS: no diagnostic counters"), {})

    def test_reject_ambiguous_or_malformed(self):
        for output in ("PERF: x=1\nPERF: x=2", "PERF: x=1 x=2",
                       "PERF: x=unknown", "PERF: x=-1"):
            with self.assertRaises(BenchmarkError):
                performance_counters(output)


if __name__ == "__main__":
    unittest.main()
