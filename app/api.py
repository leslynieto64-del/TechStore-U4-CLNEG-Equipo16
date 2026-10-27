"""API REST de TechStore con FastAPI.

Los controladores son "delgados": reciben la petición, piden al
``OrderService`` que ejecute el caso de uso y convierten el resultado en
JSON. No calculan descuentos ni cambian ``status`` por su cuenta.

Traducción de errores a HTTP:

* ``OrderNotFound``           → 404 Not Found
* ``InvalidOrderTransition``  → 409 Conflict
* ``InvalidOrderData``        → 422 Unprocessable Entity
* ``OrderItemLimitExceeded``  → 422 Unprocessable Entity
* Errores técnicos (cualquier otra excepción) NO se disfrazan: quedan como 500.

Arranque: ``uvicorn app.api:app --reload`` → http://127.0.0.1:8000/docs
"""
from typing import Callable

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.domain import (
    DomainException,
    InvalidOrderData,
    InvalidOrderTransition,
    Order,
    OrderItemLimitExceeded,
)
from app.service import OrderNotFound, OrderService
from app.specifications import discount_amount, discount_rate, total_with_discount
from cargar_csv import load_fixture

# Códigos HTTP de cada excepción de dominio (se busca por herencia).
DOMAIN_HTTP_STATUS: dict[type[DomainException], int] = {
    InvalidOrderTransition: 409,
    InvalidOrderData: 422,
    OrderItemLimitExceeded: 422,
}


# ---------------------------------------------------------------------------
# DTO de petición y de respuesta
# ---------------------------------------------------------------------------
class ShipRequest(BaseModel):
    tracking_number: str = Field(
        default="",
        description="Número de guía. Si llega vacío, el dominio rechaza el envío (422).",
        examples=["MX-123456789"],
    )


class CancelRequest(BaseModel):
    reason: str = Field(
        default="",
        description="Motivo de cancelación. Si llega vacío, el dominio rechaza la cancelación (422).",
        examples=["El cliente solicitó la cancelación"],
    )


class ItemResponse(BaseModel):
    sku: str
    quantity: int
    unit_price: str
    subtotal: str


class EventResponse(BaseModel):
    name: str
    order_id: str
    occurred_at: str


class OrderResponse(BaseModel):
    id: str
    customer_id: str
    customer_is_vip: bool
    customer_active: bool
    has_promotion: bool
    status: str
    units: int
    currency: str
    total: str = Field(description="Suma de subtotales, sin descuento.")
    discount_rate: str = Field(description="0.10, 0.05 o 0.00 según las Specifications.")
    discount_amount: str
    total_with_discount: str
    tracking_number: str | None = None
    cancellation_reason: str | None = None
    items: list[ItemResponse]
    events: list[EventResponse]


class ErrorResponse(BaseModel):
    error: str = Field(description="Tipo de error, por ejemplo InvalidOrderTransition.")
    message: str = Field(description="Mensaje legible para el usuario.")
    order_id: str | None = None
    details: list[dict] | None = None


def to_response(order: Order) -> OrderResponse:
    """Convierte la entidad Order en un DTO de respuesta (solo lectura)."""
    return OrderResponse(
        id=order.id,
        customer_id=order.customer.id,
        customer_is_vip=order.customer.is_vip,
        customer_active=order.customer.active,
        has_promotion=order.has_promotion,
        status=order.status.value,
        units=order.units,
        currency=order.total.currency,
        total=str(order.total.amount),
        discount_rate=str(discount_rate(order)),
        discount_amount=str(discount_amount(order).amount),
        total_with_discount=str(total_with_discount(order).amount),
        tracking_number=order.tracking_number,
        cancellation_reason=order.cancellation_reason,
        items=[
            ItemResponse(
                sku=item.sku,
                quantity=item.quantity,
                unit_price=str(item.unit_price.amount),
                subtotal=str(item.subtotal.amount),
            )
            for item in order.items
        ],
        events=[
            EventResponse(
                name=event.name,
                order_id=event.order_id,
                occurred_at=event.occurred_at.isoformat(),
            )
            for event in order.events
        ],
    )


# ---------------------------------------------------------------------------
# Controladores
# ---------------------------------------------------------------------------
def get_service(request: Request) -> OrderService:
    return request.app.state.service


NOT_FOUND = {404: {"model": ErrorResponse, "description": "El pedido no existe."}}
CONFLICT = {409: {"model": ErrorResponse, "description": "Transición no permitida desde el estado actual."}}
UNPROCESSABLE = {422: {"model": ErrorResponse, "description": "Datos o precondiciones de negocio inválidos."}}

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderResponse], summary="Listar pedidos en memoria")
def list_orders(service: OrderService = Depends(get_service)):
    return [to_response(order) for order in service.list_orders()]


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    responses=NOT_FOUND,
    summary="Consultar un pedido",
)
def get_order(order_id: str, service: OrderService = Depends(get_service)):
    return to_response(service.get(order_id))


@router.post(
    "/{order_id}/confirm",
    response_model=OrderResponse,
    responses={**NOT_FOUND, **CONFLICT, **UNPROCESSABLE},
    summary="Confirmar un pedido (DRAFT → CONFIRMED)",
)
def confirm_order(order_id: str, service: OrderService = Depends(get_service)):
    return to_response(service.confirm(order_id))


@router.post(
    "/{order_id}/ship",
    response_model=OrderResponse,
    responses={**NOT_FOUND, **CONFLICT, **UNPROCESSABLE},
    summary="Enviar un pedido con número de guía (CONFIRMED → SHIPPED)",
)
def ship_order(
    order_id: str,
    payload: ShipRequest | None = None,
    service: OrderService = Depends(get_service),
):
    tracking_number = payload.tracking_number if payload else ""
    return to_response(service.ship(order_id, tracking_number))


@router.post(
    "/{order_id}/cancel",
    response_model=OrderResponse,
    responses={**NOT_FOUND, **CONFLICT, **UNPROCESSABLE},
    summary="Cancelar un pedido con motivo (CONFIRMED → CANCELLED)",
)
def cancel_order(
    order_id: str,
    payload: CancelRequest | None = None,
    service: OrderService = Depends(get_service),
):
    reason = payload.reason if payload else ""
    return to_response(service.cancel(order_id, reason))


@router.post(
    "/{order_id}/deliver",
    response_model=OrderResponse,
    responses={**NOT_FOUND, **CONFLICT},
    summary="Entregar un pedido (SHIPPED → DELIVERED)",
)
def deliver_order(order_id: str, service: OrderService = Depends(get_service)):
    return to_response(service.deliver(order_id))


@router.post(
    "/{order_id}/return",
    response_model=OrderResponse,
    responses={**NOT_FOUND, **CONFLICT},
    summary="Registrar la devolución de un pedido (SHIPPED → RETURNED)",
)
def return_order(order_id: str, service: OrderService = Depends(get_service)):
    return to_response(service.return_order(order_id))


# ---------------------------------------------------------------------------
# Manejadores de errores
# ---------------------------------------------------------------------------
def _status_for(exc: DomainException) -> int:
    for exc_type in type(exc).__mro__:
        if exc_type in DOMAIN_HTTP_STATUS:
            return DOMAIN_HTTP_STATUS[exc_type]
    return 422  # Cualquier otra regla de negocio violada.


def _error(status: int, exc: Exception, request: Request, details=None) -> JSONResponse:
    body = ErrorResponse(
        error=type(exc).__name__,
        message=str(exc),
        order_id=request.path_params.get("order_id"),
        details=details,
    )
    return JSONResponse(status_code=status, content=body.model_dump(exclude_none=True))


async def order_not_found_handler(request: Request, exc: OrderNotFound) -> JSONResponse:
    return _error(404, exc, request)


async def domain_exception_handler(request: Request, exc: DomainException) -> JSONResponse:
    return _error(_status_for(exc), exc, request)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"loc": list(err.get("loc", [])), "msg": err.get("msg", "")}
        for err in exc.errors()
    ]
    body = ErrorResponse(
        error="RequestValidationError",
        message="La petición no tiene el formato esperado.",
        order_id=request.path_params.get("order_id"),
        details=details,
    )
    return JSONResponse(status_code=422, content=body.model_dump(exclude_none=True))


# ---------------------------------------------------------------------------
# Fábrica de la aplicación
# ---------------------------------------------------------------------------
def create_app(loader: Callable[[], dict[str, Order]] = load_fixture) -> FastAPI:
    """Crea una aplicación con su PROPIO repositorio en memoria.

    Cada llamada vuelve a cargar los CSV, así que las pruebas pueden crear
    aplicaciones independientes sin compartir pedidos.
    """
    application = FastAPI(
        title="TechStore U4 API",
        version="1.0.0",
        description=(
            "Núcleo de negocio TechStore (CLN · Unidad 4 · Actividad 4). "
            "Los pedidos se cargan de los CSV en memoria; los cambios se pierden al reiniciar."
        ),
    )
    application.state.service = OrderService(loader())
    application.include_router(router)
    application.add_exception_handler(OrderNotFound, order_not_found_handler)
    application.add_exception_handler(DomainException, domain_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    return application


app = create_app()
