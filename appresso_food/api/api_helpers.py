"""Utilidades compartidas por las APIs JSON: leer el cuerpo, responder errores explicados y
verificar el `hash` (HMAC-SHA256) de cualquier JSON, como en el código de la clase.

Todas las respuestas de error llevan `mensaje` (qué pasó y qué hacer) y `detail`, que es
el campo que ya leen las páginas de la app.
"""

import json
from typing import Any, Optional, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse

from appresso_food.antifraude import fraud_hashing as hashing
from appresso_food.antifraude.fraud_config import FraudConfig


def error_response(status: int, motivo: str, mensaje: str, **extra: Any) -> JSONResponse:
    return JSONResponse({"ok": False, "motivo": motivo, "mensaje": mensaje, "detail": mensaje, **extra}, status_code=status)


def json_body(example: dict, description: str = "") -> dict:
    """`openapi_extra` para que /docs muestre un cuerpo de ejemplo en rutas que leen el JSON a mano."""
    return {"requestBody": {"required": True, "description": description,
                            "content": {"application/json": {"schema": {"type": "object"}, "example": example}}}}


async def read_json_object(request: Request) -> Tuple[Optional[dict], Optional[JSONResponse]]:
    """(datos, None) si el cuerpo es un objeto JSON; si no, (None, respuesta de error explicada)."""
    body = await request.body()
    if not body.strip():
        return None, error_response(400, "EMPTY_BODY", "El cuerpo llegó vacío. Envíe un objeto JSON con el encabezado Content-Type: application/json.")
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return None, error_response(400, "MALFORMED_JSON", f"El cuerpo no es JSON válido: {exc}. Revise comillas dobles, comas y llaves.")
    if not isinstance(data, dict):
        return None, error_response(422, "INVALID_TYPE", f"El cuerpo debe ser un objeto JSON {{...}}, llegó {type(data).__name__}.")
    return data, None


def verify_hash(data: dict, config: FraudConfig) -> Tuple[int, dict]:
    """Verifica `data["hash"]` contra el HMAC-SHA256 del resto del JSON. Devuelve (status HTTP, cuerpo).

    Si el cuerpo es un sobre como {"transaccion": {...}, "hash": "..."}, también se acepta el hash
    calculado solo sobre el objeto interno."""
    received = data.get("hash")
    if received is None or (isinstance(received, str) and not received.strip()):
        return 422, {"ok": False, "coincide": False, "resultado": "RECHAZADA", "motivo": "HASH_REQUERIDO",
                     "mensaje": "Falta el campo 'hash'. Envíe los datos junto con 'hash': HMAC-SHA256 del JSON sin ese campo.",
                     "como_calcularlo": hashing.CLIENT_RECIPE}
    if not isinstance(received, str) or not hashing.HASH_RE.match(received.strip()):
        return 422, {"ok": False, "coincide": False, "resultado": "RECHAZADA", "motivo": "INVALID_HASH_FORMAT",
                     "mensaje": "El hash debe ser HMAC-SHA256 en hexadecimal: 64 caracteres 0-9 y a-f (use .hexdigest()).",
                     "hash_recibido": received}
    received = received.strip().lower()
    candidates = [("PAYLOAD_RECIBIDO", hashing.without_hash(data))]
    if len(data) == 2:
        candidates += [(f"CAMPO_{key}", value) for key, value in data.items() if key != "hash" and isinstance(value, dict)]
    match = hashing.find_match(received, candidates, config.hmac_secret)
    if match:
        label, text = match
        return 200, {"ok": True, "coincide": True, "resultado": "ACEPTADA", "algoritmo": "HMAC-SHA256",
                     "calculado_sobre": label, "texto_firmado": text, "hash_recibido": received,
                     "mensaje": "El hash coincide: los datos llegaron sin modificaciones y se firmaron con la llave compartida."}
    diagnosis = hashing.diagnose(received, candidates, config.hmac_secret, config.other_known_secrets(), config.hash_helper_enabled)
    return 422, {"ok": False, "coincide": False, "resultado": "RECHAZADA", "motivo": "HASH_MISMATCH",
                 "mensaje": f"El hash no coincide con los datos, por eso se rechaza. {diagnosis['causa_probable']}",
                 "diagnostico_hash": diagnosis}
