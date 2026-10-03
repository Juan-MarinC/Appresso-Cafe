"""Integridad de la transacción con HMAC + SHA-256 (PDF, págs. 14-19).

La representación de los datos es determinista: JSON con claves ordenadas y
separadores fijos (`sort_keys=True`, `separators=(",", ":")`), así que los mismos
datos producen siempre el mismo hash. Es exactamente el código de la clase:

    datos = json.dumps(transaccion, sort_keys=True, separators=(",", ":"))
    hmac.new(LLAVE_SECRETA, datos.encode("utf-8"), hashlib.sha256).hexdigest()

Cuando el cliente envía un `hash`, el servidor lo compara contra el HMAC del JSON
TAL COMO LLEGÓ (sin el campo `hash`), que es lo que firmó el cliente. También se
acepta el HMAC de los datos normalizados, que es el que calcula el formulario.

Un hash garantiza INTEGRIDAD (los datos no cambiaron), no autentica al remitente:
quien conozca la llave secreta puede generar hashes válidos.
"""

import hashlib
import hmac
import json
import re
from typing import Any, Dict, List, Optional, Tuple

HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")

# Cómo calcular el hash del lado del cliente (se devuelve en los diagnósticos).
CLIENT_RECIPE = (
    "datos = json.dumps(transaccion_sin_hash, sort_keys=True, separators=(',', ':')); "
    "hash = hmac.new(LLAVE_SECRETA, datos.encode('utf-8'), hashlib.sha256).hexdigest()"
)


def _number(value: float) -> Any:
    """50000.0 y 50000 deben dar el mismo hash."""
    return int(value) if float(value).is_integer() else float(value)


def canonical_fields(id_txn: str, nombre: Optional[str], cedula: Optional[str], email: str, fecha, valor: float, metodo_pago: str) -> Dict[str, Any]:
    """Campos normalizados que firma el servidor. `nombre` y `cedula` son opcionales y solo entran si existen."""
    fields = {
        "idTxn": id_txn,
        "user": email,
        "date": fecha.isoformat(timespec="milliseconds"),
        "value": _number(valor),
        "paymentMethod": metodo_pago,
    }
    if nombre is not None:
        fields["nombre"] = nombre
    if cedula is not None:
        fields["cedula"] = cedula
    return fields


def canonical_json(fields: Any) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"))


def compute_hash(fields: Any, secret: str) -> str:
    return hmac_text(canonical_json(fields), secret)


def hmac_text(text: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()


def hashes_match(expected: str, received: str) -> bool:
    return hmac.compare_digest(expected.lower(), received.lower())


def key_fingerprint(secret: str) -> str:
    """Huella pública de la llave: `hashlib.sha256(LLAVE).hexdigest()[:12]`. Permite comparar llaves sin revelarlas."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


def without_hash(data: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in data.items() if key != "hash"}


def _texts(fields: Any) -> List[str]:
    """Textos que pudo firmar el cliente: claves ordenadas (Python, como en clase) o en el orden recibido
    (JSON.stringify de JavaScript), separadores compactos o con espacios, con tildes escapadas o sin escapar."""
    texts: List[str] = []
    for ordenar in (True, False):
        for separadores in ((",", ":"), (", ", ": ")):
            for solo_ascii in (True, False):
                text = json.dumps(fields, sort_keys=ordenar, separators=separadores, ensure_ascii=solo_ascii)
                if text not in texts:
                    texts.append(text)
    return texts


def find_match(received: str, candidates: List[Tuple[str, Any]], secret: str) -> Optional[Tuple[str, str]]:
    """candidates: [(etiqueta, datos)]. Devuelve (etiqueta, texto firmado) del primero cuyo HMAC coincide."""
    for label, fields in candidates:
        for text in _texts(fields):
            if hashes_match(hmac_text(text, secret), received):
                return label, text
    return None


def find_plain_match(received: str, candidates: List[Tuple[str, Any]]) -> Optional[Tuple[str, str]]:
    """Igual que find_match pero con SHA-256 SIN llave (diapositivas 15-17). Integridad básica, no autentica."""
    for label, fields in candidates:
        for text in _texts(fields):
            if hashes_match(hashlib.sha256(text.encode("utf-8")).hexdigest(), received):
                return label, text
    return None


def diagnose(received: str, candidates: List[Tuple[str, Any]], secret: str, other_secrets: Dict[str, str],
             show_fingerprint: bool = True) -> Dict[str, Any]:
    """Explica por qué un hash no coincide, probando los errores más comunes al calcularlo.

    La huella de la llave permite comparar llaves, pero también probar llaves débiles sin conexión: solo se
    entrega en modo clase (APPRESSO_HASH_HELPER=true), que ya firma datos a pedido de cualquiera."""
    cause = None
    for _, fields in candidates:
        for text in _texts(fields):
            if hashes_match(hashlib.sha256(text.encode("utf-8")).hexdigest(), received):
                cause = ("Su hash es SHA-256 SIN llave. El servidor espera HMAC-SHA256 con la llave compartida "
                         "(un SHA-256 simple no prueba quién lo generó).")
            for name, key in other_secrets.items():
                if cause is None and hashes_match(hmac_text(text, key), received):
                    cause = (f"Los datos NO cambiaron, pero se firmaron con {name} y este servidor usa otra llave. "
                             "Arranque el servidor con APPRESSO_HMAC_SECRET igual a la llave del cliente.")
    if cause is None:
        cause = ("Los datos cambiaron después de calcular el hash, o se firmó con otra llave u otro texto. "
                 + ("Compare la huella de su llave y el texto exacto que firma el servidor (abajo)." if show_fingerprint
                    else "Compare el texto exacto que firma el servidor (abajo) con el que firmó usted."))
    result = {
        "algoritmo": "HMAC-SHA256",
        "causa_probable": cause,
        "hash_recibido": received,
        "texto_que_firma_el_servidor": canonical_json(candidates[0][1]),
        "como_calcularlo": CLIENT_RECIPE,
    }
    if show_fingerprint:
        result["huella_llave_servidor"] = key_fingerprint(secret)
        result["como_comparar"] = ("La huella de su llave es hashlib.sha256(LLAVE_SECRETA).hexdigest()[:12]; "
                                   "si no es igual a 'huella_llave_servidor', las llaves son distintas.")
    return result
