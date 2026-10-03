"""Estado operativo en memoria: el grafo de barrios, la cola de pedidos
pendientes (FIFO), el heap de despacho de domicilios y la pila de deshacer
(LIFO). Se reconstruye a partir de la base de datos cada vez que arranca la
aplicación, para que el negocio (SQLite) siga siendo la fuente de verdad.
"""

from dataclasses import dataclass
from typing import List, Optional

from appresso_food.nucleo import storage
from appresso_food.nucleo.dispatch import DispatchEntry, DispatchHeap
from appresso_food.nucleo.graph import RESTAURANT_NODE, DeliveryGraph, build_graph
from appresso_food.nucleo.models import (
    CHANNEL_DOMICILIO,
    STATUS_ENTREGADO,
    STATUS_SOLICITADO,
    Order,
    OrderItem,
)
from appresso_food.nucleo.queue_stack import PendingOrdersQueue, UndoAction, UndoStack

graph = DeliveryGraph()
pending_queue = PendingOrdersQueue()
dispatch_heap = DispatchHeap()
undo_stack = UndoStack()


@dataclass
class OrderResult:
    order: Order
    warnings: List[str]


class CoverageError(Exception):
    """El barrio solicitado no existe en el grafo de domicilios."""


def init_runtime() -> None:
    global graph
    neighborhoods = storage.get_neighborhood_names(include_restaurant=True)
    edges = storage.get_graph_edges()
    graph = build_graph(neighborhoods, edges)

    pending_queue._queue.clear()
    dispatch_heap._heap.clear()
    dispatch_heap._entries.clear()

    for order in storage.get_pending_orders():
        pending_queue.enqueue(order.order_id)
        if order.channel == CHANNEL_DOMICILIO and order.neighborhood and order.distance_km is not None:
            dispatch_heap.push(
                order.order_id, order.client, order.neighborhood, order.distance_km, order.eta_minutes or 0.0
            )


def place_order(client: str, channel: str, neighborhood: Optional[str], items: List[OrderItem], served_by: Optional[str]) -> OrderResult:
    route = None
    distance_km = None
    eta_minutes = None

    if channel == CHANNEL_DOMICILIO:
        if not neighborhood or not graph.has_node(neighborhood):
            raise CoverageError(f"'{neighborhood}' está fuera de la zona de cobertura del domicilio.")
        result = graph.shortest_path(RESTAURANT_NODE, neighborhood)
        if result is None:
            raise CoverageError(f"No hay ruta registrada hacia '{neighborhood}'.")
        route, distance_km = result
        eta_minutes = graph.eta_minutes(distance_km)

    order = Order(
        order_id=0,
        client=client,
        channel=channel,
        items=items,
        status=STATUS_SOLICITADO,
        neighborhood=neighborhood,
        served_by=served_by,
        distance_km=distance_km,
        eta_minutes=eta_minutes,
        route=route,
    )
    order.order_id = storage.create_order(order)

    warnings = storage.deduct_ingredients_for_items(items)

    pending_queue.enqueue(order.order_id)
    if channel == CHANNEL_DOMICILIO:
        dispatch_heap.push(order.order_id, client, neighborhood, distance_km, eta_minutes)

    undo_stack.push(UndoAction(kind="crear_pedido", order_id=order.order_id, payload=order))

    return OrderResult(order=order, warnings=warnings)


def advance_pending() -> Optional[Order]:
    """Atiende el siguiente pedido en la cola FIFO (mostrador/local)."""
    order_id = pending_queue.dequeue()
    if order_id is None:
        return None
    storage.update_order_status(order_id, STATUS_ENTREGADO)
    dispatch_heap.remove(order_id)
    undo_stack.push(UndoAction(kind="avanzar_pedido", order_id=order_id))
    return storage.get_order(order_id)


def dispatch_next_delivery() -> Optional[DispatchEntry]:
    """Despacha el domicilio de mayor prioridad (menor distancia) del heap."""
    entry = dispatch_heap.pop_next()
    if entry is None:
        return None
    storage.update_order_status(entry.order_id, STATUS_ENTREGADO)
    pending_queue.remove(entry.order_id)
    undo_stack.push(UndoAction(kind="despachar_domicilio", order_id=entry.order_id, payload=entry))
    return entry


def undo_last() -> Optional[str]:
    """Deshace la última acción registrada. Devuelve una descripción o None."""
    action = undo_stack.pop()
    if action is None:
        return None

    if action.kind == "crear_pedido":
        order: Order = action.payload
        storage.restore_ingredients_for_items(order.items)
        storage.delete_order(order.order_id)
        pending_queue.remove(order.order_id)
        dispatch_heap.remove(order.order_id)
        return f"Se deshizo la creación del pedido #{order.order_id} de {order.client}."

    if action.kind == "avanzar_pedido":
        storage.update_order_status(action.order_id, STATUS_SOLICITADO)
        pending_queue.enqueue(action.order_id)
        order = storage.get_order(action.order_id)
        if order and order.channel == CHANNEL_DOMICILIO and order.distance_km is not None:
            dispatch_heap.push(order.order_id, order.client, order.neighborhood, order.distance_km, order.eta_minutes or 0.0)
        return f"Se regresó el pedido #{action.order_id} a la cola de pendientes."

    if action.kind == "despachar_domicilio":
        entry: DispatchEntry = action.payload
        storage.update_order_status(entry.order_id, STATUS_SOLICITADO)
        pending_queue.enqueue(entry.order_id)
        dispatch_heap.push(entry.order_id, entry.client, entry.neighborhood, entry.distance_km, entry.eta_minutes)
        return f"Se regresó el domicilio #{entry.order_id} al heap de despacho."

    return None
