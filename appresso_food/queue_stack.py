"""Pila y cola de pedidos, tal como se plantea para el escenario 'Restaurante':
Cola -> pedidos pendientes (FIFO), Pila -> deshacer última modificación (LIFO).
"""

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, List, Optional


@dataclass
class UndoAction:
    kind: str  # "crear_pedido" | "cambiar_estado"
    order_id: int
    payload: Any = None


class PendingOrdersQueue:
    """Cola FIFO: el primer pedido que entra es el primero que se atiende."""

    def __init__(self):
        self._queue: Deque[int] = deque()

    def enqueue(self, order_id: int) -> None:
        self._queue.append(order_id)

    def dequeue(self) -> Optional[int]:
        return self._queue.popleft() if self._queue else None

    def remove(self, order_id: int) -> None:
        if order_id in self._queue:
            self._queue.remove(order_id)

    def peek(self) -> Optional[int]:
        return self._queue[0] if self._queue else None

    def as_list(self) -> List[int]:
        return list(self._queue)

    def __len__(self) -> int:
        return len(self._queue)


class UndoStack:
    """Pila LIFO: guarda las últimas acciones para poder deshacerlas en orden inverso."""

    def __init__(self, max_size: int = 20):
        self._stack: List[UndoAction] = []
        self._max_size = max_size

    def push(self, action: UndoAction) -> None:
        self._stack.append(action)
        if len(self._stack) > self._max_size:
            self._stack.pop(0)

    def pop(self) -> Optional[UndoAction]:
        return self._stack.pop() if self._stack else None

    def peek(self) -> Optional[UndoAction]:
        return self._stack[-1] if self._stack else None

    def as_list(self) -> List[UndoAction]:
        return list(reversed(self._stack))

    def __len__(self) -> int:
        return len(self._stack)
