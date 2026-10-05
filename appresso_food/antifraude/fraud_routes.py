"""Rutas del módulo antifraude: API REST (/api/...) y páginas (/transacciones, /antifraude).

Los endpoints síncronos corren en el pool de hilos de FastAPI; el único `async`
es el POST, que necesita el cuerpo crudo para poder reportar JSON malformado en
vez de dejar que el framework responda un 422 genérico.
"""

import json
import threading
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pymongo.errors import ConnectionFailure

from appresso_food.antifraude.fraud_config import FraudConfig
from appresso_food.antifraude.fraud_repo import InMemoryRepository, MongoRepository
from appresso_food.antifraude.fraud_service import ANOMALY_STATES, INVALID_STATES, FraudService, build_file_logger

from appresso_food.web import BASE_DIR, templates
router = APIRouter()

_service: Optional[FraudService] = None
_last_error: Optional[str] = None
_memory_mode = False  # True si MongoDB no estaba disponible y se guarda solo en memoria
_init_lock = threading.Lock()
_reconnect_thread: Optional[threading.Thread] = None
RECONNECT_SECONDS = 15  # cada cuánto se reintenta MongoDB mientras la app está en modo memoria


def _describe(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"


def init_fraud(force: bool = False) -> Optional[FraudService]:
    """Conecta con MongoDB y arranca el servicio. Si MongoDB no está disponible se usa un repositorio en
    memoria (los datos se pierden al reiniciar) para que el endpoint siga recibiendo transacciones, y en
    segundo plano se reintenta MongoDB hasta que vuelva."""
    global _service, _last_error, _memory_mode
    with _init_lock:
        if _service is not None and not force:
            return _service
        config = FraudConfig.from_env()
        file_logger = build_file_logger(BASE_DIR.parent / "logs" / "fraud.log")
        try:
            repo = MongoRepository(config.mongo_uri, config.mongo_db)
            repo.ping()
            _memory_mode, _last_error = False, None
        except Exception as exc:  # noqa: BLE001 - se informa tal cual al usuario
            repo = InMemoryRepository()
            _memory_mode, _last_error = True, _describe(exc)
        service = FraudService(config, repo, file_logger=file_logger)
        service.startup()
        _service = service
    if _memory_mode:
        _start_reconnect_thread()
    return _service


def try_reconnect() -> bool:
    """Si MongoDB ya responde, cambia el servicio de memoria a MongoDB. Lo recibido en memoria no se copia."""
    global _service, _last_error, _memory_mode
    config = FraudConfig.from_env()
    try:
        repo = MongoRepository(config.mongo_uri, config.mongo_db)
        repo.ping()
    except Exception as exc:  # noqa: BLE001
        _last_error = _describe(exc)
        return False
    service = FraudService(config, repo, file_logger=build_file_logger(BASE_DIR.parent / "logs" / "fraud.log"))
    service.startup()
    with _init_lock:
        _service, _memory_mode, _last_error = service, False, None
    return True


def _reconnect_loop() -> None:
    while _memory_mode:
        time.sleep(RECONNECT_SECONDS)
        if try_reconnect():
            return


def _start_reconnect_thread() -> None:
    global _reconnect_thread
    if _reconnect_thread is None or not _reconnect_thread.is_alive():
        _reconnect_thread = threading.Thread(target=_reconnect_loop, name="reconexion-mongodb", daemon=True)
        _reconnect_thread.start()


def get_service() -> FraudService:
    return _service or init_fraud()


async def mongo_unavailable_handler(request: Request, exc: ConnectionFailure) -> JSONResponse:
    """MongoDB se cayó con la app corriendo: en vez de un 500 genérico, un 503 claro y reintentable.
    La petición NO se guardó (ni cuenta en la ventana), así que el cliente puede reenviarla."""
    message = ("La base de datos (MongoDB) no responde en este momento y la petición no se guardó. "
               "Reintente en unos segundos; si persiste, revise que MongoDB esté corriendo.")
    body = {"ok": False, "motivo": "MONGODB_NO_DISPONIBLE", "mensaje": message, "detail": message,
            "error": _describe(exc), "request_id": getattr(request.state, "request_id", None)}
    return JSONResponse(body, status_code=503, headers={"Retry-After": "10"})


def _limit(value: int, default: int = 100) -> int:
    return max(1, min(value or default, 500))


# ---------------------------------------------------------------- páginas
def _page_context(request: Request) -> dict:
    service = _service or init_fraud()
    config = service.config if service else FraudConfig.from_env()
    return {
        "request": request,
        "config": config.public_dict(),
        "mongo_ok": not _memory_mode,
        "mongo_error": _last_error,
        "default_secret": config.uses_default_secret,
        "hash_helper": config.hash_helper_enabled,
        "anomaly_states": ANOMALY_STATES,
    }


@router.get("/transacciones")
def transactions_page(request: Request):
    return templates.TemplateResponse("transacciones.html", _page_context(request))


@router.get("/antifraude")
def antifraud_page(request: Request):
    return templates.TemplateResponse("antifraude.html", _page_context(request))


# ---------------------------------------------------------------- API
def _http_status(service: FraudService, outcome) -> int:
    """Una transacción bien formada que se recibió y quedó registrada como RECHAZADA (reglas o hash) responde 201 con
    el resultado en el cuerpo, como CAPRICHO: un generador externo no la toma como fallo de conexión ni la reintenta.
    Incluye el cuerpo vacío o que no es JSON (400): se guarda en la cuarentena. Sigue siendo error HTTP solo el ID repetido (409). APPRESSO_REJECTED_AS_201=false lo desactiva."""
    if service.config.rejected_as_201 and outcome.http_status in (400, 422) and outcome.body.get("estado") == "REJECTED":
        outcome.body["http_original"] = outcome.http_status
        outcome.body["clasificacion"] = "ERRONEA"
        return 201
    return outcome.http_status


# Rutas alternativas (con y sin "/" final: un POST redirigido pierde el cuerpo en muchos clientes).
@router.post("/api/transactions")
@router.post("/api/transactions/", include_in_schema=False)
@router.post("/api/transacciones", include_in_schema=False)
@router.post("/api/transacciones/", include_in_schema=False)
@router.post("/transacciones", include_in_schema=False)
@router.post("/transacciones/", include_in_schema=False)
async def post_transaction(request: Request):
    service = get_service()
    body = await request.body()
    meta = {"ip": request.client.host if request.client else None, "content_type": request.headers.get("content-type"),
            "user_agent": request.headers.get("user-agent"), "metodo": request.method, "ruta": request.url.path,
            "query": dict(request.query_params)}  # se usa solo si el cuerpo llega vacío (requests.post(url, params=...))
    outcome = await run_in_threadpool(service.process_body, body, meta)
    return JSONResponse(outcome.body, status_code=_http_status(service, outcome))


# --- cuarentena: requests que no cumplieron el contrato (se conservan para revisarlos o reprocesarlos)
@router.get("/api/transactions/invalid")
@router.get("/api/transacciones/invalidas", include_in_schema=False)
def list_invalid(estado: Optional[str] = None, limit: int = 100):
    if estado and estado not in INVALID_STATES:
        raise HTTPException(400, f"estado debe ser uno de: {', '.join(INVALID_STATES)}")
    return get_service().repo.list_invalid(estado, _limit(limit))


@router.get("/api/transactions/invalid/{invalid_id}")
def get_invalid(invalid_id: str):
    doc = get_service().repo.get_invalid(invalid_id)
    if doc is None:
        raise HTTPException(404, "No existe ese request inválido.")
    return doc


@router.post("/api/transactions/invalid/{invalid_id}/reprocess")
async def reprocess_invalid(invalid_id: str, request: Request):
    """Sin cuerpo: reprocesa el payload original. Con un JSON en el cuerpo: reprocesa esa versión corregida."""
    service = get_service()
    raw = await request.body()
    corrected = None
    if raw.strip():
        try:
            corrected = json.loads(raw.decode("utf-8-sig"))
        except ValueError as exc:
            raise HTTPException(400, f"El JSON corregido no es válido: {exc}")
    outcome = await run_in_threadpool(service.reprocess_invalid, invalid_id, corrected)
    if outcome is None:
        raise HTTPException(404, "No existe ese request inválido.")
    return JSONResponse(outcome.body, status_code=outcome.http_status)


@router.post("/api/transactions/invalid/{invalid_id}/discard")
def discard_invalid(invalid_id: str):
    doc = get_service().discard_invalid(invalid_id)
    if doc is None:
        raise HTTPException(404, "No existe ese request inválido.")
    return doc


@router.get("/api/transactions")
@router.get("/api/transactions/", include_in_schema=False)  # el alias POST con "/" hacía que este GET diera 405
@router.get("/api/transacciones", include_in_schema=False)
@router.get("/api/transacciones/", include_in_schema=False)
def list_transactions(estado: Optional[str] = None, usuario: Optional[str] = None, limit: int = 100):
    return get_service().repo.list_transactions(estado, usuario, _limit(limit))


@router.get("/api/transactions/{id_txn}/verify")
def verify_transaction(id_txn: str):
    result = get_service().verify(id_txn)
    if result is None:
        raise HTTPException(404, f"No existe la transacción '{id_txn}'.")
    return result


@router.post("/api/transactions/hash")
async def compute_hash(request: Request):
    service = get_service()
    if not service.config.hash_helper_enabled:
        raise HTTPException(404, "El cálculo de hash desde la interfaz está deshabilitado.")
    try:
        raw = json.loads(await request.body())
    except ValueError as exc:
        return JSONResponse({"ok": False, "errores": [{"campo": "_body", "codigo": "MALFORMED_JSON", "mensaje": str(exc)}]}, status_code=400)
    outcome = await run_in_threadpool(service.compute_hash_for, raw)
    return JSONResponse(outcome.body, status_code=outcome.http_status)


@router.get("/api/anomalies")
def list_anomalies(estado: Optional[str] = None, limit: int = 100):
    return get_service().repo.list_anomalies(estado, _limit(limit))


@router.get("/api/anomalies/{anomaly_id}/timeline")
def anomaly_timeline(anomaly_id: str):
    result = get_service().anomaly_timeline(anomaly_id)
    if result is None:
        raise HTTPException(404, "Anomalía no encontrada.")
    return result


@router.patch("/api/anomalies/{anomaly_id}")
async def patch_anomaly(anomaly_id: str, request: Request):
    service = get_service()
    try:
        data = json.loads(await request.body())
        estado = data["estado"]
        updated = service.update_anomaly(anomaly_id, estado)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, f"Cuerpo inválido; envíe {{\"estado\": \"{'|'.join(ANOMALY_STATES)}\"}}. {exc}")
    if updated is None:
        raise HTTPException(404, "Anomalía no encontrada.")
    return updated


@router.get("/api/logs")
def list_logs(limit: int = 100, usuario: Optional[str] = None, evento: Optional[str] = None):
    return get_service().repo.list_logs(_limit(limit), usuario, evento)


@router.get("/api/stats")
def stats():
    return get_service().stats()


@router.get("/api/window")
def sliding_window(usuario: Optional[str] = None):
    service = get_service()
    return {
        "ventana_segundos": service.config.window_seconds,
        "limite": service.config.max_transactions,
        "usuarios": service.window.snapshot(usuario.lower() if usuario else None),
    }


@router.get("/api/config")
def public_config():
    return get_service().config.public_dict()


@router.get("/api/health")
def health():
    """Consulta MongoDB de verdad (antes respondía "ok" aunque MongoDB se hubiera caído después de arrancar)."""
    service = _service or init_fraud()
    if _memory_mode:
        return {"mongodb": "no disponible (modo memoria)", "detalle": _last_error}
    try:
        service.repo.ping()
    except Exception as exc:  # noqa: BLE001
        return {"mongodb": "no disponible", "detalle": _describe(exc) + " — las transacciones responden 503 hasta que vuelva"}
    return {"mongodb": "ok", "detalle": None}
