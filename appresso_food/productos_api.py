"""API REST de productos del menú: los cinco métodos HTTP de la clase sobre un mismo recurso.

    GET    /api/productos        consultar todos          -> SELECT
    GET    /api/productos/{id}   consultar uno
    POST   /api/productos        crear                    -> INSERT
    PUT    /api/productos/{id}   reemplazar completo      -> UPDATE de todos los campos
    PATCH  /api/productos/{id}   actualizar parcialmente  -> UPDATE solo de lo enviado
    DELETE /api/productos/{id}   eliminar                 -> DELETE

Análisis y descomposición: cada campo se valida por separado y se reúnen todos los
errores; un precio que no se puede convertir ("abc") se rechaza, nunca se vuelve 0,
y "50000" se normaliza a 50000. Si el cuerpo trae `hash`, se verifica con HMAC-SHA256
antes de tocar la base de datos (igual que en las transacciones).
"""

import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from appresso_food import storage
from appresso_food.api_helpers import error_response, json_body, read_json_object, verify_hash
from appresso_food.fraud_config import FraudConfig
from appresso_food.fraud_validation import EMPTY_FIELD, INVALID_NAME, INVALID_TYPE, NULL_FIELD, FieldError, parse_value
from appresso_food.models import Product

router = APIRouter()

FIELDS = ("nombre", "categoria", "precio")
DEFAULT_CATEGORY = "General"
EXPECTED = {"nombre": "texto (obligatorio)", "precio": "número mayor a 0 (obligatorio)",
            "categoria": f"texto (opcional, por defecto '{DEFAULT_CATEGORY}')", "hash": "opcional: HMAC-SHA256 del JSON sin 'hash'"}


def _public(product: Product) -> dict:
    price = product.price
    return {"id": product.id, "nombre": product.name, "categoria": product.category,
            "precio": int(price) if float(price).is_integer() else price}


def _validate(data: dict, required: Tuple[str, ...]) -> Tuple[Dict[str, Any], List[FieldError], List[str]]:
    """Devuelve (campos limpios, errores, campos ignorados). Solo valida los campos que llegaron."""
    clean: Dict[str, Any] = {}
    errors: List[FieldError] = []
    for field in FIELDS:
        if data.get(field) is None:
            if field in required:
                errors.append(FieldError(field, NULL_FIELD, f"'{field}' es obligatorio y llegó null o ausente."))
            continue
        value = data[field]
        if field == "precio":
            number, error = parse_value(value)
            if error:
                errors.append(FieldError("precio", error.codigo, error.mensaje))
            else:
                clean["precio"] = number
        elif not isinstance(value, str):
            errors.append(FieldError(field, INVALID_TYPE, f"'{field}' debe ser un texto, llegó {type(value).__name__}."))
        elif not value.strip():
            errors.append(FieldError(field, EMPTY_FIELD, f"'{field}' no puede estar vacío."))
        elif not 2 <= len(value.strip()) <= 80 or not any(c.isalpha() for c in value):
            errors.append(FieldError(field, INVALID_NAME, f"'{field}' debe tener entre 2 y 80 caracteres e incluir letras."))
        else:
            clean[field] = " ".join(value.split())
    ignored = [key for key in data if key not in FIELDS and key != "hash"]
    return clean, errors, ignored


def _notes(ignored: List[str]) -> List[str]:
    notes = []
    for key in ignored:
        if key == "id":
            notes.append("Se ignoró 'id': lo asigna el servidor al crear y en PUT/PATCH/DELETE va en la URL.")
        else:
            notes.append(f"Se ignoró '{key}': un producto del menú solo tiene nombre, categoria y precio.")
    return notes


def _invalid(errors: List[FieldError], ignored: List[str], ayuda: Optional[str] = None) -> JSONResponse:
    mensaje = errors[0].mensaje if len(errors) == 1 else f"{len(errors)} errores de validación: " + "; ".join(e.mensaje for e in errors)
    extra = {"errores": [e.as_dict() for e in errors], "formato_esperado": EXPECTED, "notas": _notes(ignored)}
    if ayuda:
        extra["ayuda"] = ayuda
    return error_response(422, errors[0].codigo, mensaje, **extra)


async def _read(request: Request) -> Tuple[Optional[dict], Optional[dict], Optional[JSONResponse]]:
    """(datos, verificación del hash, error). El hash es opcional; si viene y no coincide se rechaza."""
    data, error = await read_json_object(request)
    if error:
        return None, None, error
    if "hash" not in data:
        return data, None, None
    status, result = verify_hash(data, FraudConfig.from_env())
    if status != 200:
        result["detail"] = result["mensaje"]
        return None, None, JSONResponse(result, status_code=status)
    return data, result, None


def _get_or_404(product_id: int, ayuda: str = "") -> Product:
    product = storage.get_product(product_id)
    if product is None:
        raise HTTPException(404, f"No existe el producto con id {product_id}. Consulte los ids con GET /api/productos. {ayuda}".strip())
    return product


def _name_taken(name: str, own_id: Optional[int] = None) -> Optional[JSONResponse]:
    other = storage.find_product_by_name(name)
    if other and other.id != own_id:
        return error_response(409, "NOMBRE_DUPLICADO", f"Ya existe un producto llamado '{other.name}' (id {other.id}). Los nombres no se pueden repetir.")
    return None


def _ok(status: int, mensaje: str, product: Product, ignored: List[str], hash_check: Optional[dict], **extra: Any) -> JSONResponse:
    notes = _notes(ignored) + extra.pop("notas", [])
    body = {"ok": True, "mensaje": mensaje, "producto": _public(product), **extra, "notas": notes}
    if hash_check:
        body["verificacion_hash"] = hash_check
    headers = {"Location": f"/api/productos/{product.id}"} if status == 201 else None
    return JSONResponse(body, status_code=status, headers=headers)


@router.get("/api/productos")
def list_products():
    """GET: consultar todos los productos del menú."""
    return [_public(p) for p in sorted(storage.get_products(), key=lambda p: p.id)]


@router.get("/api/productos/{product_id}")
def get_product(product_id: int):
    """GET: consultar un producto por id."""
    return _public(_get_or_404(product_id))


@router.post("/api/productos", status_code=201, openapi_extra=json_body({"nombre": "Monitor", "precio": 800000}))
async def create_product(request: Request):
    """POST: crear un producto (nombre y precio obligatorios; categoria opcional)."""
    data, hash_check, error = await _read(request)
    if error:
        return error
    clean, errors, ignored = _validate(data, required=("nombre", "precio"))
    if errors:
        return _invalid(errors, ignored)
    conflict = _name_taken(clean["nombre"])
    if conflict:
        return conflict
    try:
        product = storage.create_product(clean["nombre"], clean.get("categoria", DEFAULT_CATEGORY), clean["precio"])
    except sqlite3.IntegrityError:
        return error_response(409, "NOMBRE_DUPLICADO", f"Ya existe un producto llamado '{clean['nombre']}'.")
    notes = [] if "categoria" in clean else [f"No se envió 'categoria': se usó '{DEFAULT_CATEGORY}'."]
    return _ok(201, f"Producto creado con id {product.id}.", product, ignored, hash_check, notas=notes)


@router.put("/api/productos/{product_id}", openapi_extra=json_body({"nombre": "Mouse inalámbrico", "precio": 70000, "categoria": "Accesorios"}))
async def replace_product(product_id: int, request: Request):
    """PUT: reemplazar el producto completo (los campos que no envíe vuelven a su valor por defecto)."""
    before = _get_or_404(product_id, "PUT reemplaza un producto existente; para crear use POST /api/productos.")
    data, hash_check, error = await _read(request)
    if error:
        return error
    clean, errors, ignored = _validate(data, required=("nombre", "precio"))
    if errors:
        return _invalid(errors, ignored, "PUT reemplaza el producto COMPLETO: envíe nombre y precio (y categoria). "
                                         "Para cambiar solo algunos campos use PATCH.")
    conflict = _name_taken(clean["nombre"], product_id)
    if conflict:
        return conflict
    product = storage.update_product(product_id, clean["nombre"], clean.get("categoria", DEFAULT_CATEGORY), clean["precio"])
    notes = [] if "categoria" in clean else [f"PUT reemplaza todo: como no se envió 'categoria', quedó '{DEFAULT_CATEGORY}'. Use PATCH para conservarla."]
    return _ok(200, f"Producto {product_id} reemplazado completo (PUT).", product, ignored, hash_check, antes=_public(before), notas=notes)


@router.patch("/api/productos/{product_id}", openapi_extra=json_body({"precio": 60000}))
async def patch_product(product_id: int, request: Request):
    """PATCH: actualizar solo los campos enviados."""
    before = _get_or_404(product_id)
    data, hash_check, error = await _read(request)
    if error:
        return error
    clean, errors, ignored = _validate(data, required=())
    if errors:
        return _invalid(errors, ignored)
    if not clean:
        return error_response(422, "SIN_CAMBIOS", "No llegó ningún campo para actualizar. Envíe al menos uno de: nombre, categoria, precio.",
                              notas=_notes(ignored), formato_esperado=EXPECTED)
    if "nombre" in clean:
        conflict = _name_taken(clean["nombre"], product_id)
        if conflict:
            return conflict
    product = storage.update_product(
        product_id, clean.get("nombre", before.name), clean.get("categoria", before.category), clean.get("precio", before.price)
    )
    return _ok(200, f"Producto {product_id} actualizado parcialmente (PATCH): cambió {', '.join(clean)}.", product, ignored, hash_check,
               antes=_public(before), campos_actualizados=list(clean))


@router.delete("/api/productos/{product_id}")
def delete_product(product_id: int):
    """DELETE: eliminar un producto que no tenga pedidos en el historial."""
    product = _get_or_404(product_id)
    orders, units = storage.product_usage(product_id)
    if orders:
        return error_response(
            409, "PRODUCTO_EN_USO",
            f"No se puede eliminar '{product.name}': aparece en {orders} pedido(s) del historial ({units} unidades). "
            "Borrarlo dejaría esos pedidos sin producto y dañaría el ranking. Puede cambiarlo con PATCH, "
            "o crear uno nuevo con POST y eliminar ese.",
        )
    storage.delete_product(product_id)
    return {"ok": True, "mensaje": f"Producto {product_id} ('{product.name}') eliminado.", "producto_eliminado": _public(product)}
