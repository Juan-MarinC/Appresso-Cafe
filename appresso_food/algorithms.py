"""Algoritmos base sobre pedidos reales, instrumentados con OperationCounter
para poder justificar su complejidad (Big O) frente al profesor.
"""

from typing import List, Optional

from appresso_food.counter import OperationCounter
from appresso_food.models import Order


def find_order_linear(orders: List[Order], target_id: int, counter: OperationCounter) -> Optional[Order]:
    """Búsqueda lineal de un pedido por id. O(n) en el peor caso, O(1) en el mejor.
    Se usa en la vista de cocina para localizar un pedido por su número.
    """
    for order in orders:
        counter.comparisons += 1
        if order.order_id == target_id:
            return order
    return None


def total_units_sold(orders: List[Order], counter: OperationCounter) -> int:
    """Suma todas las unidades vendidas recorriendo cada ítem de cada pedido. O(n)."""
    total = 0
    for order in orders:
        for item in order.items:
            counter.additions += 1
            total += item.quantity
    return total


def recursive_total_units(orders: List[Order], counter: OperationCounter) -> int:
    """Mismo total que total_units_sold pero por divide y vencerás (recursividad
    controlada): reparte la lista en mitades hasta llegar a un pedido y combina
    resultados. Trabajo total O(n), profundidad O(log n).
    """
    def analyze_range(start: int, end: int) -> int:
        counter.calls += 1
        if start >= end:
            return 0
        if end - start == 1:
            subtotal = 0
            for item in orders[start].items:
                counter.additions += 1
                subtotal += item.quantity
            return subtotal

        midpoint = start + (end - start) // 2
        left_total = analyze_range(start, midpoint)
        right_total = analyze_range(midpoint, end)
        counter.additions += 1
        return left_total + right_total

    return analyze_range(0, len(orders))
