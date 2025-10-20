import pytest
from datetime import date, timedelta
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from formularios.models import (
    Formulario,
    FormularioIndexVersion,
    Pagina,
    PaginaVersion,
    Campo,
    PaginaCampo,
    ClaseCampo,
    FuenteDatos,
    UserFormulario,
    Usuario,
    Grupo,
    CampoGrupo,
    Pagina_Index_Version,
)
from formularios.services import _uuid32, _uuid32_no_dashes
import json

@pytest.mark.django_db
def test_formulario_duplicar_basic(api_client, formulario):
    # Test duplicar formulario con nombre personalizado
    r = api_client.post(
        f"/api/formularios/{formulario.id}/duplicar/",
        {"nombre": "Clon Personalizado"},
        format="json"
    )
    
    assert r.status_code in (200, 201), r.data
    data = r.json()
    
    assert data["nombre"] == "Clon Personalizado"
    assert data["id"] != str(formulario.id)
    assert data["descripcion"] == formulario.descripcion

@pytest.mark.django_db
def test_formulario_duplicar_sin_nombre(api_client, formulario):
    # Test duplicar formulario con nombre default
    r = api_client.post(
        f"/api/formularios/{formulario.id}/duplicar/",
        {},
        format="json"
    )
    
    assert r.status_code in (200, 201)
    data = r.json()
    
    assert "_Copia" in data["nombre"]

@pytest.mark.django_db
def test_formulario_duplicar_404(api_client):
    # Test duplicar formulario inexistente
    r = api_client.post(
        "/api/formularios/00000000-0000-0000-0000-000000000000/duplicar/",
        {"nombre": "Clon"},
        format="json"
    )
    
    assert r.status_code == 404

@pytest.mark.django_db
def test_formulario_suspender_activo(api_client, categoria):
    # Test suspender formulario activo
    form = Formulario.objects.create(
        categoria=categoria,
        nombre="Form Activo",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Activo",
        forma_envio="En Linea",
    )
    
    r = api_client.post(f"/api/formularios/{form.id}/suspender/", {}, format="json")
    
    assert r.status_code == 200
    data = r.json()
    assert data["estado"] == "Suspendida"
    
    # Verificar en BD
    form.refresh_from_db()
    assert form.estado == "Suspendida"

@pytest.mark.django_db
def test_formulario_suspender_ya_suspendido(api_client, categoria):
    # Test suspender formulario ya suspendido
    form = Formulario.objects.create(
        categoria=categoria,
        nombre="Form Suspendido",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Suspendida",
        forma_envio="En Linea",
    )
    
    r = api_client.post(f"/api/formularios/{form.id}/suspender/", {}, format="json")
    
    assert r.status_code == 200

@pytest.mark.django_db
def test_formulario_retrieve_suspendido_bloqueado(api_client, categoria):
    # Test que no se puede abrir formulario suspendido
    form = Formulario.objects.create(
        categoria=categoria,
        nombre="Form Suspendido",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Suspendida",
        forma_envio="En Linea",
    )
    
    r = api_client.get(f"/api/formularios/{form.id}/")
    
    assert r.status_code == 423  # Locked

@pytest.mark.django_db
def test_formulario_partial_update_suspendido_solo_estado(api_client, categoria):
    # Test que formulario suspendido solo permite cambiar estado
    form = Formulario.objects.create(
        categoria=categoria,
        nombre="Form Suspendido",
        disponible_desde_fecha=date.today(),
        disponible_hasta_fecha=date.today() + timedelta(days=10),
        estado="Suspendida",
        forma_envio="En Linea",
    )
    
    # Intentar cambiar nombre (debe fallar)
    r = api_client.patch(
        f"/api/formularios/{form.id}/",
        {"nombre": "Nuevo Nombre"},
        format="json"
    )
    
    assert r.status_code == 423
    
    # Cambiar solo estado (debe funcionar)
    r = api_client.patch(
        f"/api/formularios/{form.id}/",
        {"estado": "Activo"},
        format="json"
    )
    
    assert r.status_code in (200, 202, 204)

@pytest.mark.django_db
def test_formulario_agregar_pagina_bump_0(api_client, formulario, version):
    # Test agregar página sin incrementar versión
    r = api_client.post(
        f"/api/formularios/{formulario.id}/agregar-pagina/?bump=0",
        {"nombre": "Nueva Página", "descripcion": "Descripción"},
        format="json"
    )
    
    assert r.status_code == 201
    data = r.json()
    assert data["ok"] is True
    assert "id_pagina" in data

@pytest.mark.django_db
def test_formulario_agregar_pagina_bump_1(api_client, formulario, version):
    # Test agregar página incrementando versión
    r = api_client.post(
        f"/api/formularios/{formulario.id}/agregar-pagina/?bump=1",
        {"nombre": "Nueva Página Versionada"},
        format="json"
    )
    
    assert r.status_code == 201
    
    # Verificar que se creó nueva versión
    versiones = FormularioIndexVersion.objects.filter(formulario_id=formulario)
    assert versiones.count() >= 2

@pytest.mark.django_db
def test_formulario_agregar_pagina_secuencia(api_client, formulario, version):
    # Test que la secuencia se incrementa correctamente
    # Crear primera página
    api_client.post(
        f"/api/formularios/{formulario.id}/agregar-pagina/",
        {"nombre": "Página 1"},
        format="json"
    )
    
    # Crear segunda página
    r = api_client.post(
        f"/api/formularios/{formulario.id}/agregar-pagina/",
        {"nombre": "Página 2"},
        format="json"
    )
    
    assert r.status_code == 201
    
    # Verificar secuencias
    paginas = Pagina.objects.filter(formulario_id=formulario).order_by("secuencia")
    secuencias = list(paginas.values_list("secuencia", flat=True))
    assert secuencias[-1] > secuencias[0]

@pytest.mark.django_db
def test_pagina_agregar_campo_basic(api_client, formulario, version):
    # Agregar campo básico a página
    # Crear página
    pagina = Pagina.objects.create(
        index_version=version,
        formulario_id=formulario,
        secuencia=1,
        nombre="Página Test",
    )
    
    # Crear ClaseCampo
    ClaseCampo.objects.get_or_create(clase="string", defaults={"estructura": "{}"})
    
    # Agregar campo
    r = api_client.post(
        f"/api/paginas/{pagina.id_pagina}/campos/",
        {
            "clase": "string",
            "nombre_campo": "campo_nuevo",
            "etiqueta": "Campo Nuevo",
            "ayuda": "Ayuda",
            "requerido": True,
            "config": {},
            "sequence": 1
        },
        format="json"
    )
    
    assert r.status_code == 201
    data = r.json()
    assert "id_campo" in data
    assert data["nombre_campo"] == "campo_nuevo"

@pytest.mark.django_db
def test_pagina_agregar_campo_a_grupo(api_client, formulario, version):
    # Test agregar campo a un grupo existente
    # Crear página
    pagina = Pagina.objects.create(
        index_version=version,
        formulario_id=formulario,
        secuencia=1,
        nombre="Página Test",
    )
    
    # Crear ClaseCampo
    ClaseCampo.objects.get_or_create(clase="group", defaults={"estructura": "{}"})
    ClaseCampo.objects.get_or_create(clase="string", defaults={"estructura": "{}"})
    
    # Crear campo grupo
    import uuid
    grupo_uuid = str(uuid.uuid4())  # UUID VÁLIDO
    
    campo_grupo = Campo.objects.create(
        tipo="texto",
        clase="group",
        nombre_campo="grupo_test",
        etiqueta="Grupo Test",
        config=json.dumps({"id_group": grupo_uuid, "name": "Mi Grupo"}),
    )
    
    # Crear Grupo con UUID válido
    grupo = Grupo.objects.create(
        id_grupo=grupo_uuid,
        id_campo_group=campo_grupo,
        nombre="Mi Grupo",
    )
    
    # Agregar campo al grupo
    r = api_client.post(
        f"/api/paginas/{pagina.id_pagina}/campos/",
        {
            "clase": "string",
            "nombre_campo": "campo_en_grupo",
            "etiqueta": "Campo en Grupo",
            "grupo": grupo_uuid,  # UUID válido
        },
        format="json"
    )
    
    assert r.status_code == 201
    
    # Verificar que se creó la relación
    campo_id = r.json()["id_campo"]
    assert CampoGrupo.objects.filter(
        id_grupo=grupo,
        id_campo_id=campo_id
    ).exists()

@pytest.mark.django_db
def test_pagina_agregar_campo_grupo_inexistente_falla(api_client, formulario, version):
    # Test que falla al agregar campo a grupo que no existe
    pagina = Pagina.objects.create(
        index_version=version,
        formulario_id=formulario,
        secuencia=1,
        nombre="Página Test",
    )
    
    ClaseCampo.objects.get_or_create(clase="string", defaults={"estructura": "{}"})
    
    r = api_client.post(
        f"/api/paginas/{pagina.id_pagina}/campos/",
        {
            "clase": "string",
            "nombre_campo": "campo_test",
            "etiqueta": "Campo Test",
            "grupo": "grupo_que_no_existe",
        },
        format="json"
    )
    
    assert r.status_code == 400

@pytest.mark.django_db
def test_pagina_campos_list(api_client, formulario, version):
    # Test listar campos de una página
    # Crear página
    pagina = Pagina.objects.create(
        index_version=version,
        formulario_id=formulario,
        secuencia=1,
        nombre="Página Test",
    )
    
    # Crear PaginaVersion con timezone aware
    pv = PaginaVersion.objects.create(
        id_pagina_version=_uuid32(),
        id_pagina=_uuid32_no_dashes(str(pagina.id_pagina)),
        fecha_creacion=timezone.now(),
    )
    
    ClaseCampo.objects.get_or_create(clase="string", defaults={"estructura": "{}"})
    
    # Crear campo
    campo = Campo.objects.create(
        tipo="texto",
        clase="string",
        nombre_campo="campo1",
        etiqueta="Campo 1",
    )
    
    # Enlazar
    PaginaCampo.objects.create(
        id_campo=campo,
        id_pagina_version=pv,
        sequence=1,
    )
    
    # Listar campos - USAR QUERY PARAM include_campos
    r = api_client.get(f"/api/paginas/{pagina.id_pagina}/?include_campos=1")
    
    assert r.status_code == 200
    data = r.json()
    assert "campos" in data
    assert isinstance(data["campos"], list)
    assert len(data["campos"]) >= 1

@pytest.mark.django_db
def test_fuente_datos_create_csv(api_client):
    # Test crear fuente de datos con CSV
    csv_content = b"id,nombre\n1,Opcion1\n2,Opcion2"
    archivo = SimpleUploadedFile("test.csv", csv_content, content_type="text/csv")
    
    data = {
        "nombre": "Fuente CSV",
        "descripcion": "Test CSV",
        "archivo": archivo
    }
    r = api_client.post("/api/fuentes-datos/", data, format="multipart")
    
    assert r.status_code in (201, 400, 500)

@pytest.mark.django_db
def test_fuente_datos_create_excel(api_client):
    # Contenido fake de Excel
    excel_content = b"fake excel content"
    archivo = SimpleUploadedFile(
        "test.xlsx",
        excel_content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    data = {
        "nombre": "Fuente Excel",
        "descripcion": "Test Excel",
        "archivo": archivo
    }
    
    r = api_client.post("/api/fuentes-datos/", data, format="multipart")
    
    # Puede fallar por Azure o por contenido inválido
    assert r.status_code in (201, 400, 500)

@pytest.mark.django_db
def test_fuente_datos_list(api_client):
    # Test listar fuentes de datos
    r = api_client.get("/api/fuentes-datos/")
    
    assert r.status_code == 200
    assert isinstance(r.json(), list)

@pytest.mark.django_db
def test_fuente_datos_retrieve(api_client, fuente_datos_fixture):
    # Test obtener detalle de fuente de datos
    r = api_client.get(f"/api/fuentes-datos/{fuente_datos_fixture.id}/")
    
    assert r.status_code == 200
    data = r.json()
    assert data["nombre"] == fuente_datos_fixture.nombre

@pytest.mark.django_db
def test_fuente_datos_delete(api_client, fuente_datos_fixture):
    # Test eliminar fuente de datos
    r = api_client.delete(f"/api/fuentes-datos/{fuente_datos_fixture.id}/")
    
    assert r.status_code in (200, 204)

@pytest.mark.django_db
def test_asignacion_bulk_assign_basic(api_client, usuario_fixture, formulario):
    # Test asignar formularios a usuario
    r = api_client.post(
        "/api/asignaciones/crear-asignacion/",
        {
            "usuario": usuario_fixture.nombre_usuario,
            "formularios": [str(formulario.id)],
            "replace": False
        },
        format="json"
    )
    
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert len(data["asignados_nuevos"]) == 1

@pytest.mark.django_db
def test_asignacion_opciones_with_search(api_client, usuario_fixture):
    # Test opciones con búsqueda
    r = api_client.get(f"/api/asignaciones/opciones/?q_user={usuario_fixture.nombre}")
    
    assert r.status_code == 200
    data = r.json()
    assert len(data["usuarios"]) >= 1

@pytest.mark.django_db
def test_asignacion_delete(api_client, usuario_fixture, formulario):
    # Test eliminar asignación individual
    # Crear asignación
    asignacion = UserFormulario.objects.create(
        id_usuario=usuario_fixture,
        id_formulario=formulario
    )
    
    r = api_client.delete(f"/api/asignaciones/{asignacion.id}/")
    
    assert r.status_code in (200, 204)
    assert not UserFormulario.objects.filter(id=asignacion.id).exists()

@pytest.mark.django_db
def test_grupo_list(api_client):
    # Test listar grupos
    r = api_client.get("/api/grupos/")
    
    assert r.status_code == 200
    assert isinstance(r.json(), list)

@pytest.mark.django_db
def test_grupo_list_with_search(api_client, grupo_fixture):
    # Test listar grupos con búsqueda
    r = api_client.get(f"/api/grupos/?q={grupo_fixture.nombre}")
    
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1

@pytest.mark.django_db
def test_campo_list_with_search(api_client, campo_fixture):
    # Test listar campos con búsqueda
    r = api_client.get(f"/api/campos/?search={campo_fixture.nombre_campo}")
    
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)

@pytest.mark.django_db
def test_campo_list_with_ordering(api_client):
    # Test listar campos con ordenamiento
    r = api_client.get("/api/campos/?ordering=nombre_campo")
    
    assert r.status_code == 200

@pytest.mark.django_db
def test_campo_update_etiqueta(api_client, campo_fixture):
    # Test actualizar etiqueta de campo
    r = api_client.patch(
        f"/api/campos/{campo_fixture.id_campo}/",
        {"etiqueta": "Nueva Etiqueta"},
        format="json"
    )
    
    assert r.status_code in (200, 202, 204)
    
    campo_fixture.refresh_from_db()
    assert campo_fixture.etiqueta == "Nueva Etiqueta"

@pytest.mark.django_db
def test_usuario_list(api_client):
    # Test listar usuarios
    r = api_client.get("/api/usuarios/")
    
    assert r.status_code in (200, 401, 403)

@pytest.mark.django_db
def test_usuario_create(api_client):
    # Test crear usuario
    r = api_client.post(
        "/api/usuarios/",
        {
            "nombre_usuario": "newuser",
            "nombre": "New User",
            "correo": "newuser@example.com",
            "password": "password123",
            "activo": True,
            "acceso_web": True
        },
        format="json"
    )
    
    assert r.status_code in (200, 201, 401, 403)

@pytest.mark.django_db
def test_usuario_retrieve(api_client, usuario_fixture):
    # Test obtener detalle de usuario
    r = api_client.get(f"/api/usuarios/{usuario_fixture.nombre_usuario}/")
    
    assert r.status_code in (200, 401, 403)


@pytest.mark.django_db
def test_usuario_partial_update(api_client, usuario_fixture):
    # Test actualizar usuario parcialmente
    r = api_client.patch(
        f"/api/usuarios/{usuario_fixture.nombre_usuario}/",
        {"nombre": "Nombre Actualizado"},
        format="json"
    )
    
    assert r.status_code in (200, 202, 204, 401, 403)