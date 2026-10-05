"""Clientes externos (ngrok, bots de Telegram, Postman, páginas de otro dominio): formatos de entrada,
fechas epoch, CORS y HEAD. Sin servidor ni MongoDB."""

import asyncio
import json
import os
import unittest
from datetime import datetime
from unittest import mock

from fastapi import FastAPI

from appresso_food.antifraude import fraud_routes
from appresso_food.antifraude.fraud_config import FraudConfig
from appresso_food.antifraude.fraud_repo import InMemoryRepository
from appresso_food.antifraude.fraud_service import FraudService, parse_multipart
from appresso_food.api import compat

NOW = datetime(2026, 10, 4, 12, 0, 0)
EPOCH = 1759590000  # 2025-10-04 en hora local (el valor exacto se compara con datetime.fromtimestamp)


def service(lenient=True):
    config = FraudConfig(hmac_secret="x", band_rules_enabled=False, lenient_inputs=lenient)
    svc = FraudService(config, InMemoryRepository(), clock=lambda: NOW)
    svc.startup()
    return svc


def txn(i, **over):
    data = {"idTxn": f"C{i}", "user": f"u{i}@correo.com", "date": "2026-10-04T10:00:00.000", "value": 25000, "paymentMethod": "Tarjeta"}
    data.update(over)
    return data


def multipart(fields=None, file_json=None, boundary="XyZ"):
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in (fields or {}).items()]
    if file_json is not None:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="archivo"; filename="txn.json"\r\n'
                     f'Content-Type: application/json\r\n\r\n{json.dumps(file_json)}\r\n')
    return ("".join(parts) + f"--{boundary}--\r\n").encode("utf-8"), f"multipart/form-data; boundary={boundary}"


class EpochDateTests(unittest.TestCase):
    def test_epoch_seconds_milliseconds_and_text(self):
        svc = service()
        expected = datetime.fromtimestamp(EPOCH).isoformat(timespec="milliseconds")
        for i, value in enumerate([EPOCH, EPOCH * 1000, str(EPOCH), float(EPOCH)], 1):
            body = svc.process(txn(i, date=value)).body
            self.assertEqual(body["estado"], "VALID", (value, body))
            self.assertEqual(body["ventana"]["entradas"][-1]["fecha"], expected, value)

    def test_strict_mode_still_requires_iso_text(self):
        svc = service(lenient=False)
        self.assertEqual(svc.process(txn(1, date=EPOCH)).body["motivo"], "INVALID_TYPE")
        self.assertEqual(svc.process(txn(2, date=str(EPOCH))).body["motivo"], "INVALID_DATE")

    def test_absurd_epochs_are_rejected_not_crashing(self):
        svc = service()
        for i, value in enumerate([0, 10**20, -5, True], 1):
            self.assertEqual(svc.process(txn(i, date=value)).body["estado"], "REJECTED", value)


class BodyFormatTests(unittest.TestCase):
    def test_multipart_fields_like_postman_form_data(self):
        body, ctype = multipart({k: str(v) for k, v in txn(1, nombre="Belén").items()})
        out = service().process_body(body, {"content_type": ctype})
        self.assertEqual((out.http_status, out.body["estado"]), (201, "VALID"))

    def test_multipart_with_attached_json_file(self):
        body, ctype = multipart(file_json=txn(2))
        out = service().process_body(body, {"content_type": ctype})
        self.assertEqual(out.body["estado"], "VALID")

    def test_broken_multipart_is_rejected_not_crashing(self):
        out = service().process_body(b"esto no es multipart", {"content_type": "multipart/form-data; boundary=nada"})
        self.assertEqual(out.body["estado"], "REJECTED")
        self.assertIsNone(parse_multipart(b"--a\r\n", "multipart/form-data"))  # sin boundary válido

    def test_fields_in_query_string_with_empty_body(self):
        query = {k: str(v) for k, v in txn(3).items()}
        self.assertEqual(service().process_body(b"", {"query": query}).body["estado"], "VALID")
        strict = service(lenient=False).process_body(b"", {"query": query})
        self.assertEqual(strict.body["motivo"], "MALFORMED_JSON")

    def test_query_string_is_ignored_when_there_is_a_body(self):
        out = service().process_body(json.dumps(txn(4)).encode(), {"query": {"idTxn": "OTRO"}})
        self.assertEqual(out.body["idTxn"], "C4")

    def test_telegram_update_is_answered_and_not_accepted(self):
        update = {"update_id": 1, "message": {"message_id": 7, "date": EPOCH, "text": "/pagar 25000", "chat": {"id": 5, "type": "private"}}}
        out = service().process_body(json.dumps(update).encode(), {"content_type": "application/json"})
        self.assertEqual(out.body["estado"], "REJECTED")
        self.assertIsNotNone(out.body.get("id_invalida"))  # queda en la cuarentena para revisarlo


class RouteAliasTests(unittest.TestCase):
    def test_list_accepts_trailing_slash_and_spanish_alias(self):
        get_paths = {r.path for r in fraud_routes.router.routes if "GET" in getattr(r, "methods", set())}
        for path in ("/api/transactions", "/api/transactions/", "/api/transacciones", "/api/transacciones/"):
            self.assertIn(path, get_paths)


def asgi_request(app, method, path, headers=()):
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "scheme": "http",
             "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "", "client": ("127.0.0.1", 5000),
             "server": ("testserver", 80), "headers": [(k.lower().encode(), v.encode()) for k, v in headers]}
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], {k.decode().lower(): v.decode() for k, v in start["headers"]}, body


class CompatMiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()

        @self.app.get("/ping")
        def ping():
            return {"ok": True}

        compat.install(self.app)

    def test_head_answers_like_get_without_body(self):
        status, headers, body = asgi_request(self.app, "HEAD", "/ping")
        self.assertEqual((status, body), (200, b""))
        self.assertEqual(headers["content-length"], str(len(b'{"ok":true}')))

    def test_cors_preflight_from_another_site(self):
        status, headers, _ = asgi_request(self.app, "OPTIONS", "/ping", [
            ("Origin", "https://pagina-del-profesor.example"), ("Access-Control-Request-Method", "POST"),
            ("Access-Control-Request-Headers", "content-type, ngrok-skip-browser-warning")])
        self.assertEqual(status, 200)
        self.assertEqual(headers["access-control-allow-origin"], "*")
        self.assertIn("ngrok-skip-browser-warning", headers["access-control-allow-headers"].lower())

    def test_cross_origin_response_is_readable_by_the_browser(self):
        status, headers, body = asgi_request(self.app, "GET", "/ping", [("Origin", "https://otro.example")])
        self.assertEqual((status, headers["access-control-allow-origin"]), (200, "*"))
        self.assertIn("x-request-id", headers["access-control-expose-headers"].lower())

    def test_origins_are_configurable(self):
        with mock.patch.dict(os.environ, {"APPRESSO_CORS_ORIGINS": "https://a.example, https://b.example"}):
            self.assertEqual(compat.cors_origins(), ["https://a.example", "https://b.example"])
        with mock.patch.dict(os.environ, {"APPRESSO_CORS_ORIGINS": " , "}):
            self.assertEqual(compat.cors_origins(), ["*"])


if __name__ == "__main__":
    unittest.main()
