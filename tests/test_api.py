"""Pruebas de la API REST (app/api.py) con el TestClient de FastAPI.

Cada prueba recibe su propio ``client`` (aplicación nueva y pedidos recién
cargados), así que el orden de ejecución no cambia los resultados.
"""
from fastapi.testclient import TestClient

from app.api import create_app

ERROR_KEYS = {"error", "message", "order_id"}


def nombres_eventos(respuesta_json):
    return [e["name"] for e in respuesta_json["events"]]


# ===========================================================================
# Consulta
# ===========================================================================
def test_get_pedido_existente(client):
    r = client.get("/orders/O001")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "O001"
    assert body["status"] == "DRAFT"
    assert body["units"] == 4
    assert body["total"] == "2100.00"
    assert body["discount_rate"] == "0.10"
    assert body["discount_amount"] == "210.00"
    assert body["total_with_discount"] == "1890.00"
    assert len(body["items"]) == 2 and body["events"] == []


def test_get_pedido_inexistente_404(client):
    r = client.get("/orders/O999")
    assert r.status_code == 404
    assert r.json() == {
        "error": "OrderNotFound",
        "message": "No existe el pedido O999.",
        "order_id": "O999",
    }


def test_listar_los_16_pedidos(client):
    r = client.get("/orders")
    assert r.status_code == 200
    assert len(r.json()) == 16
    assert {o["status"] for o in r.json()} == {"DRAFT"}


# ===========================================================================
# Confirmación
# ===========================================================================
def test_confirmar_pedido_valido(client):
    r = client.post("/orders/O001/confirm")
    assert r.status_code == 200
    assert r.json()["status"] == "CONFIRMED"
    assert nombres_eventos(r.json()) == ["OrderConfirmed"]
    # El estado queda registrado en el repositorio en memoria.
    assert client.get("/orders/O001").json()["status"] == "CONFIRMED"


def test_confirmar_pedido_inexistente_404(client):
    r = client.post("/orders/NOEXISTE/confirm")
    assert r.status_code == 404
    assert set(r.json()) == ERROR_KEYS


def test_confirmar_dos_veces_409_sin_duplicar_evento(client):
    assert client.post("/orders/O013/confirm").status_code == 200
    r = client.post("/orders/O013/confirm")
    assert r.status_code == 409
    assert r.json()["error"] == "InvalidOrderTransition"
    estado = client.get("/orders/O013").json()
    assert estado["status"] == "CONFIRMED"
    assert nombres_eventos(estado) == ["OrderConfirmed"]


def test_confirmar_pedido_vacio_422(client):
    r = client.post("/orders/O007/confirm")
    assert r.status_code == 422
    assert r.json()["error"] == "InvalidOrderData"
    assert "no tiene artículos" in r.json()["message"]
    assert client.get("/orders/O007").json()["status"] == "DRAFT"


def test_confirmar_cliente_inactivo_422(client):
    r = client.post("/orders/O003/confirm")
    assert r.status_code == 422
    assert "inactivo" in r.json()["message"]
    assert client.get("/orders/O003").json()["events"] == []


# ===========================================================================
# Envío
# ===========================================================================
def test_enviar_con_guia(client):
    client.post("/orders/O012/confirm")
    r = client.post("/orders/O012/ship", json={"tracking_number": "MX-012"})
    assert r.status_code == 200
    assert r.json()["status"] == "SHIPPED"
    assert r.json()["tracking_number"] == "MX-012"
    assert nombres_eventos(r.json()) == ["OrderConfirmed", "OrderShipped"]


def test_enviar_sin_guia_se_rechaza_y_no_cambia_estado(client):
    client.post("/orders/O012/confirm")
    for kwargs in ({}, {"json": {}}, {"json": {"tracking_number": ""}},
                   {"json": {"tracking_number": "   "}}):
        r = client.post("/orders/O012/ship", **kwargs)
        assert r.status_code == 422, kwargs
        assert r.json()["error"] == "InvalidOrderData"
    estado = client.get("/orders/O012").json()
    assert estado["status"] == "CONFIRMED"
    assert nombres_eventos(estado) == ["OrderConfirmed"]


def test_enviar_desde_draft_409(client):
    r = client.post("/orders/O012/ship", json={"tracking_number": "MX-1"})
    assert r.status_code == 409
    assert client.get("/orders/O012").json()["status"] == "DRAFT"


def test_enviar_con_tipo_incorrecto_422_con_formato_consistente(client):
    client.post("/orders/O012/confirm")
    r = client.post("/orders/O012/ship", json={"tracking_number": 123})
    assert r.status_code == 422
    assert r.json()["error"] == "RequestValidationError"
    assert {"error", "message", "order_id", "details"} == set(r.json())


# ===========================================================================
# Cancelación
# ===========================================================================
def test_cancelar_desde_confirmed(client):
    client.post("/orders/O013/confirm")
    r = client.post("/orders/O013/cancel", json={"reason": "Cliente lo pidió"})
    assert r.status_code == 200
    assert r.json()["status"] == "CANCELLED"
    assert r.json()["cancellation_reason"] == "Cliente lo pidió"
    assert nombres_eventos(r.json())[-1] == "OrderCancelled"


def test_cancelar_sin_motivo_422(client):
    client.post("/orders/O013/confirm")
    r = client.post("/orders/O013/cancel", json={"reason": ""})
    assert r.status_code == 422
    assert client.get("/orders/O013").json()["status"] == "CONFIRMED"


def test_cancelar_desde_shipped_409_sin_cambiar_estado(client):
    client.post("/orders/O014/confirm")
    client.post("/orders/O014/ship", json={"tracking_number": "MX-014"})
    r = client.post("/orders/O014/cancel", json={"reason": "Ya no lo quiero"})
    assert r.status_code == 409
    assert "SHIPPED" in r.json()["message"]
    estado = client.get("/orders/O014").json()
    assert estado["status"] == "SHIPPED"
    assert nombres_eventos(estado) == ["OrderConfirmed", "OrderShipped"]


def test_cancelar_desde_draft_409(client):
    r = client.post("/orders/O001/cancel", json={"reason": "x"})
    assert r.status_code == 409


# ===========================================================================
# Entrega y devolución
# ===========================================================================
def test_flujo_completo_entrega(client):
    client.post("/orders/O016/confirm")
    client.post("/orders/O016/ship", json={"tracking_number": "MX-016"})
    r = client.post("/orders/O016/deliver")
    assert r.status_code == 200 and r.json()["status"] == "DELIVERED"
    assert nombres_eventos(r.json()) == ["OrderConfirmed", "OrderShipped", "OrderDelivered"]


def test_flujo_completo_devolucion(client):
    client.post("/orders/O015/confirm")
    client.post("/orders/O015/ship", json={"tracking_number": "MX-015"})
    r = client.post("/orders/O015/return")
    assert r.status_code == 200 and r.json()["status"] == "RETURNED"
    assert nombres_eventos(r.json())[-1] == "OrderReturned"


def test_entregar_sin_enviar_409(client):
    client.post("/orders/O016/confirm")
    assert client.post("/orders/O016/deliver").status_code == 409
    assert client.post("/orders/O016/return").status_code == 409


# ===========================================================================
# Aislamiento, errores técnicos y OpenAPI
# ===========================================================================
def test_aplicaciones_independientes_no_comparten_estado():
    with TestClient(create_app()) as a, TestClient(create_app()) as b:
        a.post("/orders/O001/confirm")
        assert a.get("/orders/O001").json()["status"] == "CONFIRMED"
        assert b.get("/orders/O001").json()["status"] == "DRAFT"


def test_error_tecnico_no_se_disfraza_de_error_de_dominio():
    app = create_app()

    def falla_de_infraestructura(order_id):
        raise RuntimeError("se perdió la conexión")

    app.state.service.confirm = falla_de_infraestructura
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post("/orders/O001/confirm")
    assert r.status_code == 500


def test_respuestas_exitosas_tienen_la_misma_forma(client):
    claves = set(client.get("/orders/O001").json())
    assert set(client.post("/orders/O001/confirm").json()) == claves


def test_openapi_y_swagger_disponibles(client):
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    paths = spec.json()["paths"]
    for ruta in ("/orders/{order_id}", "/orders/{order_id}/confirm",
                 "/orders/{order_id}/ship", "/orders/{order_id}/cancel"):
        assert ruta in paths
    confirm = paths["/orders/{order_id}/confirm"]["post"]["responses"]
    assert {"200", "404", "409", "422"} <= set(confirm)
    assert "ShipRequest" in spec.json()["components"]["schemas"]
    docs = client.get("/docs")
    assert docs.status_code == 200 and "swagger" in docs.text.lower()
