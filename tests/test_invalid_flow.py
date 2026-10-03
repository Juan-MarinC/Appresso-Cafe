"""Flujo de transacciones inválidas: el request original se conserva en cuarentena con su motivo,
nunca entra al procesamiento normal y puede reprocesarse después."""

import json
import unittest
from datetime import datetime

from appresso_food.antifraude.fraud_config import FraudConfig
from appresso_food.antifraude.fraud_repo import InMemoryRepository
from appresso_food.antifraude.fraud_service import FraudService

NOW = datetime(2026, 9, 30, 12, 0, 0)
META = {"ip": "203.0.113.7", "content_type": "application/json", "user_agent": "generador-externo/1.0",
        "metodo": "POST", "ruta": "/api/transacciones"}


def valid(id_txn=1, **overrides):
    data = {"idTxn": id_txn, "user": "a@a.com", "date": "2026-09-23T10:30:01.120", "value": 50000, "paymentMethod": "Tarjeta"}
    data.update(overrides)
    return data


class InvalidFlowTests(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryRepository()
        self.service = FraudService(FraudConfig(hmac_secret="secreto-de-prueba", band_rules_enabled=False), self.repo, clock=lambda: NOW)
        self.service.startup()

    def send(self, payload, meta=META):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return self.service.process_body(body, dict(meta))

    def accepted(self):
        return [t for t in self.repo.transactions if t.get("aceptada")]

    # 1. Request válido: sigue exactamente por el flujo actual y no toca la cuarentena
    def test_valid_request_goes_through_normal_flow(self):
        out = self.send(valid())
        self.assertEqual((out.http_status, out.body["estado"]), (201, "VALID"))
        self.assertNotIn("id_invalida", out.body)
        self.assertEqual(self.repo.invalid, [])
        self.assertEqual(len(self.accepted()), 1)

    # 2. Campo vacío
    def test_empty_field_is_quarantined(self):
        out = self.send(valid(2, user=""))
        self.assertEqual(out.http_status, 422)
        doc = self.repo.get_invalid(out.body["id_invalida"])
        self.assertEqual((doc["tipo_fallo"], doc["motivo"], doc["estado"]), ("VALIDACION", "EMPTY_FIELD", "PENDIENTE"))
        self.assertEqual(json.loads(doc["payload_texto"])["idTxn"], 2)  # request original intacto
        self.assertEqual(self.accepted(), [])

    # 3. Campo null
    def test_null_field_is_quarantined(self):
        out = self.send(valid(3, value=None))
        self.assertEqual(out.http_status, 422)
        doc = self.repo.get_invalid(out.body["id_invalida"])
        self.assertEqual(doc["motivo"], "NULL_FIELD")
        self.assertEqual(self.accepted(), [])

    # 4. Tipo de dato incorrecto
    def test_wrong_type_is_quarantined(self):
        out = self.send(valid(4, value="abc"))
        self.assertEqual(out.http_status, 422)
        doc = self.repo.get_invalid(out.body["id_invalida"])
        self.assertIn(doc["motivo"], ("INVALID_TYPE", "INVALID_VALUE"))
        self.assertEqual(self.accepted(), [])

    # 5. Campo obligatorio faltante (y nombres distintos: "monto" en vez de "value")
    def test_missing_required_field_is_quarantined(self):
        payload = valid(5)
        del payload["value"]
        payload["monto"] = 50000
        out = self.send(payload)
        self.assertEqual(out.http_status, 422)
        doc = self.repo.get_invalid(out.body["id_invalida"])
        self.assertEqual(doc["campos_faltantes"], ["value"])
        self.assertEqual(doc["campos_desconocidos"], ["monto"])
        self.assertEqual(self.accepted(), [])

    # 6. Campo adicional inesperado: no es motivo de rechazo, la transacción válida sigue su flujo
    def test_extra_field_does_not_break_a_valid_request(self):
        out = self.send(valid(6, canal="web", extra={"x": 1}))
        self.assertEqual(out.http_status, 201)
        self.assertEqual(self.repo.invalid, [])

    # 7. Request completamente inválido (no es JSON / vacío): 400 y se conserva el cuerpo exacto
    def test_malformed_and_empty_bodies_are_quarantined_with_400(self):
        out = self.send(b"hola {esto no es json")
        self.assertEqual(out.http_status, 400)
        doc = self.repo.get_invalid(out.body["id_invalida"])
        self.assertEqual((doc["tipo_fallo"], doc["motivo"]), ("MAL_FORMADO", "MALFORMED_JSON"))
        self.assertEqual(doc["payload_texto"], "hola {esto no es json")
        self.assertEqual(doc["origen"]["ip"], "203.0.113.7")
        self.assertEqual(self.send(b"").http_status, 400)
        self.assertEqual(len(self.repo.invalid), 2)
        self.assertEqual(self.accepted(), [])

    def test_form_encoded_body_is_processed_instead_of_rejected(self):
        meta = dict(META, content_type="application/x-www-form-urlencoded")
        body = b"idTxn=50&user=f%40f.com&date=2026-09-23T10%3A30%3A01.120&value=50000&paymentMethod=Tarjeta"
        out = self.send(body, meta)
        self.assertEqual(out.http_status, 201)

    def test_non_utf8_bodies_are_accepted_like_flask_does(self):
        """Causa de los 400 en bloque: el servicio solo aceptaba UTF-8 limpio. BOM y UTF-16 (PowerShell) fallaban."""
        for i, encoding in enumerate(("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "utf-32"), start=200):
            with self.subTest(encoding=encoding):
                out = self.send(json.dumps(valid(i)).encode(encoding))
                self.assertEqual(out.http_status, 201)
        out = self.send(str(valid(300)).encode())  # literal de Python con comillas simples
        self.assertEqual(out.http_status, 201)
        out = self.send("\n".join(json.dumps(valid(i)) for i in (301, 302)).encode())  # una transacción por línea
        self.assertEqual((out.http_status, out.body["aceptadas"]), (201, 2))
        self.assertEqual(self.repo.invalid, [])

    def test_duplicate_is_not_quarantined(self):
        self.send(valid(7))
        out = self.send(valid(7))
        self.assertEqual(out.http_status, 409)
        self.assertEqual(self.repo.invalid, [])

    # Reprocesamiento
    def test_reprocess_with_correction_moves_it_to_the_normal_flow(self):
        out = self.send(valid(8, value=None))
        invalid_id = out.body["id_invalida"]
        again = self.service.reprocess_invalid(invalid_id)  # sin corregir: sigue inválido y sigue pendiente
        self.assertEqual(again.http_status, 422)
        self.assertEqual(self.repo.get_invalid(invalid_id)["estado"], "PENDIENTE")
        self.assertEqual(len(self.repo.invalid), 1)  # el reintento no duplica la cuarentena
        fixed = self.service.reprocess_invalid(invalid_id, valid(8))
        self.assertEqual((fixed.http_status, fixed.body["estado"]), (201, "VALID"))
        doc = self.repo.get_invalid(invalid_id)
        self.assertEqual((doc["estado"], doc["intentos"]), ("REPROCESADA", 2))
        self.assertIsNotNone(doc["id_transaccion"])
        self.assertEqual(len(self.accepted()), 1)
        self.assertEqual(self.service.reprocess_invalid(invalid_id).http_status, 409)  # no se procesa dos veces

    def test_reprocess_unknown_id_and_discard(self):
        self.assertIsNone(self.service.reprocess_invalid("no-existe"))
        out = self.send(valid(9, user=""))
        doc = self.service.discard_invalid(out.body["id_invalida"])
        self.assertEqual(doc["estado"], "DESCARTADA")

    def test_batch_quarantines_only_the_bad_items(self):
        out = self.send([valid(10), valid(11, value=None), valid(12)])
        self.assertEqual((out.http_status, out.body["aceptadas"], out.body["rechazadas"]), (201, 2, 1))
        self.assertEqual(len(self.repo.invalid), 1)


if __name__ == "__main__":
    unittest.main()


class ExternalGeneratorTests(unittest.TestCase):
    """Modo generador externo (lo que acepta CAPRICHO): user como id, método libre, SHA-256 sin llave."""

    def setUp(self):
        import hashlib
        self.hashlib = hashlib
        self.service = FraudService(FraudConfig(hmac_secret="secreto-de-prueba", band_rules_enabled=False, lenient_inputs=True),
                                    InMemoryRepository(), clock=lambda: NOW)
        self.service.startup()

    def send(self, payload):
        return self.service.process_body(json.dumps(payload).encode(), {})

    def test_user_as_simple_id_and_free_payment_method(self):
        self.assertEqual(self.send(valid(1, user=25, paymentMethod="Crédito")).http_status, 201)
        self.assertEqual(self.send(valid(2, user="usuario25", paymentMethod="Transferencia")).http_status, 201)

    def test_plain_sha256_is_accepted_but_wrong_hash_is_not(self):
        data = valid(3)
        text = json.dumps(data, sort_keys=True, separators=(",", ":"))
        out = self.send(dict(data, hash=self.hashlib.sha256(text.encode()).hexdigest()))
        self.assertEqual((out.http_status, out.body["estado"]), (201, "VALID"))
        out = self.send(dict(valid(4), hash="0" * 64))
        self.assertEqual((out.http_status, out.body["motivo"]), (422, "HASH_MISMATCH"))

    def test_strict_default_still_rejects_them(self):
        strict = FraudService(FraudConfig(hmac_secret="x", band_rules_enabled=False), InMemoryRepository(), clock=lambda: NOW)
        strict.startup()
        self.assertEqual(strict.process(valid(5, user=25)).http_status, 422)
        self.assertEqual(strict.process(valid(6, paymentMethod="Crédito")).http_status, 422)

    def test_json_inside_a_string_is_unwrapped(self):
        out = self.service.process_body(json.dumps(json.dumps(valid(7))).encode(), {})
        self.assertEqual(out.http_status, 201)
