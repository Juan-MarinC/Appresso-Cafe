"""Compatibilidad con clientes externos (ngrok, bots de Telegram, Postman, páginas web de otro dominio).

- CORS: un navegador que llama la API desde otro dominio (una página del profesor, Hoppscotch, una app JS)
  primero envía un OPTIONS de verificación; sin estos encabezados el navegador bloquea la respuesta aunque
  la app la haya procesado. Orígenes permitidos: APPRESSO_CORS_ORIGINS (coma separada, por defecto "*").
  Se permite el encabezado `ngrok-skip-browser-warning`, que hace falta para saltar la advertencia de ngrok.
- HEAD: monitores de disponibilidad y algunos clientes verifican la URL con HEAD antes de usarla; FastAPI
  solo acepta GET en esas rutas y respondía 405. Aquí un HEAD se atiende como GET sin cuerpo.
"""

import json
import os
import threading
import time
from collections import deque

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


class HeadAsGetMiddleware:
    """Atiende HEAD como GET y descarta el cuerpo (conserva estado y encabezados, como manda HTTP)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "HEAD":
            await self.app(scope, receive, send)
            return

        async def send_without_body(message):
            if message["type"] == "http.response.body":
                if message.get("more_body", False):
                    return
                message = {"type": "http.response.body", "body": b"", "more_body": False}
            await send(message)

        await self.app(dict(scope, method="GET"), receive, send_without_body)


def cors_origins() -> list:
    raw = os.getenv("APPRESSO_CORS_ORIGINS", "*")
    return [origin.strip() for origin in raw.split(",") if origin.strip()] or ["*"]


class LimitePeticionesMiddleware:
    """Límite por IP para que nadie llene MongoDB ni sature la app por la URL pública.

    Escrituras (POST, PUT, PATCH, DELETE): 180 por minuto. Lecturas: 1200 por minuto (los paneles consultan cada 1,5 s).
    Las pruebas del profesor usan bastante menos. Se ajustan con APPRESSO_LIMITE_ESCRITURAS y APPRESSO_LIMITE_LECTURAS.
    """

    VENTANA = 60.0
    EXENTOS = ("127.0.0.1", "::1", "testclient")  # este mismo equipo (y las pruebas automáticas)

    def __init__(self, app, escrituras=None, lecturas=None, exentos=EXENTOS):
        self.app = app
        self.limites = {
            "escritura": escrituras or int(os.getenv("APPRESSO_LIMITE_ESCRITURAS", "180")),
            "lectura": lecturas or int(os.getenv("APPRESSO_LIMITE_LECTURAS", "1200")),
        }
        self.exentos = set(exentos)
        self._marcas = {}
        self._lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        client = scope.get("client")
        ip = client[0] if client else "?"
        if scope["type"] != "http" or ip in self.exentos:
            return await self.app(scope, receive, send)
        tipo = "lectura" if scope["method"] in ("GET", "HEAD", "OPTIONS") else "escritura"
        ahora = time.monotonic()
        with self._lock:
            if len(self._marcas) > 5000:  # no acumular IPs viejas en memoria
                self._marcas = {k: v for k, v in self._marcas.items() if v and ahora - v[-1] < self.VENTANA}
            marcas = self._marcas.setdefault((ip, tipo), deque())
            while marcas and ahora - marcas[0] > self.VENTANA:
                marcas.popleft()
            espera = int(self.VENTANA - (ahora - marcas[0])) + 1 if len(marcas) >= self.limites[tipo] else 0
            if not espera:
                marcas.append(ahora)
        if not espera:
            return await self.app(scope, receive, send)
        mensaje = f"Demasiadas peticiones desde su IP ({self.limites[tipo]} {tipo}s por minuto). Espere {espera} s y reintente."
        body = json.dumps({"ok": False, "motivo": "DEMASIADAS_PETICIONES", "mensaje": mensaje, "detail": mensaje}, ensure_ascii=False).encode()
        await send({"type": "http.response.start", "status": 429,
                    "headers": [(b"content-type", b"application/json"), (b"retry-after", str(espera).encode())]})
        await send({"type": "http.response.body", "body": body})


def install(app: FastAPI) -> None:
    """Llamar ANTES de http_log.install para que la bitácora quede por fuera y registre también los OPTIONS y los 429."""
    app.add_middleware(LimitePeticionesMiddleware)
    app.add_middleware(HeadAsGetMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
        allow_credentials=False,  # la API no usa cookies; con "*" los navegadores no permiten credenciales
        max_age=600,
    )
