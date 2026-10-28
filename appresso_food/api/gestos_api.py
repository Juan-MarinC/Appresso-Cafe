"""Modelo de gestos entrenado con ml5.neuralNetwork en /entrenar: lo guarda en static/ para que /gestos lo cargue.

Guardar escribe archivos en el servidor, así que exige un token secreto que /entrenar solo entrega a quien la abre
en el mismo equipo, directo (no por ngrok ni otro proxy) y desde el mismo sitio. La IP sola no basta: por ngrok
todo llega desde 127.0.0.1, y como CORS permite cualquier origen, otra página podría leer /entrenar con fetch.
"""

import json
import os
import secrets
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Request

from appresso_food.api.api_helpers import error_response
from appresso_food.web import STATIC_DIR

router = APIRouter()

MODELO_DIR = STATIC_DIR / "modelos" / "gestos"
LOCALES = {"127.0.0.1", "::1", "localhost"}
CABECERAS_PROXY = ("x-forwarded-for", "forwarded", "x-real-ip", "x-forwarded-host", "x-forwarded-proto", "via",
                   "cf-connecting-ip", "true-client-ip")
TOKEN = secrets.token_urlsafe(24)  # nuevo en cada arranque del servidor
MAX_BYTES = 5_000_000
# Los nombres que ml5 usa al cargar: model.json apunta a model.weights.bin y lee model_meta.json.
ARCHIVOS_JSON = ("model.json", "model_meta.json")


def _directo_y_local(request: Request) -> bool:
    sin_proxy = not any(h in request.headers for h in CABECERAS_PROXY)
    # El Host también debe ser local: una página que hace DNS rebinding a 127.0.0.1 llega con su propio dominio.
    host_local = request.url.hostname in LOCALES
    return sin_proxy and host_local and request.client is not None and request.client.host in LOCALES


def _mismo_sitio(request: Request) -> bool:
    origen = request.headers.get("origin")
    if origen and urlparse(origen).netloc != request.headers.get("host"):
        return False
    return request.headers.get("sec-fetch-site", "same-origin") in ("same-origin", "none")


def token_para(request: Request) -> Optional[str]:
    """El token para /entrenar, o None si quien la pide no puede guardar modelos."""
    permitido = _directo_y_local(request) or os.getenv("APPRESSO_ENTRENAMIENTO") == "1"
    return TOKEN if permitido and _mismo_sitio(request) else None


@router.get("/api/gestos/modelo")
async def model_status():
    """Si ya hay un modelo entrenado, cuándo se guardó y qué clases conoce."""
    meta = MODELO_DIR / "model_meta.json"
    if not meta.exists():
        return {"existe": False}
    datos = json.loads(meta.read_text(encoding="utf-8"))
    salida = next(iter(datos.get("outputs", {}).values()), {})  # ml5 nombra la salida "0" cuando se entrena con listas
    clases = list(salida.get("uniqueValues", []))
    return {"existe": True, "guardado": datetime.fromtimestamp(meta.stat().st_mtime).isoformat(timespec="seconds"),
            "clases": clases, "muestras": datos.get("_muestras"), "precision": datos.get("_precision")}


@router.post("/api/gestos/modelo", status_code=201)
async def save_model(request: Request):
    """Recibe model.json, model.weights.bin y model_meta.json (y opcionalmente muestras.json) desde /entrenar."""
    recibido = request.headers.get("x-entrenamiento-token", "")
    if not token_para(request) or not secrets.compare_digest(recibido, TOKEN):
        return error_response(403, "SOLO_LOCAL", "El modelo solo se puede guardar desde /entrenar abierta en el mismo equipo del servidor.")
    form = await request.form()
    contenido = {}
    for nombre in (*ARCHIVOS_JSON, "model.weights.bin", "muestras.json"):
        archivo = form.get(nombre)
        if archivo is None:
            continue
        datos = await archivo.read()
        if len(datos) > MAX_BYTES:
            return error_response(413, "ARCHIVO_GRANDE", f"{nombre} pesa más de {MAX_BYTES // 1_000_000} MB.")
        contenido[nombre] = datos
    faltan = [n for n in (*ARCHIVOS_JSON, "model.weights.bin") if n not in contenido]
    if faltan:
        return error_response(400, "FALTAN_ARCHIVOS", f"Faltan: {', '.join(faltan)}.")
    for nombre in (*ARCHIVOS_JSON, "muestras.json"):
        if nombre in contenido:
            try:
                json.loads(contenido[nombre])
            except ValueError:
                return error_response(400, "JSON_INVALIDO", f"{nombre} no es un JSON válido.")
    if "weightsManifest" not in json.loads(contenido["model.json"]):
        return error_response(400, "MODELO_INVALIDO", "model.json no trae weightsManifest: no es un modelo de TensorFlow.js.")

    MODELO_DIR.mkdir(parents=True, exist_ok=True)
    for nombre, datos in contenido.items():
        temporal = MODELO_DIR / (nombre + ".tmp")
        temporal.write_bytes(datos)
        temporal.replace(MODELO_DIR / nombre)  # reemplazo atómico: /gestos nunca lee un archivo a medias
    return {"ok": True, "archivos": sorted(contenido), "carpeta": "/static/modelos/gestos/"}
