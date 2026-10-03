"""Modelos de dominio: productos, ingredientes, pedidos y barrios."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

CHANNEL_LOCAL = "local"
CHANNEL_DOMICILIO = "domicilio"

STATUS_SOLICITADO = "Solicitado"
STATUS_EN_PROCESO = "En Proceso"
STATUS_ENTREGADO = "Entregado"


@dataclass
class Product:
    id: int
    name: str
    category: str
    price: float


@dataclass
class Ingredient:
    id: int
    name: str
    stock_qty: float
    unit: str


@dataclass
class Neighborhood:
    id: int
    name: str


@dataclass
class OrderItem:
    product_id: int
    product_name: str
    quantity: int
    unit_price: float

    @property
    def subtotal(self) -> float:
        return self.quantity * self.unit_price


@dataclass
class Order:
    order_id: int
    client: str
    channel: str
    items: List[OrderItem] = field(default_factory=list)
    status: str = STATUS_SOLICITADO
    neighborhood: Optional[str] = None
    served_by: Optional[str] = None
    distance_km: Optional[float] = None
    eta_minutes: Optional[float] = None
    route: Optional[List[str]] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def total(self) -> float:
        return sum(item.subtotal for item in self.items)

    @property
    def total_quantity(self) -> int:
        return sum(item.quantity for item in self.items)
