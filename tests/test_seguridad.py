"""Pruebas de las protecciones para la URL pública: menú protegido, límite de peticiones y /logs sin datos sensibles."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from appresso_food.api import compat, http_log, productos_api
from appresso_food.nucleo import storage
from test_gestos import _ConBaseTemporal


class MenuProtegidoTest(_ConBaseTemporal):
    def setUp(self):
        super().setUp()
        app = FastAPI()
        app.include_router(productos_api.router)
        self.api = TestClient(app)  # TestClient no es "este equipo": se comporta como alguien por la URL pública
        self.menu = next(p for p in storage.get_products() if p.name == "Papas Fritas")

    def test_el_menu_no_se_cambia_ni_se_borra_desde_afuera(self):
        ruta = f"/api/productos/{self.menu.id}"
        for metodo, cuerpo in (("PATCH", {"precio": 1}), ("PUT", {"nombre": "Gratis", "precio": 1}), ("DELETE", None)):
            r = self.api.request(metodo, ruta, json=cuerpo)
            self.assertEqual(r.status_code, 403, metodo)
            self.assertEqual(r.json()["motivo"], "MENU_PROTEGIDO")
        self.assertEqual(storage.get_product(self.menu.id).price, 8000)

    def test_un_producto_propio_si_se_puede_editar_y_borrar(self):
        pid = self.api.post("/api/productos", json={"nombre": "Monitor de prueba", "precio": 800000}).json()["producto"]["id"]
        self.assertEqual(self.api.patch(f"/api/productos/{pid}", json={"precio": 60000}).status_code, 200)
        self.assertEqual(self.api.delete(f"/api/productos/{pid}").status_code, 200)

    def test_hay_un_tope_de_productos(self):
        with mock.patch.object(productos_api, "MAX_PRODUCTOS", len(storage.get_products())):
            r = self.api.post("/api/productos", json={"nombre": "Uno más", "precio": 1000})
        self.assertEqual((r.status_code, r.json()["motivo"]), (409, "LIMITE_PRODUCTOS"))


class LimitePeticionesTest(unittest.TestCase):
    def _cliente(self, **limites):
        app = FastAPI()
        app.get("/x")(lambda: {"ok": True})
        app.post("/x")(lambda: {"ok": True})
        app.add_middleware(compat.LimitePeticionesMiddleware, exentos=(), **limites)
        return TestClient(app)

    def test_pasado_el_limite_responde_429_explicado(self):
        c = self._cliente(escrituras=3, lecturas=5)
        self.assertEqual([c.post("/x").status_code for _ in range(4)], [200, 200, 200, 429])
        r = c.post("/x")
        self.assertEqual(r.json()["motivo"], "DEMASIADAS_PETICIONES")
        self.assertTrue(int(r.headers["retry-after"]) > 0)
        self.assertEqual(c.get("/x").status_code, 200)  # las lecturas llevan su propia cuenta

    def test_este_equipo_no_tiene_limite(self):
        app = FastAPI()
        app.post("/x")(lambda: {"ok": True})
        app.add_middleware(compat.LimitePeticionesMiddleware, escrituras=1)
        c = TestClient(app)  # su IP es "testclient", que está exenta como 127.0.0.1
        self.assertEqual([c.post("/x").status_code for _ in range(3)], [200, 200, 200])


class LogsSinDatosSensiblesTest(unittest.TestCase):
    def test_la_cedula_no_queda_en_el_registro(self):
        self.assertEqual(http_log._ocultar('{"cedula": "1012345678", "nombre": "Ana"}'), '{"cedula": "***", "nombre": "Ana"}')
        self.assertEqual(http_log._ocultar('{"cedula": 1012345678}'), '{"cedula": "***"}')
        self.assertEqual(http_log._ocultar("nombre=Ana&cedula=1012345678"), "nombre=Ana&cedula=***")

    def test_tampoco_con_otras_formas_de_escribirla(self):
        casos = {
            '{"Cédula": "1012345678"}': '{"Cédula": "***"}',
            '{"datos": {"CEDULA": 123456789, "otros": [{"clave": "x"}]}}': '{"datos": {"CEDULA": "***", "otros": [{"clave": "***"}]}}',
            '{"c\\u00e9dula": "1012345678"}': '{"cédula": "***"}',
            "nombre=Ana&c%C3%A9dula=1012345678&pedido-token=zz": "nombre=Ana&c%C3%A9dula=***&pedido-token=***",
            '{"idTxn": "1", "cedula": "10123': '{"idTxn": "1", "cedula": "***"',  # cuerpo cortado por el límite
            'name="cedula"\r\n\r\n1012345678\r\n': 'name="cedula"\r\n\r\n***\r\n',  # multipart
        }
        for original, esperado in casos.items():
            self.assertEqual(http_log._ocultar(original), esperado, original)

    def test_un_cuerpo_en_latin1_tambien_se_oculta(self):
        # Algunas terminales de Windows mandan "Cédula" en Latin-1, no en UTF-8.
        cuerpo = '{"Cédula": "1098765432"}'.encode("latin-1")
        self.assertNotIn("1098765432", http_log._text(cuerpo))
        self.assertEqual(http_log._decodificar("añ".encode("utf-8")[:-1]), "a")  # letra partida por el corte

    def test_dentro_de_textos_y_en_varias_lineas_tambien(self):
        self.assertEqual(http_log._ocultar("hola\nclave=abc\ntoken=xyz"), "hola\nclave=***\ntoken=***")
        self.assertEqual(http_log._ocultar('{"volver": "/pagar?pedido=3&clave=abc"}'), '{"volver": "/pagar?pedido=3&clave=***"}')
        self.assertNotIn("1012345678", http_log._ocultar('{"payload_original": "{\\"cedula\\": \\"1012345678\\"}"}'))

    def test_un_json_malicioso_no_rompe_ni_esquiva_el_registro(self):
        app = FastAPI()
        app.post("/eco")(lambda: {"ok": True})
        http_log.install(app, Path(tempfile.mkdtemp()) / "http.log")
        c = TestClient(app)
        envenenado, profundo = '{"nombre": "\\ud800"}', "[" * 3000 + "]" * 3000
        for cuerpo in (envenenado, profundo):
            self.assertEqual(c.post("/eco", content=cuerpo, headers={"Content-Type": "application/json"}).status_code, 200)
        r = c.get("/api/logs/http?limit=10")
        self.assertEqual(r.status_code, 200)  # antes el carácter inválido dejaba esta ruta respondiendo 500
        rutas = [e["ruta"] for e in r.json()["peticiones"]]
        self.assertEqual(rutas.count("/eco"), 2)  # las dos quedaron registradas, también la anidada

    def test_la_traza_no_se_entrega_por_la_url_publica(self):
        entrada = {"n": 999999, "traza": "Traceback (most recent call last): ...", "id": "x"}
        app = FastAPI()
        app.include_router(http_log.router)
        with mock.patch.object(http_log, "_requests", [entrada]):
            datos = TestClient(app).get("/api/logs/http").json()
        self.assertEqual([e["traza"] for e in datos["peticiones"]], [None])


class PrivacidadTest(_ConBaseTemporal):
    def test_la_pagina_explica_la_camara_y_la_ley(self):
        html = self.client.get("/privacidad").text
        for texto in ("No guardamos imágenes ni video", "Ley 1581 de 2012", "appresso_served_by", 'id="camara"'):
            self.assertIn(texto, html)
        self.assertNotIn('id="aviso-privacidad"', html)  # en la propia página no hace falta el aviso

    def test_el_aviso_y_los_enlaces_llegan_al_kiosko(self):
        html = self.client.get("/gestos").text
        self.assertIn('id="aviso-privacidad"', html)
        self.assertIn('href="/privacidad#camara"', html)


if __name__ == "__main__":
    unittest.main()
