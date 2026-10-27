"""Pruebas unitarias del dominio (app/domain.py).

Cada prueba sigue tres pasos: preparar (Arrange), ejecutar (Act) y comprobar (Assert).
"""
from dataclasses import FrozenInstanceError
from datetime import timezone
from decimal import Decimal

import pytest

from app.domain import (
    MAX_UNITS_PER_ORDER,
    Customer,
    DomainEvent,
    DomainException,
    InvalidOrderData,
    InvalidOrderTransition,
    Money,
    Order,
    OrderItem,
    OrderItemLimitExceeded,
    OrderStatus,
)
from helpers import make_order, order_in_state, snapshot


# ===========================================================================
# Excepciones de dominio
# ===========================================================================
@pytest.mark.parametrize(
    "exc_type", [InvalidOrderData, InvalidOrderTransition, OrderItemLimitExceeded]
)
def test_excepciones_heredan_de_domain_exception(exc_type):
    assert issubclass(exc_type, DomainException)
    # No son errores técnicos genéricos como ValueError o TypeError.
    assert not issubclass(exc_type, (ValueError, TypeError))


# ===========================================================================
# Money (Value Object)
# ===========================================================================
def test_money_se_crea_con_decimal_y_mxn_por_omision():
    money = Money(Decimal("600.00"))
    assert money.amount == Decimal("600.00")
    assert money.currency == "MXN"


def test_money_acepta_cero():
    assert Money(Decimal("0")).amount == Decimal("0")


def test_money_convierte_enteros_a_decimal():
    money = Money(100)
    assert isinstance(money.amount, Decimal)
    assert money.amount == Decimal("100")


def test_money_negativo_se_rechaza():
    with pytest.raises(InvalidOrderData, match="negativo"):
        Money(Decimal("-1"))


@pytest.mark.parametrize("valor", ["NaN", "Infinity", "-Infinity", "sNaN"])
def test_money_no_finito_se_rechaza(valor):
    with pytest.raises(InvalidOrderData, match="finito"):
        Money(Decimal(valor))


@pytest.mark.parametrize("valor", [600.0, "600.00", None, True])
def test_money_rechaza_tipos_que_no_son_decimal(valor):
    with pytest.raises(InvalidOrderData):
        Money(valor)


@pytest.mark.parametrize("moneda", ["", "   ", None])
def test_money_requiere_moneda(moneda):
    with pytest.raises(InvalidOrderData, match="moneda"):
        Money(Decimal("1"), moneda)


def test_money_decimal_evita_error_de_float():
    # 0.1 + 0.2 con float da 0.30000000000000004; con Decimal es exacto.
    total = Money(Decimal("0.1")).add(Money(Decimal("0.2")))
    assert total.amount == Decimal("0.3")
    assert 0.1 + 0.2 != 0.3


def test_money_add_misma_moneda_devuelve_objeto_nuevo_sin_modificar_operandos():
    a = Money(Decimal("100"))
    b = Money(Decimal("50"))
    resultado = a.add(b)
    assert resultado == Money(Decimal("150"))
    assert resultado is not a and resultado is not b
    assert a.amount == Decimal("100") and b.amount == Decimal("50")


def test_money_add_monedas_distintas_se_rechaza():
    with pytest.raises(InvalidOrderData, match="monedas distintas"):
        Money(Decimal("10"), "MXN").add(Money(Decimal("10"), "USD"))


def test_money_add_rechaza_objetos_que_no_son_money():
    with pytest.raises(InvalidOrderData):
        Money(Decimal("10")).add(Decimal("5"))


def test_money_es_inmutable():
    money = Money(Decimal("10"))
    with pytest.raises(FrozenInstanceError):
        money.amount = Decimal("999")


def test_money_se_compara_por_valor():
    assert Money(Decimal("100"), "MXN") == Money(Decimal("100.00"), "MXN")
    assert Money(Decimal("100"), "MXN") != Money(Decimal("100"), "USD")


# ===========================================================================
# Customer
# ===========================================================================
def test_customer_compatible_con_cargador_posicional():
    customer = Customer("C001", True, False)
    assert (customer.id, customer.is_vip, customer.active) == ("C001", True, False)


def test_customer_valores_por_omision():
    customer = Customer("C999")
    assert customer.is_vip is False and customer.active is True


def test_customer_sin_id_se_rechaza():
    with pytest.raises(InvalidOrderData):
        Customer("  ")


def test_customer_es_inmutable():
    with pytest.raises(FrozenInstanceError):
        Customer("C001").active = False


def test_customer_mismo_id_es_el_mismo_cliente_aunque_cambien_sus_atributos():
    assert Customer("C001", True, True) == Customer("C001", False, False)


def test_customer_con_id_distinto_no_es_el_mismo_cliente():
    assert Customer("C001", True, True) != Customer("C002", True, True)


def test_customer_hash_coherente_con_la_igualdad():
    a = Customer("C001", True, True)
    b = Customer("C001", False, False)
    assert a == b and hash(a) == hash(b)
    assert len({a, b, Customer("C002")}) == 2


@pytest.mark.parametrize("valor", [1, 0, "1", "si", None])
def test_customer_is_vip_no_booleano_se_rechaza(valor):
    with pytest.raises(InvalidOrderData, match="is_vip"):
        Customer("C001", valor, True)


@pytest.mark.parametrize("valor", [1, 0, "1", "no", None])
def test_customer_active_no_booleano_se_rechaza(valor):
    with pytest.raises(InvalidOrderData, match="active"):
        Customer("C001", True, valor)


@pytest.mark.parametrize("identificador", ["", "   ", None, 1])
def test_customer_id_vacio_o_invalido_se_rechaza(identificador):
    with pytest.raises(InvalidOrderData, match="identificador"):
        Customer(identificador)


# ===========================================================================
# OrderItem (Value Object)
# ===========================================================================
def test_order_item_calcula_subtotal():
    item = OrderItem("SKU001", 2, Money(Decimal("600.00")))
    assert item.subtotal == Money(Decimal("1200.00"))
    assert item.subtotal.currency == "MXN"


@pytest.mark.parametrize("sku", ["", "   ", None])
def test_order_item_sku_vacio_se_rechaza(sku):
    with pytest.raises(InvalidOrderData, match="SKU"):
        OrderItem(sku, 1, Money(Decimal("10")))


@pytest.mark.parametrize("cantidad", [0, -1, -20])
def test_order_item_cantidad_cero_o_negativa_se_rechaza(cantidad):
    with pytest.raises(InvalidOrderData, match="mayor que cero"):
        OrderItem("SKU001", cantidad, Money(Decimal("10")))


@pytest.mark.parametrize("cantidad", [2.5, "2", True, None])
def test_order_item_cantidad_no_entera_se_rechaza(cantidad):
    with pytest.raises(InvalidOrderData, match="entero"):
        OrderItem("SKU001", cantidad, Money(Decimal("10")))


@pytest.mark.parametrize("precio", [Decimal("600.00"), 600, "600.00", None])
def test_order_item_precio_debe_ser_money(precio):
    with pytest.raises(InvalidOrderData, match="Money"):
        OrderItem("SKU001", 1, precio)


def test_order_item_es_inmutable():
    item = OrderItem("SKU001", 1, Money(Decimal("10")))
    with pytest.raises(FrozenInstanceError):
        item.quantity = 99


# ===========================================================================
# Order: construcción, unidades y total
# ===========================================================================
def test_order_inicia_en_draft_sin_articulos_ni_eventos():
    order = Order(customer=Customer("C1"), id="X1", has_promotion=False)
    assert order.status is OrderStatus.DRAFT
    assert order.items == () and order.events == ()


def test_order_estados_permitidos_tienen_nombres_exactos():
    assert [s.value for s in OrderStatus] == [
        "DRAFT", "CONFIRMED", "SHIPPED", "DELIVERED", "CANCELLED", "RETURNED"
    ]


def test_orders_no_comparten_listas_de_items_ni_eventos():
    a = make_order(order_id="A")
    b = make_order(order_id="B")
    a.add_item(OrderItem("SKU001", 1, Money(Decimal("1"))))
    a.confirm()
    assert b.items == () and b.events == ()


def test_order_no_permite_cambiar_estado_ni_colecciones_desde_fuera():
    order = make_order(lines=[("SKU001", 1, "10")])
    with pytest.raises(AttributeError):
        order.status = OrderStatus.SHIPPED
    with pytest.raises(AttributeError):
        order.items.append(OrderItem("SKU002", 1, Money(Decimal("1"))))
    with pytest.raises(AttributeError):
        order.events.append(DomainEvent("OrderConfirmed", order.id))
    assert order.status is OrderStatus.DRAFT and order.units == 1 and order.events == ()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"customer": "C001", "id": "X", "has_promotion": False},
        {"customer": Customer("C1"), "id": "", "has_promotion": False},
        {"customer": Customer("C1"), "id": "X", "has_promotion": "no"},
    ],
)
def test_order_constructor_valida_datos(kwargs):
    with pytest.raises(InvalidOrderData):
        Order(**kwargs)


def test_order_units_suma_cantidades_no_cuenta_renglones(orders):
    o001 = orders["O001"]
    assert len(o001.items) == 2  # dos renglones
    assert o001.units == 4  # cuatro unidades


def test_order_total_suma_subtotales_sin_descuento(orders):
    assert orders["O001"].total == Money(Decimal("2100.00"))
    assert orders["O001"].total.amount == Decimal("2100.00")


def test_order_vacio_tiene_total_cero_y_cero_unidades(orders):
    assert orders["O007"].units == 0
    assert orders["O007"].total.amount == Decimal("0")


def test_order_igualdad_por_identidad():
    a = Order(customer=Customer("C1"), id="X1")
    b = Order(customer=Customer("C2", True), id="X1")
    assert a == b  # misma identidad aunque sus datos difieran
    assert a != Order(customer=Customer("C1"), id="X2")


# ===========================================================================
# Order: add_item y límite de 20 unidades
# ===========================================================================
def test_add_item_permite_exactamente_20_unidades():
    order = make_order(lines=[("SKU003", 19, "120.00")])
    order.add_item(OrderItem("SKU003", 1, Money(Decimal("120.00"))))
    assert order.units == MAX_UNITS_PER_ORDER == 20


def test_add_item_rechaza_21_unidades_sin_modificar_items():
    order = make_order(lines=[("SKU003", 19, "120.00")])
    antes = snapshot(order)
    with pytest.raises(OrderItemLimitExceeded, match="21"):
        order.add_item(OrderItem("SKU003", 2, Money(Decimal("120.00"))))
    assert snapshot(order) == antes
    assert order.units == 19 and len(order.items) == 1


def test_add_item_rechaza_un_solo_renglon_de_21_unidades():
    order = make_order()
    with pytest.raises(OrderItemLimitExceeded):
        order.add_item(OrderItem("SKU003", 21, Money(Decimal("1"))))
    assert order.items == ()


def test_limite_es_por_unidades_no_por_renglones():
    # 20 renglones de 1 unidad = 20 unidades → permitido.
    order = make_order(lines=[(f"SKU{n:03}", 1, "1.00") for n in range(20)])
    assert len(order.items) == 20 and order.units == 20
    # 2 renglones de 10 unidades = 20 unidades; uno más se rechaza aunque haya pocos renglones.
    order2 = make_order(lines=[("A", 10, "1"), ("B", 10, "1")])
    with pytest.raises(OrderItemLimitExceeded):
        order2.add_item(OrderItem("C", 1, Money(Decimal("1"))))


def test_add_item_rechaza_moneda_distinta_de_mxn():
    order = make_order()
    with pytest.raises(InvalidOrderData, match="MXN"):
        order.add_item(OrderItem("SKU001", 1, Money(Decimal("10"), "USD")))
    assert order.items == ()


def test_add_item_rechaza_objetos_que_no_son_order_item():
    order = make_order()
    with pytest.raises(InvalidOrderData):
        order.add_item(("SKU001", 1, Money(Decimal("10"))))
    assert order.items == ()


@pytest.mark.parametrize(
    "estado", ["CONFIRMED", "SHIPPED", "DELIVERED", "CANCELLED", "RETURNED"]
)
def test_add_item_solo_en_draft(estado):
    order = order_in_state(estado)
    antes = snapshot(order)
    with pytest.raises(InvalidOrderTransition, match="DRAFT"):
        order.add_item(OrderItem("SKU002", 1, Money(Decimal("450.00"))))
    assert snapshot(order) == antes


# ===========================================================================
# Máquina de estados: confirm
# ===========================================================================
def test_confirm_valido_cambia_a_confirmed_y_registra_evento(orders):
    order = orders["O001"]
    order.confirm()
    assert order.status is OrderStatus.CONFIRMED
    assert [e.name for e in order.events] == ["OrderConfirmed"]
    assert order.events[0].order_id == "O001"


def test_confirm_pedido_vacio_se_rechaza_sin_cambios(orders):
    order = orders["O007"]
    antes = snapshot(order)
    with pytest.raises(InvalidOrderData, match="no tiene artículos"):
        order.confirm()
    assert snapshot(order) == antes and order.status is OrderStatus.DRAFT


def test_confirm_cliente_inactivo_se_rechaza_sin_cambios(orders):
    order = orders["O003"]
    antes = snapshot(order)
    with pytest.raises(InvalidOrderData, match="inactivo"):
        order.confirm()
    assert snapshot(order) == antes


def test_confirm_dos_veces_no_duplica_evento(orders):
    order = orders["O013"]
    order.confirm()
    with pytest.raises(InvalidOrderTransition, match="CONFIRMED"):
        order.confirm()
    assert order.status is OrderStatus.CONFIRMED
    assert [e.name for e in order.events] == ["OrderConfirmed"]


def test_confirm_con_20_unidades_exactas(orders):
    order = orders["O008"]
    assert order.units == 20
    order.confirm()
    assert order.status is OrderStatus.CONFIRMED


# ===========================================================================
# Máquina de estados: ship
# ===========================================================================
def test_ship_valido_guarda_guia_y_registra_evento():
    order = order_in_state("CONFIRMED")
    order.ship("  MX-123  ")
    assert order.status is OrderStatus.SHIPPED
    assert order.tracking_number == "MX-123"
    assert [e.name for e in order.events] == ["OrderConfirmed", "OrderShipped"]


@pytest.mark.parametrize("guia", ["", "   ", None])
def test_ship_sin_guia_se_rechaza_y_permanece_confirmed(guia):
    order = order_in_state("CONFIRMED")
    antes = snapshot(order)
    with pytest.raises(InvalidOrderData, match="guía"):
        order.ship(guia)
    assert snapshot(order) == antes
    assert order.status is OrderStatus.CONFIRMED
    assert "OrderShipped" not in [e.name for e in order.events]


def test_ship_desde_draft_es_transicion_invalida_aunque_tenga_guia():
    order = order_in_state("DRAFT")
    with pytest.raises(InvalidOrderTransition):
        order.ship("MX-1")
    assert order.status is OrderStatus.DRAFT and order.events == ()


# ===========================================================================
# Máquina de estados: cancel
# ===========================================================================
def test_cancel_valido_desde_confirmed():
    order = order_in_state("CONFIRMED")
    order.cancel("Cliente se arrepintió")
    assert order.status is OrderStatus.CANCELLED
    assert order.cancellation_reason == "Cliente se arrepintió"
    assert order.events[-1].name == "OrderCancelled"


@pytest.mark.parametrize("motivo", ["", "   ", None])
def test_cancel_sin_motivo_se_rechaza(motivo):
    order = order_in_state("CONFIRMED")
    antes = snapshot(order)
    with pytest.raises(InvalidOrderData, match="motivo"):
        order.cancel(motivo)
    assert snapshot(order) == antes


def test_cancel_desde_shipped_se_rechaza_sin_evento(orders):
    order = orders["O014"]
    order.confirm()
    order.ship("MX-014")
    antes = snapshot(order)
    with pytest.raises(InvalidOrderTransition, match="SHIPPED"):
        order.cancel("Ya no lo quiero")
    assert snapshot(order) == antes
    assert order.status is OrderStatus.SHIPPED
    assert "OrderCancelled" not in [e.name for e in order.events]


# ===========================================================================
# Máquina de estados: deliver y return_order
# ===========================================================================
def test_deliver_valido_desde_shipped(orders):
    order = orders["O016"]
    order.confirm()
    order.ship("MX-016")
    order.deliver()
    assert order.status is OrderStatus.DELIVERED
    assert [e.name for e in order.events] == [
        "OrderConfirmed", "OrderShipped", "OrderDelivered"
    ]


def test_return_order_valido_desde_shipped(orders):
    order = orders["O015"]
    order.confirm()
    order.ship("MX-015")
    order.return_order()
    assert order.status is OrderStatus.RETURNED
    assert [e.name for e in order.events] == [
        "OrderConfirmed", "OrderShipped", "OrderReturned"
    ]


# ===========================================================================
# Matriz completa de transiciones: solo 5 son válidas
# ===========================================================================
ALLOWED = {
    ("DRAFT", "confirm"): "CONFIRMED",
    ("CONFIRMED", "ship"): "SHIPPED",
    ("CONFIRMED", "cancel"): "CANCELLED",
    ("SHIPPED", "deliver"): "DELIVERED",
    ("SHIPPED", "return_order"): "RETURNED",
}
OPERATIONS = {
    "confirm": lambda o: o.confirm(),
    "ship": lambda o: o.ship("GUIA-OK"),
    "cancel": lambda o: o.cancel("Motivo válido"),
    "deliver": lambda o: o.deliver(),
    "return_order": lambda o: o.return_order(),
}
EVENT_OF = {
    "confirm": "OrderConfirmed",
    "ship": "OrderShipped",
    "cancel": "OrderCancelled",
    "deliver": "OrderDelivered",
    "return_order": "OrderReturned",
}


@pytest.mark.parametrize("estado", [s.value for s in OrderStatus])
@pytest.mark.parametrize("operacion", list(OPERATIONS))
def test_matriz_de_transiciones(estado, operacion):
    order = order_in_state(estado)
    antes = snapshot(order)
    eventos_antes = len(order.events)
    if (estado, operacion) in ALLOWED:
        OPERATIONS[operacion](order)
        assert order.status.value == ALLOWED[(estado, operacion)]
        assert len(order.events) == eventos_antes + 1
        assert order.events[-1].name == EVENT_OF[operacion]
    else:
        with pytest.raises(InvalidOrderTransition):
            OPERATIONS[operacion](order)
        assert snapshot(order) == antes  # sin cambio de estado ni eventos nuevos


# ===========================================================================
# Domain Events
# ===========================================================================
def test_se_generan_los_cinco_tipos_de_evento():
    nombres = set()
    for final in ("DELIVERED", "RETURNED", "CANCELLED"):
        nombres.update(e.name for e in order_in_state(final).events)
    assert nombres == {
        "OrderConfirmed", "OrderShipped", "OrderCancelled", "OrderDelivered", "OrderReturned"
    }


def test_domain_event_es_inmutable_y_usa_utc():
    order = order_in_state("CONFIRMED")
    evento = order.events[0]
    assert evento.occurred_at.tzinfo is not None
    assert evento.occurred_at.utcoffset() == timezone.utc.utcoffset(None)
    with pytest.raises(FrozenInstanceError):
        evento.name = "Otro"


def test_eventos_en_orden_cronologico():
    order = order_in_state("DELIVERED")
    fechas = [e.occurred_at for e in order.events]
    assert fechas == sorted(fechas)
    assert all(e.order_id == order.id for e in order.events)
