import random
from dataclasses import dataclass
from typing import List


@dataclass
class Pedido:
    id_pedido: int
    cliente: str
    productos: List[str]
    cantidades: List[int]
    estado: str  # 'Solicitado', 'En Proceso', 'Entregado'

    def cantidad_total(self) -> int:
        """Devuelve la cantidad total de productos del pedido."""
        return sum(self.cantidades)


def generar_pedidos(cantidad: int, semilla: int = 42) -> List[Pedido]:
    """Genera una lista de pedidos sintéticos con identificadores únicos."""
    random.seed(semilla)
    clientes = [f"Cliente{i}" for i in range(1, 11)]
    catalogo_productos = ["Café", "Té", "Latte", "Muffin", "Croissant", "Sandwich"]
    estados = ["Solicitado", "En Proceso", "Entregado"]
    pedidos: List[Pedido] = []
    for indice in range(1, cantidad + 1):
        cliente = random.choice(clientes)
        cantidad_productos = random.randint(1, 4)
        productos = random.sample(catalogo_productos, k=cantidad_productos)
        cantidades = [random.randint(1, 5) for _ in range(cantidad_productos)]
        estado = random.choice(estados)
        pedidos.append(Pedido(id_pedido=indice, cliente=cliente, productos=productos, cantidades=cantidades, estado=estado))
    return pedidos
