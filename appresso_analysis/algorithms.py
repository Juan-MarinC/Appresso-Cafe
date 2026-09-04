from typing import List, Optional
from .orders import Pedido
from .counter import ContadorOperaciones


def buscar_pedido_lineal(pedidos: List[Pedido], id_objetivo: int, contador: ContadorOperaciones) -> Optional[Pedido]:
    """Busca un pedido por ID y cuenta cada comparación realizada."""
    for pedido in pedidos:
        contador.comparaciones += 1
        if pedido.id_pedido == id_objetivo:
            return pedido
    return None


def sumar_productos(pedidos: List[Pedido], contador: ContadorOperaciones) -> int:
    """Suma las cantidades de todos los productos y cuenta las sumas."""
    total = 0
    for pedido in pedidos:
        for cantidad in pedido.cantidades:
            contador.sumas += 1
            total += cantidad
    return total


def analizar_recursivamente(pedidos: List[Pedido], indice: int, contador: ContadorOperaciones) -> int:
    """Suma cantidades recursivamente dividiendo la entrada en rangos pequeños."""
    def analizar_rango(inicio: int, fin: int) -> int:
        contador.llamadas += 1
        if inicio >= fin:
            return 0
        if fin - inicio == 1:
            total = 0
            for cantidad in pedidos[inicio].cantidades:
                contador.sumas += 1
                total += cantidad
            return total

        mitad = inicio + (fin - inicio) // 2
        total_izquierdo = analizar_rango(inicio, mitad)
        total_derecho = analizar_rango(mitad, fin)
        contador.sumas += 1
        return total_izquierdo + total_derecho

    return analizar_rango(indice, len(pedidos))
