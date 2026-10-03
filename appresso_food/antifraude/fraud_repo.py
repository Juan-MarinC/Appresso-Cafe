"""Persistencia del módulo antifraude.

`MongoRepository` es la implementación real (MongoDB). `InMemoryRepository`
tiene la misma interfaz y se usa en las pruebas unitarias para no depender de
una base de datos.

Colecciones (adaptación a documentos del modelo de la pág. 45 del PDF):

    usuarios        _id, nombre, email*, cedula, estado, fecha_creacion, fecha_actualizacion
    transacciones   _id, id_txn, usuario_id, usuario_email, nombre_cliente, cedula, valor,
                    fecha_txn, metodo_pago, estado, motivo, errores[], hash, hash_origen,
                    aceptada, cantidad_ventana, payload_original, fecha_ref,
                    fecha_creacion, fecha_actualizacion
    anomalias       _id, transaccion_id, id_txn, usuario_id, usuario_email, tipo, nivel, estado,
                    cantidad_transacciones, ventana_segundos, limite, transacciones_ventana[],
                    fecha_txn, fecha_creacion, fecha_actualizacion
    logs            ts, nivel, evento, usuario, id_txn, transaccion_id, estado, motivo, hash,
                    anomalia, detalle

    transacciones_invalidas
                    _id, recibido_en, tipo_fallo, motivo, errores[], payload_texto, truncado, campos_faltantes[],
                    campos_desconocidos[], origen{ip, content_type, user_agent, metodo, ruta}, estado
                    (PENDIENTE|REPROCESADA|DESCARTADA), intentos, historial[], id_transaccion

`transacciones` guarda TODOS los intentos (válidos, sospechosos y rechazados) para
conservar el historial; `aceptada` marca los que cuentan como transacción real y
sobre ese subconjunto se garantiza ID único (índice único parcial).
"""

import itertools
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError


class DuplicateTransactionError(Exception):
    pass


def to_public(value: Any) -> Any:
    """Convierte un documento de Mongo en algo serializable a JSON."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            out["id" if key == "_id" else key] = to_public(item)
        return out
    if isinstance(value, list):
        return [to_public(item) for item in value]
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="milliseconds")
    return value


class MongoRepository:
    def __init__(self, uri: str, db_name: str):
        self.client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[db_name]

    def ping(self) -> bool:
        self.client.admin.command("ping")
        return True

    def ensure_indexes(self) -> None:
        db = self.db
        db.usuarios.create_index([("email", ASCENDING)], unique=True, name="uq_usuario_email")
        # ID único solo entre transacciones aceptadas: un rechazo no "quema" el ID.
        db.transacciones.create_index(
            [("id_txn", ASCENDING)], unique=True, partialFilterExpression={"aceptada": True}, name="uq_id_txn_aceptada"
        )
        db.transacciones.create_index([("usuario_email", ASCENDING), ("fecha_txn", DESCENDING)], name="ix_txn_usuario_fecha")
        db.transacciones.create_index([("fecha_ref", DESCENDING)], name="ix_txn_fecha_ref")
        db.transacciones.create_index([("estado", ASCENDING), ("fecha_ref", DESCENDING)], name="ix_txn_estado")
        db.anomalias.create_index([("usuario_email", ASCENDING), ("fecha_txn", DESCENDING)], name="ix_anom_usuario_fecha")
        db.anomalias.create_index([("estado", ASCENDING), ("fecha_creacion", DESCENDING)], name="ix_anom_estado")
        db.anomalias.create_index([("tipo", ASCENDING)], name="ix_anom_tipo")
        db.anomalias.create_index([("transaccion_id", ASCENDING)], name="ix_anom_transaccion")
        db.logs.create_index([("ts", DESCENDING)], name="ix_log_ts")
        db.logs.create_index([("usuario", ASCENDING), ("ts", DESCENDING)], name="ix_log_usuario")
        db.logs.create_index([("id_txn", ASCENDING)], name="ix_log_idtxn")
        db.logs.create_index([("evento", ASCENDING)], name="ix_log_evento")
        db.transacciones_invalidas.create_index([("estado", ASCENDING), ("recibido_en", DESCENDING)], name="ix_invalida_estado")

    # --- escritura -----------------------------------------------------
    def upsert_user(self, email: str, nombre: Optional[str], cedula: Optional[str], now: datetime) -> str:
        # nombre/cédula son opcionales por API: si no llegan, se conservan los que ya tenía el usuario.
        known = {k: v for k, v in (("nombre", nombre), ("cedula", cedula)) if v is not None}
        doc = self.db.usuarios.find_one_and_update(
            {"email": email},
            {
                "$set": {**known, "fecha_actualizacion": now},
                "$setOnInsert": {"email": email, "estado": "ACTIVO", "fecha_creacion": now},
            },
            upsert=True,
            return_document=True,
        )
        return str(doc["_id"])

    def insert_transaction(self, doc: dict) -> str:
        # insert_one agrega "_id" (ObjectId) al dict recibido: se inserta una copia para no filtrarlo a quien llama.
        try:
            return str(self.db.transacciones.insert_one(dict(doc)).inserted_id)
        except DuplicateKeyError as exc:
            raise DuplicateTransactionError(doc.get("id_txn")) from exc

    def insert_anomaly(self, doc: dict) -> str:
        return str(self.db.anomalias.insert_one(dict(doc)).inserted_id)

    def insert_log(self, doc: dict) -> None:
        self.db.logs.insert_one(dict(doc))

    # --- cuarentena de requests inválidos ------------------------------
    def insert_invalid(self, doc: dict) -> str:
        return str(self.db.transacciones_invalidas.insert_one(dict(doc)).inserted_id)

    def list_invalid(self, estado: Optional[str], limit: int) -> List[dict]:
        query = {"estado": estado} if estado else {}
        return [to_public(d) for d in self.db.transacciones_invalidas.find(query).sort("recibido_en", DESCENDING).limit(limit)]

    def get_invalid(self, invalid_id: str) -> Optional[dict]:
        try:
            doc = self.db.transacciones_invalidas.find_one({"_id": ObjectId(invalid_id)})
        except (InvalidId, TypeError):
            return None
        return to_public(doc) if doc else None

    def update_invalid(self, invalid_id: str, fields: dict) -> Optional[dict]:
        try:
            oid = ObjectId(invalid_id)
        except (InvalidId, TypeError):
            return None
        doc = self.db.transacciones_invalidas.find_one_and_update({"_id": oid}, {"$set": fields}, return_document=True)
        return to_public(doc) if doc else None

    def update_anomaly_estado(self, anomaly_id: str, estado: str, now: datetime) -> Optional[dict]:
        try:
            oid = ObjectId(anomaly_id)
        except (InvalidId, TypeError):
            return None
        doc = self.db.anomalias.find_one_and_update(
            {"_id": oid}, {"$set": {"estado": estado, "fecha_actualizacion": now}}, return_document=True
        )
        return to_public(doc) if doc else None

    # --- lectura -------------------------------------------------------
    def find_accepted_by_id_txn(self, id_txn: str) -> Optional[dict]:
        doc = self.db.transacciones.find_one({"id_txn": id_txn, "aceptada": True})
        return to_public(doc) if doc else None

    def count_user_accepted_between(self, email: str, start: datetime, end: datetime) -> int:
        return self.db.transacciones.count_documents(
            {"usuario_email": email, "aceptada": True, "fecha_txn": {"$gte": start, "$lte": end}}
        )

    def user_accepted_between(self, email: str, start: datetime, end: datetime) -> List[dict]:
        """Transacciones aceptadas del usuario con fecha en el intervalo abierto (start, end)."""
        cursor = self.db.transacciones.find(
            {"usuario_email": email, "aceptada": True, "fecha_txn": {"$gt": start, "$lt": end}},
            {"id_txn": 1, "fecha_txn": 1, "valor": 1},
        )
        return [to_public(d) for d in cursor]

    def recent_accepted(self, limit: int) -> List[dict]:
        cursor = self.db.transacciones.find({"aceptada": True}).sort("fecha_txn", DESCENDING).limit(limit)
        return [to_public(d) for d in cursor]

    def list_transactions(self, estado: Optional[str], usuario: Optional[str], limit: int) -> List[dict]:
        query: Dict[str, Any] = {}
        if estado:
            query["estado"] = estado
        if usuario:
            query["usuario_email"] = usuario.lower()
        cursor = self.db.transacciones.find(query).sort("fecha_creacion", DESCENDING).limit(limit)
        return [to_public(d) for d in cursor]

    def get_transaction(self, id_txn: str) -> Optional[dict]:
        doc = self.db.transacciones.find_one({"id_txn": id_txn}, sort=[("aceptada", DESCENDING), ("fecha_creacion", DESCENDING)])
        return to_public(doc) if doc else None

    def transactions_since(self, since: datetime) -> List[dict]:
        projection = {"fecha_ref": 1, "estado": 1, "valor": 1, "usuario_email": 1, "metodo_pago": 1, "aceptada": 1, "motivo": 1}
        return [to_public(d) for d in self.db.transacciones.find({"fecha_ref": {"$gte": since}}, projection)]

    def list_anomalies(self, estado: Optional[str], limit: int) -> List[dict]:
        query = {"estado": estado} if estado else {}
        return [to_public(d) for d in self.db.anomalias.find(query).sort("fecha_creacion", DESCENDING).limit(limit)]

    def get_anomaly(self, anomaly_id: str) -> Optional[dict]:
        try:
            doc = self.db.anomalias.find_one({"_id": ObjectId(anomaly_id)})
        except (InvalidId, TypeError):
            return None
        return to_public(doc) if doc else None

    def anomalies_since(self, since: datetime) -> List[dict]:
        return [to_public(d) for d in self.db.anomalias.find({"fecha_txn": {"$gte": since}}, {"transacciones_ventana": 0})]

    def list_logs(self, limit: int, usuario: Optional[str], evento: Optional[str]) -> List[dict]:
        query: Dict[str, Any] = {}
        if usuario:
            query["usuario"] = usuario.lower()
        if evento:
            query["evento"] = evento
        return [to_public(d) for d in self.db.logs.find(query).sort("ts", DESCENDING).limit(limit)]

    def count_users(self) -> int:
        return self.db.usuarios.count_documents({})


class InMemoryRepository:
    """Misma interfaz que MongoRepository, sin base de datos (pruebas)."""

    def __init__(self):
        self.users: Dict[str, dict] = {}
        self.transactions: List[dict] = []
        self.anomalies: List[dict] = []
        self.logs: List[dict] = []
        self.invalid: List[dict] = []
        self._ids = itertools.count(1)

    def ping(self) -> bool:
        return True

    def ensure_indexes(self) -> None:
        pass

    def upsert_user(self, email, nombre, cedula, now) -> str:
        user = self.users.get(email)
        if user is None:
            user = {"_id": str(next(self._ids)), "email": email, "estado": "ACTIVO", "fecha_creacion": now}
            self.users[email] = user
        user.update({k: v for k, v in (("nombre", nombre), ("cedula", cedula)) if v is not None}, fecha_actualizacion=now)
        return user["_id"]

    def insert_transaction(self, doc) -> str:
        if doc.get("aceptada") and self.find_accepted_by_id_txn(doc["id_txn"]):
            raise DuplicateTransactionError(doc["id_txn"])
        doc = dict(doc, _id=str(next(self._ids)))
        self.transactions.append(doc)
        return doc["_id"]

    def insert_anomaly(self, doc) -> str:
        doc = dict(doc, _id=str(next(self._ids)))
        self.anomalies.append(doc)
        return doc["_id"]

    def insert_log(self, doc) -> None:
        self.logs.append(dict(doc))

    def insert_invalid(self, doc) -> str:
        doc = dict(doc, _id=str(next(self._ids)))
        self.invalid.append(doc)
        return doc["_id"]

    def list_invalid(self, estado, limit):
        docs = [d for d in self.invalid if not estado or d["estado"] == estado]
        return [to_public(d) for d in reversed(docs)][:limit]

    def get_invalid(self, invalid_id):
        return next((to_public(d) for d in self.invalid if d["_id"] == invalid_id), None)

    def update_invalid(self, invalid_id, fields):
        for doc in self.invalid:
            if doc["_id"] == invalid_id:
                doc.update(fields)
                return to_public(doc)
        return None

    def update_anomaly_estado(self, anomaly_id, estado, now):
        for doc in self.anomalies:
            if doc["_id"] == anomaly_id:
                doc.update(estado=estado, fecha_actualizacion=now)
                return to_public(doc)
        return None

    def find_accepted_by_id_txn(self, id_txn):
        return next((to_public(d) for d in self.transactions if d.get("aceptada") and d["id_txn"] == id_txn), None)

    def count_user_accepted_between(self, email, start, end) -> int:
        return sum(1 for d in self.transactions if d.get("aceptada") and d["usuario_email"] == email and start <= d["fecha_txn"] <= end)

    def user_accepted_between(self, email, start, end):
        return [to_public(d) for d in self.transactions if d.get("aceptada") and d["usuario_email"] == email and start < d["fecha_txn"] < end]

    def recent_accepted(self, limit):
        docs = sorted((d for d in self.transactions if d.get("aceptada")), key=lambda d: d["fecha_txn"], reverse=True)
        return [to_public(d) for d in docs[:limit]]

    def list_transactions(self, estado, usuario, limit):
        docs = [d for d in self.transactions if (not estado or d["estado"] == estado) and (not usuario or d.get("usuario_email") == usuario.lower())]
        return [to_public(d) for d in reversed(docs)][:limit]

    def get_transaction(self, id_txn):
        docs = [d for d in self.transactions if d.get("id_txn") == id_txn]
        docs.sort(key=lambda d: (bool(d.get("aceptada")), d["fecha_creacion"]), reverse=True)
        return to_public(docs[0]) if docs else None

    def transactions_since(self, since):
        return [to_public(d) for d in self.transactions if d["fecha_ref"] >= since]

    def list_anomalies(self, estado, limit):
        docs = [d for d in self.anomalies if not estado or d["estado"] == estado]
        return [to_public(d) for d in reversed(docs)][:limit]

    def get_anomaly(self, anomaly_id):
        return next((to_public(d) for d in self.anomalies if d["_id"] == anomaly_id), None)

    def anomalies_since(self, since):
        return [to_public({k: v for k, v in d.items() if k != "transacciones_ventana"}) for d in self.anomalies if d["fecha_txn"] >= since]

    def list_logs(self, limit, usuario, evento):
        docs = [d for d in self.logs if (not usuario or d.get("usuario") == usuario.lower()) and (not evento or d["evento"] == evento)]
        return [to_public(d) for d in reversed(docs)][:limit]

    def count_users(self) -> int:
        return len(self.users)
