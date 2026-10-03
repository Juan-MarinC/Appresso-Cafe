import unittest

from appresso_food.nucleo.algorithms import find_order_linear, recursive_total_units, total_units_sold
from appresso_food.nucleo.counter import OperationCounter
from appresso_food.nucleo.models import Order, OrderItem


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


if __name__ == "__main__":
    unittest.main()
