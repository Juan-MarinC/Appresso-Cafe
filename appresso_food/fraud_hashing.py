"""Integridad de la transacción con HMAC + SHA-256 (PDF, págs. 14-19).

La representación de los datos es determinista: JSON con claves ordenadas y
separadores fijos (`sort_keys=True`, `separators=(",", ":")`), así que los mismos
datos producen siempre el mismo hash.

Un hash garantiza INTEGRIDAD (los datos no cambiaron), no autentica al remitente:
quien conozca la llave secreta puede generar hashes válidos.
"""

import hashlib
import hmac
import json
import re
from typing import Any, Dict

HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _number(value: float) -> Any:
    """50000.0 y 50000 deben dar el mismo hash."""
    return int(value) if float(value).is_integer() else float(value)


def canonical_fields(id_txn: str, nombre: str, cedula: str, email: str, fecha, valor: float, metodo_pago: str) -> Dict[str, Any]:
    return {
        "idTxn": id_txn,
        "nombre": nombre,
        "cedula": cedula,
        "user": email,
        "date": fecha.isoformat(timespec="milliseconds"),
        "value": _number(valor),
        "paymentMethod": metodo_pago,
    }


def canonical_json(fields: Dict[str, Any]) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"))


def compute_hash(fields: Dict[str, Any], secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical_json(fields).encode("utf-8"), hashlib.sha256).hexdigest()


def hashes_match(expected: str, received: str) -> bool:
    return hmac.compare_digest(expected.lower(), received.lower())
