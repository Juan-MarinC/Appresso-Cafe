"""Heap de prioridad para decidir qué domicilio se despacha primero.

La prioridad es la distancia calculada por el grafo (appresso_food.graph):
entre más cerca esté el barrio, antes debe salir el domicilio. Ante un
empate en distancia, gana el pedido que llegó primero (FIFO), igual que en
un heap real: la raíz siempre es el elemento de mayor prioridad sin importar
el orden de ingreso.
"""

import heapq
import itertools
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class DispatchEntry:
    order_id: int
    client: str
    neighborhood: str
    distance_km: float
    eta_minutes: float


class DispatchHeap:
    def __init__(self):
        self._heap = []
        self._counter = itertools.count()
        self._entries = {}

    def push(self, order_id: int, client: str, neighborhood: str, distance_km: float, eta_minutes: float) -> None:
        sequence = next(self._counter)
        entry = DispatchEntry(order_id, client, neighborhood, distance_km, eta_minutes)
        self._entries[order_id] = entry
        heapq.heappush(self._heap, (distance_km, sequence, order_id))

    def pop_next(self) -> Optional[DispatchEntry]:
        """Extrae el domicilio de mayor prioridad (menor distancia)."""
        while self._heap:
            distance_km, _, order_id = heapq.heappop(self._heap)
            entry = self._entries.pop(order_id, None)
            if entry is not None:
                return entry
        return None

    def remove(self, order_id: int) -> None:
        """Quita una entrada (por ejemplo al deshacer un pedido).

        También purga la tupla del heap físico: si no lo hiciéramos, un
        `push` posterior con el mismo order_id (p. ej. al deshacer un
        'avanzar_pedido') dejaría dos tuplas apuntando a la misma entrada y
        `as_priority_list` la mostraría duplicada.
        """
        if self._entries.pop(order_id, None) is None:
            return
        self._heap = [entry for entry in self._heap if entry[2] != order_id]
        heapq.heapify(self._heap)

    def peek(self) -> Optional[DispatchEntry]:
        for distance_km, _, order_id in sorted(self._heap):
            if order_id in self._entries:
                return self._entries[order_id]
        return None

    def as_priority_list(self) -> List[DispatchEntry]:
        """Devuelve las entradas ordenadas por prioridad sin vaciar el heap."""
        ordered = sorted(self._heap)
        return [self._entries[order_id] for _, _, order_id in ordered if order_id in self._entries]

    def __len__(self) -> int:
        return len(self._entries)
