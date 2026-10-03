"""Ranking de 'más pedidos' para guiar al cliente y al negocio."""

from typing import Dict, List, Tuple

from appresso_food.nucleo import storage


def most_ordered(limit: int = 5) -> List[Tuple[str, int]]:
    """Top de productos más pedidos (para mostrarle al cliente en el menú)."""
    return storage.top_products(limit)


def most_ordered_by_neighborhood() -> Dict[str, List[Tuple[str, int]]]:
    """Producto favorito de cada barrio: usa la relación barrio <-> producto."""
    return storage.top_products_by_neighborhood(limit_per_neighborhood=1)


def channel_comparison() -> Dict[str, Dict[str, float]]:
    """Comparación de ventas: local vs domicilio."""
    return storage.channel_summary()
