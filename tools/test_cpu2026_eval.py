"""Reject benchmark results measured with a missing or incorrect memory setup."""
import unittest

from run_cpu2026 import BenchmarkError, evaluation_memory


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


if __name__ == "__main__":
    unittest.main()
