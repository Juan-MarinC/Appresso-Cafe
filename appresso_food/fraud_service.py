"""Orquestación del flujo de detección (POST /api/transactions).

    Request -> JSON -> validación y normalización -> hash (HMAC-SHA256) -> duplicados
            -> identificar usuario -> actualizar ventana deslizante (entra / salen)
            -> contar -> comparar con el límite -> regla por horario (2.ª capa)
            -> guardar en MongoDB -> registrar log -> responder

Estados de la transacción:   VALID | SUSPICIOUS | REJECTED
Una transacción mal formada se RECHAZA (REJECTED + motivo); una bien formada que
dispara una regla de detección queda SUSPICIOUS. Son cosas distintas.
"""

import json
import logging
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from appresso_food import fraud_hashing as hashing
from appresso_food import fraud_validation as validation
from appresso_food.fraud_config import FraudConfig
from appresso_food.fraud_repo import DuplicateTransactionError
from appresso_food.fraud_validation import FieldError, NormalizedTransaction
from appresso_food.sliding_window import SlidingWindowManager, WindowEntry, densest_window

STATUS_VALID = "VALID"
STATUS_REJECTED = "REJECTED"
STATUS_SUSPICIOUS = "SUSPICIOUS"

POSSIBLE_FRAUD = "POSSIBLE_FRAUD"
TOO_MANY_TRANSACTIONS = "TOO_MANY_TRANSACTIONS"

ANOMALY_STATES = ["NUEVA", "ABIERTA", "REVISADA", "DESCARTADA"]
LEVELS = ["BAJO", "MEDIO", "ALTO"]

REBUILD_LIMIT = 5000
MAX_PAYLOAD_CHARS = 4000


def build_file_logger(path: Path) -> logging.Logger:
    """Log en archivo (PDF, pág. 28). El log en MongoDB es el que consulta el dashboard."""
    logger = logging.getLogger("appresso.fraud")
    if not logger.handlers:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


@dataclass
class Outcome:
    http_status: int
    body: dict


def _clip(value: Any, size: int = 120) -> Optional[str]:
    if value is None:
        return None
    return str(value)[:size]


def _parse_hms(text: str) -> int:
    h, m, s = (int(part) for part in text.split(":"))
    return h * 3600 + m * 60 + s


def band_for(ts: datetime, rules: List[Tuple[str, str, str, int]]) -> Optional[Tuple[str, datetime, datetime, int]]:
    """Franja horaria de `ts`: (nombre, inicio, fin, límite). Soporta franjas que cruzan la medianoche."""
    seconds = ts.hour * 3600 + ts.minute * 60 + ts.second
    midnight = ts.replace(hour=0, minute=0, second=0, microsecond=0)
    for name, start_text, end_text, limit in rules:
        start_s, end_s = _parse_hms(start_text), _parse_hms(end_text)
        if start_s <= end_s:
            if start_s <= seconds <= end_s:
                start, end = midnight + timedelta(seconds=start_s), midnight + timedelta(seconds=end_s)
                return name, start, end + timedelta(milliseconds=999), limit
        elif seconds >= start_s:
            return name, midnight + timedelta(seconds=start_s), midnight + timedelta(days=1, seconds=end_s, milliseconds=999), limit
        elif seconds <= end_s:
            return name, midnight - timedelta(days=1) + timedelta(seconds=start_s), midnight + timedelta(seconds=end_s, milliseconds=999), limit
    return None


class FraudService:
    def __init__(
        self,
        config: FraudConfig,
        repo,
        clock: Callable[[], datetime] = datetime.now,
        file_logger: Optional[logging.Logger] = None,
    ):
        self.config = config
        self.repo = repo
        self.clock = clock
        self.window = SlidingWindowManager(config.window_seconds)
        self.file_logger = file_logger
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ arranque
    def startup(self) -> None:
        self.repo.ensure_indexes()
        self._rebuild_windows()
        self._log("INFO", "SISTEMA_INICIADO", detalle=f"ventana={self.config.window_seconds}s limite={self.config.max_transactions}")

    def _rebuild_windows(self) -> None:
        """La ventana activa vive en memoria; al reiniciar se reconstruye desde el historial en MongoDB."""
        self.window.clear()
        by_user: Dict[str, List[dict]] = defaultdict(list)
        for doc in self.repo.recent_accepted(REBUILD_LIMIT):
            by_user[doc["usuario_email"]].append(doc)
        window = timedelta(seconds=self.config.window_seconds)
        for email, docs in by_user.items():
            stamps = [(datetime.fromisoformat(d["fecha_txn"]), d) for d in docs]
            latest = max(ts for ts, _ in stamps)
            entries = [
                WindowEntry(ts=ts, txn_id=d["id_txn"], valor=d["valor"], seq=self.window.next_seq())
                for ts, d in stamps
                if ts > latest - window
            ]
            self.window.load(email, entries)

    # ------------------------------------------------------------------ logs
    def _log(self, nivel: str, evento: str, usuario=None, id_txn=None, transaccion_id=None, estado=None, motivo=None, hash=None, anomalia=None, detalle=None) -> None:
        doc = {
            "ts": self.clock(),
            "nivel": nivel,
            "evento": evento,
            "usuario": usuario,
            "id_txn": id_txn,
            "transaccion_id": transaccion_id,
            "estado": estado,
            "motivo": motivo,
            "hash": hash,
            "anomalia": anomalia,
            "detalle": detalle,
        }
        try:
            self.repo.insert_log(doc)
        except Exception:  # el log nunca debe tumbar el procesamiento
            if self.file_logger:
                self.file_logger.exception("No se pudo escribir el log en MongoDB")
        if self.file_logger:
            level = {"INFO": logging.INFO, "WARN": logging.WARNING, "ERROR": logging.ERROR}[nivel]
            self.file_logger.log(
                level,
                "%s usuario=%s idTxn=%s estado=%s motivo=%s anomalia=%s hash=%s detalle=%s",
                evento, usuario, id_txn, estado, motivo, anomalia, (hash or "")[:16], detalle,
            )

    # ------------------------------------------------------------------ entrada
    def process_body(self, body: bytes) -> Outcome:
        text = body.decode("utf-8", errors="replace")
        try:
            raw = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            errors = [FieldError("_body", validation.MALFORMED_JSON, f"El cuerpo no es JSON válido: {exc}")]
            return self._reject(None, text, errors, self.clock(), http_status=400)
        return self.process(raw, text)

    def process(self, raw: Any, raw_text: Optional[str] = None) -> Outcome:
        now = self.clock()
        if raw_text is None:
            try:
                raw_text = json.dumps(raw, default=str)
            except (TypeError, ValueError):
                raw_text = repr(raw)

        norm, errors = validation.validate_transaction(raw, self.config)
        if errors:
            return self._reject(raw, raw_text, errors, now)

        expected = hashing.compute_hash(self._canonical(norm), self.config.hmac_secret)
        if norm.hash_cliente and not hashing.hashes_match(expected, norm.hash_cliente):
            return self._reject(
                raw, raw_text,
                [FieldError("hash", validation.HASH_MISMATCH, "El hash recibido no coincide con los datos: la transacción fue modificada o firmada con otra llave.")],
                now, norm=norm, hash_value=norm.hash_cliente, http_status=422,
            )
        hash_origin = "CLIENTE_VERIFICADO" if norm.hash_cliente else "SERVIDOR"

        with self._lock:
            if self.repo.find_accepted_by_id_txn(norm.id_txn):
                return self._duplicate(raw, raw_text, norm, expected, now)

            user_id = self.repo.upsert_user(norm.email, norm.nombre, norm.cedula, now)
            result = self.window.add(norm.email, norm.fecha, norm.id_txn, norm.valor)  # entra + salen
            members, count = result.members, result.count
            if result.out_of_order:
                # Llegó con fecha anterior a otras ya recibidas: lo que ya salió de la ventana activa pudo
                # formar grupo con ella, así que se cuenta con el historial completo del usuario (±N s).
                delta = self.window_delta()
                history = self.repo.user_accepted_between(norm.email, norm.fecha - delta, norm.fecha + delta)
                entries = [
                    WindowEntry(ts=datetime.fromisoformat(h["fecha_txn"]), txn_id=h["id_txn"], valor=h["valor"], seq=self.window.next_seq())
                    for h in history
                ]
                members = densest_window(entries + [result.entered], result.entered, delta)
                count = len(members)
            in_window = members

            anomalies: List[dict] = []
            if count >= self.config.max_transactions:
                anomalies.append(
                    self._anomaly_doc(
                        POSSIBLE_FRAUD, "MEDIO" if count == self.config.max_transactions else "ALTO",
                        count, self.config.window_seconds, self.config.max_transactions, norm, user_id, in_window, now,
                    )
                )

            band_info = None
            if self.config.band_rules_enabled:
                band = band_for(norm.fecha, self.config.band_rules)
                if band:
                    name, start, end, limit = band
                    total = self.repo.count_user_accepted_between(norm.email, start, end) + 1
                    band_info = {"franja": name, "limite": limit, "cantidad": total}
                    if total > limit:
                        doc = self._anomaly_doc(
                            TOO_MANY_TRANSACTIONS, "BAJO", total, round((end - start).total_seconds()), limit, norm, user_id, [], now,
                        )
                        doc["franja"] = name
                        anomalies.append(doc)

            estado = STATUS_SUSPICIOUS if anomalies else STATUS_VALID
            motivo = anomalies[0]["tipo"] if anomalies else None
            doc = {
                "id_txn": norm.id_txn,
                "usuario_id": user_id,
                "usuario_email": norm.email,
                "nombre_cliente": norm.nombre,
                "cedula": norm.cedula,
                "valor": norm.valor,
                "fecha_txn": norm.fecha,
                "metodo_pago": norm.metodo_pago,
                "estado": estado,
                "motivo": motivo,
                "errores": [],
                "hash": expected,
                "hash_origen": hash_origin,
                "aceptada": True,
                "cantidad_ventana": count,
                "payload_original": _clip(raw_text, MAX_PAYLOAD_CHARS),
                "fecha_ref": norm.fecha,
                "fecha_creacion": now,
                "fecha_actualizacion": now,
            }
            try:
                txn_id = self.repo.insert_transaction(doc)
            except DuplicateTransactionError:  # carrera entre procesos: el índice único manda
                self.window.remove(norm.email, norm.id_txn)
                return self._duplicate(raw, raw_text, norm, expected, now)

            for anomaly in anomalies:
                anomaly["transaccion_id"] = txn_id
                anomaly["id"] = self.repo.insert_anomaly(anomaly)

        self._log_window_events(norm, txn_id, result, count)
        for anomaly in anomalies:
            self._log("WARN", "ANOMALIA_DETECTADA", norm.email, norm.id_txn, txn_id, estado, anomaly["tipo"], expected, anomaly["tipo"],
                      f"cantidad={anomaly['cantidad_transacciones']} limite={anomaly['limite']} ventana={anomaly['ventana_segundos']}s nivel={anomaly['nivel']}")
        self._log("WARN" if anomalies else "INFO", f"TXN_{estado}", norm.email, norm.id_txn, txn_id, estado, motivo, expected,
                  anomalies[0]["tipo"] if anomalies else None, f"cantidad_ventana={count}")

        body = {
            "ok": True,
            "estado": estado,
            "motivo": motivo,
            "mensaje": self._message(estado, count, anomalies),
            "id": txn_id,
            "idTxn": norm.id_txn,
            "usuario": norm.email,
            "hash": expected,
            "hash_origen": hash_origin,
            "ventana": {
                "usuario": norm.email,
                "cantidad": count,
                "limite": self.config.max_transactions,
                "ventana_segundos": self.config.window_seconds,
                "tardia": result.out_of_order,
                "entradas": [self._entry_dict(e) for e in in_window],
                "salieron": [self._entry_dict(e) for e in result.evicted],
            },
            "franja_horaria": band_info,
            "anomalias": [{k: v for k, v in a.items() if k not in ("transacciones_ventana", "fecha_creacion", "fecha_actualizacion", "fecha_txn", "usuario_id", "transaccion_id")} for a in anomalies],
            "errores": [],
        }
        return Outcome(201, body)

    # ------------------------------------------------------------------ helpers
    def window_delta(self) -> timedelta:
        return timedelta(seconds=self.config.window_seconds)

    @staticmethod
    def _entry_dict(entry: WindowEntry) -> dict:
        return {"idTxn": entry.txn_id, "fecha": entry.ts.isoformat(timespec="milliseconds"), "valor": entry.valor}

    @staticmethod
    def _canonical(norm: NormalizedTransaction) -> dict:
        return hashing.canonical_fields(norm.id_txn, norm.nombre, norm.cedula, norm.email, norm.fecha, norm.valor, norm.metodo_pago)

    def _message(self, estado: str, count: int, anomalies: List[dict]) -> str:
        if estado == STATUS_SUSPICIOUS:
            parts = []
            for anomaly in anomalies:
                if anomaly["tipo"] == POSSIBLE_FRAUD:
                    parts.append(f"{count} transacciones del mismo usuario dentro de {self.config.window_seconds:g} s "
                                 f"(límite {self.config.max_transactions}) [regla principal: ventana deslizante]")
                else:
                    parts.append(f"{anomaly['cantidad_transacciones']} transacciones del usuario en la franja {anomaly['franja']} "
                                 f"(límite {anomaly['limite']}) [segunda capa: regla por horario]")
            return "Transacción aceptada pero marcada como SOSPECHOSA: " + "; ".join(parts) + "."
        return f"Transacción válida. Quedan {count} en la ventana de {self.config.window_seconds:g} s del usuario."

    def _anomaly_doc(self, tipo, nivel, cantidad, ventana_s, limite, norm, user_id, in_window, now) -> dict:
        return {
            "tipo": tipo,
            "nivel": nivel,
            "estado": "NUEVA",
            "cantidad_transacciones": cantidad,
            "ventana_segundos": ventana_s,
            "limite": limite,
            "usuario_id": user_id,
            "usuario_email": norm.email,
            "id_txn": norm.id_txn,
            "fecha_txn": norm.fecha,
            "transacciones_ventana": [{"id_txn": e.txn_id, "fecha_txn": e.ts, "valor": e.valor} for e in in_window],
            "fecha_creacion": now,
            "fecha_actualizacion": now,
        }

    def _log_window_events(self, norm, txn_id, result, count) -> None:
        note = "fuera_de_orden (contada con el historial)" if result.out_of_order else "en_orden"
        self._log("INFO", "VENTANA_ENTRA", norm.email, norm.id_txn, txn_id, detalle=f"cantidad={count} {note}")
        for gone in result.evicted:
            self._log("INFO", "VENTANA_SALE", norm.email, gone.txn_id, detalle=
                      f"salió de la ventana activa por {norm.id_txn} (edad >= {self.config.window_seconds:g}s); sigue en el historial")

    def _duplicate(self, raw, raw_text, norm, hash_value, now) -> Outcome:
        errors = [FieldError("idTxn", validation.DUPLICATE_TRANSACTION, f"Ya existe una transacción aceptada con el ID '{norm.id_txn}'.")]
        return self._reject(raw, raw_text, errors, now, norm=norm, hash_value=hash_value, http_status=409)

    def _reject(self, raw, raw_text, errors: List[FieldError], now, norm: Optional[NormalizedTransaction] = None,
                hash_value: Optional[str] = None, http_status: int = 422) -> Outcome:
        source = raw if isinstance(raw, dict) else {}
        valor = source.get("value")
        doc = {
            "id_txn": norm.id_txn if norm else (_clip(source.get("idTxn")) if isinstance(source.get("idTxn"), (str, int)) and not isinstance(source.get("idTxn"), bool) else None),
            "usuario_id": None,
            "usuario_email": norm.email if norm else _clip(source.get("user")),
            "nombre_cliente": norm.nombre if norm else _clip(source.get("nombre")),
            "cedula": norm.cedula if norm else _clip(source.get("cedula"), 40),
            "valor": norm.valor if norm else (float(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) and valor == valor else None),
            "fecha_txn": norm.fecha if norm else None,
            "metodo_pago": norm.metodo_pago if norm else _clip(source.get("paymentMethod"), 40),
            "estado": STATUS_REJECTED,
            "motivo": errors[0].codigo,
            "errores": [e.as_dict() for e in errors],
            "hash": hash_value,
            "hash_origen": None,
            "aceptada": False,
            "cantidad_ventana": None,
            "payload_original": _clip(raw_text, MAX_PAYLOAD_CHARS),
            "fecha_ref": now,
            "fecha_creacion": now,
            "fecha_actualizacion": now,
        }
        try:
            txn_id = self.repo.insert_transaction(doc)
        except Exception as exc:  # la respuesta al cliente no depende de poder guardar el rechazo
            txn_id = None
            self._log("ERROR", "RECHAZO_NO_GUARDADO", detalle=str(exc))
        evento = "HASH_NO_COINCIDE" if errors[0].codigo == validation.HASH_MISMATCH else "TXN_REJECTED"
        self._log("WARN", evento, doc["usuario_email"], doc["id_txn"], txn_id, STATUS_REJECTED, errors[0].codigo, hash_value,
                  detalle="; ".join(f"{e.campo}:{e.codigo}" for e in errors))
        body = {
            "ok": False,
            "estado": STATUS_REJECTED,
            "motivo": errors[0].codigo,
            "mensaje": errors[0].mensaje if len(errors) == 1 else f"{len(errors)} errores de validación.",
            "id": txn_id,
            "idTxn": doc["id_txn"],
            "errores": [e.as_dict() for e in errors],
            "hash": hash_value,
        }
        return Outcome(http_status, body)

    # ------------------------------------------------------------------ consultas
    def compute_hash_for(self, raw: Any) -> Outcome:
        """Calcula el hash que el servidor espera para unos datos (útil para firmar/probar desde el formulario)."""
        norm, errors = validation.validate_transaction(raw, self.config)
        if errors:
            return Outcome(422, {"ok": False, "errores": [e.as_dict() for e in errors]})
        fields = self._canonical(norm)
        return Outcome(200, {"ok": True, "hash": hashing.compute_hash(fields, self.config.hmac_secret), "canonico": hashing.canonical_json(fields)})

    def verify(self, id_txn: str) -> Optional[dict]:
        """Valida posteriormente el hash guardado recalculándolo con los datos guardados."""
        doc = self.repo.get_transaction(id_txn)
        if doc is None:
            return None
        if not doc.get("hash") or not doc.get("aceptada"):
            return {"idTxn": id_txn, "verificable": False, "mensaje": "La transacción fue rechazada: no tiene un hash de datos aceptados."}
        fields = hashing.canonical_fields(
            doc["id_txn"], doc["nombre_cliente"], doc["cedula"], doc["usuario_email"],
            datetime.fromisoformat(doc["fecha_txn"]), doc["valor"], doc["metodo_pago"],
        )
        recomputed = hashing.compute_hash(fields, self.config.hmac_secret)
        matches = hashing.hashes_match(recomputed, doc["hash"])
        self._log("INFO" if matches else "ERROR", "HASH_VERIFICADO" if matches else "HASH_INCONSISTENTE", doc["usuario_email"], id_txn,
                  doc["id"], doc["estado"], None if matches else validation.HASH_MISMATCH, doc["hash"])
        return {
            "idTxn": id_txn,
            "verificable": True,
            "coincide": matches,
            "hash_guardado": doc["hash"],
            "hash_recalculado": recomputed,
            "mensaje": "Integridad correcta: los datos guardados no cambiaron." if matches else "INCONSISTENCIA: los datos guardados ya no coinciden con su hash.",
        }

    def update_anomaly(self, anomaly_id: str, estado: str) -> Optional[dict]:
        if estado not in ANOMALY_STATES:
            raise ValueError(f"Estado inválido. Use: {', '.join(ANOMALY_STATES)}.")
        doc = self.repo.update_anomaly_estado(anomaly_id, estado, self.clock())
        if doc:
            self._log("INFO", "ANOMALIA_ESTADO", doc.get("usuario_email"), doc.get("id_txn"), doc.get("transaccion_id"), detalle=f"nuevo_estado={estado}")
        return doc

    def anomaly_timeline(self, anomaly_id: str) -> Optional[dict]:
        doc = self.repo.get_anomaly(anomaly_id)
        if doc is None:
            return None
        events = sorted(doc.get("transacciones_ventana", []), key=lambda e: e["fecha_txn"])
        origin = datetime.fromisoformat(events[0]["fecha_txn"]) if events else None
        for event in events:
            event["offset_segundos"] = round((datetime.fromisoformat(event["fecha_txn"]) - origin).total_seconds(), 3)
        doc["linea_de_tiempo"] = events
        doc["duracion_segundos"] = events[-1]["offset_segundos"] if events else 0
        return doc

    # ------------------------------------------------------------------ estadísticas
    def stats(self) -> dict:
        now = self.clock()
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        since_date = min(month_start, today - timedelta(days=14), week_start - timedelta(days=7))
        since = datetime.combine(since_date, datetime.min.time())

        txns = [dict(t, fecha=datetime.fromisoformat(t["fecha_ref"])) for t in self.repo.transactions_since(since)]
        anomalies = [dict(a, fecha=datetime.fromisoformat(a["fecha_txn"])) for a in self.repo.anomalies_since(since)]

        def in_range(items, start, end=None):
            return [i for i in items if i["fecha"].date() >= start and (end is None or i["fecha"].date() <= end)]

        def period(start, end=None) -> dict:
            t, a = in_range(txns, start, end), in_range(anomalies, start, end)
            accepted = [x for x in t if x.get("aceptada")]
            suspicious = [x for x in accepted if x["estado"] == STATUS_SUSPICIOUS]
            users = {x["usuario_email"] for x in accepted}
            states = Counter(x["estado"] for x in a)
            return {
                "total_transacciones": len(accepted),
                "rechazadas": len(t) - len(accepted),
                "total_anomalias": len(a),
                "transacciones_sospechosas": len(suspicious),
                "porcentaje_anomalias": round(100 * len(suspicious) / len(accepted), 1) if accepted else 0.0,
                "usuarios_afectados": len({x["usuario_email"] for x in a}),
                "valor_sospechoso": round(sum(x.get("valor") or 0 for x in suspicious), 2),
                "usuarios_distintos": len(users),
                "promedio_por_usuario": round(len(accepted) / len(users), 2) if users else 0.0,
                "anomalias_por_estado": {s: states.get(s, 0) for s in ANOMALY_STATES},
            }

        periods = {"hoy": period(today), "semana": period(week_start), "mes": period(month_start)}

        month_t = [x for x in in_range(txns, month_start) if x.get("aceptada")]
        month_a = in_range(anomalies, month_start)
        month_all = in_range(txns, month_start)

        per_user_t, per_user_a = Counter(x["usuario_email"] for x in month_t), Counter(x["usuario_email"] for x in month_a)
        recurrent = [
            {"usuario": u, "transacciones": per_user_t[u], "anomalias": per_user_a.get(u, 0)}
            for u in sorted(per_user_t, key=lambda k: (per_user_a.get(k, 0), per_user_t[k]), reverse=True)
            if per_user_t[u] >= 2 or per_user_a.get(u, 0) >= 1
        ][:10]

        cases = Counter(a["tipo"] for a in month_a) + Counter(x["motivo"] for x in month_all if x["estado"] == STATUS_REJECTED and x.get("motivo"))

        by_hour = [{"hora": h, "transacciones": 0, "anomalias": 0} for h in range(24)]
        for x in month_t:
            by_hour[x["fecha"].hour]["transacciones"] += 1
        for x in month_a:
            by_hour[x["fecha"].hour]["anomalias"] += 1

        evolution = []
        for offset in range(13, -1, -1):
            day = today - timedelta(days=offset)
            day_t, day_a = in_range(txns, day, day), in_range(anomalies, day, day)
            evolution.append({
                "fecha": day.isoformat(),
                "transacciones": sum(1 for x in day_t if x.get("aceptada")),
                "anomalias": len(day_a),
                "rechazadas": sum(1 for x in day_t if not x.get("aceptada")),
            })

        payments = defaultdict(lambda: {"cantidad": 0, "valor": 0.0})
        for x in month_t:
            payments[x.get("metodo_pago")]["cantidad"] += 1
            payments[x.get("metodo_pago")]["valor"] += x.get("valor") or 0

        def trend(current: dict, previous: dict) -> dict:
            def delta(key):
                base = previous[key]
                return {"actual": current[key], "anterior": base,
                        "cambio_pct": round(100 * (current[key] - base) / base, 1) if base else None}
            return {"transacciones": delta("total_transacciones"), "anomalias": delta("total_anomalias")}

        yesterday = today - timedelta(days=1)
        trends = {
            "hoy_vs_ayer": trend(periods["hoy"], period(yesterday, yesterday)),
            "semana_vs_anterior": trend(periods["semana"], period(week_start - timedelta(days=7), week_start - timedelta(days=1))),
        }

        return {
            "generado": now.isoformat(timespec="seconds"),
            "config": self.config.public_dict(),
            "periodos": periods,
            "anomalias_por_nivel": {lv: sum(1 for a in month_a if a["nivel"] == lv) for lv in LEVELS},
            "anomalias_por_tipo": dict(Counter(a["tipo"] for a in month_a)),
            "metodos_pago": sorted(({"metodo": k, **v} for k, v in payments.items()), key=lambda r: -r["cantidad"]),
            "por_hora": by_hour,
            "horas_pico": [h["hora"] for h in sorted(by_hour, key=lambda h: (-h["anomalias"], -h["transacciones"])) if h["anomalias"] or h["transacciones"]][:3],
            "evolucion": evolution,
            "tendencias": trends,
            "usuarios_recurrentes": recurrent,
            "casos_recurrentes": [{"caso": k, "cantidad": v} for k, v in cases.most_common(8)],
            "multiples_transacciones": [
                {"usuario": a["usuario_email"], "cantidad": a["cantidad_transacciones"], "tipo": a["tipo"], "fecha": a["fecha_txn"]}
                for a in sorted((a for a in month_a if a["tipo"] == POSSIBLE_FRAUD), key=lambda a: -a["cantidad_transacciones"])[:8]
            ],
            "usuarios_registrados": self.repo.count_users(),
        }
