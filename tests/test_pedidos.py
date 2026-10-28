"""POST /pedidos con entradas malas: responde 400 con un mensaje, nunca 500, y no crea pedidos de más."""

import re
import unittest
from types import SimpleNamespace

from appresso_food import paginas
from appresso_food.antifraude import fraud_routes
from appresso_food.nucleo import runtime, storage
from appresso_food.nucleo.models import CHANNEL_LOCAL, OrderItem
from test_gestos import _ConBaseTemporal


class PedidosTest(_ConBaseTemporal):
    def setUp(self):
        super().setUp()
        paginas._pedidos_por_token.clear()
        self.producto = storage.get_products()[0]

    def _pedir(self, **cambios):
        datos = {"client": "Ana", "channel": "local", "product_id": [str(self.producto.id)], "quantity": ["1"]}
        datos.update(cambios)
        return self.client.post("/pedidos", data=datos)

    def test_numeros_invalidos_son_400(self):
        self.assertEqual(self._pedir(quantity=["abc"]).status_code, 400)
        self.assertEqual(self._pedir(product_id=["x"]).status_code, 400)
        self.assertEqual(storage.get_pending_orders(), [])

    def test_cantidad_maxima_por_producto(self):
        self.assertEqual(self._pedir(quantity=[str(paginas.MAX_CANTIDAD + 1)]).status_code, 400)
        self.assertEqual(self._pedir(quantity=[str(paginas.MAX_CANTIDAD)]).status_code, 200)

    def test_canal_desconocido_es_400(self):
        self.assertEqual(self._pedir(channel="drone").status_code, 400)
        self.assertEqual(storage.get_pending_orders(), [])

    def test_nombre_largo_es_400_y_se_quitan_espacios(self):
        self.assertEqual(self._pedir(client="A" * (paginas.MAX_NOMBRE + 1)).status_code, 400)
        self.assertEqual(self._pedir(client="  Ana  ").status_code, 200)
        self.assertEqual(storage.get_pending_orders()[0].client, "Ana")

    def test_sin_inventario_no_crea_el_pedido(self):
        conn = storage._connect()
        conn.execute("UPDATE ingredients SET stock_qty = 0")
        conn.commit()
        conn.close()
        respuesta = self._pedir()
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("No alcanza el inventario", respuesta.text)
        self.assertEqual(storage.get_pending_orders(), [])

    def test_inventario_se_suma_entre_productos_del_mismo_pedido(self):
        # Dos líneas del mismo producto: cada una cabe sola, juntas no.
        item = OrderItem(product_id=self.producto.id, product_name=self.producto.name, quantity=1, unit_price=self.producto.price)
        conn = storage._connect()
        ingrediente_id, por_unidad = storage._recipe(conn.cursor(), self.producto.id)[0]
        conn.execute("UPDATE ingredients SET stock_qty = ? WHERE id = ?", (por_unidad * 1.5, ingrediente_id))
        conn.commit()
        conn.close()
        with self.assertRaises(runtime.StockError):
            runtime.place_order("Ana", CHANNEL_LOCAL, None, [item, item], served_by=None)
        self.assertEqual(len(runtime.place_order("Ana", CHANNEL_LOCAL, None, [item], served_by=None).order.items), 1)

    def test_doble_envio_con_el_mismo_token_crea_un_solo_pedido(self):
        token = re.search(r'name="pedido_token" value="([^"]+)"', self.client.get("/").text).group(1)
        primero = self._pedir(pedido_token=token)
        segundo = self._pedir(pedido_token=token)
        self.assertEqual((primero.status_code, segundo.status_code), (200, 200))
        self.assertEqual(len(storage.get_pending_orders()), 1)
        self._pedir(pedido_token="otro-formulario")
        self.assertEqual(len(storage.get_pending_orders()), 2)

    def test_cada_pagina_trae_un_token_nuevo(self):
        patron = r'name="pedido_token" value="([^"]+)"'
        self.assertNotEqual(re.findall(patron, self.client.get("/").text), re.findall(patron, self.client.get("/").text))
        self.assertEqual(len(set(re.findall(patron, self.client.get("/gestos").text))), 1)  # los 4 combos comparten el de la página


class PagoTest(_ConBaseTemporal):
    """Unir un pedido con su transacción de la pasarela (la pasarela se reemplaza por un diccionario)."""

    def setUp(self):
        super().setUp()
        self.transacciones = {}
        original = fraud_routes._service
        fraud_routes._service = SimpleNamespace(repo=SimpleNamespace(get_transaction=self.transacciones.get))
        self.addCleanup(setattr, fraud_routes, "_service", original)
        producto = storage.get_products()[0]
        item = OrderItem(product_id=producto.id, product_name=producto.name, quantity=2, unit_price=producto.price)
        self.pedido = runtime.place_order("Ana", CHANNEL_LOCAL, None, [item], served_by=None).order

    def _pagar(self, id_txn, estado="VALID", valor=None, pedido=None):
        self.transacciones[id_txn] = {"id_txn": id_txn, "estado": estado, "valor": self.pedido.total if valor is None else valor}
        return self.client.post(f"/api/pedidos/{pedido or self.pedido.order_id}/pago", json={"idTxn": id_txn})

    def test_pago_valido_por_el_total_marca_el_pedido(self):
        self.assertRegex(self._confirmacion(), rf'href="/transacciones\?pedido=\d+&valor={int(self.pedido.total)}"')
        self.assertEqual(self._pagar("t1").status_code, 200)
        self.assertEqual(storage.get_order(self.pedido.order_id).paid_txn, "t1")
        self.assertEqual(self._pagar("t1").status_code, 200)  # reintentar el mismo pago no falla
        self.assertIn("Pagado", self.client.get("/cocina").text)

    def test_rechaza_pagos_que_no_cuadran(self):
        self.assertEqual(self.client.post(f"/api/pedidos/{self.pedido.order_id}/pago", json={"idTxn": "nadie"}).status_code, 404)
        self.assertEqual(self._pagar("t2", estado="SUSPICIOUS").status_code, 409)
        self.assertEqual(self._pagar("t3", valor=self.pedido.total - 1).status_code, 409)
        self.assertEqual(self._pagar("t4", pedido=9999).status_code, 404)
        self.assertIsNone(storage.get_order(self.pedido.order_id).paid_txn)

    def test_una_transaccion_no_paga_dos_pedidos_ni_un_pedido_dos_veces(self):
        self.assertEqual(self._pagar("t5").status_code, 200)
        self.assertEqual(self._pagar("t6").status_code, 409)
        otro = runtime.place_order("Luis", CHANNEL_LOCAL, None, self.pedido.items, served_by=None).order
        self.assertEqual(self.client.post(f"/api/pedidos/{otro.order_id}/pago", json={"idTxn": "t5"}).status_code, 409)

    def test_un_pedido_pagado_no_se_puede_deshacer(self):
        self._pagar("t7")
        self.assertIn("ya está pagado", runtime.undo_last())  # el pedido es lo último que se hizo
        self.assertEqual(storage.get_order(self.pedido.order_id).paid_txn, "t7")

    def _confirmacion(self):
        producto = storage.get_products()[0]
        datos = {"client": "Ana", "channel": "local", "product_id": [str(producto.id)], "quantity": ["2"]}
        return self.client.post("/pedidos", data=datos).text


if __name__ == "__main__":
    unittest.main()
