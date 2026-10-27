"""Specification Pattern y política de descuentos de TechStore.

Una Specification responde una pregunta de negocio (``is_satisfied_by``) con
True o False y NUNCA modifica el pedido. Las reglas se combinan con:

* ``a & b``  → AndSpec (se cumplen ambas)
* ``a | b``  → OrSpec  (se cumple al menos una)
* ``~a``     → NotSpec (se niega la regla)

Reglas del laboratorio (README.txt del paquete y práctica guiada, sección 8):

* 10 %: cliente VIP, total > 500 MXN, al menos 4 unidades y sin promoción.
* 5 %:  total > 5000 MXN y sin promoción.
* Si se cumplen ambas, se aplica 10 % (prioridad).
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.domain import Money, Order


# ---------------------------------------------------------------------------
# Base y composición
# ---------------------------------------------------------------------------
class Specification:
    """Regla de negocio evaluable y combinable."""

    def is_satisfied_by(self, order: Order) -> bool:
        raise NotImplementedError

    def __and__(self, other: Specification) -> AndSpec:
        return AndSpec(self, other)

    def __or__(self, other: Specification) -> OrSpec:
        return OrSpec(self, other)

    def __invert__(self) -> NotSpec:
        return NotSpec(self)


class AndSpec(Specification):
    def __init__(self, left: Specification, right: Specification) -> None:
        self.left, self.right = left, right

    def is_satisfied_by(self, order: Order) -> bool:
        return self.left.is_satisfied_by(order) and self.right.is_satisfied_by(order)

    def __repr__(self) -> str:
        return f"({self.left!r} & {self.right!r})"


class OrSpec(Specification):
    def __init__(self, left: Specification, right: Specification) -> None:
        self.left, self.right = left, right

    def is_satisfied_by(self, order: Order) -> bool:
        return self.left.is_satisfied_by(order) or self.right.is_satisfied_by(order)

    def __repr__(self) -> str:
        return f"({self.left!r} | {self.right!r})"


class NotSpec(Specification):
    def __init__(self, spec: Specification) -> None:
        self.spec = spec

    def is_satisfied_by(self, order: Order) -> bool:
        return not self.spec.is_satisfied_by(order)

    def __repr__(self) -> str:
        return f"~{self.spec!r}"


# ---------------------------------------------------------------------------
# Specifications concretas
# ---------------------------------------------------------------------------
class MinimumAmountSpec(Specification):
    """El total del pedido es ESTRICTAMENTE mayor que el mínimo (usa >, no >=)."""

    def __init__(self, minimum: Decimal) -> None:
        if isinstance(minimum, bool) or not isinstance(minimum, (Decimal, int)):
            raise TypeError("El mínimo debe ser Decimal, por ejemplo Decimal('500').")
        self.minimum = Decimal(minimum)

    def is_satisfied_by(self, order: Order) -> bool:
        return order.total.amount > self.minimum

    def __repr__(self) -> str:
        return f"MinimumAmountSpec({self.minimum})"


class VIPCustomerSpec(Specification):
    """El cliente del pedido es VIP."""

    def is_satisfied_by(self, order: Order) -> bool:
        return order.customer.is_vip

    def __repr__(self) -> str:
        return "VIPCustomerSpec()"


class MinimumUnitsSpec(Specification):
    """El pedido tiene AL MENOS ``minimum`` unidades (suma de cantidades, >=)."""

    def __init__(self, minimum: int) -> None:
        if isinstance(minimum, bool) or not isinstance(minimum, int):
            raise TypeError("El mínimo de unidades debe ser un entero.")
        self.minimum = minimum

    def is_satisfied_by(self, order: Order) -> bool:
        return order.units >= self.minimum

    def __repr__(self) -> str:
        return f"MinimumUnitsSpec({self.minimum})"


class ActivePromotionSpec(Specification):
    """El pedido tiene una promoción activa (se usa negada: ~ActivePromotionSpec())."""

    def is_satisfied_by(self, order: Order) -> bool:
        return order.has_promotion

    def __repr__(self) -> str:
        return "ActivePromotionSpec()"


# ---------------------------------------------------------------------------
# Reglas compuestas del laboratorio
# ---------------------------------------------------------------------------
VIP_DISCOUNT_RATE = Decimal("0.10")
HIGH_AMOUNT_DISCOUNT_RATE = Decimal("0.05")
NO_DISCOUNT_RATE = Decimal("0.00")

# Regla del 10 %: AND de cuatro condiciones, con NOT sobre la promoción.
VIP_DISCOUNT_SPEC = (
    MinimumAmountSpec(Decimal("500"))
    & VIPCustomerSpec()
    & MinimumUnitsSpec(4)
    & ~ActivePromotionSpec()
)

# Regla del 5 %: total > 5000 y sin promoción (no exige VIP ni 4 unidades).
HIGH_AMOUNT_DISCOUNT_SPEC = MinimumAmountSpec(Decimal("5000")) & ~ActivePromotionSpec()

# Elegibilidad general: basta con cumplir una de las dos reglas (OR).
DISCOUNT_ELIGIBLE_SPEC = VIP_DISCOUNT_SPEC | HIGH_AMOUNT_DISCOUNT_SPEC


# ---------------------------------------------------------------------------
# Política de descuento (componente que decide el porcentaje)
# ---------------------------------------------------------------------------
def discount_rate(order: Order) -> Decimal:
    """Porcentaje de descuento que corresponde al pedido.

    1. Si no cumple la regla OR (ninguna de las dos), 0 %.
    2. Si cumple la regla VIP, 10 % (tiene prioridad aunque también cumpla 5 %).
    3. En otro caso cumple solo la regla alternativa: 5 %.
    """
    if not DISCOUNT_ELIGIBLE_SPEC.is_satisfied_by(order):
        return NO_DISCOUNT_RATE
    if VIP_DISCOUNT_SPEC.is_satisfied_by(order):
        return VIP_DISCOUNT_RATE
    return HIGH_AMOUNT_DISCOUNT_RATE


def discount_amount(order: Order) -> Money:
    """Importe del descuento = total × porcentaje, redondeado a centavos (ROUND_HALF_UP)."""
    total = order.total
    amount = (total.amount * discount_rate(order)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return Money(amount, total.currency)


def total_with_discount(order: Order) -> Money:
    """Total a pagar = total original − descuento. No modifica ``order.total``."""
    total = order.total
    return Money(total.amount - discount_amount(order).amount, total.currency)
