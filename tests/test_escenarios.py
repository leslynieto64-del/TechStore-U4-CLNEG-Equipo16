"""Ejecuta los 15 escenarios de datos/escenarios.csv y comprueba su resultado."""
import pytest

from cargar_csv import rows
from ejecutar_escenarios import ejecutar_escenario

ESCENARIOS = rows("escenarios.csv")

# Comprobaciones adicionales del enunciado (estado final, unidades, eventos).
DETALLE_ESPERADO = {
    "E03": {"estado_final": "DRAFT", "eventos": []},
    "E06": {"estado_final": "DRAFT", "eventos": []},
    "E07": {"estado_final": "CONFIRMED", "unidades_final": 20, "eventos": ["OrderConfirmed"]},
    "E08": {"estado_final": "DRAFT", "unidades_final": 19, "eventos": []},
    "E11": {"estado_final": "CONFIRMED", "eventos": ["OrderConfirmed"]},
    "E12": {"estado_final": "CONFIRMED", "eventos": ["OrderConfirmed"]},
    "E13": {"estado_final": "SHIPPED", "eventos": ["OrderConfirmed", "OrderShipped"]},
    "E14": {"estado_final": "RETURNED",
            "eventos": ["OrderConfirmed", "OrderShipped", "OrderReturned"]},
    "E15": {"estado_final": "DELIVERED",
            "eventos": ["OrderConfirmed", "OrderShipped", "OrderDelivered"]},
}


def test_hay_15_escenarios():
    assert [e["caso_id"] for e in ESCENARIOS] == [f"E{n:02}" for n in range(1, 16)]


@pytest.mark.parametrize("fila", ESCENARIOS, ids=[e["caso_id"] for e in ESCENARIOS])
def test_escenario(fila):
    resultado = ejecutar_escenario(fila)
    assert resultado.resultado == fila["objetivo"], resultado.pasos
    assert resultado.invariantes_ok, "una operación rechazada modificó el pedido"
    for campo, valor in DETALLE_ESPERADO.get(fila["caso_id"], {}).items():
        assert getattr(resultado, campo) == valor, campo
    if fila["accion"] == "evaluar_descuento":
        assert resultado.estado_final == "DRAFT" and resultado.eventos == []


def test_escenarios_no_se_contaminan_entre_si():
    primero = ejecutar_escenario(ESCENARIOS[11])  # E12 confirma O013
    segundo = ejecutar_escenario(ESCENARIOS[11])
    assert primero.estado_inicial == segundo.estado_inicial == "DRAFT"
