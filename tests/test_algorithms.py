import math
import unittest

from appresso_food.nucleo.algorithms import find_order_linear, recursive_total_units, total_units_sold
from appresso_food.nucleo.counter import OperationCounter
from appresso_food.nucleo.models import Order, OrderItem
from test_gestos import _ConBaseTemporal


def make_order(order_id: int, quantities: list[int]) -> Order:
    items = [OrderItem(product_id=1, product_name="Hamburguesa", quantity=q, unit_price=10000) for q in quantities]
    return Order(order_id=order_id, client="Cliente", channel="local", items=items)


class AlgorithmsTest(unittest.TestCase):
    def setUp(self):
        self.orders = [make_order(1, [2]), make_order(2, [1, 3]), make_order(3, [4])]

    def test_find_order_linear_counts_comparisons(self):
        counter = OperationCounter()
        found = find_order_linear(self.orders, 2, counter)

        self.assertEqual(found.order_id, 2)
        self.assertEqual(counter.comparisons, 2)

    def test_find_order_linear_missing_scans_everything(self):
        counter = OperationCounter()
        found = find_order_linear(self.orders, 99, counter)

        self.assertIsNone(found)
        self.assertEqual(counter.comparisons, len(self.orders))

    def test_total_units_sold_matches_recursive_total(self):
        counter_iter = OperationCounter()
        counter_rec = OperationCounter()

        iterative_total = total_units_sold(self.orders, counter_iter)
        recursive_total = recursive_total_units(self.orders, counter_rec)

        self.assertEqual(iterative_total, recursive_total)
        self.assertEqual(iterative_total, 2 + 1 + 3 + 4)

    def test_la_recursion_hace_2n_menos_1_llamadas_y_baja_log_n_niveles(self):
        for n in (1, 8, 100, 1000):
            counter = OperationCounter()
            recursive_total_units([make_order(i, [1]) for i in range(n)], counter)
            self.assertEqual(counter.calls, 2 * n - 1)
            self.assertEqual(counter.max_depth, math.ceil(math.log2(n)) + 1)


class LaboratorioTest(_ConBaseTemporal):
    def test_la_tabla_muestra_cada_n_hasta_el_elegido(self):
        html = self.client.post("/laboratorio", data={"size": "1000"}).text
        for n in (10, 100, 1000):
            self.assertIn(f"<td>{n}</td><td>{n}</td>", html)  # peor caso: n comparaciones
            self.assertIn(f"<td>{2 * n - 1}</td>", html)
        self.assertNotIn("<td>10000</td>", html)

    def test_el_csv_se_genera_y_no_se_sirven_archivos_del_disco(self):
        csv = self.client.get("/laboratorio/operation_counts.csv?size=100")
        self.assertEqual(csv.headers["content-type"].split(";")[0], "text/csv")
        self.assertEqual(csv.text.splitlines()[2].split(",")[:2], ["100", "100"])
        for archivo in ("README.md", "requirements.txt", ".gitignore"):
            self.assertEqual(self.client.get(f"/download/{archivo}").status_code, 404)

    def test_un_tamano_fuera_de_la_lista_es_400(self):
        self.assertEqual(self.client.post("/laboratorio", data={"size": "99999999"}).status_code, 400)
        self.assertEqual(self.client.get("/laboratorio/operation_counts.csv?size=-5").status_code, 400)


if __name__ == "__main__":
    unittest.main()
