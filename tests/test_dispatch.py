import unittest

from appresso_food.nucleo.dispatch import DispatchHeap


class DispatchHeapTest(unittest.TestCase):
    def test_pop_next_returns_closest_regardless_of_arrival_order(self):
        heap = DispatchHeap()
        heap.push(order_id=1, client="A", neighborhood="Lejos", distance_km=8.0, eta_minutes=20)
        heap.push(order_id=2, client="B", neighborhood="Cerca", distance_km=1.5, eta_minutes=5)
        heap.push(order_id=3, client="C", neighborhood="Medio", distance_km=4.0, eta_minutes=10)

        first = heap.pop_next()
        second = heap.pop_next()
        third = heap.pop_next()

        self.assertEqual([first.order_id, second.order_id, third.order_id], [2, 3, 1])

    def test_tie_breaks_by_arrival_order(self):
        heap = DispatchHeap()
        heap.push(order_id=1, client="A", neighborhood="X", distance_km=3.0, eta_minutes=10)
        heap.push(order_id=2, client="B", neighborhood="Y", distance_km=3.0, eta_minutes=10)

        first = heap.pop_next()
        self.assertEqual(first.order_id, 1)

    def test_remove_excludes_entry_without_reordering_errors(self):
        heap = DispatchHeap()
        heap.push(order_id=1, client="A", neighborhood="X", distance_km=2.0, eta_minutes=5)
        heap.push(order_id=2, client="B", neighborhood="Y", distance_km=5.0, eta_minutes=12)
        heap.remove(1)

        self.assertEqual(len(heap), 1)
        entry = heap.pop_next()
        self.assertEqual(entry.order_id, 2)

    def test_remove_then_push_again_does_not_duplicate_in_priority_list(self):
        """Regresión: deshacer un 'avanzar_pedido' hace remove() y luego push()
        del mismo order_id; no debe quedar dos veces en as_priority_list().
        """
        heap = DispatchHeap()
        heap.push(order_id=1, client="A", neighborhood="X", distance_km=9.3, eta_minutes=23)
        heap.remove(1)
        heap.push(order_id=1, client="A", neighborhood="X", distance_km=9.3, eta_minutes=23)

        priority_list = heap.as_priority_list()
        self.assertEqual(len(priority_list), 1)
        self.assertEqual(len(heap), 1)


if __name__ == "__main__":
    unittest.main()
