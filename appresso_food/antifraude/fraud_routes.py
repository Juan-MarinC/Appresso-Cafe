"""Rutas del módulo antifraude: API REST (/api/...) y páginas (/transacciones, /antifraude).

Los endpoints síncronos corren en el pool de hilos de FastAPI; el único `async`
es el POST, que necesita el cuerpo crudo para poder reportar JSON malformado en
vez de dejar que el framework responda un 422 genérico.
"""

import json
import threading
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from appresso_food.antifraude.fraud_config import FraudConfig
from appresso_food.antifraude.fraud_repo import InMemoryRepository, MongoRepository
from appresso_food.antifraude.fraud_service import ANOMALY_STATES, INVALID_STATES, FraudService, build_file_logger

from appresso_food.web import BASE_DIR, templates
router = APIRouter()

_service: Optional[FraudService] = None
_last_error: Optional[str] = None
_memory_mode = False  # True si MongoDB no estaba disponible y se guarda solo en memoria
_init_lock = threading.Lock()


def init_fraud(force: bool = False) -> Optional[FraudService]:
    """Conecta con MongoDB y arranca el servicio. Si MongoDB no está disponible se usa un repositorio en
    memoria (los datos se pierden al reiniciar) para que el endpoint siga recibiendo transacciones."""
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
            _memory_mode, _last_error = True, f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
        service = FraudService(config, repo, file_logger=file_logger)
        service.startup()
        _service = service
        return _service


def get_service() -> FraudService:
    return _service or init_fraud()


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
            "user_agent": request.headers.get("user-agent"), "metodo": request.method, "ruta": request.url.path}
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
    service = _service or init_fraud()
    return {"mongodb": "no disponible (modo memoria)" if _memory_mode else "ok", "detalle": _last_error}
