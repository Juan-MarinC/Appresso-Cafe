"""Progresión aritmética aplicada a fidelización de clientes.

Si un cliente viene aumentando su pedido en una cantidad fija cada semana,
a_n = a_1 + (n-1)d permite calcular en qué semana llegará a una meta de
unidades (y por lo tanto a un descuento por fidelización).
"""


def arithmetic_progression(start: int, difference: int, terms: int) -> list[int]:
    """Devuelve los primeros `terms` valores de una progresión aritmética."""
    return [start + difference * index for index in range(terms)]


def weeks_to_reach(target: int, start: int = 2, difference: int = 2) -> int:
    """Semanas necesarias para alcanzar `target` con un incremento fijo semanal."""
    if difference <= 0:
        return -1
    weeks = 0
    current = start
    while current < target:
        current += difference
        weeks += 1
    return weeks


def infer_weekly_increase(weekly_quantities: list[int]) -> int:
    """Estima la diferencia común (d) a partir del historial real de un cliente,
    promediando el incremento entre semanas consecutivas.
    """
    if len(weekly_quantities) < 2:
        return 0
    diffs = [weekly_quantities[i + 1] - weekly_quantities[i] for i in range(len(weekly_quantities) - 1)]
    return round(sum(diffs) / len(diffs))
