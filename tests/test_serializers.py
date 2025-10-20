import pytest
import json
from datetime import date, timedelta
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError
from formularios.serializers import (
    FuenteDatosSerializer,
    FuenteDatosCreateSerializer,
    CrearCampoEnPaginaSerializer,
    UsuarioCreateSerializer,
    UsuarioUpdateSerializer,
    FormularioUpdateSerializer,
    CampoUpdateSerializer,
    AsignacionBulkSerializer,
    _normalize_dataset_config,
)
from formularios.models import (
    Usuario,
    Formulario,
    FuenteDatos,
    Campo,
    ClaseCampo,
)

def test_normalize_dataset_config_flat_structure():
    # Test normalización de config plano a estructura anidada
    config = {
        "fuente_id": "123e4567-e89b-12d3-a456-426614174000",
        "mode": "pair",
        "key_column": "id",
        "label_column": "nombre"
    }
    
    result = _normalize_dataset_config(config)
    
    assert "dataset" in result
    assert result["dataset"]["fuente_id"] == config["fuente_id"]
    assert result["dataset"]["mode"] == "pair"

def test_normalize_dataset_config_nested_structure():
    # Test que estructura anidada se mantiene
    config = {
        "dataset": {
            "fuente_id": "123e4567-e89b-12d3-a456-426614174000",
            "mode": "single",
            "column": "nombre"
        }
    }
    
    result = _normalize_dataset_config(config)
    
    assert result["dataset"]["fuente_id"] == config["dataset"]["fuente_id"]
    assert result["dataset"]["mode"] == "single"

def test_normalize_dataset_config_file_alias():
    # Test que 'file' se mapea a 'fuente_id
    config = {
        "file": "123e4567-e89b-12d3-a456-426614174000",
        "mode": "pair"
    }
    
    result = _normalize_dataset_config(config)
    
    assert result["dataset"]["fuente_id"] == config["file"]

def test_normalize_dataset_config_defaults():
    # Test que se aplican valores por defecto
    config = {
        "fuente_id": "123e4567-e89b-12d3-a456-426614174000"
    }
    
    result = _normalize_dataset_config(config)
    
    assert result["dataset"]["mode"] == "pair"
    assert result["dataset"]["cache_inline"] is True
    assert result["dataset"]["max_items_inline"] == 300

def test_normalize_dataset_config_json_string():
    # Test normalización desde string JSON
    config_str = '{"fuente_id": "123", "mode": "single"}'
    
    result = _normalize_dataset_config(config_str)
    
    assert "dataset" in result
    assert result["dataset"]["fuente_id"] == "123"

def test_normalize_dataset_config_invalid_json():
    # Test manejo de JSON inválido
    config_str = "invalid json {"
    
    result = _normalize_dataset_config(config_str)
    
    assert result == {}

@pytest.mark.django_db
def test_fuente_datos_serializer_validate_archivo_excel_valid():
    # Test validación de archivo Excel válido
    archivo = SimpleUploadedFile(
        "test.xlsx",
        b"fake excel content",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    serializer = FuenteDatosSerializer()
    result = serializer.validate_archivo(archivo)
    
    assert result == archivo

@pytest.mark.django_db
def test_fuente_datos_serializer_validate_archivo_csv_valid():
    # Test validación de archivo CSV válido
    archivo = SimpleUploadedFile(
        "test.csv",
        b"id,nombre\n1,test",
        content_type="text/csv"
    )
    
    serializer = FuenteDatosSerializer()
    result = serializer.validate_archivo(archivo)
    
    assert result == archivo

@pytest.mark.django_db
def test_fuente_datos_serializer_validate_archivo_invalid_extension():
    # Test rechazo de extensión inválida
    archivo = SimpleUploadedFile(
        "test.txt",
        b"contenido texto",
        content_type="text/plain"
    )
    
    serializer = FuenteDatosSerializer()
    
    with pytest.raises(ValidationError, match="Solo se permiten archivos Excel"):
        serializer.validate_archivo(archivo)

@pytest.mark.django_db
def test_fuente_datos_serializer_validate_archivo_too_large():
    # Crear archivo simulado de 11MB
    large_content = b"x" * (11 * 1024 * 1024)
    archivo = SimpleUploadedFile(
        "test.xlsx",
        large_content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    serializer = FuenteDatosSerializer()
    
    with pytest.raises(ValidationError, match="no puede superar los 10MB"):
        serializer.validate_archivo(archivo)

@pytest.mark.django_db
def test_crear_campo_serializer_basic_validation():
    # Test validación básica de campo
    data = {
        "clase": "string",
        "nombre_campo": "campo_test",
        "etiqueta": "Campo de Prueba",
        "ayuda": "Texto de ayuda",
        "requerido": True,
        "config": {},
        "sequence": 1
    }
    
    serializer = CrearCampoEnPaginaSerializer(data=data)
    assert serializer.is_valid()

@pytest.mark.django_db
def test_crear_campo_serializer_nombre_campo_invalid():
    # Test rechazo de nombre_campo con caracteres inválidos
    data = {
        "clase": "string",
        "nombre_campo": "campo con espacios!",  # inválido
        "etiqueta": "Campo de Prueba",
    }
    
    serializer = CrearCampoEnPaginaSerializer(data=data)
    assert not serializer.is_valid()
    assert "nombre_campo" in serializer.errors

@pytest.mark.django_db
def test_crear_campo_serializer_dataset_sin_fuente_id_falla():
    # Test que falla si dataset no tiene fuente_id
    data = {
        "clase": "dataset",
        "nombre_campo": "campo_dataset",
        "etiqueta": "Dataset Campo",
        "config": {
            "dataset": {
                "mode": "single",
                "column": "nombre"
            }
        }
    }
    
    serializer = CrearCampoEnPaginaSerializer(data=data)
    assert not serializer.is_valid()
    assert "config" in serializer.errors

@pytest.mark.django_db
def test_crear_campo_serializer_dataset_mode_invalid():
    # Test que falla con mode inválido
    data = {
        "clase": "dataset",
        "nombre_campo": "campo_dataset",
        "etiqueta": "Dataset Campo",
        "config": {
            "dataset": {
                "fuente_id": "123e4567-e89b-12d3-a456-426614174000",
                "mode": "invalid_mode",
                "column": "test"
            }
        }
    }
    
    serializer = CrearCampoEnPaginaSerializer(data=data)
    assert not serializer.is_valid()

@pytest.mark.django_db
def test_usuario_create_serializer_valid():
    # Test creación válida de usuario
    data = {
        "nombre_usuario": "nuevo_user",
        "nombre": "Nuevo Usuario",
        "correo": "nuevo@example.com",
        "password": "password123",
        "activo": True,
        "acceso_web": True
    }
    
    serializer = UsuarioCreateSerializer(data=data)
    assert serializer.is_valid()

@pytest.mark.django_db
def test_usuario_create_serializer_correo_duplicado(usuario_test):
    # Test que falla con correo duplicado
    data = {
        "nombre_usuario": "otro_user",
        "nombre": "Otro Usuario",
        "correo": usuario_test.correo,  # correo ya existe
        "password": "password123",
    }
    
    serializer = UsuarioCreateSerializer(data=data)
    assert not serializer.is_valid()
    assert "correo" in serializer.errors

@pytest.mark.django_db
def test_usuario_create_serializer_nombre_usuario_duplicado(usuario_test):
    # Test que falla con nombre_usuario duplicado
    data = {
        "nombre_usuario": usuario_test.nombre_usuario,  # ya existe
        "nombre": "Otro Usuario",
        "correo": "otro@example.com",
        "password": "password123",
    }
    
    serializer = UsuarioCreateSerializer(data=data)
    assert not serializer.is_valid()
    assert "nombre_usuario" in serializer.errors

@pytest.mark.django_db
def test_usuario_create_serializer_password_too_short():
    # Test que falla con password muy corta
    data = {
        "nombre_usuario": "nuevo_user",
        "nombre": "Nuevo Usuario",
        "correo": "nuevo@example.com",
        "password": "123",  # muy corta
    }
    
    serializer = UsuarioCreateSerializer(data=data)
    assert not serializer.is_valid()
    assert "password" in serializer.errors

@pytest.mark.django_db
def test_usuario_create_serializer_creates_user():
    # Test que efectivamente crea el usuario con password hasheado
    data = {
        "nombre_usuario": "nuevo_user",
        "nombre": "Nuevo Usuario",
        "correo": "nuevo@example.com",
        "password": "password123",
        "activo": True,
        "acceso_web": False
    }
    
    serializer = UsuarioCreateSerializer(data=data)
    assert serializer.is_valid()
    
    user = serializer.save()
    
    assert user.nombre_usuario == "nuevo_user"
    assert user.password != "password123"  # debe estar hasheado
    assert user.password.startswith("$argon2")

@pytest.mark.django_db
def test_usuario_update_serializer_partial_update(usuario_test):
    # Test actualización parcial de usuario
    data = {
        "nombre": "Nombre Actualizado"
    }
    
    serializer = UsuarioUpdateSerializer(usuario_test, data=data, partial=True)
    assert serializer.is_valid()
    
    user = serializer.save()
    assert user.nombre == "Nombre Actualizado"

@pytest.mark.django_db
def test_usuario_update_serializer_update_password(usuario_test):
    # Test actualización de password
    old_password = usuario_test.password
    
    data = {
        "password": "newpassword123"
    }
    
    serializer = UsuarioUpdateSerializer(usuario_test, data=data, partial=True)
    assert serializer.is_valid()
    
    user = serializer.save()
    assert user.password != old_password
    assert user.password.startswith("$argon2")

@pytest.mark.django_db
def test_formulario_update_serializer_valid(formulario_test):
    # Test actualización válida de formulario
    data = {
        "nombre": "Formulario Actualizado",
        "descripcion": "Nueva descripción"
    }
    
    serializer = FormularioUpdateSerializer(formulario_test, data=data, partial=True)
    assert serializer.is_valid()


@pytest.mark.django_db
def test_formulario_update_serializer_fecha_hasta_antes_desde_falla(formulario_test):
    # Test que falla si fecha_hasta < fecha_desde
    data = {
        "disponible_desde_fecha": date.today(),
        "disponible_hasta_fecha": date.today() - timedelta(days=1)
    }
    
    serializer = FormularioUpdateSerializer(formulario_test, data=data, partial=True)
    assert not serializer.is_valid()
    assert "disponible_hasta_fecha" in serializer.errors

@pytest.mark.django_db
def test_formulario_update_serializer_fechas_iguales_valido(formulario_test):
    # Test que permite fechas iguales
    mismo_dia = date.today()
    data = {
        "disponible_desde_fecha": mismo_dia,
        "disponible_hasta_fecha": mismo_dia
    }
    
    serializer = FormularioUpdateSerializer(formulario_test, data=data, partial=True)
    assert serializer.is_valid()

@pytest.mark.django_db
def test_campo_update_serializer_basic(campo_test):
    # Test actualización básica de campo
    data = {
        "etiqueta": "Nueva Etiqueta",
        "ayuda": "Nueva ayuda"
    }
    
    serializer = CampoUpdateSerializer(campo_test, data=data, partial=True)
    assert serializer.is_valid()
    
    campo = serializer.save()
    assert campo.etiqueta == "Nueva Etiqueta"

@pytest.mark.django_db
def test_asignacion_bulk_serializer_valid(usuario_test, formulario_test):
    # Test validación exitosa de asignación
    data = {
        "usuario": usuario_test.nombre_usuario,
        "formularios": [str(formulario_test.id)],
        "replace": False
    }
    
    serializer = AsignacionBulkSerializer(data=data)
    assert serializer.is_valid()
    assert "user_obj" in serializer.validated_data
    assert "form_ids" in serializer.validated_data

@pytest.mark.django_db
def test_asignacion_bulk_serializer_usuario_no_existe():
    # Test que falla si usuario no existe
    data = {
        "usuario": "usuario_inexistente",
        "formularios": ["123e4567-e89b-12d3-a456-426614174000"],
        "replace": False
    }
    
    serializer = AsignacionBulkSerializer(data=data)
    assert not serializer.is_valid()
    assert "usuario" in serializer.errors

@pytest.mark.django_db
def test_asignacion_bulk_serializer_formularios_inexistentes(usuario_test):
    # Test que falla si hay formularios inexistentes
    data = {
        "usuario": usuario_test.nombre_usuario,
        "formularios": [
            "123e4567-e89b-12d3-a456-426614174000",
            "223e4567-e89b-12d3-a456-426614174000"
        ],
        "replace": False
    }
    
    serializer = AsignacionBulkSerializer(data=data)
    assert not serializer.is_valid()
    assert "formularios" in serializer.errors

@pytest.fixture
def usuario_test(db):
    # Fixture para usuario de prueba
    from formularios.services import hash_password
    return Usuario.objects.create(
        nombre_usuario="testuser",
        nombre="Test User",
        correo="test@example.com",
        password=hash_password("testpass123"),
        activo=True,
        acceso_web=True,
    )

@pytest.fixture
def formulario_test(db, categoria):
    # Fixture para formulario de prueba
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
    # Fixture para campo de prueba
    ClaseCampo.objects.get_or_create(clase="string", defaults={"estructura": "{}"})
    return Campo.objects.create(
        tipo="texto",
        clase="string",
        nombre_campo="campo_test",
        etiqueta="Campo Test",
        config=json.dumps({}),
        requerido=False,
    )

@pytest.fixture
def fuente_datos_test(db, usuario_test):
    # Fixture para fuente de datos de prueba
    return FuenteDatos.objects.create(
        nombre="Fuente Test",
        descripcion="Test",
        archivo_nombre="test.csv",
        blob_name="test_blob.csv",
        blob_url="https://test.blob.core.windows.net/test.csv",
        tipo_archivo="csv",
        columnas=["id", "nombre"],
        preview_data=[],
        creado_por=usuario_test,
    )