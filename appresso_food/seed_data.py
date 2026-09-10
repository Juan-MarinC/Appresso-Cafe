"""Datos iniciales: menú, ingredientes, barrios y distancias del grafo de domicilios.

Los barrios corresponden a zonas reales de Medellín (el mismo tipo de ejemplo
usado en la diapositiva de grafos: Belén Castilla, El Poblado, etc.) y las
distancias son aproximadas, pensadas para que el grafo tenga varias rutas
posibles entre el restaurante y cada barrio -tal como en el ejemplo A-B-C-D
de la diapositiva, donde el camino más corto no siempre es el directo.
"""

from appresso_food.graph import RESTAURANT_NODE

PRODUCTS = [
    ("Hamburguesa Clásica", "Hamburguesas", 16000),
    ("Hamburguesa Doble", "Hamburguesas", 21000),
    ("Perro Caliente", "Perros calientes", 12000),
    ("Alitas BBQ x6", "Pollo", 19000),
    ("Papas Fritas", "Acompañantes", 8000),
    ("Papas con Queso", "Acompañantes", 11000),
    ("Pizza Personal", "Pizza", 17000),
    ("Ensalada César", "Saludable", 14000),
    ("Malteada", "Bebidas", 9000),
    ("Gaseosa", "Bebidas", 5000),
]

INGREDIENTS = [
    ("Pan de hamburguesa", 500, "unidad"),
    ("Carne de res", 400, "porción"),
    ("Pollo", 300, "porción"),
    ("Salchicha", 300, "unidad"),
    ("Papa", 800, "porción"),
    ("Queso", 600, "porción"),
    ("Masa de pizza", 200, "unidad"),
    ("Lechuga", 500, "porción"),
    ("Tomate", 500, "porción"),
    ("Salsa BBQ", 400, "porción"),
    ("Leche", 300, "porción"),
    ("Gaseosa (lata)", 500, "unidad"),
]

# product_name -> [(ingredient_name, qty_required), ...]
PRODUCT_INGREDIENTS = {
    "Hamburguesa Clásica": [("Pan de hamburguesa", 1), ("Carne de res", 1), ("Lechuga", 1), ("Tomate", 1)],
    "Hamburguesa Doble": [("Pan de hamburguesa", 1), ("Carne de res", 2), ("Queso", 1), ("Lechuga", 1)],
    "Perro Caliente": [("Pan de hamburguesa", 1), ("Salchicha", 1), ("Salsa BBQ", 1)],
    "Alitas BBQ x6": [("Pollo", 2), ("Salsa BBQ", 1)],
    "Papas Fritas": [("Papa", 1)],
    "Papas con Queso": [("Papa", 1), ("Queso", 1)],
    "Pizza Personal": [("Masa de pizza", 1), ("Queso", 1), ("Tomate", 1)],
    "Ensalada César": [("Lechuga", 1), ("Tomate", 1), ("Pollo", 1)],
    "Malteada": [("Leche", 1)],
    "Gaseosa": [("Gaseosa (lata)", 1)],
}

# El restaurante está ubicado en Laureles y conecta con varios barrios;
# algunos barrios solo se alcanzan pasando por otro (para que Dijkstra tenga
# que comparar rutas, igual que el ejemplo A -> B directo vs A -> C -> D -> B).
NEIGHBORHOODS = [
    "Laureles",
    "El Poblado",
    "Belén Castilla",
    "Belén Rincón",
    "Robledo",
    "Envigado",
    "Sabaneta",
    "Centro",
    "Buenos Aires",
    "Itagüí",
]

EDGES = [
    (RESTAURANT_NODE, "Laureles", 0.8),
    ("Laureles", "Robledo", 3.5),
    ("Laureles", "Belén Castilla", 2.6),
    ("Laureles", "Centro", 4.0),
    ("Belén Castilla", "Belén Rincón", 1.8),
    ("Belén Castilla", "El Poblado", 6.5),
    ("Belén Rincón", "Itagüí", 3.2),
    ("Centro", "Buenos Aires", 3.0),
    ("Centro", "El Poblado", 4.5),
    ("Buenos Aires", "El Poblado", 2.4),
    ("El Poblado", "Envigado", 3.8),
    ("Envigado", "Sabaneta", 2.9),
    ("Itagüí", "Sabaneta", 2.2),
    ("Itagüí", "Envigado", 4.1),
]

COVERAGE_NOTE = (
    "El grafo solo cubre los barrios listados arriba. Un domicilio hacia un "
    "barrio fuera del grafo se rechaza automáticamente por estar fuera de "
    "cobertura."
)
