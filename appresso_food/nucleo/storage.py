"""Persistencia en SQLite.

Relaciones del modelo (mínimo dos, con ambas tablas vinculadas de verdad):
  1. orders.neighborhood_id -> neighborhoods.id      (pedido <-> barrio)
  2. order_items.order_id   -> orders.id             (pedido <-> producto, vía tabla puente)
     order_items.product_id -> products.id
  3. product_ingredients    -> products / ingredients (producto <-> ingrediente, bono de inventario)

Con (1) y (2) ya se puede responder, por ejemplo, "qué producto es el más
pedido en Belén Castilla": se hace un join orders -> order_items -> products
filtrando por neighborhoods.name.
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from appresso_food.nucleo import seed_data
from appresso_food.nucleo.graph import RESTAURANT_NODE
from appresso_food.nucleo.models import Ingredient, Neighborhood, Order, OrderItem, Product

DB_PATH = Path(__file__).resolve().parent.parent / "appresso_food.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,
    price REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    stock_qty REAL NOT NULL,
    unit TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS product_ingredients (
    product_id INTEGER NOT NULL REFERENCES products(id),
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),
    qty_required REAL NOT NULL,
    PRIMARY KEY (product_id, ingredient_id)
);

CREATE TABLE IF NOT EXISTS neighborhoods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    is_restaurant INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS neighborhood_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origin_id INTEGER NOT NULL REFERENCES neighborhoods(id),
    destination_id INTEGER NOT NULL REFERENCES neighborhoods(id),
    distance_km REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    client TEXT NOT NULL,
    channel TEXT NOT NULL,
    neighborhood_id INTEGER REFERENCES neighborhoods(id),
    status TEXT NOT NULL,
    served_by TEXT,
    distance_km REAL,
    eta_minutes REAL,
    route TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = _connect()
    conn.executescript(SCHEMA)
    conn.commit()
    _seed_if_empty(conn)
    conn.close()


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM products")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO products (name, category, price) VALUES (?, ?, ?)",
            seed_data.PRODUCTS,
        )

    cur.execute("SELECT COUNT(*) FROM ingredients")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO ingredients (name, stock_qty, unit) VALUES (?, ?, ?)",
            seed_data.INGREDIENTS,
        )

    cur.execute("SELECT COUNT(*) FROM product_ingredients")
    if cur.fetchone()[0] == 0:
        product_ids = dict(cur.execute("SELECT name, id FROM products").fetchall())
        ingredient_ids = dict(cur.execute("SELECT name, id FROM ingredients").fetchall())
        rows = []
        for product_name, requirements in seed_data.PRODUCT_INGREDIENTS.items():
            for ingredient_name, qty in requirements:
                rows.append((product_ids[product_name], ingredient_ids[ingredient_name], qty))
        cur.executemany(
            "INSERT INTO product_ingredients (product_id, ingredient_id, qty_required) VALUES (?, ?, ?)",
            rows,
        )

    cur.execute("SELECT COUNT(*) FROM neighborhoods")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO neighborhoods (name, is_restaurant) VALUES (?, 1)",
            (RESTAURANT_NODE,),
        )
        cur.executemany(
            "INSERT INTO neighborhoods (name, is_restaurant) VALUES (?, 0)",
            [(name,) for name in seed_data.NEIGHBORHOODS],
        )

    cur.execute("SELECT COUNT(*) FROM neighborhood_edges")
    if cur.fetchone()[0] == 0:
        name_to_id = dict(cur.execute("SELECT name, id FROM neighborhoods").fetchall())
        cur.executemany(
            "INSERT INTO neighborhood_edges (origin_id, destination_id, distance_km) VALUES (?, ?, ?)",
            [(name_to_id[a], name_to_id[b], dist) for a, b, dist in seed_data.EDGES],
        )

    conn.commit()


# ---------------------------------------------------------------------------
# Productos e ingredientes
# ---------------------------------------------------------------------------

def get_products() -> List[Product]:
    conn = _connect()
    rows = conn.execute("SELECT id, name, category, price FROM products ORDER BY category, name").fetchall()
    conn.close()
    return [Product(*row) for row in rows]


def get_product(product_id: int) -> Optional[Product]:
    conn = _connect()
    row = conn.execute("SELECT id, name, category, price FROM products WHERE id = ?", (product_id,)).fetchone()
    conn.close()
    return Product(*row) if row else None


def get_ingredients() -> List[Ingredient]:
    conn = _connect()
    rows = conn.execute("SELECT id, name, stock_qty, unit FROM ingredients ORDER BY name").fetchall()
    conn.close()
    return [Ingredient(*row) for row in rows]


def deduct_ingredients_for_items(items: List[OrderItem]) -> List[str]:
    """Descuenta inventario por cada producto vendido. Devuelve alertas de stock bajo."""
    conn = _connect()
    cur = conn.cursor()
    warnings: List[str] = []
    for item in items:
        rows = cur.execute(
            "SELECT ingredient_id, qty_required FROM product_ingredients WHERE product_id = ?",
            (item.product_id,),
        ).fetchall()
        for ingredient_id, qty_required in rows:
            needed = qty_required * item.quantity
            cur.execute(
                "UPDATE ingredients SET stock_qty = stock_qty - ? WHERE id = ?",
                (needed, ingredient_id),
            )
            remaining = cur.execute("SELECT name, stock_qty FROM ingredients WHERE id = ?", (ingredient_id,)).fetchone()
            if remaining and remaining[1] <= 0:
                warnings.append(f"{remaining[0]} sin stock")
    conn.commit()
    conn.close()
    return warnings


def restore_ingredients_for_items(items: List[OrderItem]) -> None:
    """Revierte el descuento de inventario (usado por la pila de deshacer)."""
    conn = _connect()
    cur = conn.cursor()
    for item in items:
        rows = cur.execute(
            "SELECT ingredient_id, qty_required FROM product_ingredients WHERE product_id = ?",
            (item.product_id,),
        ).fetchall()
        for ingredient_id, qty_required in rows:
            cur.execute(
                "UPDATE ingredients SET stock_qty = stock_qty + ? WHERE id = ?",
                (qty_required * item.quantity, ingredient_id),
            )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Barrios / grafo
# ---------------------------------------------------------------------------

def get_neighborhood_names(include_restaurant: bool = False) -> List[str]:
    conn = _connect()
    if include_restaurant:
        rows = conn.execute("SELECT name FROM neighborhoods ORDER BY is_restaurant DESC, name").fetchall()
    else:
        rows = conn.execute("SELECT name FROM neighborhoods WHERE is_restaurant = 0 ORDER BY name").fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_graph_edges() -> List[Tuple[str, str, float]]:
    conn = _connect()
    rows = conn.execute(
        """
        SELECT o.name, d.name, e.distance_km
        FROM neighborhood_edges e
        JOIN neighborhoods o ON o.id = e.origin_id
        JOIN neighborhoods d ON d.id = e.destination_id
        """
    ).fetchall()
    conn.close()
    return [(row[0], row[1], row[2]) for row in rows]


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------

def create_order(order: Order) -> int:
    conn = _connect()
    cur = conn.cursor()

    neighborhood_id = None
    if order.neighborhood:
        row = cur.execute("SELECT id FROM neighborhoods WHERE name = ?", (order.neighborhood,)).fetchone()
        neighborhood_id = row[0] if row else None

    cur.execute(
        """
        INSERT INTO orders (client, channel, neighborhood_id, status, served_by, distance_km, eta_minutes, route, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order.client,
            order.channel,
            neighborhood_id,
            order.status,
            order.served_by,
            order.distance_km,
            order.eta_minutes,
            json.dumps(order.route) if order.route else None,
            order.created_at,
        ),
    )
    order_id = cur.lastrowid

    for item in order.items:
        cur.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
            (order_id, item.product_id, item.quantity, item.unit_price),
        )

    conn.commit()
    conn.close()
    return order_id


def delete_order(order_id: int) -> None:
    conn = _connect()
    conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
    conn.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
    conn.commit()
    conn.close()


def get_order_status(order_id: int) -> Optional[str]:
    conn = _connect()
    row = conn.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    conn.close()
    return row[0] if row else None


def update_order_status(order_id: int, status: str) -> None:
    conn = _connect()
    conn.execute("UPDATE orders SET status = ? WHERE order_id = ?", (status, order_id))
    conn.commit()
    conn.close()


def _row_to_order(conn: sqlite3.Connection, row) -> Order:
    (order_id, client, channel, neighborhood_name, status, served_by,
     distance_km, eta_minutes, route_json, created_at) = row
    items_rows = conn.execute(
        """
        SELECT oi.product_id, p.name, oi.quantity, oi.unit_price
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        """,
        (order_id,),
    ).fetchall()
    items = [OrderItem(product_id=r[0], product_name=r[1], quantity=r[2], unit_price=r[3]) for r in items_rows]
    return Order(
        order_id=order_id,
        client=client,
        channel=channel,
        items=items,
        status=status,
        neighborhood=neighborhood_name,
        served_by=served_by,
        distance_km=distance_km,
        eta_minutes=eta_minutes,
        route=json.loads(route_json) if route_json else None,
        created_at=created_at,
    )


_ORDER_SELECT = """
    SELECT o.order_id, o.client, o.channel, n.name, o.status, o.served_by,
           o.distance_km, o.eta_minutes, o.route, o.created_at
    FROM orders o
    LEFT JOIN neighborhoods n ON n.id = o.neighborhood_id
"""


def get_order(order_id: int) -> Optional[Order]:
    conn = _connect()
    row = conn.execute(_ORDER_SELECT + " WHERE o.order_id = ?", (order_id,)).fetchone()
    order = _row_to_order(conn, row) if row else None
    conn.close()
    return order


def get_all_orders() -> List[Order]:
    conn = _connect()
    rows = conn.execute(_ORDER_SELECT + " ORDER BY o.created_at").fetchall()
    orders = [_row_to_order(conn, row) for row in rows]
    conn.close()
    return orders


def get_pending_orders() -> List[Order]:
    conn = _connect()
    rows = conn.execute(
        _ORDER_SELECT + " WHERE o.status = 'Solicitado' ORDER BY o.created_at"
    ).fetchall()
    orders = [_row_to_order(conn, row) for row in rows]
    conn.close()
    return orders


def get_client_history(client: str) -> List[Order]:
    conn = _connect()
    rows = conn.execute(
        _ORDER_SELECT + " WHERE o.client = ? ORDER BY o.created_at", (client,)
    ).fetchall()
    orders = [_row_to_order(conn, row) for row in rows]
    conn.close()
    return orders


# ---------------------------------------------------------------------------
# Analítica: ranking, canales, series diarias
# ---------------------------------------------------------------------------

def top_products(limit: int = 5) -> List[Tuple[str, int]]:
    conn = _connect()
    rows = conn.execute(
        """
        SELECT p.name, SUM(oi.quantity) AS total_qty
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        GROUP BY p.name
        ORDER BY total_qty DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [(row[0], row[1]) for row in rows]


def top_products_by_neighborhood(limit_per_neighborhood: int = 1) -> Dict[str, List[Tuple[str, int]]]:
    """Producto más pedido por barrio: relación barrio <-> producto vía pedidos."""
    conn = _connect()
    rows = conn.execute(
        """
        SELECT n.name, p.name, SUM(oi.quantity) AS total_qty
        FROM orders o
        JOIN neighborhoods n ON n.id = o.neighborhood_id
        JOIN order_items oi ON oi.order_id = o.order_id
        JOIN products p ON p.id = oi.product_id
        WHERE o.channel = 'domicilio'
        GROUP BY n.name, p.name
        ORDER BY n.name, total_qty DESC
        """
    ).fetchall()
    conn.close()

    result: Dict[str, List[Tuple[str, int]]] = {}
    for neighborhood_name, product_name, total_qty in rows:
        bucket = result.setdefault(neighborhood_name, [])
        if len(bucket) < limit_per_neighborhood:
            bucket.append((product_name, total_qty))
    return result


def channel_summary() -> Dict[str, Dict[str, float]]:
    conn = _connect()
    rows = conn.execute(
        """
        SELECT o.channel, COUNT(DISTINCT o.order_id) AS orders_count,
               COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS revenue
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.order_id
        GROUP BY o.channel
        """
    ).fetchall()
    conn.close()
    return {row[0]: {"orders": row[1], "revenue": row[2]} for row in rows}


def daily_totals(channel: Optional[str] = None) -> List[float]:
    """Unidades vendidas por día (para la proyección de ventas)."""
    conn = _connect()
    query = """
        SELECT substr(o.created_at, 1, 10) AS day, SUM(oi.quantity) AS units
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.order_id
    """
    params: Tuple = ()
    if channel:
        query += " WHERE o.channel = ?"
        params = (channel,)
    query += " GROUP BY day ORDER BY day"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [row[1] for row in rows]


# ---------------------------------------------------------------------------
# API REST de productos (GET / POST / PUT / PATCH / DELETE)
# ---------------------------------------------------------------------------

def find_product_by_name(name: str) -> Optional[Product]:
    conn = _connect()
    row = conn.execute("SELECT id, name, category, price FROM products WHERE lower(name) = lower(?)", (name,)).fetchone()
    conn.close()
    return Product(*row) if row else None


def create_product(name: str, category: str, price: float) -> Product:
    conn = _connect()
    cur = conn.execute("INSERT INTO products (name, category, price) VALUES (?, ?, ?)", (name, category, price))
    conn.commit()
    product_id = cur.lastrowid
    conn.close()
    return Product(product_id, name, category, price)


def update_product(product_id: int, name: str, category: str, price: float) -> Optional[Product]:
    conn = _connect()
    cur = conn.execute("UPDATE products SET name = ?, category = ?, price = ? WHERE id = ?", (name, category, price, product_id))
    conn.commit()
    conn.close()
    return Product(product_id, name, category, price) if cur.rowcount else None


def product_usage(product_id: int) -> Tuple[int, int]:
    """(pedidos en los que aparece, unidades vendidas). Un producto con historial no se puede borrar."""
    conn = _connect()
    row = conn.execute(
        "SELECT COUNT(DISTINCT order_id), COALESCE(SUM(quantity), 0) FROM order_items WHERE product_id = ?", (product_id,)
    ).fetchone()
    conn.close()
    return row[0], row[1]


def delete_product(product_id: int) -> None:
    conn = _connect()
    conn.execute("DELETE FROM product_ingredients WHERE product_id = ?", (product_id,))
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
