"""Pruebas de los datos originales y del cargador del profesor."""
import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from cargar_csv import BASE, load_fixture, rows

# Huellas SHA-256 de los CSV de CLN_U4_Paquete_Alumno.zip calculadas sobre los
# bytes tal como están almacenados (incluyen BOM UTF-8 y saltos de línea CRLF).
# .gitattributes (*.csv -text) evita que Git modifique esos bytes.
HUELLAS_ORIGINALES = {
    "clientes.csv": "da9fd57c0a68824899ce9fde246c04d02ef96dbe6c4dc5bc7768792e5383e8e0",
    "productos.csv": "ecacde51403c29b77b80f2ba1993d34cb1f3b3ef3af22d501ece13ca8c7dd3c2",
    "pedidos.csv": "550bac130628582d2c6303f806cbddabff5994ebd974089d4966d9cc29dde8b8",
    "detalle_pedidos.csv": "8dcd9573b18a9391a46e7baa4f11fc5c4a97c3b78cafa1022bb0f1435f97623a",
    "escenarios.csv": "1bcee568abee998d01d6632dcc6024aa375d8bd79e4a467698785b2d0141bbda",
}


@pytest.mark.parametrize("archivo", sorted(HUELLAS_ORIGINALES))
def test_csv_originales_sin_modificar(archivo):
    contenido = (Path(BASE) / archivo).read_bytes()  # sin normalizar nada
    assert hashlib.sha256(contenido).hexdigest() == HUELLAS_ORIGINALES[archivo]


@pytest.mark.parametrize(
    "archivo, cantidad",
    [("clientes.csv", 12), ("productos.csv", 12), ("pedidos.csv", 16),
     ("detalle_pedidos.csv", 21), ("escenarios.csv", 15)],
)
def test_cantidad_de_registros(archivo, cantidad):
    assert len(rows(archivo)) == cantidad


def test_cargador_produce_16_pedidos_en_draft(orders):
    assert len(orders) == 16
    assert {o.status.value for o in orders.values()} == {"DRAFT"}


def test_pedido_o001_inicia_draft(orders):
    # Prueba propuesta en la práctica guiada (sección 12).
    assert orders["O001"].status.value == "DRAFT"
    assert orders["O001"].units == 4
    assert orders["O001"].total.amount == Decimal("2100.00")


@pytest.mark.parametrize(
    "pedido, unidades, total",
    [("O006", 1, "18000.00"), ("O007", 0, "0"), ("O008", 20, "2400.00"),
     ("O009", 19, "2280.00"), ("O010", 2, "500.00"), ("O011", 3, "1500.00")],
)
def test_unidades_y_totales_de_pedidos_frontera(orders, pedido, unidades, total):
    assert orders[pedido].units == unidades
    assert orders[pedido].total.amount == Decimal(total)


def test_cada_carga_es_independiente():
    a = load_fixture()
    b = load_fixture()
    a["O001"].confirm()
    assert b["O001"].status.value == "DRAFT"
    assert a["O001"] is not b["O001"]
