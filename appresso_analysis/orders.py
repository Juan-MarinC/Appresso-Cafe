import random
from dataclasses import dataclass
from typing import List


@dataclass
class Order:
    order_id: int
    client: str
    products: List[str]
    quantities: List[int]
    status: str  # 'Solicitado', 'En Proceso', 'Entregado'

    def total_quantity(self) -> int:
        """Return the total quantity of all products in the order."""
        return sum(self.quantities)


def generate_orders(num: int, seed: int = 42) -> List[Order]:
    """Generate a list of synthetic orders.
    Each order receives a unique ``order_id`` starting at 1.
    """
    random.seed(seed)
    clients = [f"Cliente{i}" for i in range(1, 11)]
    product_catalog = ["Café", "Té", "Latte", "Muffin", "Croissant", "Sandwich"]
    statuses = ["Solicitado", "En Proceso", "Entregado"]
    orders: List[Order] = []
    for i in range(1, num + 1):
        client = random.choice(clients)
        num_items = random.randint(1, 4)
        products = random.sample(product_catalog, k=num_items)
        quantities = [random.randint(1, 5) for _ in range(num_items)]
        status = random.choice(statuses)
        orders.append(Order(order_id=i, client=client, products=products, quantities=quantities, status=status))
    return orders
