import pytest
from datetime import datetime
from io import BytesIO
from zipfile import ZipFile
import pandas as pd
import json
from django.utils import timezone
from formularios.exports import (
    _to_naive_local,
    _sanitize_filename,
    _build_field_catalog,
    _flatten_entry_row,
    dataframe_por_form,
    excel_bytes_para_un_form,
    content_bytes_para_un_form,
    zip_bytes_todos_los_forms,
)
from formularios.models import FormularioEntry
import uuid as uuid_lib


def test_to_naive_local_none():
    # Test que None retorna None
    assert _to_naive_local(None) is None


def test_to_naive_local_naive_datetime():
    # Test que datetime naive se retorna sin cambios
    dt = datetime(2025, 1, 15, 10, 30, 0)
    result = _to_naive_local(dt)
    assert result == dt
    assert result.tzinfo is None


def test_to_naive_local_aware_datetime():
    # Test que datetime aware se convierte a naive local
    dt = timezone.make_aware(datetime(2025, 1, 15, 10, 30, 0))
    result = _to_naive_local(dt)
    
    assert result.tzinfo is None
    assert isinstance(result, datetime)


def test_sanitize_filename_normal():
    # Test sanitización de nombre normal
    result = _sanitize_filename("Mi Formulario 2025")
    assert result == "Mi Formulario 2025"


def test_sanitize_filename_special_chars():
    # Test que elimina caracteres especiales
    result = _sanitize_filename("Form@#$%^&*ario!")
    assert "@" not in result
    assert "#" not in result
    assert "*" not in result


def test_sanitize_filename_max_length():
    # Test que respeta longitud máxima
    long_name = "a" * 100
    result = _sanitize_filename(long_name, maxlen=60)
    assert len(result) == 60


def test_sanitize_filename_empty():
    # Test que nombre vacío devuelve 'export'
    result = _sanitize_filename("")
    assert result == "export"


def test_sanitize_filename_preserves_allowed():
    # Test que preserva caracteres permitidos
    result = _sanitize_filename("Form_2025-v1.0 (final)")
    assert "_" in result
    assert "-" in result
    assert "." in result
    assert "(" in result
    assert ")" in result


def test_build_field_catalog_empty():
    # Test con form_json vacío
    result = _build_field_catalog({})
    assert result == []


def test_build_field_catalog_no_paginas():
    # Test con form_json sin páginas
    form_json = {"nombre": "Form Test"}
    result = _build_field_catalog(form_json)
    assert result == []


def test_build_field_catalog_basic():
    # Test construcción básica de catálogo
    form_json = {
        "paginas": [
            {
                "id_pagina": "page1",
                "campos": [
                    {
                        "id_campo": "campo1",
                        "nombre_interno": "nombre",
                        "etiqueta": "Nombre Completo",
                        "clase": "string",
                        "tipo": "texto",
                        "requerido": True,
                        "sequence": 1
                    },
                    {
                        "id_campo": "campo2",
                        "nombre_interno": "edad",
                        "etiqueta": "Edad",
                        "clase": "number",
                        "tipo": "numerico",
                        "requerido": False,
                        "sequence": 2
                    }
                ]
            }
        ]
    }
    
    result = _build_field_catalog(form_json)
    
    assert len(result) == 2
    assert result[0]["id_campo"] == "campo1"
    assert result[0]["etiqueta"] == "Nombre Completo"
    assert result[1]["id_campo"] == "campo2"


def test_build_field_catalog_multiple_pages():
    # Test con múltiples páginas
    form_json = {
        "paginas": [
            {
                "id_pagina": "page1",
                "campos": [{"id_campo": "c1", "etiqueta": "Campo 1", "sequence": 1}]
            },
            {
                "id_pagina": "page2",
                "campos": [{"id_campo": "c2", "etiqueta": "Campo 2", "sequence": 2}]
            }
        ]
    }
    
    result = _build_field_catalog(form_json)
    assert len(result) == 2


def test_build_field_catalog_sorted_by_sequence():
    # Test que ordena por sequence
    form_json = {
        "paginas": [
            {
                "id_pagina": "page1",
                "campos": [
                    {"id_campo": "c3", "etiqueta": "Campo 3", "sequence": 3},
                    {"id_campo": "c1", "etiqueta": "Campo 1", "sequence": 1},
                    {"id_campo": "c2", "etiqueta": "Campo 2", "sequence": 2},
                ]
            }
        ]
    }
    
    result = _build_field_catalog(form_json)
    
    assert result[0]["id_campo"] == "c1"
    assert result[1]["id_campo"] == "c2"
    assert result[2]["id_campo"] == "c3"


@pytest.mark.django_db
def test_flatten_entry_row_with_fields(formulario_entry_with_fields):
    # Test con campos de respuesta
    result = _flatten_entry_row(formulario_entry_with_fields)
    
    # Verificar metadatos
    assert "Nombre Formulario" in result
    assert "Usuario" in result
    
    # Verificar campos de respuesta
    assert "Nombre" in result
    assert result["Nombre"] == "Juan Pérez"


@pytest.mark.django_db
def test_flatten_entry_row_boolean_field(formulario_entry_boolean):
    # Test normalización de campo booleano
    result = _flatten_entry_row(formulario_entry_boolean)
    
    assert "Acepta Términos" in result
    assert isinstance(result["Acepta Términos"], bool)


@pytest.mark.django_db
def test_flatten_entry_row_dataset_field(formulario_entry_dataset):
    # Test normalización de campo dataset
    result = _flatten_entry_row(formulario_entry_dataset)
    
    assert "País" in result
    # Debe extraer el label del dataset
    assert result["País"] in ["Guatemala", "México", "Honduras"]


@pytest.mark.django_db
def test_flatten_entry_row_missing_field():
    # Test con campo faltante en respuesta
    entry = FormularioEntry(
        id=str(uuid_lib.uuid4()),
        id_usuario="testuser",
        form_id=str(uuid_lib.uuid4()),
        index_version_id=str(uuid_lib.uuid4()),
        form_name="Form Test",
        filled_at_local=datetime(2025, 1, 15, 10, 0, 0),
        status="Completado",
        fill_json={},  # sin datos
        form_json={
            "paginas": [{
                "id_pagina": "page1",
                "campos": [{
                    "id_campo": "c1",
                    "nombre_interno": "nombre",
                    "etiqueta": "Nombre"
                }]
            }]
        },
        created_at=datetime(2025, 1, 15, 10, 0, 0),
        updated_at=datetime(2025, 1, 15, 10, 0, 0),
    )
    
    result = _flatten_entry_row(entry)
    
    # Campo debe existir pero con valor None
    assert "Nombre" in result
    assert result["Nombre"] is None


@pytest.mark.django_db
def test_dataframe_por_form_empty():
    # Test con formulario sin respuestas
    df = dataframe_por_form(str(uuid_lib.uuid4()))
    
    assert df.empty


@pytest.mark.django_db
def test_dataframe_por_form_with_entries(formulario_entries_multiple):
    # Test con múltiples respuestas
    form_id = formulario_entries_multiple[0].form_id
    df = dataframe_por_form(form_id)
    
    assert not df.empty
    assert len(df) == len(formulario_entries_multiple)
    
    # Verificar columnas esperadas
    assert "Nombre Formulario" in df.columns
    assert "Usuario" in df.columns
    assert "Status" in df.columns


@pytest.mark.django_db
def test_excel_bytes_empty_form():
    # Test exportación de formulario sin respuestas
    fname, content = excel_bytes_para_un_form(str(uuid_lib.uuid4()))
    
    assert fname.endswith(".xlsx")
    assert content == b""


@pytest.mark.django_db
def test_excel_bytes_with_entries(formulario_entries_multiple):
    # Test exportación con respuestas
    form_id = formulario_entries_multiple[0].form_id
    fname, content = excel_bytes_para_un_form(str(form_id))
    
    assert fname.endswith(".xlsx")
    assert len(content) > 0
    
    # Verificar que es un Excel válido
    excel_file = BytesIO(content)
    df_respuestas = pd.read_excel(excel_file, sheet_name="Respuestas")
    
    assert not df_respuestas.empty
    assert len(df_respuestas) == len(formulario_entries_multiple)


@pytest.mark.django_db
def test_content_bytes_xlsx(formulario_entries_multiple):
    # Test exportación en formato XLSX
    form_id = formulario_entries_multiple[0].form_id
    fname, content, mime = content_bytes_para_un_form(str(form_id), "xlsx")
    
    assert fname.endswith(".xlsx")
    assert mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert len(content) > 0


@pytest.mark.django_db
def test_content_bytes_csv(formulario_entries_multiple):
    # Test exportación en formato CSV
    form_id = formulario_entries_multiple[0].form_id
    fname, content, mime = content_bytes_para_un_form(str(form_id), "csv")
    
    assert fname.endswith(".csv")
    assert mime == "text/csv"
    assert len(content) > 0
    
    # Verificar que es CSV válido
    csv_file = BytesIO(content)
    df = pd.read_csv(csv_file)
    assert not df.empty


@pytest.mark.django_db
def test_content_bytes_json(formulario_entries_multiple):
    # Test exportación en formato JSON
    form_id = formulario_entries_multiple[0].form_id
    fname, content, mime = content_bytes_para_un_form(str(form_id), "json")
    
    assert fname.endswith(".json")
    assert mime == "application/json"
    assert len(content) > 0
    
    # Verificar que es JSON válido
    data = json.loads(content.decode("utf-8"))
    assert isinstance(data, list)
    assert len(data) == len(formulario_entries_multiple)


@pytest.mark.django_db
def test_content_bytes_invalid_format_defaults_xlsx(formulario_entries_multiple):
    # Test que formato inválido usa XLSX por defecto
    form_id = formulario_entries_multiple[0].form_id
    fname, content, mime = content_bytes_para_un_form(str(form_id), "invalid_format")
    
    assert fname.endswith(".xlsx")
    assert mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.mark.django_db
def test_content_bytes_empty_form():
    # Test con formulario sin datos
    fname, content, mime = content_bytes_para_un_form(str(uuid_lib.uuid4()), "xlsx")
    
    assert fname.endswith(".xlsx")
    assert content == b""


@pytest.mark.django_db
def test_zip_bytes_empty():
    # Test ZIP sin formularios
    fname, content = zip_bytes_todos_los_forms("xlsx")
    
    assert fname.endswith(".zip")
    assert len(content) > 0
    
    # Verificar que es un ZIP válido
    zip_file = ZipFile(BytesIO(content))
    assert len(zip_file.namelist()) == 0


@pytest.mark.django_db
def test_zip_bytes_multiple_forms(formulario_entries_multiple_forms):
    # Test ZIP con múltiples formularios
    fname, content = zip_bytes_todos_los_forms("xlsx")
    
    assert fname.endswith(".zip")
    assert len(content) > 0
    
    # Verificar contenido del ZIP
    zip_file = ZipFile(BytesIO(content))
    files = zip_file.namelist()
    
    # Debe haber múltiples archivos
    assert len(files) >= 2
    
    # Todos deben ser .xlsx
    for f in files:
        assert f.endswith(".xlsx")


@pytest.mark.django_db
def test_zip_bytes_csv_format(formulario_entries_multiple_forms):
    # Test ZIP con formato CSV
    fname, content = zip_bytes_todos_los_forms("csv")
    
    assert fname == "formularios_respuestas_csv.zip"
    
    zip_file = ZipFile(BytesIO(content))
    files = zip_file.namelist()
    
    # Todos deben ser .csv
    for f in files:
        assert f.endswith(".csv")


@pytest.mark.django_db
def test_zip_bytes_json_format(formulario_entries_multiple_forms):
    # Test ZIP con formato JSON
    fname, content = zip_bytes_todos_los_forms("json")
    
    assert fname == "formularios_respuestas_json.zip"
    
    zip_file = ZipFile(BytesIO(content))
    files = zip_file.namelist()
    
    # Todos deben ser .json
    for f in files:
        assert f.endswith(".json")


@pytest.mark.django_db
def test_zip_bytes_file_content_valid(formulario_entries_multiple_forms):
    # Test que los archivos dentro del ZIP son válidos
    fname, content = zip_bytes_todos_los_forms("xlsx")
    
    zip_file = ZipFile(BytesIO(content))
    
    # Leer primer archivo del ZIP
    first_file = zip_file.namelist()[0]
    file_content = zip_file.read(first_file)
    
    # Verificar que es un Excel válido
    excel_file = BytesIO(file_content)
    df = pd.read_excel(excel_file, sheet_name="Respuestas")
    
    assert not df.empty


# =============== FIXTURES ===============

@pytest.fixture
def formulario_entry_basic(db):
    # Fixture para entry básico
    return FormularioEntry.objects.create(
        id=str(uuid_lib.uuid4()),
        id_usuario="testuser",
        form_id=str(uuid_lib.uuid4()),
        index_version_id=str(uuid_lib.uuid4()),
        form_name="Formulario de Prueba",
        filled_at_local=timezone.now(),
        status="Completado",
        fill_json={},
        form_json={"paginas": []},
        created_at=timezone.now(),
        updated_at=timezone.now(),
    )


@pytest.fixture
def formulario_entry_with_fields(db):
    # Fixture para entry con campos
    return FormularioEntry.objects.create(
        id=str(uuid_lib.uuid4()),
        id_usuario="testuser",
        form_id=str(uuid_lib.uuid4()),
        index_version_id=str(uuid_lib.uuid4()),
        form_name="Formulario con Campos",
        filled_at_local=timezone.now(),
        status="Completado",
        fill_json={
            "page1": {
                "nombre": "Juan Pérez",
                "edad": "30"
            }
        },
        form_json={
            "paginas": [{
                "id_pagina": "page1",
                "campos": [
                    {
                        "id_campo": "c1",
                        "nombre_interno": "nombre",
                        "etiqueta": "Nombre",
                        "clase": "string"
                    },
                    {
                        "id_campo": "c2",
                        "nombre_interno": "edad",
                        "etiqueta": "Edad",
                        "clase": "number"
                    }
                ]
            }]
        },
        created_at=timezone.now(),
        updated_at=timezone.now(),
    )


@pytest.fixture
def formulario_entry_boolean(db):
    # Fixture para entry con campo booleano
    return FormularioEntry.objects.create(
        id=str(uuid_lib.uuid4()),
        id_usuario="testuser",
        form_id=str(uuid_lib.uuid4()),
        index_version_id=str(uuid_lib.uuid4()),
        form_name="Formulario Boolean",
        filled_at_local=timezone.now(),
        status="Completado",
        fill_json={
            "page1": {
                "acepta": "true"
            }
        },
        form_json={
            "paginas": [{
                "id_pagina": "page1",
                "campos": [{
                    "id_campo": "c1",
                    "nombre_interno": "acepta",
                    "etiqueta": "Acepta Términos",
                    "clase": "boolean"
                }]
            }]
        },
        created_at=timezone.now(),
        updated_at=timezone.now(),
    )


@pytest.fixture
def formulario_entry_dataset(db):
    # Fixture para entry con campo dataset
    return FormularioEntry.objects.create(
        id=str(uuid_lib.uuid4()),
        id_usuario="testuser",
        form_id=str(uuid_lib.uuid4()),
        index_version_id=str(uuid_lib.uuid4()),
        form_name="Formulario Dataset",
        filled_at_local=timezone.now(),
        status="Completado",
        fill_json={
            "page1": {
                "pais": {"id": "GT", "label": "Guatemala"}
            }
        },
        form_json={
            "paginas": [{
                "id_pagina": "page1",
                "campos": [{
                    "id_campo": "c1",
                    "nombre_interno": "pais",
                    "etiqueta": "País",
                    "clase": "dataset"
                }]
            }]
        },
        created_at=timezone.now(),
        updated_at=timezone.now(),
    )


@pytest.fixture
def formulario_entries_multiple(db):
    # Fixture para múltiples entries del mismo formulario
    form_id = str(uuid_lib.uuid4())
    version_id = str(uuid_lib.uuid4())
    entries = []
    
    for i in range(3):
        entry = FormularioEntry.objects.create(
            id=str(uuid_lib.uuid4()),
            id_usuario=f"user{i}",
            form_id=form_id,
            index_version_id=version_id,
            form_name="Formulario Multiple",
            filled_at_local=timezone.now(),
            status="Completado",
            fill_json={
                "page1": {
                    "nombre": f"Usuario {i}",
                }
            },
            form_json={
                "paginas": [{
                    "id_pagina": "page1",
                    "campos": [{
                        "id_campo": "c1",
                        "nombre_interno": "nombre",
                        "etiqueta": "Nombre"
                    }]
                }]
            },
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        entries.append(entry)
    
    return entries


@pytest.fixture
def formulario_entries_multiple_forms(db):
    # Fixture para entries de múltiples formularios
    entries = []
    
    for form_num in range(3):
        form_id = str(uuid_lib.uuid4())
        version_id = str(uuid_lib.uuid4())
        
        for i in range(2):
            entry = FormularioEntry.objects.create(
                id=str(uuid_lib.uuid4()),
                id_usuario=f"user{i}",
                form_id=form_id,
                index_version_id=version_id,
                form_name=f"Formulario {form_num}",
                filled_at_local=timezone.now(),
                status="Completado",
                fill_json={},
                form_json={"paginas": []},
                created_at=timezone.now(),
                updated_at=timezone.now(),
            )
            entries.append(entry)
    
    return entries


@pytest.fixture
def formulario_entry_special_name(db):
    # Fixture para entry con nombre especial
    return FormularioEntry.objects.create(
        id=str(uuid_lib.uuid4()),
        id_usuario="testuser",
        form_id=str(uuid_lib.uuid4()),
        index_version_id=str(uuid_lib.uuid4()),
        form_name="Form@#$%Test!",
        filled_at_local=timezone.now(),
        status="Completado",
        fill_json={},
        form_json={"paginas": []},
        created_at=timezone.now(),
        updated_at=timezone.now(),
    )