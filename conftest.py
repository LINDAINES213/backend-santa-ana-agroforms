import pytest
from datetime import date, timedelta
from django.utils import timezone
from django.db import connection
from rest_framework.test import APIClient
from oauth2_provider.models import Application, AccessToken
from formularios.models import (
    Categoria, 
    Formulario, 
    FormularioIndexVersion,
    Usuario,
    FuenteDatos,
    Grupo,
    Campo,
    ClaseCampo,
)
from formularios.services import hash_password
import json
import uuid

# Habilita BD para todos los tests siempre
@pytest.fixture(autouse=True)
def _enable_db_access_for_all_tests(db):
    pass

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def categoria(db):
    return Categoria.objects.create(
        nombre="Campo",
        descripcion=""
    )

@pytest.fixture(scope="session", autouse=True)
def ensure_formulario_entry_table(django_db_blocker):
    with django_db_blocker.unblock():
        with connection.cursor() as cur:
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='formularios_entry';"
            )
            exists = cur.fetchone() is not None

        if not exists:
            from formularios.models import FormularioEntry
            # Crear la tabla explícitamente con el schema editor
            with connection.schema_editor() as schema:
                schema.create_model(FormularioEntry)

@pytest.fixture(autouse=True)
def drf_allow_any_permissions(settings):
    rest = getattr(settings, "REST_FRAMEWORK", {}) or {}
    rest["DEFAULT_PERMISSION_CLASSES"] = [
        "rest_framework.permissions.AllowAny",
    ]
    settings.REST_FRAMEWORK = rest
    yield

@pytest.fixture
def formulario(db, categoria):
    return Formulario.objects.create(
        categoria=categoria,
        nombre="Formulario",
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
    # Intentar obtener la versión creada por el signal primero
    existing_version = FormularioIndexVersion.objects.filter(formulario_id=formulario).first()
    if existing_version:
        return existing_version
    return FormularioIndexVersion.objects.create(formulario_id=formulario)

@pytest.fixture
def authenticated_user(db):
    return Usuario.objects.create(
        nombre_usuario="testuser",
        nombre="Test User",
        correo="test@example.com",
        password=hash_password("testpass123"),
        activo=True,
        acceso_web=True,
    )

@pytest.fixture
def api_client_authenticated(db, authenticated_user):
    client = APIClient()
    
    # Crear aplicación OAuth2
    app, _ = Application.objects.get_or_create(
        name='Test App',
        defaults={
            'client_type': Application.CLIENT_CONFIDENTIAL,
            'authorization_grant_type': Application.GRANT_PASSWORD,
        }
    )
    
    # Crear token
    token = AccessToken.objects.create(
        user=authenticated_user,
        token="test-token-123",
        application=app,
        expires=timezone.now() + timedelta(hours=10),
        scope='read write'
    )
    
    # Autenticar cliente
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.token}')
    
    return client

@pytest.fixture
def usuario_fixture(db):
    return Usuario.objects.create(
        nombre_usuario="usuario_test",
        nombre="Usuario Test",
        correo="usuario@test.com",
        password=hash_password("password123"),
        activo=True,
        acceso_web=True,
    )

@pytest.fixture
def fuente_datos_fixture(db, authenticated_user):
    return FuenteDatos.objects.create(
        nombre="Fuente Test",
        descripcion="Test",
        archivo_nombre="test.csv",
        blob_name="test_blob.csv",
        blob_url="https://test.blob.core.windows.net/test.csv",
        tipo_archivo="csv",
        columnas=["id", "nombre"],
        preview_data=[{"id": 1, "nombre": "Test"}],
        activo=True,
        creado_por=authenticated_user,
    )

@pytest.fixture
def grupo_fixture(db):
    # Crear ClaseCampo si no existe
    ClaseCampo.objects.get_or_create(
        clase="group", 
        defaults={"estructura": "{}"}
    )
    
    grupo_id = str(uuid.uuid4())
    
    # Crear campo group
    campo_group = Campo.objects.create(
        tipo="group",
        clase="group",
        nombre_campo="grupo_test",
        etiqueta="Grupo Test",
        config=json.dumps({
            "id_group": grupo_id, 
            "name": "Grupo Test"
        }),
    )
    
    # Crear grupo
    return Grupo.objects.create(
        id_grupo=grupo_id,
        id_campo_group=campo_group,
        nombre="Grupo Test",
    )

@pytest.fixture
def campo_fixture(db):
    # Crear ClaseCampo si no existe
    ClaseCampo.objects.get_or_create(
        clase="string", 
        defaults={"estructura": "{}"}
    )
    
    return Campo.objects.create(
        tipo="texto",
        clase="string",
        nombre_campo="campo_test",
        etiqueta="Campo Test",
        ayuda="Ayuda test",
        config="{}",
        requerido=False,
    )

@pytest.fixture
def usuario_test(db):
    return Usuario.objects.create(
        nombre_usuario="testuser_serial",
        nombre="Test User Serial",
        correo="test_serial@example.com",
        password=hash_password("testpass123"),
        activo=True,
        acceso_web=True,
    )

@pytest.fixture
def formulario_test(db, categoria):
    return Formulario.objects.create(
        categoria=categoria,
        nombre="Formulario Test",
        descripcion="Test",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Activo",
        forma_envio="En Linea",
    )

@pytest.fixture
def campo_test(db):
    ClaseCampo.objects.get_or_create(
        clase="string", 
        defaults={"estructura": "{}"}
    )
    
    return Campo.objects.create(
        tipo="texto",
        clase="string",
        nombre_campo="campo_test_serial",
        etiqueta="Campo Test Serial",
        config=json.dumps({}),
        requerido=False,
    )

@pytest.fixture
def fuente_datos_test(db, usuario_test):
    return FuenteDatos.objects.create(
        nombre="Fuente Test Serial",
        descripcion="Test",
        archivo_nombre="test_serial.csv",
        blob_name="test_blob_serial.csv",
        blob_url="https://test.blob.core.windows.net/test_serial.csv",
        tipo_archivo="csv",
        columnas=["id", "nombre"],
        preview_data=[],
        activo=True,
        creado_por=usuario_test,
    )