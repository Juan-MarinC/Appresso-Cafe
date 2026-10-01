"""Ventana deslizante por usuario (PDF, págs. 29-34 y 37-41).

Es una ventana DESLIZANTE de verdad, no un contador que se reinicia cada N
segundos: cada usuario tiene su propia lista ordenada de transacciones y, con
cada transacción nueva,

    1. se agrega a la ventana del usuario (en orden cronológico),
    2. se eliminan las que quedaron fuera de los N segundos (SALEN),
    3. se cuenta lo que queda y se compara con el límite.

La ventana se mide con la fecha de la transacción (`fecha_txn`), no con la hora
de llegada, así los casos de prueba son reproducibles. Intervalo vigente:

    (último - N, último]      -> una transacción exactamente N segundos más antigua ya salió

La ventana ACTIVA solo guarda lo vigente. El historial completo vive en MongoDB
y en los logs; nada de lo que sale de aquí se pierde.
"""

import bisect
import itertools
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional


@dataclass(frozen=True)
class WindowEntry:
    ts: datetime
    txn_id: str
    valor: float
    seq: int = 0


@dataclass
class AddResult:
    user: str
    count: int
    entered: WindowEntry
    evicted: List[WindowEntry]  # las que SALEN por esta transacción (nunca incluye a la propia)
    entries: List[WindowEntry]  # ventana activa del usuario tras entrar y salir
    members: List[WindowEntry]  # las transacciones que forman la ventana contada (incluye a la nueva)
    out_of_order: bool = False  # llegó con una fecha anterior a la última ya recibida del usuario
    in_active_window: bool = True  # False si ya estaba fuera de la ventana vigente al llegar

    @property
    def late(self) -> bool:  # nombre anterior
        return self.out_of_order


def densest_window(entries: List[WindowEntry], target: WindowEntry, window: timedelta) -> List[WindowEntry]:
    """Mayor grupo de transacciones dentro de un intervalo de MENOS de `window` que contenga a `target`.

    No basta mirar hacia atrás desde la fecha de `target`: si llegan 10:00:10, 10:00:01 y 10:00:02 son
    3 transacciones en 9 s aunque la última en llegar sea la de 10:00:02.
    """
    ordered = sorted(entries, key=lambda e: (e.ts, e.seq))
    k = ordered.index(target)
    best: List[WindowEntry] = []
    j = 0
    for i in range(k + 1):
        j = max(j, i)
        while j + 1 < len(ordered) and ordered[j + 1].ts - ordered[i].ts < window:
            j += 1
        if j >= k and j - i + 1 > len(best):
            best = ordered[i : j + 1]
    return best


class SlidingWindowManager:
    def __init__(self, window_seconds: float):
        self.window = timedelta(seconds=window_seconds)
        self._windows: Dict[str, List[WindowEntry]] = {}
        self._seq = itertools.count()
        self._lock = threading.RLock()

    @property
    def window_seconds(self) -> float:
        return self.window.total_seconds()

    def add(self, user: str, ts: datetime, txn_id: str, valor: float) -> AddResult:
        with self._lock:
            entries = self._windows.setdefault(user, [])
            entry = WindowEntry(ts=ts, txn_id=txn_id, valor=valor, seq=next(self._seq))
            out_of_order = bool(entries) and ts < entries[-1].ts

            bisect.insort(entries, entry, key=lambda e: (e.ts, e.seq))  # 1. entra (orden cronológico)

            cutoff = entries[-1].ts - self.window
            gone = [e for e in entries if e.ts <= cutoff]  # 2. salen
            if gone:
                self._windows[user] = entries = [e for e in entries if e.ts > cutoff]
            in_active = entry not in gone

            # 3. cuenta: el grupo más denso de < N segundos que contiene a la nueva
            members = densest_window(entries + ([] if in_active else [entry]), entry, self.window)
            return AddResult(
                user=user, count=len(members), entered=entry, evicted=[e for e in gone if e is not entry],
                entries=list(entries), members=members, out_of_order=out_of_order, in_active_window=in_active,
            )

    def remove(self, user: str, txn_id: str) -> None:
        """Deshace un `add` (p. ej. si la persistencia falló)."""
        with self._lock:
            entries = self._windows.get(user)
            if entries:
                self._windows[user] = [e for e in entries if e.txn_id != txn_id]

    def snapshot(self, user: Optional[str] = None) -> List[dict]:
        """Estado actual de la ventana activa (uno o todos los usuarios)."""
        with self._lock:
            users = [user] if user else sorted(self._windows)
            out = []
            for u in users:
                entries = self._windows.get(u, [])
                if not entries:
                    continue
                anchor = entries[-1].ts
                out.append(
                    {
                        "usuario": u,
                        "ancla": anchor.isoformat(timespec="milliseconds"),
                        "inicio_ventana": (anchor - self.window).isoformat(timespec="milliseconds"),
                        "cantidad": len(entries),
                        "entradas": [
                            {
                                "idTxn": e.txn_id,
                                "fecha": e.ts.isoformat(timespec="milliseconds"),
                                "valor": e.valor,
                                "edad_segundos": round((anchor - e.ts).total_seconds(), 3),
                                "sale_en_segundos": round(self.window_seconds - (anchor - e.ts).total_seconds(), 3),
                            }
                            for e in entries
                        ],
                    }
                )
            return out

    def clear(self) -> None:
        with self._lock:
            self._windows.clear()

    def load(self, user: str, entries: List[WindowEntry]) -> None:
        """Reconstruye la ventana de un usuario (al reiniciar el servidor)."""
        with self._lock:
            self._windows[user] = sorted(entries, key=lambda e: (e.ts, e.seq))

    def next_seq(self) -> int:
        return next(self._seq)
