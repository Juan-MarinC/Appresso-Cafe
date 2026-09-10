"""Grafo de barrios para calcular rutas y distancias de domicilio (Dijkstra).

Cada barrio es un nodo y cada arista guarda la distancia en kilómetros entre
dos barrios. El restaurante físico es un nodo más (RESTAURANT_NODE) desde el
cual se calculan las rutas hacia el barrio del cliente.
"""

import heapq
from typing import Dict, List, Optional, Tuple

RESTAURANT_NODE = "Restaurante"
AVG_SPEED_KMH = 24.0


class DeliveryGraph:
    def __init__(self):
        self._adjacency: Dict[str, Dict[str, float]] = {}

    def add_node(self, name: str) -> None:
        self._adjacency.setdefault(name, {})

    def add_route(self, origin: str, destination: str, distance_km: float) -> None:
        """Agrega una arista bidireccional entre dos nodos (el mapa no es dirigido)."""
        self.add_node(origin)
        self.add_node(destination)
        self._adjacency[origin][destination] = distance_km
        self._adjacency[destination][origin] = distance_km

    def has_node(self, name: str) -> bool:
        return name in self._adjacency

    def nodes(self) -> List[str]:
        return list(self._adjacency.keys())

    def edges(self) -> List[Tuple[str, str, float]]:
        seen = set()
        result = []
        for origin, neighbors in self._adjacency.items():
            for destination, distance in neighbors.items():
                key = tuple(sorted((origin, destination)))
                if key not in seen:
                    seen.add(key)
                    result.append((origin, destination, distance))
        return result

    def shortest_path(self, origin: str, destination: str) -> Optional[Tuple[List[str], float]]:
        """Dijkstra: distancia mínima y ruta entre dos nodos del grafo.

        Devuelve ``None`` si alguno de los nodos no existe o no hay camino.
        """
        if origin not in self._adjacency or destination not in self._adjacency:
            return None

        distances = {node: float("inf") for node in self._adjacency}
        previous: Dict[str, Optional[str]] = {node: None for node in self._adjacency}
        distances[origin] = 0.0
        heap: List[Tuple[float, str]] = [(0.0, origin)]
        visited = set()

        while heap:
            current_distance, current_node = heapq.heappop(heap)
            if current_node in visited:
                continue
            visited.add(current_node)

            if current_node == destination:
                break

            for neighbor, weight in self._adjacency[current_node].items():
                candidate = current_distance + weight
                if candidate < distances[neighbor]:
                    distances[neighbor] = candidate
                    previous[neighbor] = current_node
                    heapq.heappush(heap, (candidate, neighbor))

        if distances[destination] == float("inf"):
            return None

        path = []
        node = destination
        while node is not None:
            path.append(node)
            node = previous[node]
        path.reverse()
        return path, distances[destination]

    def eta_minutes(self, distance_km: float, avg_speed_kmh: float = AVG_SPEED_KMH) -> float:
        return (distance_km / avg_speed_kmh) * 60


def build_graph(neighborhoods: List[str], edges: List[Tuple[str, str, float]]) -> DeliveryGraph:
    graph = DeliveryGraph()
    for name in neighborhoods:
        graph.add_node(name)
    for origin, destination, distance in edges:
        graph.add_route(origin, destination, distance)
    return graph
