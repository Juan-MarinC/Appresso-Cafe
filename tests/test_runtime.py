import tempfile
import unittest
from pathlib import Path

from appresso_food.nucleo import runtime
from appresso_food.nucleo import storage
from appresso_food.nucleo.models import CHANNEL_DOMICILIO, CHANNEL_LOCAL, OrderItem
from appresso_food.nucleo.runtime import CoverageError


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        storage.DB_PATH = Path(self._tmp_dir.name) / "test.db"
        storage.init_db()
        runtime.init_runtime()
        self.product = storage.get_products()[0]

    def tearDown(self):
        self._tmp_dir.cleanup()

    def _cart(self, quantity=2):
        return [OrderItem(product_id=self.product.id, product_name=self.product.name, quantity=quantity, unit_price=self.product.price)]

    def test_domicilio_order_gets_route_and_enters_dispatch_heap(self):
        neighborhood = storage.get_neighborhood_names()[0]
        result = runtime.place_order("Ana", CHANNEL_DOMICILIO, neighborhood, self._cart(), served_by="Cajero1")

        self.assertIsNotNone(result.order.distance_km)
        self.assertGreater(result.order.distance_km, 0)
        self.assertEqual(len(runtime.dispatch_heap), 1)
        self.assertIn(result.order.order_id, runtime.pending_queue.as_list())

    def test_out_of_coverage_neighborhood_is_rejected(self):
        with self.assertRaises(CoverageError):
            runtime.place_order("Ana", CHANNEL_DOMICILIO, "Ciudad Inexistente", self._cart(), served_by=None)

    def test_undo_removes_created_order_and_restores_stock(self):
        ingredient_before = storage.get_ingredients()[0]
        result = runtime.place_order("Ana", CHANNEL_LOCAL, None, self._cart(), served_by=None)
        order_id = result.order.order_id

        runtime.undo_last()

        self.assertIsNone(storage.get_order(order_id))
        self.assertNotIn(order_id, runtime.pending_queue.as_list())
        ingredient_after = storage.get_ingredients()[0]
        self.assertEqual(ingredient_before.stock_qty, ingredient_after.stock_qty)

    def test_local_order_relation_shows_in_ranking(self):
        runtime.place_order("Ana", CHANNEL_LOCAL, None, self._cart(quantity=3), served_by=None)
        top = storage.top_products(limit=1)
        self.assertEqual(top[0][0], self.product.name)
        self.assertEqual(top[0][1], 3)


if __name__ == "__main__":
    unittest.main()
