"""Pruebas del Specification Pattern y de la política de descuentos."""
from decimal import Decimal

import pytest

from app.domain import Money
from app.specifications import (
    DISCOUNT_ELIGIBLE_SPEC,
    HIGH_AMOUNT_DISCOUNT_SPEC,
    VIP_DISCOUNT_SPEC,
    ActivePromotionSpec,
    AndSpec,
    MinimumAmountSpec,
    MinimumUnitsSpec,
    NotSpec,
    OrSpec,
    Specification,
    VIPCustomerSpec,
    discount_amount,
    discount_rate,
    total_with_discount,
)
from helpers import make_order, snapshot


class Siempre(Specification):
    def __init__(self, valor: bool):
        self.valor = valor

    def is_satisfied_by(self, order):
        return self.valor


VERDADERO, FALSO = Siempre(True), Siempre(False)


# ===========================================================================
# Specifications individuales
# ===========================================================================
@pytest.mark.parametrize(
    "precio, esperado", [("499.99", False), ("500.00", False), ("500.01", True)]
)
def test_minimum_amount_es_estricto(precio, esperado):
    order = make_order(lines=[("SKU", 1, precio)])
    assert MinimumAmountSpec(Decimal("500")).is_satisfied_by(order) is esperado


def test_minimum_amount_no_acepta_float():
    with pytest.raises(TypeError):
        MinimumAmountSpec(500.0)


@pytest.mark.parametrize("vip", [True, False])
def test_vip_customer_spec(vip):
    assert VIPCustomerSpec().is_satisfied_by(make_order(vip=vip)) is vip


@pytest.mark.parametrize("unidades, esperado", [(3, False), (4, True), (5, True)])
def test_minimum_units_cuenta_unidades(unidades, esperado):
    order = make_order(lines=[("SKU", unidades, "10")])
    assert MinimumUnitsSpec(4).is_satisfied_by(order) is esperado


def test_minimum_units_no_cuenta_renglones():
    # 1 renglón con 4 unidades cumple; 3 renglones con 1 unidad cada uno no.
    assert MinimumUnitsSpec(4).is_satisfied_by(make_order(lines=[("A", 4, "1")]))
    tres = make_order(lines=[("A", 1, "1"), ("B", 1, "1"), ("C", 1, "1")])
    assert not MinimumUnitsSpec(4).is_satisfied_by(tres)


@pytest.mark.parametrize("promo", [True, False])
def test_active_promotion_spec(promo):
    assert ActivePromotionSpec().is_satisfied_by(make_order(promo=promo)) is promo


# ===========================================================================
# Composición AND, OR, NOT
# ===========================================================================
@pytest.mark.parametrize(
    "a, b, y, o",
    [
        (VERDADERO, VERDADERO, True, True),
        (VERDADERO, FALSO, False, True),
        (FALSO, VERDADERO, False, True),
        (FALSO, FALSO, False, False),
    ],
)
def test_tablas_de_verdad_and_or(a, b, y, o):
    order = make_order()
    assert (a & b).is_satisfied_by(order) is y
    assert (a | b).is_satisfied_by(order) is o


def test_not_invierte_el_resultado():
    order = make_order()
    assert (~VERDADERO).is_satisfied_by(order) is False
    assert (~FALSO).is_satisfied_by(order) is True


def test_operadores_crean_objetos_de_composicion():
    assert isinstance(VERDADERO & FALSO, AndSpec)
    assert isinstance(VERDADERO | FALSO, OrSpec)
    assert isinstance(~VERDADERO, NotSpec)


def test_base_specification_debe_implementarse():
    with pytest.raises(NotImplementedError):
        Specification().is_satisfied_by(make_order())


def test_reglas_compuestas_usan_composicion_real():
    assert isinstance(VIP_DISCOUNT_SPEC, AndSpec)
    assert isinstance(HIGH_AMOUNT_DISCOUNT_SPEC, AndSpec)
    assert isinstance(HIGH_AMOUNT_DISCOUNT_SPEC.right, NotSpec)
    assert isinstance(DISCOUNT_ELIGIBLE_SPEC, OrSpec)


def test_evaluar_specification_no_modifica_el_pedido(orders):
    order = orders["O001"]
    antes = snapshot(order)
    for spec in (VIP_DISCOUNT_SPEC, HIGH_AMOUNT_DISCOUNT_SPEC, DISCOUNT_ELIGIBLE_SPEC):
        spec.is_satisfied_by(order)
    discount_rate(order)
    discount_amount(order)
    total_with_discount(order)
    assert snapshot(order) == antes
    assert order.total.amount == Decimal("2100.00")  # el total original no cambia


# ===========================================================================
# Reglas del laboratorio con los pedidos del CSV
# ===========================================================================
@pytest.mark.parametrize(
    "pedido, tasa",
    [
        ("O001", "0.10"),  # VIP, 2100 > 500, 4 unidades, sin promoción
        ("O002", "0.00"),  # no VIP y total < 5000
        ("O005", "0.00"),  # promoción activa bloquea
        ("O006", "0.05"),  # 18000 > 5000, sin promoción
        ("O010", "0.00"),  # total exactamente 500
        ("O011", "0.00"),  # VIP con solo 3 unidades
    ],
)
def test_descuento_de_pedidos_csv(orders, pedido, tasa):
    assert discount_rate(orders[pedido]) == Decimal(tasa)


def test_importe_y_total_con_descuento_o001(orders):
    assert discount_amount(orders["O001"]) == Money(Decimal("210.00"))
    assert total_with_discount(orders["O001"]) == Money(Decimal("1890.00"))


def test_importe_y_total_con_descuento_o006(orders):
    assert discount_amount(orders["O006"]) == Money(Decimal("900.00"))
    assert total_with_discount(orders["O006"]) == Money(Decimal("17100.00"))


def test_sin_descuento_el_total_no_cambia(orders):
    assert discount_amount(orders["O002"]).amount == Decimal("0")
    assert total_with_discount(orders["O002"]) == orders["O002"].total


# ===========================================================================
# Fronteras y prioridad
# ===========================================================================
def test_vip_con_4_unidades_y_total_exactamente_500_no_recibe_descuento():
    # Aísla el umbral estricto (O010 además no es VIP ni tiene 4 unidades).
    order = make_order(vip=True, lines=[("SKU", 4, "125.00")])
    assert order.total.amount == Decimal("500.00") and order.units == 4
    assert discount_rate(order) == Decimal("0.00")


def test_vip_con_4_unidades_y_500_01_recibe_10():
    order = make_order(vip=True, lines=[("A", 3, "125.00"), ("B", 1, "125.01")])
    assert order.total.amount == Decimal("500.01")
    assert discount_rate(order) == Decimal("0.10")


def test_vip_con_3_unidades_no_recibe_10():
    order = make_order(vip=True, lines=[("A", 3, "400.00")])
    assert discount_rate(order) == Decimal("0.00")


def test_no_vip_con_total_exactamente_5000_no_recibe_5():
    order = make_order(lines=[("A", 1, "5000.00")])
    assert discount_rate(order) == Decimal("0.00")


def test_no_vip_con_5000_01_recibe_5_aunque_tenga_una_unidad():
    order = make_order(lines=[("A", 1, "5000.01")])
    assert discount_rate(order) == Decimal("0.05")


def test_vip_sin_4_unidades_pero_mas_de_5000_recibe_5():
    order = make_order(vip=True, lines=[("A", 1, "18000.00")])
    assert discount_rate(order) == Decimal("0.05")


def test_prioridad_10_cuando_se_cumplen_ambas_reglas():
    order = make_order(vip=True, lines=[("A", 4, "2000.00")])  # 8000 MXN
    assert VIP_DISCOUNT_SPEC.is_satisfied_by(order)
    assert HIGH_AMOUNT_DISCOUNT_SPEC.is_satisfied_by(order)
    assert discount_rate(order) == Decimal("0.10")


@pytest.mark.parametrize("vip, unidades, precio", [(True, 4, "2000.00"), (False, 1, "9000.00")])
def test_promocion_activa_bloquea_ambos_descuentos(vip, unidades, precio):
    order = make_order(vip=vip, promo=True, lines=[("A", unidades, precio)])
    assert not DISCOUNT_ELIGIBLE_SPEC.is_satisfied_by(order)
    assert discount_rate(order) == Decimal("0.00")


def test_descuento_redondea_a_centavos():
    order = make_order(vip=True, lines=[("A", 4, "138.8875")])  # total 555.55
    assert order.total.amount == Decimal("555.5500")
    assert discount_amount(order).amount == Decimal("55.56")  # 55.555 → 55.56
    assert total_with_discount(order).amount == Decimal("499.99")
