"""Funciones auxiliares para construir pedidos de prueba."""
from decimal import Decimal

from app.domain import Customer, Money, Order, OrderItem


def make_order(
    *,
    vip: bool = False,
    active: bool = True,
    promo: bool = False,
    lines: list[tuple[str, int, str]] | None = None,
    order_id: str = "T001",
) -> Order:
    """Construye un pedido de prueba: lines = [(sku, cantidad, "precio")]."""
    order = Order(customer=Customer("CX", vip, active), id=order_id, has_promotion=promo)
    for sku, quantity, price in lines or []:
        order.add_item(OrderItem(sku, quantity, Money(Decimal(price))))
    return order


def order_in_state(state: str) -> Order:
    """Lleva un pedido válido al estado indicado usando solo transiciones válidas."""
    order = make_order(lines=[("SKU001", 1, "600.00")])
    path = {
        "DRAFT": [],
        "CONFIRMED": ["confirm"],
        "SHIPPED": ["confirm", "ship"],
        "DELIVERED": ["confirm", "ship", "deliver"],
        "RETURNED": ["confirm", "ship", "return_order"],
        "CANCELLED": ["confirm", "cancel"],
    }[state]
    for step in path:
        if step == "ship":
            order.ship("GUIA-1")
        elif step == "cancel":
            order.cancel("Motivo de prueba")
        else:
            getattr(order, step)()
    return order


def snapshot(order: Order):
    """Fotografía del pedido para comprobar que una operación fallida no cambió nada."""
    return (order.status, order.items, order.events, order.units, order.total,
            order.tracking_number, order.cancellation_reason)
