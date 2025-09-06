import pytest
from datetime import date, timedelta
from rest_framework.test import APIClient
from formularios.models import Categoria, Formulario, FormularioIndexVersion

# Habilita BD para todos los tests siempre
@pytest.fixture(autouse=True)
def _enable_db_access_for_all_tests(db):
    pass

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def categoria(db):
    return Categoria.objects.create(nombre="Cat QA", descripcion="Pruebas")

@pytest.fixture
def formulario(db, categoria):
    return Formulario.objects.create(
        categoria=categoria,
        nombre="Campo",
        descripcion="",
        permitir_fotos=False,
        permitir_gps=False,
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=7),
        estado="Activa",
        forma_envio="En Linea",
        es_publico=False,
        auto_envio=False,
    )

@pytest.fixture
def version(db, formulario):
    return FormularioIndexVersion.objects.create(formulario=formulario)
