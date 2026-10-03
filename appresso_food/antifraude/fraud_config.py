"""Configuración del módulo antifraude (todo parametrizable por variables de entorno).

Variables de entorno:
    APPRESSO_WINDOW_SECONDS   tamaño de la ventana deslizante en segundos (10)
    APPRESSO_MAX_TRANSACTIONS umbral: N o más transacciones del mismo usuario dentro de la ventana
                              se marcan como POSSIBLE_FRAUD (3)
    APPRESSO_HMAC_SECRET      llave secreta del HMAC-SHA256 (por defecto la del ejemplo de clase)
    APPRESSO_MONGO_URI        cadena de conexión a MongoDB (mongodb://localhost:27017)
    APPRESSO_MONGO_DB         base de datos (appresso_food)
    APPRESSO_BAND_RULES_ENABLED  "true"/"false": segunda capa de reglas por horario (true)
    APPRESSO_BAND_RULES       JSON con las franjas horarias, ver DEFAULT_BAND_RULES
    APPRESSO_PAYMENT_METHODS  métodos de pago válidos separados por coma
    APPRESSO_HASH_HELPER      "true"/"false": habilita POST /api/transactions/hash, que firma datos con
                              la llave del servidor para poder probar desde el formulario (true)
"""

import json
import os
from dataclasses import dataclass, field
from typing import List, Tuple

from appresso_food.antifraude.fraud_hashing import key_fingerprint

# Llave del código de la clase (LLAVE_SECRETA = b"mi_llave_privada_123"): quien firme con ese mismo
# código obtiene hashes que este servidor acepta sin configurar nada.
DEFAULT_SECRET = "mi_llave_privada_123"
# Llave por defecto de versiones anteriores: solo se usa para verificar transacciones ya guardadas.
LEGACY_SECRET = "appresso-dev-secret-change-me"

# Llaves conocidas, para explicar un HASH_MISMATCH ("firmó con la llave X, el servidor usa otra").
KNOWN_SECRETS = {
    "la llave de ejemplo de la clase ('mi_llave_privada_123')": DEFAULT_SECRET,
    "la llave de desarrollo anterior de Appresso": LEGACY_SECRET,
}

# (nombre, inicio, fin, límite de ventas por usuario en la franja). Valores del PDF, pág. 38.
# Una franja que cruza la medianoche (inicio > fin) continúa al día siguiente.
DEFAULT_BAND_RULES: List[Tuple[str, str, str, int]] = [
    ("MAÑANA", "05:00:01", "12:00:00", 10),
    ("TARDE", "12:00:01", "20:00:00", 6),
    ("NOCHE", "20:00:01", "05:00:00", 3),
]

DEFAULT_PAYMENT_METHODS = ["Tarjeta", "Efectivo", "Nequi", "Daviplata", "PSE", "Transferencia"]


@dataclass
class FraudConfig:
    window_seconds: float = 10.0
    max_transactions: int = 3
    hmac_secret: str = DEFAULT_SECRET
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "appresso_food"
    band_rules_enabled: bool = True
    band_rules: List[Tuple[str, str, str, int]] = field(default_factory=lambda: list(DEFAULT_BAND_RULES))
    payment_methods: List[str] = field(default_factory=lambda: list(DEFAULT_PAYMENT_METHODS))
    hash_helper_enabled: bool = True
    # Modo "generador externo" (lo que sí aceptaba CAPRICHO): user como correo O identificador simple, método de pago
    # de texto libre, SHA-256 sin llave además del HMAC, y 201 (en vez de 422) cuando la transacción se recibió y se
    # registró como RECHAZADA. En el dataclass es False (estricto, usado por las pruebas); from_env lo activa.
    lenient_inputs: bool = False
    rejected_as_201: bool = False

    @classmethod
    def from_env(cls) -> "FraudConfig":
        cfg = cls()
        cfg.window_seconds = float(os.getenv("APPRESSO_WINDOW_SECONDS", cfg.window_seconds))
        cfg.max_transactions = int(os.getenv("APPRESSO_MAX_TRANSACTIONS", cfg.max_transactions))
        cfg.hmac_secret = os.getenv("APPRESSO_HMAC_SECRET", cfg.hmac_secret)
        cfg.mongo_uri = os.getenv("APPRESSO_MONGO_URI", cfg.mongo_uri)
        cfg.mongo_db = os.getenv("APPRESSO_MONGO_DB", cfg.mongo_db)
        cfg.band_rules_enabled = os.getenv("APPRESSO_BAND_RULES_ENABLED", "true").lower() != "false"
        cfg.hash_helper_enabled = os.getenv("APPRESSO_HASH_HELPER", "true").lower() != "false"
        cfg.lenient_inputs = os.getenv("APPRESSO_LENIENT_INPUTS", "true").lower() != "false"
        cfg.rejected_as_201 = os.getenv("APPRESSO_REJECTED_AS_201", "true").lower() != "false"
        raw_rules = os.getenv("APPRESSO_BAND_RULES")
        if raw_rules:
            cfg.band_rules = [tuple(rule) for rule in json.loads(raw_rules)]
        raw_methods = os.getenv("APPRESSO_PAYMENT_METHODS")
        if raw_methods:
            cfg.payment_methods = [m.strip() for m in raw_methods.split(",") if m.strip()]
        if cfg.window_seconds <= 0 or cfg.max_transactions < 1:
            raise ValueError("APPRESSO_WINDOW_SECONDS debe ser > 0 y APPRESSO_MAX_TRANSACTIONS >= 1")
        return cfg

    @property
    def uses_default_secret(self) -> bool:
        return self.hmac_secret == DEFAULT_SECRET

    def other_known_secrets(self) -> dict:
        """Llaves conocidas distintas de la configurada (descripción -> llave)."""
        return {name: key for name, key in KNOWN_SECRETS.items() if key != self.hmac_secret}

    def public_dict(self) -> dict:
        """Configuración visible para el frontend (nunca incluye la llave secreta ni la URI)."""
        return {
            "hash": {
                "algoritmo": "HMAC-SHA256",
                "llave_de_clase": self.uses_default_secret,
                **({"huella_llave": key_fingerprint(self.hmac_secret)} if self.hash_helper_enabled else {}),
            },
            "window_seconds": self.window_seconds,
            "max_transactions": self.max_transactions,
            "band_rules_enabled": self.band_rules_enabled,
            "band_rules": [
                {"nombre": n, "inicio": s, "fin": e, "limite": limit} for n, s, e, limit in self.band_rules
            ],
            "payment_methods": self.payment_methods,
            "lenient_inputs": self.lenient_inputs,
            "rejected_as_201": self.rejected_as_201,
        }
