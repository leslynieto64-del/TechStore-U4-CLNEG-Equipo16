"""Application Service de pedidos.

Coordina los casos de uso: busca el pedido en el repositorio en memoria y
llama al método de negocio de ``Order``. No contiene reglas de negocio:
esas viven en ``app.domain`` y ``app.specifications``.

Es independiente de FastAPI, así que se podría reutilizar desde una
interfaz de consola, una interfaz gráfica o un proceso por lotes.
"""
from __future__ import annotations

import threading

from app.domain import Order


class OrderNotFound(Exception):
    """El identificador no corresponde a ningún pedido (HTTP 404).

    No hereda de DomainException: no es una regla de negocio violada, sino
    un recurso que no existe en el repositorio.
    """

    def __init__(self, order_id: str) -> None:
        super().__init__(f"No existe el pedido {order_id}.")
        self.order_id = order_id


class OrderService:
    """Casos de uso sobre pedidos guardados en un diccionario en memoria."""

    def __init__(self, orders: dict[str, Order]) -> None:
        self._orders = orders
        # El servidor atiende peticiones en varios hilos; el candado evita que
        # dos peticiones simultáneas validen y cambien el mismo pedido a la vez.
        self._lock = threading.Lock()

    def list_orders(self) -> list[Order]:
        return list(self._orders.values())

    def get(self, order_id: str) -> Order:
        order = self._orders.get(order_id)
        if order is None:
            raise OrderNotFound(order_id)
        return order

    def confirm(self, order_id: str) -> Order:
        with self._lock:
            order = self.get(order_id)
            order.confirm()
            return order

    def ship(self, order_id: str, tracking_number: str) -> Order:
        with self._lock:
            order = self.get(order_id)
            order.ship(tracking_number)
            return order

    def cancel(self, order_id: str, reason: str) -> Order:
        with self._lock:
            order = self.get(order_id)
            order.cancel(reason)
            return order

    def deliver(self, order_id: str) -> Order:
        with self._lock:
            order = self.get(order_id)
            order.deliver()
            return order

    def return_order(self, order_id: str) -> Order:
        with self._lock:
            order = self.get(order_id)
            order.return_order()
            return order
