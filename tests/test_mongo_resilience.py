"""MongoDB que se cae o tarda en arrancar: la app responde 503 explicado (no 500), no deja transacciones
a medias en la ventana, /api/health dice la verdad y desde el modo memoria se reconecta sola."""

import asyncio
import unittest
from datetime import datetime
from unittest import mock

from fastapi import FastAPI
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from appresso_food.antifraude import fraud_routes
from appresso_food.antifraude.fraud_config import FraudConfig
from appresso_food.antifraude.fraud_repo import InMemoryRepository
from appresso_food.antifraude.fraud_service import FraudService

NOW = datetime(2026, 10, 4, 12, 0, 0)
DOWN = ServerSelectionTimeoutError("localhost:27017: No se puede establecer una conexión")


class FailingInsertRepo(InMemoryRepository):
    def insert_transaction(self, doc):
        if doc.get("aceptada"):
            raise DOWN
        return super().insert_transaction(doc)


class FailingPingRepo(InMemoryRepository):
    def ping(self):
        raise DOWN


class HealthyMongo(InMemoryRepository):
    """Hace de MongoRepository cuando MongoDB ya volvió."""

    def __init__(self, uri=None, db_name=None):
        super().__init__()


class DeadMongo(InMemoryRepository):
    def __init__(self, uri=None, db_name=None):
        super().__init__()

    def ping(self):
        raise DOWN


def txn(i):
    return {"idTxn": f"R{i}", "user": "r@correo.com", "date": f"2026-10-04T10:00:0{i}.000", "value": 1000, "paymentMethod": "Tarjeta"}


class RouteStateMixin:
    """Guarda y restaura el estado global del módulo de rutas."""

    def setUp(self):
        self._saved = (fraud_routes._service, fraud_routes._memory_mode, fraud_routes._last_error)

    def tearDown(self):
        fraud_routes._service, fraud_routes._memory_mode, fraud_routes._last_error = self._saved


class RollbackTests(unittest.TestCase):
    def test_failed_save_does_not_stay_in_the_window(self):
        svc = FraudService(FraudConfig(hmac_secret="x", band_rules_enabled=False), FailingInsertRepo(), clock=lambda: NOW)
        svc.startup()
        with self.assertRaises(ServerSelectionTimeoutError):
            svc.process(txn(1))
        self.assertEqual(svc.window.snapshot("r@correo.com"), [])  # no cuenta para la regla de 3 en 10 s


class UnavailableHandlerTests(unittest.TestCase):
    def test_mongo_down_answers_503_with_retry_after(self):
        app = FastAPI()

        @app.get("/boom")
        def boom():
            raise DOWN

        app.add_exception_handler(ConnectionFailure, fraud_routes.mongo_unavailable_handler)  # como en app.py
        messages = []

        async def run():
            scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
                     "path": "/boom", "raw_path": b"/boom", "query_string": b"", "root_path": "", "headers": [],
                     "client": ("127.0.0.1", 1), "server": ("testserver", 80)}

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                messages.append(message)

            await app(scope, receive, send)

        asyncio.run(run())
        start = next(m for m in messages if m["type"] == "http.response.start")
        headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        self.assertEqual(start["status"], 503)
        self.assertEqual(headers["retry-after"], "10")
        self.assertIn(b"MONGODB_NO_DISPONIBLE", body)


class HealthTests(RouteStateMixin, unittest.TestCase):
    def test_health_reports_mongo_down_after_startup(self):
        svc = FraudService(FraudConfig(hmac_secret="x"), FailingPingRepo(), clock=lambda: NOW)
        fraud_routes._service, fraud_routes._memory_mode = svc, False
        self.assertEqual(fraud_routes.health()["mongodb"], "no disponible")

    def test_health_ok_when_mongo_answers(self):
        svc = FraudService(FraudConfig(hmac_secret="x"), InMemoryRepository(), clock=lambda: NOW)
        fraud_routes._service, fraud_routes._memory_mode = svc, False
        self.assertEqual(fraud_routes.health(), {"mongodb": "ok", "detalle": None})


class ReconnectTests(RouteStateMixin, unittest.TestCase):
    def test_switches_from_memory_to_mongo_when_it_comes_back(self):
        fraud_routes._service, fraud_routes._memory_mode = None, True
        with mock.patch.object(fraud_routes, "MongoRepository", HealthyMongo):
            self.assertTrue(fraud_routes.try_reconnect())
        self.assertFalse(fraud_routes._memory_mode)
        self.assertIsInstance(fraud_routes._service.repo, HealthyMongo)
        self.assertIsNone(fraud_routes._last_error)

    def test_keeps_memory_mode_while_mongo_is_down(self):
        memory = FraudService(FraudConfig(hmac_secret="x"), InMemoryRepository(), clock=lambda: NOW)
        fraud_routes._service, fraud_routes._memory_mode = memory, True
        with mock.patch.object(fraud_routes, "MongoRepository", DeadMongo):
            self.assertFalse(fraud_routes.try_reconnect())
        self.assertTrue(fraud_routes._memory_mode)
        self.assertIs(fraud_routes._service, memory)  # no se pierde lo que ya está en memoria
        self.assertIn("ServerSelectionTimeoutError", fraud_routes._last_error)


if __name__ == "__main__":
    unittest.main()
