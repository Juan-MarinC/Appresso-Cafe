"""Validación y normalización de transacciones (PDF, págs. 21-22).

Regla central: un valor que no se puede convertir de forma inequívoca NUNCA se
convierte en 0, NaN u otro valor "válido". Se rechaza con un código y un motivo.
`"50000"` sí se normaliza a 50000.0; `"abc"` genera INVALID_VALUE.

Este módulo es la autoridad final: el frontend valida lo mismo solo para dar
feedback inmediato, pero el backend no confía en él.

`nombre` y `cedula` no son campos del PDF: el formulario los exige, pero por API
son opcionales (ausentes o null) para aceptar el formato del PDF tal cual. Si
llegan, se validan igual que el resto.
"""

import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional, Tuple

from appresso_food.antifraude.fraud_config import FraudConfig
from appresso_food.antifraude.fraud_hashing import HASH_RE

# Códigos de motivo
NULL_FIELD = "NULL_FIELD"
EMPTY_FIELD = "EMPTY_FIELD"
INVALID_TYPE = "INVALID_TYPE"
INVALID_EMAIL = "INVALID_EMAIL"
INVALID_VALUE = "INVALID_VALUE"
INVALID_DATE = "INVALID_DATE"
INVALID_ID = "INVALID_ID"
INVALID_NAME = "INVALID_NAME"
INVALID_CEDULA = "INVALID_CEDULA"
INVALID_PAYMENT_METHOD = "INVALID_PAYMENT_METHOD"
INVALID_HASH_FORMAT = "INVALID_HASH_FORMAT"
MALFORMED_JSON = "MALFORMED_JSON"
DUPLICATE_TRANSACTION = "DUPLICATE_TRANSACTION"
HASH_MISMATCH = "HASH_MISMATCH"

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")
ID_RE = re.compile(r"^[A-Za-z0-9_\-:.]{1,64}$")
USER_ID_RE = re.compile(r"^[a-z0-9._+\-]{2,120}$")
METHOD_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 ._\-]{2,40}$")
CEDULA_RE = re.compile(r"^\d{6,10}$")
NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")  # admite signo solo para dar el mismo mensaje que un número negativo

MAX_VALUE = 1_000_000_000


@dataclass
class FieldError:
    campo: str
    codigo: str
    mensaje: str

    def as_dict(self) -> dict:
        return {"campo": self.campo, "codigo": self.codigo, "mensaje": self.mensaje}


@dataclass
class NormalizedTransaction:
    id_txn: str
    nombre: Optional[str]
    cedula: Optional[str]
    email: str
    fecha: datetime
    valor: float
    metodo_pago: str
    hash_cliente: Optional[str]


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").casefold()


def _presence(raw: dict, key: str, errors: List[FieldError], label: str, optional: bool = False) -> Tuple[bool, Any]:
    """True si el campo trae un valor utilizable (ni ausente, ni null, ni vacío). Un opcional puede faltar o ser null."""
    if key not in raw or raw[key] is None:
        if not optional:
            errors.append(FieldError(key, NULL_FIELD, f"'{label}' es obligatorio y llegó null o ausente."))
        return False, None
    value = raw[key]
    if isinstance(value, str) and not value.strip():
        errors.append(FieldError(key, EMPTY_FIELD, f"'{label}' no puede estar vacío."))
        return False, None
    return True, value


def _type_error(key: str, label: str, value: Any, expected: str) -> FieldError:
    return FieldError(key, INVALID_TYPE, f"'{label}' debe ser {expected}, llegó {type(value).__name__}.")


def parse_value(value: Any) -> Tuple[Optional[float], Optional[FieldError]]:
    """Convierte el valor a número o devuelve el error. Nunca devuelve 0/NaN por defecto."""
    label = "valor"
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None, _type_error("value", label, value, "un número")
    if isinstance(value, str):
        text = value.strip()
        if not NUMERIC_RE.match(text):
            return None, FieldError("value", INVALID_VALUE, f"'{value}' no es un número válido (use dígitos, sin separadores de miles).")
        number = float(text)
    else:
        number = float(value)
    if math.isnan(number) or math.isinf(number):
        return None, FieldError("value", INVALID_VALUE, "El valor no es un número finito.")
    if number <= 0:
        return None, FieldError("value", INVALID_VALUE, "El valor debe ser mayor a cero.")
    if number > MAX_VALUE:
        return None, FieldError("value", INVALID_VALUE, f"El valor supera el máximo permitido ({MAX_VALUE:,}).")
    return number, None


def parse_date(value: Any) -> Tuple[Optional[datetime], Optional[FieldError]]:
    if not isinstance(value, str):
        return None, _type_error("date", "fecha", value, "un texto ISO 8601")
    text = value.strip()
    if ":" not in text:
        return None, FieldError("date", INVALID_DATE, "La fecha debe incluir fecha y hora (ej: 2026-09-23T10:30:01.120).")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None, FieldError("date", INVALID_DATE, f"'{value}' no es una fecha y hora ISO 8601 válida.")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    if not 2000 <= parsed.year <= 2100:
        return None, FieldError("date", INVALID_DATE, "El año de la fecha está fuera del rango permitido (2000-2100).")
    return parsed.replace(microsecond=(parsed.microsecond // 1000) * 1000), None


def validate_transaction(raw: Any, config: FraudConfig) -> Tuple[Optional[NormalizedTransaction], List[FieldError]]:
    """Devuelve (transacción normalizada, []) o (None, errores). Reúne TODOS los errores, no solo el primero."""
    errors: List[FieldError] = []
    if not isinstance(raw, dict):
        return None, [FieldError("_body", INVALID_TYPE, "El cuerpo debe ser un objeto JSON con los campos de la transacción.")]

    id_txn = nombre = cedula = email = metodo = hash_cliente = None
    fecha = valor = None

    ok, value = _presence(raw, "idTxn", errors, "ID de transacción")
    if ok:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            errors.append(_type_error("idTxn", "ID de transacción", value, "un entero o texto"))
        elif isinstance(value, int) and value < 0:
            errors.append(FieldError("idTxn", INVALID_ID, "El ID no puede ser negativo."))
        elif not ID_RE.match(str(value).strip()):
            errors.append(FieldError("idTxn", INVALID_ID, "El ID admite letras, números, guion y guion bajo (máx. 64)."))
        else:
            id_txn = str(value).strip()

    ok, value = _presence(raw, "nombre", errors, "nombre del cliente", optional=True)
    if ok:
        if not isinstance(value, str):
            errors.append(_type_error("nombre", "nombre del cliente", value, "un texto"))
        elif not 2 <= len(value.strip()) <= 80 or not any(c.isalpha() for c in value):
            errors.append(FieldError("nombre", INVALID_NAME, "El nombre debe tener entre 2 y 80 caracteres e incluir letras."))
        else:
            nombre = " ".join(value.split())

    ok, value = _presence(raw, "cedula", errors, "cédula", optional=True)
    if ok:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            errors.append(_type_error("cedula", "cédula", value, "un número o texto de dígitos"))
        elif not CEDULA_RE.match(str(value).strip()):
            errors.append(FieldError("cedula", INVALID_CEDULA, "La cédula debe tener entre 6 y 10 dígitos, sin puntos ni letras."))
        else:
            cedula = str(value).strip()

    ok, value = _presence(raw, "user", errors, "correo electrónico")
    if ok and config.lenient_inputs and isinstance(value, int) and not isinstance(value, bool) and value > 0:
        value = str(value)  # identificador numérico de usuario (ej. 25)
    if ok:
        if config.lenient_inputs and isinstance(value, str) and "@" not in value and USER_ID_RE.match(value.strip().lower()):
            email = value.strip().lower()  # identificador simple de usuario (ej. "usuario25"), no correo
        elif not isinstance(value, str):
            errors.append(_type_error("user", "correo electrónico", value, "un texto"))
        elif len(value.strip()) > 254 or not EMAIL_RE.match(value.strip()):
            errors.append(FieldError("user", INVALID_EMAIL, f"'{value}' no es un correo electrónico válido."))
        else:
            email = value.strip().lower()

    ok, value = _presence(raw, "date", errors, "fecha y hora")
    if ok:
        fecha, error = parse_date(value)
        if error:
            errors.append(error)

    ok, value = _presence(raw, "value", errors, "valor")
    if ok:
        valor, error = parse_value(value)
        if error:
            errors.append(error)

    ok, value = _presence(raw, "paymentMethod", errors, "método de pago")
    if ok:
        if not isinstance(value, str):
            errors.append(_type_error("paymentMethod", "método de pago", value, "un texto"))
        else:
            by_folded = {_fold(m): m for m in config.payment_methods}
            metodo = by_folded.get(_fold(value.strip()))
            if metodo is None and config.lenient_inputs and METHOD_RE.match(value.strip()):
                metodo = " ".join(value.split())  # método que no está en la lista (Crédito, Transferencia...): se registra tal cual
            if metodo is None:
                errors.append(FieldError("paymentMethod", INVALID_PAYMENT_METHOD, f"'{value}' no es un método válido. Use: {', '.join(config.payment_methods)}."))

    supplied = raw.get("hash")
    if supplied is not None and not (isinstance(supplied, str) and not supplied.strip()):
        if not isinstance(supplied, str):
            errors.append(_type_error("hash", "hash", supplied, "un texto hexadecimal"))
        elif not HASH_RE.match(supplied.strip()):
            errors.append(FieldError("hash", INVALID_HASH_FORMAT, "El hash debe ser SHA-256 en hexadecimal (64 caracteres)."))
        else:
            hash_cliente = supplied.strip().lower()

    if errors:
        return None, errors
    return NormalizedTransaction(id_txn, nombre, cedula, email, fecha, valor, metodo, hash_cliente), []
