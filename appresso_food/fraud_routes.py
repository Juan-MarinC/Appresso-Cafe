"""Rutas del módulo antifraude: API REST (/api/...) y páginas (/transacciones, /antifraude).

Los endpoints síncronos corren en el pool de hilos de FastAPI; el único `async`
es el POST, que necesita el cuerpo crudo para poder reportar JSON malformado en
vez de dejar que el framework responda un 422 genérico.
"""

import json
import threading
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from appresso_food.fraud_config import FraudConfig
from appresso_food.fraud_repo import MongoRepository
from appresso_food.fraud_service import ANOMALY_STATES, FraudService, build_file_logger

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
router = APIRouter()

_service: Optional[FraudService] = None
_last_error: Optional[str] = None
_init_lock = threading.Lock()


def init_fraud(force: bool = False) -> Optional[FraudService]:
    """Conecta con MongoDB y arranca el servicio. Si Mongo no está disponible la app
    sigue funcionando (pedidos, cocina...) y los endpoints antifraude responden 503."""
    global _service, _last_error
    with _init_lock:
        if _service is not None and not force:
            return _service
        try:
            config = FraudConfig.from_env()
            repo = MongoRepository(config.mongo_uri, config.mongo_db)
            repo.ping()
            service = FraudService(config, repo, file_logger=build_file_logger(BASE_DIR.parent / "logs" / "fraud.log"))
            service.startup()
            _service, _last_error = service, None
        except Exception as exc:  # noqa: BLE001 - se informa tal cual al usuario
            _service, _last_error = None, f"{type(exc).__name__}: {exc}"
        return _service


def get_service() -> FraudService:
    service = _service or init_fraud()
    if service is None:
        raise HTTPException(
            status_code=503,
            detail=f"MongoDB no disponible. Inicie MongoDB y reintente. ({_last_error})",
        )
    return service


def _limit(value: int, default: int = 100) -> int:
    return max(1, min(value or default, 500))


# ---------------------------------------------------------------- páginas
def _page_context(request: Request) -> dict:
    service = _service or init_fraud()
    config = service.config if service else FraudConfig.from_env()
    return {
        "request": request,
        "config": config.public_dict(),
        "mongo_ok": service is not None,
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
@router.post("/api/transactions")
async def post_transaction(request: Request):
    service = get_service()
    body = await request.body()
    outcome = await run_in_threadpool(service.process_body, body)
    return JSONResponse(outcome.body, status_code=outcome.http_status)


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
    return {"mongodb": "ok" if service else "no disponible", "detalle": _last_error}
