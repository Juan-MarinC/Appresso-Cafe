from typing import List
from .orders import Order
from .counter import OperationCounter


def find_order_linear(orders: List[Order], target_id: int, counter: OperationCounter) -> Order:
    """Linear search for an order by id. Counts each comparison as an operation."""
    for order in orders:
        counter.comparisons += 1
        if order.order_id == target_id:
            return order
    return None


def total_products(orders: List[Order], counter: OperationCounter) -> int:
    """Sum total quantity of all products across orders. Counts each addition as operation."""
    total = 0
    for order in orders:
        for qty in order.quantities:
            counter.additions += 1
            total += qty
    return total


def recursive_analyze(orders: List[Order], index: int, counter: OperationCounter) -> int:
    """Iteratively sum product quantities.
    This avoids Python recursion limits when the number of orders is large.
    """
    total = 0
    while index < len(orders):
        counter.calls += 1
        for qty in orders[index].quantities:
            counter.additions += 1
            total += qty
        index += 1
    return total
