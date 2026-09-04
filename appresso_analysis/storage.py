import sqlite3
import json
from pathlib import Path
from typing import List

from .orders import Pedido

# Archivo de base de datos SQLite junto a este módulo
DB_PATH = Path(__file__).with_name('appresso.db')

def inicializar_bd() -> None:
    """Crea la tabla de pedidos si todavía no existe."""
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

def insertar_pedidos(pedidos: List[Pedido]) -> None:
    """Guarda pedidos en la base de datos y reemplaza IDs repetidos."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for pedido in pedidos:
        cur.execute(
            '''
            INSERT OR REPLACE INTO orders (order_id, client, products, quantities, status)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (
                pedido.id_pedido,
                pedido.cliente,
                json.dumps(pedido.productos),
                json.dumps(pedido.cantidades),
                pedido.estado,
            ),
        )
    conn.commit()
    conn.close()

def obtener_pedidos() -> List[Pedido]:
    """Devuelve todos los pedidos como objetos ``Pedido``."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT order_id, client, products, quantities, status FROM orders')
    rows = cur.fetchall()
    conn.close()
    pedidos: List[Pedido] = []
    for row in rows:
        order_id, client, products_json, quantities_json, status = row
        pedidos.append(
            Pedido(
                id_pedido=order_id,
                cliente=client,
                productos=json.loads(products_json),
                cantidades=json.loads(quantities_json),
                estado=status,
            )
        )
    return pedidos
