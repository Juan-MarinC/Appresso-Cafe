"""Rutas de la capacitación que no dependen de MongoDB: hash HMAC sobre cualquier JSON,
total de una lista de productos (análisis y descomposición de problemas) e índice de la API.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from appresso_food.antifraude import fraud_hashing as hashing
from appresso_food.api.api_helpers import error_response, json_body, read_json_object, verify_hash
from appresso_food.antifraude.fraud_config import FraudConfig

router = APIRouter()


@router.post("/api/hash/calcular", openapi_extra=json_body({"id": 1001, "producto": "Mouse", "cantidad": 4, "valor": 50000},
                                                         "Cualquier objeto JSON; se calcula su HMAC-SHA256."))
async def compute_hash(request: Request):
    """Calcula el HMAC-SHA256 de cualquier JSON con la llave del servidor (el código de la diapositiva)."""
    config = FraudConfig.from_env()
    if not config.hash_helper_enabled:
        return error_response(404, "AYUDA_DE_HASH_DESHABILITADA", "El cálculo de hash por la API está deshabilitado (APPRESSO_HASH_HELPER=false): "
                              "firmar datos a pedido de cualquiera permitiría fabricar hashes válidos. Calcule el hash en su equipo con la llave compartida.",
                              como_calcularlo=hashing.CLIENT_RECIPE)
    data, error = await read_json_object(request)
    if error:
        return error
    data = hashing.without_hash(data)
    return {
        "ok": True,
        "algoritmo": "HMAC-SHA256",
        "hash": hashing.compute_hash(data, config.hmac_secret),
        "texto_firmado": hashing.canonical_json(data),
        "huella_llave": hashing.key_fingerprint(config.hmac_secret),
        "mensaje": "Envíe estos mismos datos más este 'hash' a /api/hash/verificar (o a /api/transactions) para que el servidor los valide.",
    }


@router.post("/api/hash/verificar", openapi_extra=json_body({"id": 1001, "producto": "Mouse", "cantidad": 4, "valor": 50000, "hash": "(64 hex)"},
                                                          "Cualquier objeto JSON con un campo 'hash'."))
async def verify(request: Request):
    """Recibe un JSON con su `hash`, recalcula el HMAC-SHA256 y responde si se acepta o se rechaza (y por qué)."""
    data, error = await read_json_object(request)
    if error:
        return error
    status, body = verify_hash(data, FraudConfig.from_env())
    return JSONResponse(body, status_code=status)


def calculate_total(products: Any) -> Dict[str, Any]:
    """Total de una lista de productos, resuelto como en la clase: cada producto es un subproblema
    independiente (convertir -> validar -> multiplicar -> sumar) y un producto inválido se informa y
    se salta, sin tumbar el total de los demás."""
    if not isinstance(products, list):
        return {"ok": False, "motivo": "INVALID_TYPE", "mensaje": f"'productos' debe ser una lista, llegó {type(products).__name__}."}
    total = 0.0
    lines: List[dict] = []
    invalid: List[dict] = []
    for index, item in enumerate(products):
        name = item.get("producto", f"#{index + 1}") if isinstance(item, dict) else f"#{index + 1}"
        try:
            if not isinstance(item, dict):
                raise TypeError("cada producto debe ser un objeto con producto, valor y cantidad")
            if isinstance(item["valor"], bool) or isinstance(item["cantidad"], bool):
                raise TypeError("valor y cantidad no pueden ser booleanos")
            if isinstance(item["cantidad"], float) and not item["cantidad"].is_integer():
                raise ValueError("la cantidad debe ser un entero")
            value, quantity = float(item["valor"]), int(item["cantidad"])
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("el valor no es finito")
            if value <= 0:
                invalid.append({"producto": name, "motivo": "Valor inválido", "mensaje": f"Valor inválido para {name}: debe ser mayor a 0."})
                continue
            if quantity <= 0:
                invalid.append({"producto": name, "motivo": "Cantidad inválida", "mensaje": f"Cantidad inválida para {name}: debe ser mayor a 0."})
                continue
            subtotal = value * quantity
            total += subtotal
            lines.append({"producto": name, "cantidad": quantity, "valor": value, "subtotal": subtotal, "detalle": f"{name}: {quantity} x ${value:.0f} = ${subtotal:.0f}"})
        except (ValueError, TypeError, KeyError) as exc:
            reason = f"falta el campo {exc}" if isinstance(exc, KeyError) else str(exc)
            invalid.append({"producto": name, "motivo": "Datos inválidos", "mensaje": f"Datos inválidos para {name} ({reason})."})
    return {"ok": True, "total": total, "total_texto": f"Total: ${total:.0f}", "lineas": lines, "invalidos": invalid}


@router.post("/api/totales", openapi_extra=json_body({"productos": [
    {"producto": "Mouse", "valor": "50000", "cantidad": "2"}, {"producto": "Teclado", "valor": 80000, "cantidad": 1}]},
    "Ejemplo de la diapositiva de análisis y descomposición de problemas."))
async def totals(request: Request):
    """Suma valor x cantidad de cada producto; los textos numéricos se convierten y los inválidos se informan."""
    data, error = await read_json_object(request)
    if error:
        return error
    result = calculate_total(data.get("productos"))
    return JSONResponse(result, status_code=200 if result["ok"] else 422)


@router.get("/api")
def api_index(request: Request):
    """Lista de todas las rutas de la API con su método y qué hacen."""
    rows = []
    for route in request.app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api") or not getattr(route, "methods", None):
            continue
        doc = (route.endpoint.__doc__ or "").strip().splitlines()
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            rows.append({"metodo": method, "ruta": path, "descripcion": doc[0] if doc else ""})
    rows.sort(key=lambda r: (r["ruta"], r["metodo"]))
    return {"app": "Appresso Food", "documentacion_interactiva": "/docs", "logs_en_vivo": "/logs", "rutas": rows}
