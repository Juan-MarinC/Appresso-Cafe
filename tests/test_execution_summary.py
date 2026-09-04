import unittest

from appresso_analysis.app import resumen_ejecucion


class ExecutionSummaryTest(unittest.TestCase):
    def test_build_execution_summary_counts_operations_and_time(self):
        summary = resumen_ejecucion(tamano=10, operaciones_busqueda=7, operaciones_totales=25, llamadas_recursivas=12, segundos_transcurridos=0.245)

        self.assertEqual(summary["size"], 10)
        self.assertEqual(summary["processed_operations"], 44)
        self.assertEqual(summary["elapsed_seconds"], 0.245)
        self.assertIn("Tiempo", summary["message"])


if __name__ == "__main__":
    unittest.main()
