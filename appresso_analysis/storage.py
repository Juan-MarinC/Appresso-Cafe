import sqlite3
import json
from pathlib import Path
from typing import List

from .orders import Order

# SQLite database file located next to this module
DB_PATH = Path(__file__).with_name('appresso.db')

def init_db() -> None:
    """Create the orders table if it does not exist."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY,
            client TEXT NOT NULL,
            products TEXT NOT NULL,  -- JSON encoded list
            quantities TEXT NOT NULL, -- JSON encoded list
            status TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def insert_orders(orders: List[Order]) -> None:
    """Insert a list of :class:`Order` objects into the database.
    Existing rows with the same ``order_id`` are replaced.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for order in orders:
        cur.execute(
            '''
            INSERT OR REPLACE INTO orders (order_id, client, products, quantities, status)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (
                order.order_id,
                order.client,
                json.dumps(order.products),
                json.dumps(order.quantities),
                order.status,
            ),
        )
    conn.commit()
    conn.close()

def get_all_orders() -> List[Order]:
    """Return all orders from the database as ``Order`` instances."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT order_id, client, products, quantities, status FROM orders')
    rows = cur.fetchall()
    conn.close()
    orders: List[Order] = []
    for row in rows:
        order_id, client, products_json, quantities_json, status = row
        orders.append(
            Order(
                order_id=order_id,
                client=client,
                products=json.loads(products_json),
                quantities=json.loads(quantities_json),
                status=status,
            )
        )
    return orders
