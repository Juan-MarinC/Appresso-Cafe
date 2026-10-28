"""Página /gestos: combos que se piden con la mano y que se envían con el formulario normal de /pedidos.

Las reglas de los gestos (JavaScript) se prueban aparte: node --test tests/gestos_reglas.test.js
"""

import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from appresso_food import paginas
from appresso_food.api import gestos_api
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
        self.assertEqual(html.count('<form class="combo"'), 4)
        self.assertIn('data-numero="4"', html)
        self.assertIn('id="bienvenida"', html)
        self.assertIn('<form method="post" action="/pedidos" id="carrito-form">', html)

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
        # Lo que arma el carrito de gestos.js con 3 de un combo: cada cantidad del combo por 3
        datos = {"client": "Ana", "channel": "local", "product_id": ids, "quantity": [str(q * 3) for q in base]}
        self.assertEqual(self.client.post("/pedidos", data=datos).status_code, 200)
        pedido = storage.get_pending_orders()[0]
        self.assertEqual(sorted(i.quantity for i in pedido.items), sorted(q * 3 for q in base))

    def test_carrito_con_varios_combos_para_llevar(self):
        # Lo que arma gestos.js: cada producto una vez, con la suma de los combos del carrito.
        html = self.client.get("/gestos").text
        ids, cantidades = [], []
        for combo in re.findall(r'<form class="combo".*?</form>', html, re.S)[:2]:
            ids += re.findall(r'name="product_id" value="(\d+)"', combo)
            cantidades += re.findall(r'data-base="(\d+)"', combo)
        suma = {}
        for i, q in zip(ids, cantidades):
            suma[i] = suma.get(i, 0) + int(q)
        datos = {"client": "Ana", "channel": "local", "para_llevar": "1",
                 "product_id": list(suma), "quantity": [str(q) for q in suma.values()]}
        respuesta = self.client.post("/pedidos", data=datos)
        self.assertIn("para llevar", respuesta.text)
        pedido = storage.get_pending_orders()[0]
        self.assertTrue(pedido.para_llevar)
        self.assertEqual(pedido.total_quantity, sum(suma.values()))
        self.assertIn("para llevar", self.client.get("/cocina").text)

    def test_para_llevar_solo_aplica_al_local(self):
        producto = storage.get_products()[0]
        item = OrderItem(product_id=producto.id, product_name=producto.name, quantity=1, unit_price=producto.price)
        barrio = storage.get_neighborhood_names()[0]
        pedido = runtime.place_order("Domi", CHANNEL_DOMICILIO, barrio, [item], served_by=None, para_llevar=True).order
        self.assertFalse(storage.get_order(pedido.order_id).para_llevar)

    def test_una_base_vieja_recibe_la_columna_para_llevar(self):
        conn = storage._connect()
        conn.execute("ALTER TABLE orders DROP COLUMN para_llevar")
        conn.commit()
        conn.close()
        storage.init_db()
        self.test_el_formulario_de_un_combo_crea_el_pedido()


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


class ModeloGestosTest(unittest.TestCase):
    """Guardar el modelo entrenado en /entrenar: solo desde el mismo equipo y con archivos válidos."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._original = gestos_api.MODELO_DIR
        gestos_api.MODELO_DIR = Path(self._tmp.name) / "gestos"
        app = FastAPI()
        app.include_router(gestos_api.router)
        app.include_router(paginas.router)
        self.client = TestClient(app)

    def tearDown(self):
        gestos_api.MODELO_DIR = self._original
        os.environ.pop("APPRESSO_ENTRENAMIENTO", None)
        self._tmp.cleanup()

    def _archivos(self, **cambios):
        meta = {"outputs": {"0": {"uniqueValues": ["combo1", "nada"]}}, "_muestras": 240, "_precision": 97.5}  # como lo guarda ml5
        archivos = {
            "model.json": json.dumps({"modelTopology": {}, "weightsManifest": [{"paths": ["./model.weights.bin"], "weights": []}]}),
            "model.weights.bin": b"pesos",
            "model_meta.json": json.dumps(meta),
        }
        archivos.update(cambios)
        return {k: (k, v) for k, v in archivos.items() if v is not None}

    def _guardar(self, **cabeceras):
        cabeceras.setdefault("X-Entrenamiento-Token", gestos_api.TOKEN)
        return self.client.post("/api/gestos/modelo", files=self._archivos(), headers=cabeceras)

    def test_desde_otro_equipo_no_se_puede_guardar(self):
        self.assertEqual(self._guardar().status_code, 403)
        self.assertFalse(gestos_api.MODELO_DIR.exists())

    def test_sin_token_o_desde_otro_sitio_no_se_puede_guardar(self):
        os.environ["APPRESSO_ENTRENAMIENTO"] = "1"
        self.assertEqual(self._guardar(**{"X-Entrenamiento-Token": "adivinado"}).status_code, 403)
        self.assertEqual(self._guardar(Origin="https://otro-sitio.example").status_code, 403)
        self.assertEqual(self._guardar(**{"Sec-Fetch-Site": "cross-site"}).status_code, 403)
        self.assertFalse(gestos_api.MODELO_DIR.exists())

    def test_por_ngrok_la_pagina_no_entrega_el_token(self):
        # Por un túnel todo llega desde 127.0.0.1, pero el proxy agrega X-Forwarded-For.
        original = gestos_api.LOCALES
        gestos_api.LOCALES = original | {"testclient", "testserver"}  # el cliente de pruebas hace de "mismo equipo"
        self.addCleanup(setattr, gestos_api, "LOCALES", original)
        local = self.client
        self.assertIn(gestos_api.TOKEN, local.get("/entrenar").text)
        por_tunel = local.get("/entrenar", headers={"X-Forwarded-For": "203.0.113.9"}).text
        self.assertNotIn(gestos_api.TOKEN, por_tunel)
        self.assertNotIn(gestos_api.TOKEN, local.get("/entrenar", headers={"CF-Connecting-IP": "203.0.113.9"}).text)
        # DNS rebinding: llega desde 127.0.0.1 pero con el Host del sitio atacante.
        self.assertNotIn(gestos_api.TOKEN, local.get("/entrenar", headers={"Host": "atacante.example:8000"}).text)
        tunel = local.post("/api/gestos/modelo", files=self._archivos(),
                           headers={"X-Entrenamiento-Token": gestos_api.TOKEN, "X-Forwarded-For": "203.0.113.9"})
        self.assertEqual(tunel.status_code, 403)

    def test_guardar_y_consultar_el_modelo(self):
        os.environ["APPRESSO_ENTRENAMIENTO"] = "1"
        self.assertEqual(self.client.get("/api/gestos/modelo").json(), {"existe": False})
        respuesta = self._guardar()
        self.assertEqual(respuesta.status_code, 201)
        self.assertTrue((gestos_api.MODELO_DIR / "model.weights.bin").exists())
        estado = self.client.get("/api/gestos/modelo").json()
        self.assertTrue(estado["existe"])
        self.assertEqual(estado["clases"], ["combo1", "nada"])
        self.assertEqual(estado["precision"], 97.5)

    def test_rechaza_archivos_faltantes_o_invalidos(self):
        os.environ["APPRESSO_ENTRENAMIENTO"] = "1"
        token = {"X-Entrenamiento-Token": gestos_api.TOKEN}
        sin_pesos = self.client.post("/api/gestos/modelo", files=self._archivos(**{"model.weights.bin": None}), headers=token)
        self.assertEqual(sin_pesos.status_code, 400)
        roto = self.client.post("/api/gestos/modelo", files=self._archivos(**{"model_meta.json": "{no es json"}), headers=token)
        self.assertEqual(roto.json()["motivo"], "JSON_INVALIDO")
        sin_manifiesto = self.client.post("/api/gestos/modelo", files=self._archivos(**{"model.json": "{}"}), headers=token)
        self.assertEqual(sin_manifiesto.json()["motivo"], "MODELO_INVALIDO")
        self.assertFalse((gestos_api.MODELO_DIR / "model.json").exists())

    def test_pagina_de_entrenamiento(self):
        html = self.client.get("/entrenar").text
        self.assertEqual(html.count('class="clase"'), len(paginas.CLASES_GESTOS))
        self.assertIn('data-minimo="30"', html)


if __name__ == "__main__":
    unittest.main()
