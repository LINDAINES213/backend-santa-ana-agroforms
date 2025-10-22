import pytest
from datetime import date, timedelta
from django.utils import timezone
from django.core.exceptions import ValidationError
from formularios.services import (
    hash_password,
    verify_password,
    duplicar_formulario,
    crear_campo_y_versionar_pagina,
    crear_campo_en_pagina,
    _uuid32_no_dashes,
    uuid32,
    versionar_pagina_sin_clonar,
    _materializar_dataset_para_campo,
)
from formularios.models import (
    Formulario,
    FormularioIndexVersion,
    Pagina,
    PaginaVersion,
    Campo,
    PaginaCampo,
    ClaseCampo,
    FuenteDatos,
    FuenteDatosValor,
    Grupo,
)
from io import BytesIO
import pandas as pd
import uuid


def test_uuid32_no_dashes_valid_with_dashes():
    # Test conversión de UUID con guiones a formato sin guiones
    uid = "550e8400-e29b-41d4-a716-446655440000"
    result = _uuid32_no_dashes(uid)
    assert result == "550e8400e29b41d4a716446655440000"
    assert len(result) == 32


def test_uuid32_no_dashes_valid_without_dashes():
    # Test UUID ya sin guiones se mantiene igual
    uid = "550e8400e29b41d4a716446655440000"
    result = _uuid32_no_dashes(uid)
    assert result == uid


def test_uuid32_no_dashes_invalid_format():
    # Test UUID con formato inválido lanza error
    with pytest.raises(ValueError, match="id_pagina inválido"):
        _uuid32_no_dashes("invalid-uuid-format")


def test_uuid32_generates_valid_format():
    # Test generación de UUID en formato 32 caracteres
    result = uuid32()
    assert len(result) == 32
    assert result.islower()
    assert all(c in "0123456789abcdef" for c in result)


def test_uuid32_from_uuid_object():
    # Test conversión de objeto UUID a string de 32 caracteres
    uid = uuid.uuid4()
    result = uuid32(uid)
    assert len(result) == 32
    assert str(uid).replace("-", "") == result


def test_hash_password_generates_valid_hash():
    # Test que hash_password genera un hash válido de Argon2
    plain = "p4s5word123!"
    hashed = hash_password(plain)
    
    # Verifica formato Argon2
    assert hashed.startswith("$argon2")
    assert len(hashed) > 50


def test_verify_password_correct():
    # Test verificación de password correcta
    plain = "p4s5word123!"
    hashed = hash_password(plain)
    
    assert verify_password(hashed, plain) is True

@pytest.mark.django_db
def test_duplicar_formulario_basic(categoria):
    # Test duplicación básica de formulario sin páginas ni campos
    original = Formulario.objects.create(
        categoria=categoria,
        nombre="Original",
        descripcion="Descripción original",
        permitir_fotos=True,
        permitir_gps=False,
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Activo",
        forma_envio="En Linea",
        es_publico=False,
        auto_envio=False,
    )
    
    clon = duplicar_formulario(original, "Clon del Original")
    
    # Verificar que se creó el clon
    assert clon.id != original.id
    assert clon.nombre == "Clon del Original"
    assert clon.descripcion == original.descripcion
    assert clon.permitir_fotos == original.permitir_fotos
    assert clon.categoria == original.categoria


@pytest.mark.django_db
def test_duplicar_formulario_with_default_name(categoria):
    # Test duplicación sin especificar nuevo nombre
    original = Formulario.objects.create(
        categoria=categoria,
        nombre="Original",
        descripcion="Test",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Activo",
        forma_envio="En Linea",
    )
    
    clon = duplicar_formulario(original)
    
    assert clon.nombre == "Original_Copia"


@pytest.mark.django_db(transaction=True)
def test_duplicar_formulario_con_paginas_y_campos(categoria):
    # Crear formulario original
    original = Formulario.objects.create(
        categoria=categoria,
        nombre="Original Completo",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Activo",
        forma_envio="En Linea",
    )
    
    # Esperar a que se ejecute el signal
    from django.db import connection
    connection.cursor().execute("SELECT 1")  # Force commit
    
    # Crear versión
    version_orig = FormularioIndexVersion.objects.filter(formulario_id=original).first()
    if not version_orig:
        version_orig = FormularioIndexVersion.objects.create(formulario_id=original)
    
    # Crear página
    pagina_orig = Pagina.objects.create(
        index_version=version_orig,
        formulario_id=original,
        secuencia=1,
        nombre="Página 1",
        descripcion="Descripción página 1",
    )
    
    # Crear ClaseCampo si no existe
    ClaseCampo.objects.get_or_create(clase="string", defaults={"estructura": "{}"})
    
    # Crear campo
    campo_orig = Campo.objects.create(
        tipo="texto",
        clase="string",
        nombre_campo="campo_test",
        etiqueta="Campo de Prueba",
        ayuda="Ayuda del campo",
        config="{}",
        requerido=True,
    )
    
    # Crear PaginaVersion con timezone aware
    from formularios.services import uuid32
    pv_orig = PaginaVersion.objects.create(
        id_pagina_version=uuid32(),
        id_pagina=_uuid32_no_dashes(str(pagina_orig.id_pagina)),
        fecha_creacion=timezone.now(),
    )
    
    # Enlazar campo con página
    PaginaCampo.objects.create(
        id_campo=campo_orig,
        id_pagina_version=pv_orig,
        sequence=1,
    )
    
    # Duplicar
    clon = duplicar_formulario(original, "Clon Completo")
    
    # Verificaciones
    assert clon.id != original.id
    assert clon.nombre == "Clon Completo"
    
    # Verificar que se creó nueva versión
    version_clon = FormularioIndexVersion.objects.filter(formulario_id=clon).first()
    assert version_clon is not None
    assert version_clon.id_index_version != version_orig.id_index_version
    
    # Verificar que se clonaron las páginas
    paginas_clon = Pagina.objects.filter(formulario_id=clon)
    assert paginas_clon.count() >= 1  # Al menos 1 (puede tener la del signal + la clonada)

@pytest.mark.django_db
def test_crear_campo_y_versionar_sin_clase_falla(categoria):
    # Test que falla si no se proporciona clase
    formulario = Formulario.objects.create(
        categoria=categoria,
        nombre="Form Test",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Activo",
        forma_envio="En Linea",
    )
    
    version = FormularioIndexVersion.objects.create(formulario_id=formulario)
    
    pagina = Pagina.objects.create(
        index_version=version,
        formulario_id=formulario,
        secuencia=1,
        nombre="Página Test",
    )
    
    data = {
        "nombre_campo": "test_field",
        "etiqueta": "Campo de Prueba",
    }
    
    with pytest.raises(ValidationError, match="clase.*obligatorio"):
        crear_campo_y_versionar_pagina(pagina, data)


@pytest.mark.django_db
def test_crear_campo_clase_invalida_falla(categoria):
    # Test que falla si la clase no existe
    formulario = Formulario.objects.create(
        categoria=categoria,
        nombre="Form Test",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Activo",
        forma_envio="En Linea",
    )
    
    version = FormularioIndexVersion.objects.create(formulario_id=formulario)
    
    pagina = Pagina.objects.create(
        index_version=version,
        formulario_id=formulario,
        secuencia=1,
        nombre="Página Test",
    )
    
    data = {
        "clase": "clase_inexistente",
        "nombre_campo": "test_field",
        "etiqueta": "Campo de Prueba",
    }
    
    with pytest.raises(ValidationError, match="clase.*no existe"):
        crear_campo_y_versionar_pagina(pagina, data)

@pytest.mark.django_db
def test_crear_campo_en_pagina_basic(categoria):
    # Test creación de campo en página existente
    # Setup
    formulario = Formulario.objects.create(
        categoria=categoria,
        nombre="Form Test",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Activo",
        forma_envio="En Linea",
    )
    
    version = FormularioIndexVersion.objects.create(formulario_id=formulario)
    
    pagina = Pagina.objects.create(
        index_version=version,
        formulario_id=formulario,
        secuencia=1,
        nombre="Página Test",
    )
    
    ClaseCampo.objects.get_or_create(clase="text", defaults={"estructura": "{}"})
    
    payload = {
        "clase": "text",
        "nombre_campo": "campo_texto",
        "etiqueta": "Campo de Texto",
        "ayuda": "Ingrese texto",
        "requerido": True,
        "config": {"maxlength": 100},
    }
    
    id_pagina = str(pagina.id_pagina)
    
    result = crear_campo_en_pagina(id_pagina, payload)
    
    # Verificaciones
    assert "id_campo" in result
    assert result["nombre_campo"] == "campo_texto"
    assert result["etiqueta"] == "Campo de Texto"
    assert result["tipo"] == "text"


@pytest.mark.django_db
def test_crear_campo_en_pagina_clase_invalida():
    # Test que falla con clase inexistente
    from django.core.exceptions import ValidationError
    
    payload = {
        "clase": "clase_que_no_existe",
        "nombre_campo": "campo_test",
        "etiqueta": "Test",
    }
    
    with pytest.raises(ValidationError, match="clase.*no existe"):
        crear_campo_en_pagina("550e8400e29b41d4a716446655440000", payload)