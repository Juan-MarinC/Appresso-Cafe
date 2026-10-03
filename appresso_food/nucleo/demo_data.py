"""Generador de pedidos sintéticos para el laboratorio de complejidad
computacional (Big O). No se guardan en la base de datos: sirven únicamente
para medir cómo escalan los algoritmos de appresso_food.algorithms cuando
crece la cantidad de pedidos (10, 100, 1.000, 10.000, n...), tal como pide
la diapositiva de Programación Avanzada.
"""

import random
from typing import List

from appresso_food.nucleo.models import CHANNEL_DOMICILIO, CHANNEL_LOCAL, Order, OrderItem
from appresso_food.nucleo.models import Product


def generate_demo_orders(num: int, products: List[Product], neighborhoods: List[str], seed: int = 42) -> List[Order]:
    random.seed(seed)
    clients = [f"Cliente{i}" for i in range(1, 21)]
    orders: List[Order] = []
    for i in range(1, num + 1):
        client = random.choice(clients)
        channel = random.choice([CHANNEL_LOCAL, CHANNEL_DOMICILIO])
        chosen_products = random.sample(products, k=min(len(products), random.randint(1, 4)))
        items = [
            OrderItem(product_id=p.id, product_name=p.name, quantity=random.randint(1, 5), unit_price=p.price)
            for p in chosen_products
        ]
        neighborhood = random.choice(neighborhoods) if channel == CHANNEL_DOMICILIO else None
        orders.append(Order(order_id=i, client=client, channel=channel, items=items, neighborhood=neighborhood))
    return orders
