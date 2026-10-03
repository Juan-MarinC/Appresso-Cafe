import hashlib
import hmac
import json
import unittest
from datetime import datetime, timedelta

from appresso_food import fraud_hashing as hashing
from appresso_food.fraud_config import DEFAULT_SECRET, LEGACY_SECRET, FraudConfig
from appresso_food.fraud_repo import InMemoryRepository
from appresso_food.fraud_service import FraudService, band_for
from appresso_food.sliding_window import SlidingWindowManager

NOW = datetime(2026, 9, 30, 12, 0, 0)
BASE = datetime(2026, 9, 23, 10, 0, 0)


def txn(id_txn, user="a@a.com", at=BASE, **overrides):
    data = {
        "idTxn": id_txn,
        "nombre": "Ana Pérez",
        "cedula": "1012345678",
        "user": user,
        "date": at.isoformat(timespec="milliseconds"),
        "value": 50000,
        "paymentMethod": "Tarjeta",
    }
    data.update(overrides)
    return data


def at(seconds, minutes=0, hours=10):
    return datetime(2026, 9, 23, hours, minutes, 0) + timedelta(seconds=seconds)


class FraudTestBase(unittest.TestCase):
    def setUp(self):
        self.config = FraudConfig(hmac_secret="secreto-de-prueba", band_rules_enabled=False)
        self.repo = InMemoryRepository()
        self.service = FraudService(self.config, self.repo, clock=lambda: NOW)
        self.service.startup()

    def send(self, payload):
        return self.service.process(payload)


class ValidationTests(FraudTestBase):
    def test_1_valid_transaction(self):
        out = self.send(txn(1))
        self.assertEqual((out.http_status, out.body["estado"]), (201, "VALID"))
        self.assertEqual(len(out.body["hash"]), 64)
        self.assertEqual(out.body["ventana"]["cantidad"], 1)

    def test_2_null_field_rejected(self):
        for field in ("idTxn", "user", "date", "value", "paymentMethod"):
            out = self.send(txn(10, **{field: None}))
            self.assertEqual((out.body["estado"], out.body["motivo"]), ("REJECTED", "NULL_FIELD"), field)
            self.assertIn("formato_esperado", out.body)
        absent = txn(11)
        del absent["user"]
        self.assertEqual(self.send(absent).body["motivo"], "NULL_FIELD")

    def test_nombre_and_cedula_are_optional_in_the_api(self):
        pdf_format = txn(12)
        del pdf_format["nombre"], pdf_format["cedula"]
        self.assertEqual(self.send(pdf_format).body["estado"], "VALID")
        self.assertEqual(self.send(txn(13, nombre=None, cedula=None)).body["estado"], "VALID")
        self.assertNotIn("nombre", self.repo.users["a@a.com"])
        self.send(txn(14))
        self.send(txn(15, nombre=None))  # no borra el nombre que ya tenía el usuario
        self.assertEqual(self.repo.users["a@a.com"]["nombre"], "Ana Pérez")
        self.assertTrue(self.service.verify("12")["coincide"])

    def test_3_empty_field_rejected(self):
        for field in ("nombre", "user", "date", "paymentMethod"):
            out = self.send(txn(20, **{field: "   "}))
            self.assertEqual((out.body["estado"], out.body["motivo"]), ("REJECTED", "EMPTY_FIELD"), field)

    def test_4_invalid_email_rejected(self):
        for email in ("sin-arroba", "a@", "a@b", "@a.com", "a b@a.com", "a@@a.com"):
            out = self.send(txn(30, user=email))
            self.assertEqual((out.body["estado"], out.body["motivo"]), ("REJECTED", "INVALID_EMAIL"), email)

    def test_5_wrong_types_rejected(self):
        cases = {"value": [[50000], {"a": 1}, True], "idTxn": [True, 1.5, [1]], "user": [123], "date": [20260923], "nombre": [7], "paymentMethod": [5]}
        for field, values in cases.items():
            for value in values:
                out = self.send(txn(40, **{field: value}))
                self.assertEqual(out.body["estado"], "REJECTED", (field, value))
                self.assertEqual(out.body["motivo"], "INVALID_TYPE", (field, value))

    def test_6_numeric_string_is_normalized(self):
        out = self.send(txn(50, value="50000"))
        self.assertEqual(out.body["estado"], "VALID")
        stored = self.repo.find_accepted_by_id_txn("50")
        self.assertEqual(stored["valor"], 50000.0)
        self.assertIsInstance(stored["valor"], float)
        self.assertEqual(self.send(txn(51, value="12500.50")).body["estado"], "VALID")

    def test_6b_invalid_numbers_never_become_zero(self):
        for bad in ("abc", "50.000,00", "5e3", "-100", "0", 0, -5, "NaN", "inf", float("nan"), float("inf"), 10**12, "1 000"):
            out = self.send(txn(60, value=bad))
            self.assertEqual((out.body["estado"], out.body["motivo"]), ("REJECTED", "INVALID_VALUE"), repr(bad))
        self.assertEqual(self.repo.find_accepted_by_id_txn("60"), None)
        self.assertEqual(sum(1 for t in self.repo.transactions if t["aceptada"]), 0)

    def test_invalid_date_cedula_payment(self):
        self.assertEqual(self.send(txn(70, date="ayer")).body["motivo"], "INVALID_DATE")
        self.assertEqual(self.send(txn(71, date="2026-09-23")).body["motivo"], "INVALID_DATE")
        self.assertEqual(self.send(txn(72, date="2026-13-45T10:00:00")).body["motivo"], "INVALID_DATE")
        self.assertEqual(self.send(txn(73, cedula="12ab")).body["motivo"], "INVALID_CEDULA")
        self.assertEqual(self.send(txn(74, paymentMethod="Bitcoin")).body["motivo"], "INVALID_PAYMENT_METHOD")
        self.assertEqual(self.send(txn(75, paymentMethod="tarjeta")).body["estado"], "VALID")

    def test_all_errors_are_reported(self):
        out = self.send(txn(80, user="mal", value="abc", cedula="12ab"))
        self.assertEqual({e["campo"] for e in out.body["errores"]}, {"user", "value", "cedula"})

    def test_malformed_json_and_non_object(self):
        out = self.service.process_body(b'{"idTxn": 1, "user": ')
        self.assertEqual((out.http_status, out.body["motivo"]), (400, "MALFORMED_JSON"))
        self.assertEqual(self.service.process_body(b"[1,2]").body["motivo"], "INVALID_TYPE")
        self.assertEqual(self.repo.transactions[0]["estado"], "REJECTED")  # se conserva con su motivo

    def test_rejected_transactions_are_kept_and_not_counted(self):
        self.send(txn(90, user="mal"))
        self.assertEqual(len(self.repo.transactions), 1)
        self.assertFalse(self.repo.transactions[0]["aceptada"])
        self.assertEqual(self.service.window.snapshot(), [])

    def test_7_duplicate_id_rejected(self):
        self.assertEqual(self.send(txn(100)).body["estado"], "VALID")
        out = self.send(txn(100, at=at(1)))
        self.assertEqual((out.http_status, out.body["motivo"]), (409, "DUPLICATE_TRANSACTION"))
        accepted = [t for t in self.repo.transactions if t["aceptada"]]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(self.service.window.snapshot("a@a.com")[0]["cantidad"], 1)

    def test_rejected_id_can_be_resubmitted_fixed(self):
        self.assertEqual(self.send(txn(110, user="mal")).body["estado"], "REJECTED")
        self.assertEqual(self.send(txn(110)).body["estado"], "VALID")

    def test_id_accepts_int_and_string(self):
        self.assertEqual(self.send(txn(120)).body["idTxn"], "120")
        self.assertEqual(self.send(txn("TX-120")).body["idTxn"], "TX-120")
        self.assertEqual(self.send(txn("120", at=at(30))).body["motivo"], "DUPLICATE_TRANSACTION")


class SlidingWindowTests(FraudTestBase):
    def test_8_three_in_ten_seconds_is_possible_fraud(self):
        outs = [self.send(txn(i, at=at(s))) for i, s in ((1, 1), (2, 4), (3, 8))]
        self.assertEqual([o.body["estado"] for o in outs], ["VALID", "VALID", "SUSPICIOUS"])
        third = outs[2].body
        self.assertEqual(third["motivo"], "POSSIBLE_FRAUD")
        self.assertEqual(third["anomalias"][0]["cantidad_transacciones"], 3)
        self.assertEqual(third["anomalias"][0]["ventana_segundos"], 10)
        self.assertEqual(len(self.repo.anomalies), 1)
        self.assertEqual(self.repo.anomalies[0]["estado"], "NUEVA")

    def test_spread_out_transactions_are_normal(self):
        outs = [self.send(txn(i, at=at(s))) for i, s in ((1, 1), (2, 5), (3, 12))]
        self.assertEqual([o.body["estado"] for o in outs], ["VALID"] * 3)
        self.assertEqual(outs[2].body["ventana"]["cantidad"], 2)
        self.assertEqual(self.repo.anomalies, [])

    def test_window_is_sliding_not_fixed(self):
        # Una ventana fija por buckets de 10 s separaría {8, 9} de {11}. La deslizante ve 3 en 3 s.
        outs = [self.send(txn(i, at=at(s))) for i, s in ((1, 8), (2, 9), (3, 11))]
        self.assertEqual(outs[2].body["estado"], "SUSPICIOUS")

    def test_boundary_exactly_window_seconds_leaves(self):
        self.send(txn(1, at=at(0)))
        self.send(txn(2, at=at(5)))
        out = self.send(txn(3, at=at(10)))  # la de t=0 tiene edad == 10 s: ya salió
        self.assertEqual(out.body["ventana"]["cantidad"], 2)
        self.assertEqual([e["idTxn"] for e in out.body["ventana"]["salieron"]], ["1"])
        # Llega fuera de orden: 0, 5 y 9.999 caben en menos de 10 s (y también 5, 9.999 y 10) -> 3 = sospechosa.
        out = self.send(txn(4, at=at(9.999)))
        self.assertTrue(out.body["ventana"]["tardia"])
        self.assertEqual((out.body["ventana"]["cantidad"], out.body["estado"]), (3, "SUSPICIOUS"))

    def test_out_of_order_arrival_is_still_detected(self):
        # Hallazgo del QA: 10:00:10, 10:00:01, 10:00:02 son 3 transacciones en 9 s aunque la última en llegar sea la de :02.
        outs = [self.send(txn(i, at=at(s))) for i, s in ((1, 10), (2, 1), (3, 2))]
        self.assertEqual([o.body["estado"] for o in outs], ["VALID", "VALID", "SUSPICIOUS"])
        self.assertEqual(outs[2].body["ventana"]["cantidad"], 3)
        self.assertEqual(sorted(e["idTxn"] for e in outs[2].body["ventana"]["entradas"]), ["1", "2", "3"])
        timeline = self.service.anomaly_timeline(self.repo.anomalies[0]["_id"])
        self.assertEqual([e["id_txn"] for e in timeline["linea_de_tiempo"]], ["2", "3", "1"])

    def test_out_of_order_after_eviction_uses_history(self):
        # :01 y :02 ya salieron de la ventana activa cuando llega :03, pero siguen en el historial.
        outs = [self.send(txn(i, at=at(s))) for i, s in ((1, 1), (2, 2), (3, 20), (4, 3))]
        self.assertEqual([o.body["estado"] for o in outs], ["VALID", "VALID", "VALID", "SUSPICIOUS"])
        self.assertEqual(outs[3].body["ventana"]["cantidad"], 3)
        self.assertEqual(sorted(e["idTxn"] for e in outs[3].body["ventana"]["entradas"]), ["1", "2", "4"])

    def test_out_of_order_does_not_flag_when_spread_out(self):
        outs = [self.send(txn(i, at=at(s))) for i, s in ((1, 30), (2, 1), (3, 12))]
        self.assertEqual([o.body["estado"] for o in outs], ["VALID"] * 3)

    def test_late_arrival_is_not_listed_as_its_own_eviction(self):
        self.send(txn(1, at=at(30)))
        out = self.send(txn(2, at=at(1)))  # llega 29 s tarde: ya estaba fuera de la ventana vigente
        self.assertTrue(out.body["ventana"]["tardia"])
        self.assertEqual(out.body["ventana"]["salieron"], [])
        self.assertFalse([l for l in self.repo.logs if l["evento"] == "VENTANA_SALE" and l["id_txn"] == "2"])

    def test_invalid_values_report_consistent_messages_and_ids(self):
        self.assertEqual(self.send(txn(1, value="-5")).body["mensaje"], self.send(txn(2, value=-5)).body["mensaje"])
        self.send(txn(True))
        self.assertIsNone(self.repo.transactions[-1]["id_txn"])  # un booleano no se guarda como "True"

    def test_9_users_have_independent_windows(self):
        self.send(txn(1, "u1@a.com", at(1)))
        self.send(txn(2, "u2@a.com", at(2)))
        out = self.send(txn(3, "u3@a.com", at(3)))
        self.assertEqual(out.body["estado"], "VALID")
        snapshot = {w["usuario"]: [e["idTxn"] for e in w["entradas"]] for w in self.service.window.snapshot()}
        self.assertEqual(snapshot, {"u1@a.com": ["1"], "u2@a.com": ["2"], "u3@a.com": ["3"]})
        self.assertEqual(self.repo.anomalies, [])

    def test_9b_interleaved_users_do_not_mix(self):
        for i, user in enumerate(["x@a.com", "y@a.com"] * 4):
            out = self.send(txn(i, user, at(i * 0.5)))
        self.assertEqual(out.body["ventana"]["cantidad"], 4)  # 4 de cada uno, 8 en total
        self.assertEqual(sorted({a["usuario_email"] for a in self.repo.anomalies}), ["x@a.com", "y@a.com"])

    def test_10_leaves_active_window_but_stays_in_history(self):
        self.send(txn(1, at=at(0)))
        self.send(txn(2, at=at(3)))
        out = self.send(txn(3, at=at(14)))
        self.assertEqual([e["idTxn"] for e in out.body["ventana"]["salieron"]], ["1", "2"])
        active = [e["idTxn"] for e in self.service.window.snapshot("a@a.com")[0]["entradas"]]
        self.assertEqual(active, ["3"])
        self.assertEqual(sorted(t["id_txn"] for t in self.repo.transactions), ["1", "2", "3"])  # historial intacto
        events = [(l["evento"], l["id_txn"]) for l in self.repo.logs if l["evento"] == "VENTANA_SALE"]
        self.assertEqual(events, [("VENTANA_SALE", "1"), ("VENTANA_SALE", "2")])

    def test_12_burst_like_a_bot(self):
        counts, states = [], []
        for i in range(8):
            out = self.send(txn(i, at=at(i * 0.2)))
            counts.append(out.body["ventana"]["cantidad"])
            states.append(out.body["estado"])
        self.assertEqual(counts, [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(states[:2], ["VALID", "VALID"])
        self.assertTrue(all(s == "SUSPICIOUS" for s in states[2:]))
        levels = [a["nivel"] for a in self.repo.anomalies]
        self.assertEqual(levels[0], "MEDIO")
        self.assertTrue(all(l == "ALTO" for l in levels[1:]))

    def test_every_response_is_json_serializable(self):
        bodies = [self.send(txn(i, at=at(i))).body for i in range(1, 5)]  # incluye SUSPICIOUS con anomalías
        bodies.append(self.send(txn(99, user="mal")).body)  # REJECTED
        bodies.append(self.send(txn(1)).body)  # DUPLICATE
        for body in bodies:
            json.dumps(body)

    def test_threshold_and_window_are_configurable(self):
        config = FraudConfig(window_seconds=3, max_transactions=2, hmac_secret="x", band_rules_enabled=False)
        service = FraudService(config, InMemoryRepository(), clock=lambda: NOW)
        service.startup()
        self.assertEqual(service.process(txn(1, at=at(0))).body["estado"], "VALID")
        self.assertEqual(service.process(txn(2, at=at(2))).body["estado"], "SUSPICIOUS")
        self.assertEqual(service.process(txn(3, at=at(30))).body["estado"], "VALID")

    def test_window_rebuilds_from_history_after_restart(self):
        self.send(txn(1, at=at(0)))
        self.send(txn(2, at=at(4)))
        restarted = FraudService(self.config, self.repo, clock=lambda: NOW)
        restarted.startup()
        out = restarted.process(txn(3, at=at(7)))
        self.assertEqual(out.body["estado"], "SUSPICIOUS")

    def test_sliding_window_manager_directly(self):
        window = SlidingWindowManager(10)
        results = [window.add("u", at(s), str(i), 1.0) for i, s in enumerate([0, 3, 9, 10, 25])]
        self.assertEqual([r.count for r in results], [1, 2, 3, 3, 1])
        self.assertEqual([[e.txn_id for e in r.evicted] for r in results], [[], [], [], ["0"], ["1", "2", "3"]])


class BandRuleTests(unittest.TestCase):
    def setUp(self):
        self.config = FraudConfig(hmac_secret="x", band_rules_enabled=True, window_seconds=0.001)
        self.repo = InMemoryRepository()
        self.service = FraudService(self.config, self.repo, clock=lambda: NOW)
        self.service.startup()

    def test_band_for(self):
        rules = self.config.band_rules
        self.assertEqual(band_for(datetime(2026, 9, 23, 5, 0, 1), rules)[0], "MAÑANA")
        self.assertEqual(band_for(datetime(2026, 9, 23, 12, 0, 0), rules)[0], "MAÑANA")
        self.assertEqual(band_for(datetime(2026, 9, 23, 12, 0, 1), rules)[0], "TARDE")
        self.assertEqual(band_for(datetime(2026, 9, 23, 20, 0, 0), rules)[0], "TARDE")
        self.assertEqual(band_for(datetime(2026, 9, 23, 20, 0, 1), rules)[0], "NOCHE")
        self.assertEqual(band_for(datetime(2026, 9, 24, 5, 0, 0), rules)[0], "NOCHE")
        name, start, end, limit = band_for(datetime(2026, 9, 24, 1, 0, 0), rules)
        self.assertEqual((name, limit, start.day, end.day), ("NOCHE", 3, 23, 24))

    def test_night_limit_is_a_second_layer(self):
        outs = [self.service.process(txn(i, at=datetime(2026, 9, 23, 21, i * 10, 0))) for i in range(1, 5)]
        self.assertEqual([o.body["estado"] for o in outs], ["VALID", "VALID", "VALID", "SUSPICIOUS"])
        self.assertEqual(outs[3].body["motivo"], "TOO_MANY_TRANSACTIONS")
        self.assertEqual(outs[3].body["anomalias"][0]["nivel"], "BAJO")
        self.assertEqual(outs[3].body["franja_horaria"]["franja"], "NOCHE")
        self.assertEqual(outs[3].body["anomalias"][0]["ventana_segundos"], 32400)  # 20:00:01 a 05:00:00, sin decimales raros

    def test_night_band_crosses_midnight(self):
        times = [datetime(2026, 9, 23, 23, 0), datetime(2026, 9, 24, 0, 30), datetime(2026, 9, 24, 2, 0), datetime(2026, 9, 24, 4, 59)]
        outs = [self.service.process(txn(i, at=t)) for i, t in enumerate(times, 1)]
        self.assertEqual(outs[3].body["motivo"], "TOO_MANY_TRANSACTIONS")

    def test_morning_band_allows_more(self):
        outs = [self.service.process(txn(i, at=datetime(2026, 9, 23, 6, i, 0))) for i in range(1, 11)]
        self.assertTrue(all(o.body["estado"] == "VALID" for o in outs))
        self.assertEqual(self.service.process(txn(11, at=datetime(2026, 9, 23, 6, 30, 0))).body["motivo"], "TOO_MANY_TRANSACTIONS")

    def test_sliding_window_remains_the_main_rule(self):
        service = FraudService(FraudConfig(hmac_secret="x", band_rules_enabled=True), InMemoryRepository(), clock=lambda: NOW)
        service.startup()
        outs = [service.process(txn(i, at=at(i))) for i in range(1, 4)]  # 10:00 -> franja MAÑANA (límite 10)
        self.assertEqual(outs[2].body["motivo"], "POSSIBLE_FRAUD")


class HashTests(FraudTestBase):
    def _client_hash(self, payload):
        return self.service.compute_hash_for(payload).body["hash"]

    def test_deterministic_and_order_independent(self):
        a = hashing.compute_hash({"b": 1, "a": 2}, "k")
        b = hashing.compute_hash({"a": 2, "b": 1}, "k")
        self.assertEqual(a, b)
        self.assertNotEqual(a, hashing.compute_hash({"a": 2, "b": 1}, "otra-llave"))
        self.assertEqual(hashing.canonical_json({"b": 1, "a": 2}), '{"a":2,"b":1}')

    def test_server_generates_and_stores_hash(self):
        out = self.send(txn(1))
        self.assertEqual(out.body["hash_origen"], "SERVIDOR")
        self.assertEqual(self.repo.find_accepted_by_id_txn("1")["hash"], out.body["hash"])

    def test_valid_client_hash_is_accepted_even_with_string_number(self):
        h = self._client_hash(txn(2))
        out = self.send(txn(2, value="50000", hash=h))  # 50000 y "50000" normalizan igual
        self.assertEqual((out.body["estado"], out.body["hash_origen"]), ("VALID", "CLIENTE_VERIFICADO"))

    def test_11_modified_data_is_detected(self):
        h = self._client_hash(txn(3))
        out = self.send(txn(3, value=51000, hash=h))
        self.assertEqual((out.http_status, out.body["motivo"]), (422, "HASH_MISMATCH"))
        self.assertEqual(self.repo.find_accepted_by_id_txn("3"), None)
        self.assertTrue(any(l["evento"] == "HASH_NO_COINCIDE" for l in self.repo.logs))
        self.assertEqual(self.send(txn(3, hash="0" * 64)).body["motivo"], "HASH_MISMATCH")
        self.assertEqual(self.send(txn(3, hash="xyz")).body["motivo"], "INVALID_HASH_FORMAT")

    @staticmethod
    def _class_hash(payload, key):
        """El código de la diapositiva, tal cual."""
        datos = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hmac.new(key, datos.encode("utf-8"), hashlib.sha256).hexdigest()

    def test_hash_computed_like_the_class_slide_is_accepted(self):
        # idTxn entero, fecha sin milisegundos y sin nombre/cédula: el servidor normaliza distinto,
        # pero el hash se compara contra el JSON tal como llegó.
        payload = {"idTxn": 1001, "user": "Profe@Correo.com", "date": "2026-09-23T10:30:01", "value": 50000, "paymentMethod": "tarjeta"}
        out = self.send(dict(payload, hash=self._class_hash(payload, b"secreto-de-prueba")))
        self.assertEqual((out.http_status, out.body["estado"], out.body["hash_origen"]), (201, "VALID", "CLIENTE_VERIFICADO"))
        self.assertEqual(out.body["verificacion_hash"]["calculado_sobre"], "PAYLOAD_RECIBIDO")
        self.assertTrue(self.service.verify("1001")["coincide"])
        # Unicode sin escapar (JSON.stringify de JavaScript) también se acepta.
        js = {"idTxn": 1002, "nombre": "Ana Pérez", "user": "a@a.com", "date": "2026-09-23T10:30:02", "value": 50000, "paymentMethod": "Tarjeta"}
        js_text = json.dumps(js, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        js_hash = hmac.new(b"secreto-de-prueba", js_text.encode("utf-8"), hashlib.sha256).hexdigest()
        self.assertEqual(self.send(dict(js, hash=js_hash)).body["estado"], "VALID")

    def test_hash_mismatch_explains_the_cause(self):
        payload = {"idTxn": 2001, "user": "p@p.com", "date": "2026-09-23T10:30:01", "value": 50000, "paymentMethod": "Tarjeta"}
        cases = {
            "otra-llave": (self._class_hash(payload, DEFAULT_SECRET.encode()), "mi_llave_privada_123"),
            "sin-llave": (hashlib.sha256(hashing.canonical_json(payload).encode()).hexdigest(), "SIN llave"),
            "alterado": (self._class_hash(dict(payload, value=1), b"secreto-de-prueba"), "cambiaron"),
        }
        for name, (client_hash, expected_text) in cases.items():
            out = self.send(dict(payload, hash=client_hash))
            self.assertEqual((out.http_status, out.body["motivo"]), (422, "HASH_MISMATCH"), name)
            diagnosis = out.body["diagnostico_hash"]
            self.assertIn(expected_text, diagnosis["causa_probable"], name)
            self.assertEqual(diagnosis["texto_que_firma_el_servidor"], hashing.canonical_json(payload))
            self.assertEqual(diagnosis["huella_llave_servidor"], hashing.key_fingerprint("secreto-de-prueba"))

    def test_default_key_is_the_class_key_and_old_data_still_verifies(self):
        self.assertEqual(FraudConfig().hmac_secret, "mi_llave_privada_123")
        legacy = FraudService(FraudConfig(hmac_secret=LEGACY_SECRET, band_rules_enabled=False), self.repo, clock=lambda: NOW)
        legacy.process(txn(3001))
        current = FraudService(FraudConfig(band_rules_enabled=False), self.repo, clock=lambda: NOW)
        result = current.verify("3001")
        self.assertTrue(result["coincide"])
        self.assertIn("anterior", result["mensaje"])

    def test_11b_tampering_after_storage_is_detected(self):
        self.send(txn(4))
        self.assertTrue(self.service.verify("4")["coincide"])
        self.repo.transactions[0]["valor"] = 1.0  # alguien edita la base de datos
        result = self.service.verify("4")
        self.assertFalse(result["coincide"])
        self.assertIn("INCONSISTENCIA", result["mensaje"])
        self.assertTrue(any(l["evento"] == "HASH_INCONSISTENTE" for l in self.repo.logs))
        self.assertIsNone(self.service.verify("no-existe"))


class LogsAndStatsTests(FraudTestBase):
    def test_logs_record_what_when_who(self):
        self.send(txn(1, at=at(0)))
        self.send(txn(2, at=at(1)))
        self.send(txn(3, at=at(2)))
        self.send(txn(4, user="mal"))
        events = {l["evento"] for l in self.repo.logs}
        self.assertTrue({"VENTANA_ENTRA", "TXN_VALID", "TXN_SUSPICIOUS", "ANOMALIA_DETECTADA", "TXN_REJECTED"} <= events)
        suspicious = next(l for l in self.repo.logs if l["evento"] == "TXN_SUSPICIOUS")
        self.assertEqual((suspicious["usuario"], suspicious["id_txn"], suspicious["estado"], suspicious["anomalia"]), ("a@a.com", "3", "SUSPICIOUS", "POSSIBLE_FRAUD"))
        self.assertEqual(len(suspicious["hash"]), 64)
        self.assertEqual(suspicious["ts"], NOW)

    def test_anomaly_state_changes(self):
        for i in range(3):
            self.send(txn(i, at=at(i)))
        anomaly_id = self.repo.anomalies[0]["_id"]
        self.assertEqual(self.service.update_anomaly(anomaly_id, "REVISADA")["estado"], "REVISADA")
        with self.assertRaises(ValueError):
            self.service.update_anomaly(anomaly_id, "OTRA")
        self.assertIsNone(self.service.update_anomaly("999", "ABIERTA"))
        timeline = self.service.anomaly_timeline(anomaly_id)
        self.assertEqual([e["offset_segundos"] for e in timeline["linea_de_tiempo"]], [0, 1, 2])

    def test_stats(self):
        service = FraudService(self.config, InMemoryRepository(), clock=lambda: datetime(2026, 9, 23, 10, 5, 0))
        service.startup()
        for i in range(3):
            service.process(txn(i, at=at(i)))
        service.process(txn(10, user="b@b.com", at=at(5), paymentMethod="Nequi"))
        service.process(txn(11, user="mal"))
        stats = service.stats()
        hoy = stats["periodos"]["hoy"]
        self.assertEqual((hoy["total_transacciones"], hoy["rechazadas"], hoy["total_anomalias"]), (4, 1, 1))
        self.assertEqual(hoy["transacciones_sospechosas"], 1)
        self.assertEqual(hoy["porcentaje_anomalias"], 25.0)
        self.assertEqual(hoy["usuarios_afectados"], 1)
        self.assertEqual(hoy["valor_sospechoso"], 50000)
        self.assertEqual(hoy["promedio_por_usuario"], 2.0)
        self.assertEqual(hoy["anomalias_por_estado"]["NUEVA"], 1)
        self.assertEqual({m["metodo"] for m in stats["metodos_pago"]}, {"Tarjeta", "Nequi"})
        self.assertEqual(stats["por_hora"][10]["anomalias"], 1)
        self.assertEqual(stats["usuarios_recurrentes"][0]["usuario"], "a@a.com")


if __name__ == "__main__":
    unittest.main()
