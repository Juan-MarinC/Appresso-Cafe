import unittest

from appresso_food.graph import DeliveryGraph


class DeliveryGraphTest(unittest.TestCase):
    def setUp(self):
        # Mismo ejemplo de la diapositiva: A-B directo (4 km) vs A-C-D-B (2+3+1=6 km).
        self.graph = DeliveryGraph()
        self.graph.add_route("A", "B", 4)
        self.graph.add_route("A", "C", 2)
        self.graph.add_route("C", "D", 3)
        self.graph.add_route("D", "B", 1)

    def test_shortest_path_prefers_direct_route_when_cheaper(self):
        path, distance = self.graph.shortest_path("A", "B")
        self.assertEqual(path, ["A", "B"])
        self.assertEqual(distance, 4)

    def test_shortest_path_prefers_indirect_route_when_cheaper(self):
        self.graph.add_route("A", "B", 10)
        path, distance = self.graph.shortest_path("A", "B")
        self.assertEqual(path, ["A", "C", "D", "B"])
        self.assertEqual(distance, 6)

    def test_unknown_node_returns_none(self):
        self.assertIsNone(self.graph.shortest_path("A", "Marte"))

    def test_has_node(self):
        self.assertTrue(self.graph.has_node("A"))
        self.assertFalse(self.graph.has_node("Marte"))


if __name__ == "__main__":
    unittest.main()
