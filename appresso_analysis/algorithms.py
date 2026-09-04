from typing import List, Optional
from .orders import Order
from .counter import OperationCounter


def find_order_linear(orders: List[Order], target_id: int, counter: OperationCounter) -> Optional[Order]:
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
    """Recursively sum quantities by dividing the input into smaller ranges."""
    def analyze_range(start: int, end: int) -> int:
        counter.calls += 1
        if start >= end:
            return 0
        if end - start == 1:
            total = 0
            for qty in orders[start].quantities:
                counter.additions += 1
                total += qty
            return total

        midpoint = start + (end - start) // 2
        left_total = analyze_range(start, midpoint)
        right_total = analyze_range(midpoint, end)
        counter.additions += 1
        return left_total + right_total

    return analyze_range(index, len(orders))
