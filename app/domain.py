"""Núcleo de dominio de TechStore.

Contiene las piezas del modelo DDD de la Actividad 4:

* Excepciones de dominio (violaciones de reglas de negocio, no errores técnicos).
* Value Objects: ``Money`` y ``OrderItem`` (inmutables, se comparan por valor).
* ``Customer``: datos del cliente que el pedido necesita consultar; su
  identidad es su ``id``.
* ``OrderStatus``: los seis estados permitidos del pedido.
* ``DomainEvent``: hecho del negocio que ya ocurrió (inmutable, con fecha UTC).
* ``Order``: entidad y Aggregate Root; protege las invariantes del pedido y
  ejecuta la máquina de estados.

Este módulo no depende de FastAPI, de CSV ni de ninguna infraestructura:
se puede usar desde la API, desde un script o desde las pruebas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

DEFAULT_CURRENCY = "MXN"
MAX_UNITS_PER_ORDER = 20  # Límite de UNIDADES (suma de cantidades), no de renglones.

# Excepciones de dominio
class DomainException(Exception):
    """Base de todas las violaciones de reglas de negocio de TechStore."""


class InvalidOrderData(DomainException):
    """Datos inválidos o precondición de negocio no cumplida.

    Ejemplos: importe negativo, SKU vacío, pedido vacío, cliente inactivo,
    envío sin guía, cancelación sin motivo. La API la traduce a HTTP 422.
    """


class InvalidOrderTransition(DomainException):
    """La operación no es compatible con el estado actual del pedido.

    Ejemplos: confirmar dos veces, cancelar un pedido SHIPPED, agregar
    artículos a un pedido CONFIRMED. La API la traduce a HTTP 409.
    """


class OrderItemLimitExceeded(DomainException):
    """Agregar el artículo haría que el pedido superara 20 unidades (HTTP 422)."""

# Value Objects
@dataclass(frozen=True)
class Money:
    """Importe monetario inmutable. Usa ``Decimal`` y MXN por omisión."""

    amount: Decimal
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        amount = self.amount
        # bool es subclase de int en Python: True no es un importe válido.
        if isinstance(amount, bool) or not isinstance(amount, (Decimal, int)):
            raise InvalidOrderData(
                "El importe debe ser Decimal (por ejemplo Decimal('600.00')), "
                f"no {type(amount).__name__}; float introduce errores de redondeo."
            )
        if isinstance(amount, int):
            amount = Decimal(amount)
            # frozen=True impide la asignación normal; solo se normaliza aquí,
            # durante la construcción.
            object.__setattr__(self, "amount", amount)
        if not amount.is_finite():
            raise InvalidOrderData(f"El importe debe ser un número finito, no {amount}.")
        if amount < 0:
            raise InvalidOrderData(f"El importe no puede ser negativo: {amount}.")
        if not isinstance(self.currency, str) or not self.currency.strip():
            raise InvalidOrderData("La moneda es obligatoria (por ejemplo 'MXN').")

    def add(self, other: Money) -> Money:
        """Devuelve un Money nuevo con la suma; no modifica los operandos."""
        if not isinstance(other, Money):
            raise InvalidOrderData("Solo se puede sumar Money con otro Money.")
        if self.currency != other.currency:
            raise InvalidOrderData(
                f"No se pueden sumar monedas distintas: {self.currency} y {other.currency}."
            )
        return Money(self.amount + other.amount, self.currency)

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"


@dataclass(frozen=True)
class Customer:
    """Cliente de TechStore (compatible con ``cargar_csv.py``).

    Su identidad depende solo de ``id``: dos clientes con el mismo
    identificador son el mismo cliente aunque cambien ``is_vip`` o ``active``.
    ``compare=False`` excluye esos atributos de ``__eq__`` y de ``__hash__``,
    así que la igualdad y el hash son coherentes.
    """

    id: str
    is_vip: bool = field(default=False, compare=False)
    active: bool = field(default=True, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise InvalidOrderData("El cliente requiere un identificador no vacío.")
        # Se exige bool real: 1, 0, "1" o "si" no son valores válidos.
        if not isinstance(self.is_vip, bool):
            raise InvalidOrderData(
                f"is_vip del cliente {self.id} debe ser True o False, "
                f"no {type(self.is_vip).__name__}."
            )
        if not isinstance(self.active, bool):
            raise InvalidOrderData(
                f"active del cliente {self.id} debe ser True o False, "
                f"no {type(self.active).__name__}."
            )


@dataclass(frozen=True)
class OrderItem:
    """Renglón del pedido: SKU, cantidad y precio unitario (inmutable)."""

    sku: str
    quantity: int
    unit_price: Money

    def __post_init__(self) -> None:
        if not isinstance(self.sku, str) or not self.sku.strip():
            raise InvalidOrderData("El SKU del artículo no puede estar vacío.")
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise InvalidOrderData(
                f"La cantidad de {self.sku} debe ser un número entero."
            )
        if self.quantity <= 0:
            raise InvalidOrderData(
                f"La cantidad de {self.sku} debe ser mayor que cero (se recibió {self.quantity})."
            )
        if not isinstance(self.unit_price, Money):
            raise InvalidOrderData(
                f"El precio unitario de {self.sku} debe ser un objeto Money."
            )

    @property
    def subtotal(self) -> Money:
        """Subtotal = cantidad × precio unitario (se calcula, no se captura)."""
        return Money(self.unit_price.amount * self.quantity, self.unit_price.currency)

# Estados y eventos
class OrderStatus(str, Enum):
    """Los seis estados del ciclo de vida de un pedido."""

    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    RETURNED = "RETURNED"


ORDER_CONFIRMED = "OrderConfirmed"
ORDER_SHIPPED = "OrderShipped"
ORDER_CANCELLED = "OrderCancelled"
ORDER_DELIVERED = "OrderDelivered"
ORDER_RETURNED = "OrderReturned"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class DomainEvent:
    """Hecho relevante que YA ocurrió en el dominio (nombre en pasado)."""

    name: str
    order_id: str
    occurred_at: datetime = field(default_factory=_utc_now)

# Aggregate Root
class Order:
    """Pedido de TechStore: entidad con identidad y Aggregate Root.

    Todas las modificaciones pasan por sus métodos de negocio. ``status``,
    ``items`` y ``events`` son de solo lectura desde fuera: nadie puede
    escribir ``order.status = ...`` ni ``order.items.append(...)``.

    Regla de cada transición: (1) validar, (2) cambiar el estado,
    (3) registrar el evento. Si una validación falla se lanza una excepción
    antes de tocar nada, así que el pedido queda exactamente como estaba.
    """

    def __init__(self, customer: Customer, id: str, has_promotion: bool = False) -> None:
        if not isinstance(customer, Customer):
            raise InvalidOrderData("El pedido requiere un Customer válido.")
        if not isinstance(id, str) or not id.strip():
            raise InvalidOrderData("El pedido requiere un identificador no vacío.")
        if not isinstance(has_promotion, bool):
            raise InvalidOrderData("has_promotion debe ser True o False.")
        self._customer = customer
        self._id = id
        self._has_promotion = has_promotion
        self._status = OrderStatus.DRAFT  # Todo pedido nace en DRAFT.
        self._items: list[OrderItem] = []  # Lista nueva para cada pedido.
        self._events: list[DomainEvent] = []  # Lista nueva para cada pedido.
        self._tracking_number: str | None = None
        self._cancellation_reason: str | None = None

    # Lectura 
    @property
    def id(self) -> str:
        return self._id

    @property
    def customer(self) -> Customer:
        return self._customer

    @property
    def has_promotion(self) -> bool:
        return self._has_promotion

    @property
    def status(self) -> OrderStatus:
        return self._status

    @property
    def items(self) -> tuple[OrderItem, ...]:
        """Copia de solo lectura de los artículos."""
        return tuple(self._items)

    @property
    def events(self) -> tuple[DomainEvent, ...]:
        """Copia de solo lectura de los eventos registrados."""
        return tuple(self._events)

    @property
    def tracking_number(self) -> str | None:
        return self._tracking_number

    @property
    def cancellation_reason(self) -> str | None:
        return self._cancellation_reason

    @property
    def units(self) -> int:
        """Suma de cantidades de todos los renglones (no cuenta renglones)."""
        return sum(item.quantity for item in self._items)

    @property
    def total(self) -> Money:
        """Suma de subtotales, SIN descuento (ver app.specifications)."""
        total = Money(Decimal("0.00"), DEFAULT_CURRENCY)
        for item in self._items:
            total = total.add(item.subtotal)
        return total

    # Modificación de artículos 
    def add_item(self, item: OrderItem) -> None:
        """Agrega un artículo respetando estado DRAFT, moneda y límite de 20 unidades."""
        if self._status is not OrderStatus.DRAFT:
            raise InvalidOrderTransition(
                f"No se pueden agregar artículos al pedido {self._id}: está en "
                f"{self._status.value} y solo un pedido DRAFT admite artículos."
            )
        if not isinstance(item, OrderItem):
            raise InvalidOrderData("Solo se pueden agregar objetos OrderItem válidos.")
        if item.unit_price.currency != DEFAULT_CURRENCY:
            raise InvalidOrderData(
                f"El artículo {item.sku} está en {item.unit_price.currency}; "
                f"los pedidos solo admiten {DEFAULT_CURRENCY}."
            )
        new_units = self.units + item.quantity
        if new_units > MAX_UNITS_PER_ORDER:
            raise OrderItemLimitExceeded(
                f"No se pueden agregar {item.quantity} unidad(es) de {item.sku} al pedido "
                f"{self._id}: tendría {new_units} unidades y el máximo es "
                f"{MAX_UNITS_PER_ORDER}."
            )
        self._items.append(item)

    #  Máquina de estados 
    def confirm(self) -> None:
        """DRAFT → CONFIRMED. Requiere artículos y cliente activo."""
        self._require_status(OrderStatus.DRAFT, "confirmar")
        if not self._items:
            raise InvalidOrderData(
                f"No se puede confirmar el pedido {self._id}: no tiene artículos."
            )
        if not self._customer.active:
            raise InvalidOrderData(
                f"No se puede confirmar el pedido {self._id}: el cliente "
                f"{self._customer.id} está inactivo."
            )
        self._status = OrderStatus.CONFIRMED
        self._record(ORDER_CONFIRMED)

    def ship(self, tracking_number: str) -> None:
        """CONFIRMED → SHIPPED. Requiere un número de guía no vacío."""
        self._require_status(OrderStatus.CONFIRMED, "enviar")
        if not isinstance(tracking_number, str) or not tracking_number.strip():
            raise InvalidOrderData(
                f"No se puede enviar el pedido {self._id} sin número de guía."
            )
        self._tracking_number = tracking_number.strip()
        self._status = OrderStatus.SHIPPED
        self._record(ORDER_SHIPPED)

    def cancel(self, reason: str) -> None:
        """CONFIRMED → CANCELLED. Requiere un motivo no vacío."""
        self._require_status(OrderStatus.CONFIRMED, "cancelar")
        if not isinstance(reason, str) or not reason.strip():
            raise InvalidOrderData(
                f"No se puede cancelar el pedido {self._id} sin indicar un motivo."
            )
        self._cancellation_reason = reason.strip()
        self._status = OrderStatus.CANCELLED
        self._record(ORDER_CANCELLED)

    def deliver(self) -> None:
        """SHIPPED → DELIVERED."""
        self._require_status(OrderStatus.SHIPPED, "entregar")
        self._status = OrderStatus.DELIVERED
        self._record(ORDER_DELIVERED)

    def return_order(self) -> None:
        """SHIPPED → RETURNED."""
        self._require_status(OrderStatus.SHIPPED, "devolver")
        self._status = OrderStatus.RETURNED
        self._record(ORDER_RETURNED)

    # Apoyo interno 
    def _require_status(self, expected: OrderStatus, action: str) -> None:
        if self._status is not expected:
            raise InvalidOrderTransition(
                f"No se puede {action} el pedido {self._id}: está en "
                f"{self._status.value} y esta operación solo se permite desde "
                f"{expected.value}."
            )

    def _record(self, event_name: str) -> None:
        self._events.append(DomainEvent(event_name, self._id))

    # Identidad de entidad 
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Order):
            return NotImplemented
        return self._id == other._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __repr__(self) -> str:
        return (
            f"Order(id={self._id!r}, status={self._status.value}, "
            f"units={self.units}, total={self.total})"
        )
