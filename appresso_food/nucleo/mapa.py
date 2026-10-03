"""Datos del mapa de domicilios: posición de cada barrio en el dibujo y ruta más corta (Dijkstra)."""

from typing import Optional

from appresso_food.nucleo import runtime
from appresso_food.nucleo.graph import RESTAURANT_NODE

# Posición en el mapa esquemático (x, y en una caja de 1000 x 700).
POSICIONES = {
    RESTAURANT_NODE: (430, 330),
    "Laureles": (300, 400),
    "Robledo": (110, 270),
    "Belén Castilla": (240, 580),
    "Belén Rincón": (420, 640),
    "Centro": (560, 190),
    "Buenos Aires": (770, 230),
    "El Poblado": (790, 430),
    "Envigado": (880, 580),
    "Itagüí": (590, 600),
    "Sabaneta": (760, 650),
}


def datos_mapa() -> dict:
    graph = runtime.graph
    nodos = []
    for nombre in graph.nodes():
        x, y = POSICIONES.get(nombre, (500, 350))
        ruta = graph.shortest_path(RESTAURANT_NODE, nombre)
        km = ruta[1] if ruta else None
        nodos.append({"nombre": nombre, "x": x, "y": y, "distancia_km": km,
                      "minutos": round(graph.eta_minutes(km)) if km is not None else None})
    return {
        "restaurante": RESTAURANT_NODE,
        "nodos": nodos,
        "aristas": [{"origen": o, "destino": d, "km": km} for o, d, km in graph.edges()],
    }


def ruta_a(barrio: str) -> Optional[dict]:
    resultado = runtime.graph.shortest_path(RESTAURANT_NODE, barrio)
    if resultado is None:
        return None
    ruta, km = resultado
    return {"barrio": barrio, "ruta": ruta, "distancia_km": km, "minutos": round(runtime.graph.eta_minutes(km))}
