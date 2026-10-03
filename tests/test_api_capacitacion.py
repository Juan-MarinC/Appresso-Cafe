"""Pruebas de la API de productos (REST), el hash genérico, los totales y la bitácora HTTP.

No necesitan servidor ni MongoDB: usan una base SQLite temporal y las funciones puras de cada módulo.
Las rutas completas por HTTP se prueban con tests/prueba_profesor.py contra el servidor corriendo.
"""

import hashlib
import hmac
import json
import tempfile
import unittest
from pathlib import Path

from appresso_food import fraud_hashing as hashing
from appresso_food import http_log, productos_api, storage
from appresso_food.api_helpers import verify_hash
from appresso_food.capacitacion_api import calculate_total
from appresso_food.fraud_config import DEFAULT_SECRET, FraudConfig
from appresso_food.models import OrderItem, Order


def class_hash(payload, key=DEFAULT_SECRET.encode()):
    """El código de la diapositiva, tal cual."""
    datos = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, datos.encode("utf-8"), hashlib.sha256).hexdigest()


class ProductValidationTests(unittest.TestCase):
    def test_string_price_is_normalized_and_abc_is_never_zero(self):
        clean, errors, _ = productos_api._validate({"nombre": "Monitor", "precio": "50000"}, ("nombre", "precio"))
        self.assertEqual((clean["precio"], errors), (50000.0, []))
        for bad in ("abc", "-5", 0, "50.000,00", True, [1], None):
            clean, errors, _ = productos_api._validate({"nombre": "Monitor", "precio": bad}, ("nombre", "precio"))
            self.assertTrue(errors and "precio" not in clean, bad)

    def test_all_errors_reported_and_unknown_fields_ignored_with_note(self):
        clean, errors, ignored = productos_api._validate({"nombre": "", "precio": "abc", "id": 7, "color": "rojo"}, ("nombre", "precio"))
        self.assertEqual({e.campo for e in errors}, {"nombre", "precio"})
        self.assertEqual(ignored, ["id", "color"])
        self.assertEqual(len(productos_api._notes(ignored)), 2)

    def test_patch_validates_only_what_arrives(self):
        clean, errors, _ = productos_api._validate({"precio": 60000}, ())
        self.assertEqual((clean, errors), ({"precio": 60000.0}, []))


class ProductStorageTests(unittest.TestCase):
    def setUp(self):
        self._original = storage.DB_PATH
        self._tmp = tempfile.TemporaryDirectory()
        storage.DB_PATH = Path(self._tmp.name) / "test.db"
        storage.init_db()

    def tearDown(self):
        storage.DB_PATH = self._original
        self._tmp.cleanup()

    def test_crud_cycle_matches_the_slide(self):
        product = storage.create_product("Monitor", "General", 800000)
        self.assertEqual(storage.get_product(product.id).price, 800000)
        storage.update_product(product.id, "Monitor", "General", 60000)  # PATCH del precio
        self.assertEqual(storage.get_product(product.id).price, 60000)
        self.assertIsNone(storage.update_product(99999, "x", "y", 1))
        storage.delete_product(product.id)
        self.assertIsNone(storage.get_product(product.id))

    def test_name_lookup_is_case_insensitive(self):
        self.assertEqual(storage.find_product_by_name("hamburguesa clásica").name, "Hamburguesa Clásica")
        self.assertIsNone(storage.find_product_by_name("no existe"))

    def test_product_with_history_reports_usage(self):
        burger = storage.get_products()[0]
        self.assertEqual(storage.product_usage(burger.id), (0, 0))
        storage.create_order(Order(order_id=0, client="Ana", channel="local", items=[OrderItem(burger.id, burger.name, 3, burger.price)], created_at="2026-10-03T10:00:00"))
        self.assertEqual(storage.product_usage(burger.id), (1, 3))


class GenericHashTests(unittest.TestCase):
    config = FraudConfig()
    slide = {"id": 1001, "producto": "Mouse", "cantidad": 4, "valor": 50000}

    def test_slide_example_is_accepted(self):
        status, body = verify_hash(dict(self.slide, hash=class_hash(self.slide)), self.config)
        self.assertEqual((status, body["resultado"]), (200, "ACEPTADA"))

    def test_modified_data_is_rejected_with_the_reason(self):
        status, body = verify_hash(dict(self.slide, cantidad=3, hash=class_hash(self.slide)), self.config)
        self.assertEqual((status, body["motivo"]), (422, "HASH_MISMATCH"))
        self.assertIn("mensaje", body)
        self.assertEqual(body["diagnostico_hash"]["texto_que_firma_el_servidor"], hashing.canonical_json(dict(self.slide, cantidad=3)))

    def test_other_key_and_plain_sha256_are_explained(self):
        legacy = verify_hash(dict(self.slide, hash=class_hash(self.slide, b"appresso-dev-secret-change-me")), self.config)[1]
        self.assertIn("anterior de Appresso", legacy["diagnostico_hash"]["causa_probable"])
        plain = hashlib.sha256(hashing.canonical_json(self.slide).encode()).hexdigest()
        self.assertIn("SIN llave", verify_hash(dict(self.slide, hash=plain), self.config)[1]["diagnostico_hash"]["causa_probable"])

    def test_fingerprint_only_in_class_mode(self):
        wrong = dict(self.slide, hash="0" * 64)
        self.assertIn("huella_llave_servidor", verify_hash(wrong, FraudConfig())[1]["diagnostico_hash"])
        strict = FraudConfig(hmac_secret="llave-real", hash_helper_enabled=False)
        diagnosis = verify_hash(wrong, strict)[1]["diagnostico_hash"]
        self.assertNotIn("huella_llave_servidor", diagnosis)
        self.assertNotIn("huella_llave", strict.public_dict()["hash"])
        self.assertIn("huella_llave", FraudConfig().public_dict()["hash"])

    def test_missing_or_malformed_hash(self):
        self.assertEqual(verify_hash(dict(self.slide), self.config)[1]["motivo"], "HASH_REQUERIDO")
        self.assertEqual(verify_hash(dict(self.slide, hash="abc"), self.config)[1]["motivo"], "INVALID_HASH_FORMAT")

    def test_envelope_with_inner_object(self):
        envelope = {"transaccion": self.slide, "hash": class_hash(self.slide)}
        self.assertEqual(verify_hash(envelope, self.config)[0], 200)


class TotalsTests(unittest.TestCase):
    def test_slide_example(self):
        result = calculate_total([
            {"producto": "Mouse", "valor": "50000", "cantidad": "2"},
            {"producto": "Teclado", "valor": 80000, "cantidad": 1},
        ])
        self.assertEqual((result["total"], result["total_texto"]), (180000.0, "Total: $180000"))
        self.assertEqual(result["lineas"][0]["detalle"], "Mouse: 2 x $50000 = $100000")

    def test_invalid_items_are_reported_and_skipped(self):
        result = calculate_total([
            {"producto": "A", "valor": -1, "cantidad": 1},
            {"producto": "B", "valor": 10, "cantidad": 0},
            {"producto": "C", "valor": "abc", "cantidad": 1},
            {"producto": "D", "valor": 10, "cantidad": 2.5},
            {"producto": "E", "valor": True, "cantidad": 1},
            {"producto": "F"},
            "no soy un objeto",
            {"producto": "G", "valor": 5, "cantidad": 2},
        ])
        self.assertEqual(result["total"], 10.0)
        self.assertEqual(len(result["invalidos"]), 7)
        self.assertEqual(result["invalidos"][0]["mensaje"], "Valor inválido para A: debe ser mayor a 0.")
        self.assertEqual(result["invalidos"][1]["mensaje"], "Cantidad inválida para B: debe ser mayor a 0.")

    def test_not_a_list(self):
        self.assertFalse(calculate_total({"producto": "x"})["ok"])


class HttpLogHelperTests(unittest.TestCase):
    def test_client_and_origin_detection(self):
        self.assertEqual(http_log._client_name("python-requests/2.32.3"), "Python requests")
        self.assertEqual(http_log._client_name("Mozilla/5.0 (Windows NT 10.0) WindowsPowerShell/5.1"), "PowerShell")
        self.assertEqual(http_log._client_name("PostmanRuntime/7.39"), "Postman")
        self.assertEqual(http_log._origin("ab12.ngrok-free.app", True), "ngrok")
        self.assertEqual(http_log._origin("localhost:8000", False), "local")

    def test_summary_explains_the_response(self):
        body = json.dumps({"estado": "REJECTED", "motivo": "HASH_MISMATCH", "mensaje": "no coincide"}).encode()
        self.assertEqual(http_log._summary(422, body, None), "REJECTED · HASH_MISMATCH · no coincide")
        self.assertEqual(http_log._summary(200, b"[1,2,3]", None), "3 elemento(s)")
        self.assertIn("ZeroDivisionError", http_log._summary(500, b"", ZeroDivisionError("division by zero")))


if __name__ == "__main__":
    unittest.main()
