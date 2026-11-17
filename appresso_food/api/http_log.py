"""Bitácora HTTP: registra cada petición que llega a la app (local o por ngrok) con lo que se
envió, lo que se respondió y por qué; y convierte los errores genéricos en respuestas explicadas.

Dónde se ve:
    - Página /logs (se actualiza sola) y GET /api/logs/http (JSON).
    - Consola del servidor y archivo logs/http.log.

Las consultas automáticas de las páginas (el dashboard antifraude refresca cada 1,5 s) se
guardan aparte para que no tapen las peticiones reales, como las del profesor por ngrok.
"""

import itertools
import json
import re
import logging
import threading
import time
import traceback
import unicodedata
import uuid
from collections import deque
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
from urllib.parse import unquote_plus, urlsplit

from fastapi import APIRouter, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

MAX_BODY_CHARS = 4000
IGNORED_PREFIXES = ("/static/",)
IGNORED_PATHS = {"/favicon.ico", "/api/logs/http"}  # la propia página de logs consulta esta ruta cada 2 s
POLLING_PAGES = {"/antifraude", "/transacciones", "/logs"}

STATUS_TEXT = {
    200: "OK", 201: "Creado", 204: "Sin contenido", 303: "Redirección", 307: "Redirección",
    400: "Petición mal formada", 404: "No existe", 405: "Método no permitido", 409: "Conflicto",
    422: "Datos rechazados por validación", 500: "Error interno del servidor", 503: "Servicio no disponible",
}
STATUS_CODE = {400: "PETICION_INVALIDA", 404: "NO_EXISTE", 405: "METODO_NO_PERMITIDO", 409: "CONFLICTO", 503: "SERVICIO_NO_DISPONIBLE"}

# (texto en el User-Agent, nombre a mostrar). PowerShell va antes que Mozilla porque su User-Agent incluye ambos.
CLIENTS = [
    ("python-requests", "Python requests"), ("python-urllib", "Python urllib"), ("python-httpx", "Python httpx"),
    ("curl", "curl"), ("postman", "Postman"), ("insomnia", "Insomnia"), ("thunder client", "Thunder Client"),
    ("powershell", "PowerShell"), ("axios", "axios"), ("node", "Node.js"), ("mozilla", "Navegador"),
]

from appresso_food.web import templates
router = APIRouter()
logger = logging.getLogger("appresso.http")

_requests: deque = deque(maxlen=1000)
_polling: deque = deque(maxlen=200)
_lock = threading.Lock()
_seq = itertools.count(1)
_state = {"url_publica": None, "archivo": None}


def setup_logger(path: Path) -> None:
    if logger.handlers:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    for handler in (logging.StreamHandler(), RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _state["archivo"] = str(path)


def _client_name(user_agent: str) -> str:
    lowered = user_agent.lower()
    return next((name for token, name in CLIENTS if token in lowered), user_agent[:40] or "desconocido")


def _origin(host: str, forwarded: bool) -> str:
    if "ngrok" in host:
        return "ngrok"
    if host.endswith(".app.github.dev"):
        return "codespaces"
    return "proxy" if forwarded else "local"


# /logs es público (también por ngrok): la clave de pago y los tokens no se guardan, o cualquiera podría usarlos;
# la cédula tampoco, porque es un dato personal. Se compara el nombre del campo sin mayúsculas, tildes ni signos
# ("Cédula", "pedido-token" y "c%C3%A9dula" cuentan igual).
_SENSIBLES = {"clave", "token", "pedidotoken", "cedula"}
# Respaldo para lo que no se puede leer como JSON o formulario (un cuerpo cortado, multipart): por nombre, sin
# importar mayúsculas, y aunque el valor quede sin cerrar por el corte.
_SECRETOS = r"clave|token|pedido_token|c[eé]dula"
_SECRETO_TEXTO_JSON = re.compile(rf'"({_SECRETOS})"(\s*:\s*)(?:"(?:[^"\\]|\\.)*(?:"|$)|-?\d[\d.eE+-]*)', re.I)
_SECRETO_MULTIPART = re.compile(rf'(name="(?:{_SECRETOS})"\r?\n\r?\n)[^\r\n]*', re.I)


def _sensible(nombre) -> bool:
    sin_tildes = unicodedata.normalize("NFKD", str(nombre)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sin_tildes.lower()) in _SENSIBLES


def _ocultar_datos(dato):
    """Reemplaza los campos sensibles a cualquier profundidad de un JSON ya leído."""
    if isinstance(dato, dict):
        return {k: "***" if _sensible(k) else _ocultar_datos(v) for k, v in dato.items()}
    if isinstance(dato, list):
        return [_ocultar_datos(v) for v in dato]
    return dato


def _ocultar_form(text: str) -> str:
    """Formulario o query (a=1&b=2): oculta el valor de los campos sensibles sin tocar cómo venía escrito el resto."""
    partes = []
    for parte in text.split("&"):
        nombre, igual, _ = parte.partition("=")
        partes.append(f"{nombre}=***" if igual and _sensible(unquote_plus(nombre)) else parte)
    return "&".join(partes)


def _ocultar(text: str) -> str:
    try:
        return json.dumps(_ocultar_datos(json.loads(text)), ensure_ascii=False)
    except ValueError:
        pass
    if "\n" not in text:
        text = _ocultar_form(text)
    text = _SECRETO_TEXTO_JSON.sub(r'"\1"\2"***"', text)
    return _SECRETO_MULTIPART.sub(r"\1***", text)


def _decodificar(raw: bytes) -> str:
    """UTF-8; si el corte partió una letra, sin esos últimos bytes; si no es UTF-8 (algunas terminales de Windows
    mandan Latin-1), como cp1252. Con errors="replace", "Cédula" quedaba "C�dula" y ya no se reconocía para ocultarla."""
    for fin in range(len(raw), max(len(raw) - 4, -1), -1):
        try:
            return raw[:fin].decode("utf-8")
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1252", errors="replace")


def _text(raw: bytes) -> Optional[str]:
    if not raw:
        return None
    text = _ocultar(_decodificar(raw))
    return text + " …(recortado)" if len(raw) >= MAX_BODY_CHARS else text


def _summary(status: int, response_body: bytes, error: Optional[BaseException]) -> str:
    """Una línea con lo que respondió la app: estado/motivo/mensaje si es JSON."""
    if error is not None:
        return f"{type(error).__name__}: {error}"
    try:
        data = json.loads(response_body)
    except ValueError:
        return STATUS_TEXT.get(status, "")
    if isinstance(data, list):
        return f"{len(data)} elemento(s)"
    if not isinstance(data, dict):
        return STATUS_TEXT.get(status, "")
    parts = [data[key] for key in ("estado", "resultado", "motivo") if isinstance(data.get(key), str)]
    message = data.get("mensaje") or data.get("detail")
    if isinstance(message, str):
        parts.append(message)
    elif message:
        parts.append(json.dumps(message, ensure_ascii=False)[:200])
    return " · ".join(dict.fromkeys(parts))[:400] or STATUS_TEXT.get(status, "")


def _record(scope, request_id, started, status, request_body, response_body, error, trace) -> None:
    headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
    method, path = scope["method"], scope["path"]
    host = headers.get("host", "")
    origin = _origin(host, "x-forwarded-for" in headers)
    polling = method == "GET" and path.startswith("/api/") and urlsplit(headers.get("referer", "")).path in POLLING_PAGES
    client = scope.get("client")
    user_agent = headers.get("user-agent", "")
    entry = {
        "n": next(_seq),
        "id": request_id,
        "ts": datetime.now().isoformat(timespec="milliseconds"),
        "metodo": method,
        "ruta": path,
        "query": _ocultar(scope.get("query_string", b"").decode("latin-1")),
        "status": status,
        "status_texto": STATUS_TEXT.get(status, ""),
        "ms": round((time.perf_counter() - started) * 1000, 1),
        "ip": client[0] if client else None,
        "origen": origin,
        "host": host,
        "cliente": _client_name(user_agent),
        "user_agent": user_agent[:200],
        "cuerpo": _text(request_body),
        "respuesta": _text(response_body),
        "resultado": _summary(status, response_body, error),
        "automatica": polling,
        "error": f"{type(error).__name__}: {error}" if error is not None else None,
        "traza": trace[-4000:] if trace else None,
    }
    with _lock:
        (_polling if polling else _requests).append(entry)
        if origin == "ngrok":
            _state["url_publica"] = f"https://{host}"
    if polling or not logger.handlers:
        return
    level = logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO
    query = f"?{entry['query']}" if entry["query"] else ""
    logger.log(level, "[%s] %s %s%s -> %s %s (%s ms) | %s %s %s | %s", request_id, method, path, query, status,
               entry["status_texto"], entry["ms"], origin, entry["ip"], entry["cliente"], entry["resultado"])
    if trace:
        logger.error("[%s] traza:\n%s", request_id, trace)


class HttpLogMiddleware:
    """Middleware ASGI puro: copia (recortados) el cuerpo enviado y el JSON respondido sin alterar la petición."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"].startswith(IGNORED_PREFIXES) or scope["path"] in IGNORED_PATHS:
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex[:8]
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        request_body, response_body = bytearray(), bytearray()
        response = {"status": None, "json": False}

        async def receive_logged():
            message = await receive()
            if message["type"] == "http.request":
                request_body.extend(message.get("body", b"")[: MAX_BODY_CHARS - len(request_body)])
            return message

        async def send_logged(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                content_type = next((value for key, value in headers if key.lower() == b"content-type"), b"")
                response.update(status=message["status"], json=b"json" in content_type)
                message = {**message, "headers": headers + [(b"x-request-id", request_id.encode())]}
            elif message["type"] == "http.response.body" and response["json"]:
                response_body.extend(message.get("body", b"")[: MAX_BODY_CHARS - len(response_body)])
            await send(message)

        error, trace = None, None
        try:
            await self.app(scope, receive_logged, send_logged)
        except Exception as exc:
            error, trace = exc, traceback.format_exc()
            raise
        finally:
            _record(scope, request_id, started, response["status"] or 500, bytes(request_body), bytes(response_body), error, trace)


# ---------------------------------------------------------------- errores explicados
def _request_id(request: Request) -> Optional[str]:
    return getattr(request.state, "request_id", None)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    method, path, status = request.method, request.url.path, exc.status_code
    detail = exc.detail
    if status == 404 and detail == "Not Found":
        detail = f"La ruta {method} {path} no existe. Vea todas las rutas en /api o pruébelas en /docs."
    elif status == 405:
        allowed = (exc.headers or {}).get("Allow", "")
        detail = f"La ruta {path} existe pero no acepta {method}. Métodos permitidos: {allowed}."
    message = detail if isinstance(detail, str) else STATUS_TEXT.get(status, "Error")
    body = {"ok": False, "motivo": STATUS_CODE.get(status, f"HTTP_{status}"), "mensaje": message, "detail": detail, "request_id": _request_id(request)}
    return JSONResponse(body, status_code=status, headers=exc.headers)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = jsonable_encoder(exc.errors())
    parts = []
    for error in errors:
        field = ".".join(str(p) for p in error.get("loc", []) if p not in ("query", "path", "body")) or "cuerpo"
        parts.append(f"'{field}' {error.get('msg')} (llegó {json.dumps(error.get('input'), ensure_ascii=False)[:60]})")
    message = "Parámetros inválidos: " + "; ".join(parts)
    return JSONResponse({"ok": False, "motivo": "PARAMETRO_INVALIDO", "mensaje": message, "detail": errors, "request_id": _request_id(request)}, status_code=422)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    message = (f"Error inesperado del servidor al procesar {request.method} {request.url.path}: {type(exc).__name__}: {exc}. "
               f"Quedó registrado en /logs" + (f" (id {request_id})." if request_id else "."))
    return JSONResponse({"ok": False, "motivo": "ERROR_INTERNO", "mensaje": message, "detail": message, "request_id": request_id}, status_code=500)


def install(app: FastAPI, log_path: Path) -> None:
    setup_logger(log_path)
    app.add_middleware(HttpLogMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(router)


# ---------------------------------------------------------------- rutas
@router.get("/logs")
def logs_page(request: Request):
    """Página de logs en vivo: cada petición, qué envió, qué respondió la app y por qué."""
    return templates.TemplateResponse("logs.html", {"request": request})


@router.get("/api/logs/http")
def http_logs(request: Request, desde: int = 0, limit: int = 200, automaticas: bool = False):
    """Peticiones HTTP recientes, la más nueva primero. `desde` = último número recibido, para traer solo las nuevas."""
    from appresso_food.api.gestos_api import token_para  # aquí: gestos_api se carga después que este módulo

    with _lock:
        entries = list(_requests) + (list(_polling) if automaticas else [])
        last = max((e["n"] for e in itertools.chain(_requests, _polling)), default=0)
    entries = sorted((e for e in entries if e["n"] > desde), key=lambda e: e["n"], reverse=True)[: max(1, min(limit, 1000))]
    if not token_para(request):  # la traza muestra rutas y código internos: solo para el equipo del local (siguen en logs/http.log)
        entries = [{**e, "traza": None} for e in entries]
    return {"ultimo": last, "peticiones": entries, "url_publica": _state["url_publica"], "archivo": _state["archivo"]}
