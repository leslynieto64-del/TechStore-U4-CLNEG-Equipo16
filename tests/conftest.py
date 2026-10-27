"""Fixtures compartidas por las pruebas (pytest las inyecta por nombre)."""
import pytest

from cargar_csv import load_fixture


@pytest.fixture
def orders():
    """Carga NUEVA de los 16 pedidos para cada prueba (aislamiento)."""
    return load_fixture()


@pytest.fixture
def client():
    """Aplicación nueva con su propio repositorio en memoria para cada prueba."""
    # Se importa aquí para que las pruebas del dominio no dependan de FastAPI.
    from fastapi.testclient import TestClient

    from app.api import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
