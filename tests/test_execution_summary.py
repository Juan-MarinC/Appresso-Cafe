import unittest

from appresso_analysis.app import build_execution_summary


class ExecutionSummaryTest(unittest.TestCase):
    def test_build_execution_summary_counts_operations_and_time(self):
        summary = build_execution_summary(size=10, find_ops=7, total_ops=25, rec_calls=12, elapsed_seconds=0.245)

        self.assertEqual(summary["size"], 10)
        self.assertEqual(summary["processed_operations"], 44)
        self.assertEqual(summary["elapsed_seconds"], 0.245)
        self.assertIn("Tiempo", summary["message"])


if __name__ == "__main__":
    unittest.main()
