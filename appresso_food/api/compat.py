"""Compatibilidad con clientes externos (ngrok, bots de Telegram, Postman, páginas web de otro dominio).

- CORS: un navegador que llama la API desde otro dominio (una página del profesor, Hoppscotch, una app JS)
  primero envía un OPTIONS de verificación; sin estos encabezados el navegador bloquea la respuesta aunque
  la app la haya procesado. Orígenes permitidos: APPRESSO_CORS_ORIGINS (coma separada, por defecto "*").
  Se permite el encabezado `ngrok-skip-browser-warning`, que hace falta para saltar la advertencia de ngrok.
- HEAD: monitores de disponibilidad y algunos clientes verifican la URL con HEAD antes de usarla; FastAPI
  solo acepta GET en esas rutas y respondía 405. Aquí un HEAD se atiende como GET sin cuerpo.
"""

import os

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


def install(app: FastAPI) -> None:
    """Llamar ANTES de http_log.install para que la bitácora quede por fuera y registre también los OPTIONS."""
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
