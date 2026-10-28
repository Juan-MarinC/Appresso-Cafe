"""Página /gestos: combos que se piden con la mano y que se envían con el formulario normal de /pedidos.

Las reglas de los gestos (JavaScript) se prueban aparte: node --test tests/gestos_reglas.test.js
"""

import re
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from appresso_food import paginas
from appresso_food.nucleo import runtime, storage
from appresso_food.nucleo.models import CHANNEL_DOMICILIO, OrderItem
from appresso_food.web import STATIC_DIR


class _ConBaseTemporal(unittest.TestCase):
    """Base SQLite temporal y una app con solo las páginas (sin MongoDB)."""

    def setUp(self):
        self._original = storage.DB_PATH
        self._tmp = tempfile.TemporaryDirectory()
        storage.DB_PATH = Path(self._tmp.name) / "test.db"
        storage.init_db()
        runtime.init_runtime()
        app = FastAPI()
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
        app.include_router(paginas.router)
        self.client = TestClient(app)

    def tearDown(self):
        storage.DB_PATH = self._original
        self._tmp.cleanup()


class GestosTest(_ConBaseTemporal):
    def test_combos_numerados_con_su_total(self):
        combos = paginas._combos(storage.get_products())
        self.assertEqual([c["numero"] for c in combos], [1, 2, 3, 4])
        clasico = combos[0]
        self.assertEqual(clasico["nombre"], "Combo clásico")
        self.assertEqual(clasico["total"], sum(p.price * q for p, q in clasico["lineas"]))

    def test_combo_con_producto_faltante_no_aparece_y_no_deja_huecos(self):
        productos = [p for p in storage.get_products() if p.name != "Hamburguesa Doble"]
        combos = paginas._combos(productos)
        self.assertNotIn("Combo doble", [c["nombre"] for c in combos])
        self.assertEqual([c["numero"] for c in combos], [1, 2, 3])

    def test_pagina_muestra_un_formulario_por_combo(self):
        html = self.client.get("/gestos").text
        self.assertEqual(html.count('action="/pedidos"'), 4)
        self.assertIn('data-numero="4"', html)

    def test_el_formulario_de_un_combo_crea_el_pedido(self):
        html = self.client.get("/gestos").text
        primero = re.search(r'<form class="combo".*?</form>', html, re.S).group(0)
        datos = {
            "client": "Ana",
            "channel": "local",
            "product_id": re.findall(r'name="product_id" value="(\d+)"', primero),
            "quantity": re.findall(r'name="quantity" value="(\d+)"', primero),
        }
        respuesta = self.client.post("/pedidos", data=datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("Ana", respuesta.text)
        self.assertEqual(len(storage.get_pending_orders()), 1)

    def test_combo_pedido_con_cantidad_multiplica_los_productos(self):
        html = self.client.get("/gestos").text
        self.assertIn('class="combo__cantidad"', html)
        primero = re.search(r'<form class="combo".*?</form>', html, re.S).group(0)
        ids = re.findall(r'name="product_id" value="(\d+)"', primero)
        base = [int(q) for q in re.findall(r'data-base="(\d+)"', primero)]
        # Lo que hace gestos.js al elegir cantidad 3: cada cantidad del combo por 3
        datos = {"client": "Ana", "channel": "local", "product_id": ids, "quantity": [str(q * 3) for q in base]}
        self.assertEqual(self.client.post("/pedidos", data=datos).status_code, 200)
        pedido = storage.get_pending_orders()[0]
        self.assertEqual(sorted(i.quantity for i in pedido.items), sorted(q * 3 for q in base))


class TurnosTest(_ConBaseTemporal):
    def _pedir(self, cliente, canal="local", barrio=None):
        producto = storage.get_products()[0]
        item = OrderItem(product_id=producto.id, product_name=producto.name, quantity=1, unit_price=producto.price)
        return runtime.place_order(cliente, canal, barrio, [item], served_by=None).order.order_id

    def test_preparando_y_listos_solo_del_local(self):
        primero = self._pedir("Ana Gómez")
        segundo = self._pedir("Luis")
        self._pedir("Domi", CHANNEL_DOMICILIO, storage.get_neighborhood_names()[0])
        runtime.advance_pending()  # cocina atiende el primero de la cola
        datos = self.client.get("/api/turnos").json()
        self.assertEqual(datos["listos"], [{"numero": primero, "cliente": "Ana"}])
        self.assertEqual([t["numero"] for t in datos["preparando"]], [segundo])

    def test_pagina_de_turnos(self):
        self.assertEqual(self.client.get("/turnos").status_code, 200)

    def test_un_pedido_listo_de_otro_dia_no_sale_en_pantalla(self):
        viejo = self._pedir("Ayer")
        runtime.advance_pending()
        conn = storage._connect()
        conn.execute("UPDATE orders SET created_at = ? WHERE order_id = ?", ("2020-01-01T10:00:00", viejo))
        conn.commit()
        conn.close()
        self.assertEqual(self.client.get("/api/turnos").json()["listos"], [])

    def test_confirmacion_desde_gestos_ofrece_volver_al_kiosko(self):
        producto = storage.get_products()[0]
        datos = {"client": "Ana", "channel": "local", "product_id": [str(producto.id)], "quantity": ["1"]}
        desde_gestos = self.client.post("/pedidos", data=datos, headers={"referer": "http://testserver/gestos"}).text
        desde_menu = self.client.post("/pedidos", data=datos, headers={"referer": "http://testserver/"}).text
        self.assertIn('id="volver-gestos"', desde_gestos)
        self.assertNotIn('id="volver-gestos"', desde_menu)
        self.assertIn("/turnos?pedido=", desde_menu)


class AyudaTest(_ConBaseTemporal):
    def setUp(self):
        super().setUp()
        paginas._avisos_ayuda.clear()

    def test_pedir_listar_y_atender(self):
        creado = self.client.post("/api/ayuda")
        self.assertEqual(creado.status_code, 201)
        aviso = creado.json()["id"]
        self.assertEqual([a["id"] for a in self.client.get("/api/ayuda").json()], [aviso])
        self.assertEqual(self.client.post(f"/api/ayuda/{aviso}/atender").status_code, 200)
        self.assertEqual(self.client.get("/api/ayuda").json(), [])

    def test_no_repite_el_aviso_mientras_esta_reciente(self):
        primero = self.client.post("/api/ayuda").json()["id"]
        repetido = self.client.post("/api/ayuda")
        self.assertEqual(repetido.status_code, 200)
        self.assertEqual(repetido.json()["id"], primero)
        self.assertEqual(len(self.client.get("/api/ayuda").json()), 1)

    def test_atender_un_aviso_que_no_existe_es_404(self):
        self.assertEqual(self.client.post("/api/ayuda/999/atender").status_code, 404)

    def test_cocina_carga_el_aviso(self):
        html = self.client.get("/cocina").text
        self.assertIn('id="aviso-ayuda"', html)
        self.assertIn("cocina-ayuda.js", html)


if __name__ == "__main__":
    unittest.main()
