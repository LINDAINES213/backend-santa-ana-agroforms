import pytest
from django.utils import timezone
from django.core.exceptions import ValidationError

from formularios.models import (
    Formulario, Categoria, FormularioIndexVersion, Pagina, Campo,
    FormularioActualVersion, PaginaActualVersion
)
from formularios.services import (
    duplicar_formulario, activar_version, delete_formulario_hard,
    crear_campo_bumpeando_version_actual
)


def _create_basic_form():
    cat = Categoria.objects.create(nombre='C', descripcion='')
    return Formulario.objects.create(
        categoria=cat, nombre='F0', descripcion='',
        permitir_fotos=False, permitir_gps=False,
        disponible_desde_fecha='2024-01-01', disponible_hasta_fecha='2024-12-31',
        estado='Activa', forma_envio='En Linea', es_publico=False, auto_envio=False
    )


def test_duplicate_no_version_copy_0_pages(db):
    f = _create_basic_form()
    res = duplicar_formulario(f.id)
    assert res['ok'] is True
    assert res['paginas_copiadas'] == 0


def test_duplicate_with_pages_copy_everything(db):
    f = _create_basic_form()
    v = FormularioIndexVersion.objects.create(formulario=f)
    p1 = Pagina.objects.create(index_version=v, formulario=f, secuencia=1, nombre='P1', descripcion='')
    p2 = Pagina.objects.create(index_version=v, formulario=f, secuencia=2, nombre='P2', descripcion='')
    Campo.objects.create(pagina=p1, tipo='text', clase='base', nombre_campo='c1', etiqueta='C1', ayuda='', config={}, requerido=False, sequence=1)
    Campo.objects.create(pagina=p2, tipo='text', clase='base', nombre_campo='c2', etiqueta='C2', ayuda='', config={}, requerido=True, sequence=1)

    res = duplicar_formulario(f.id)
    assert res['ok'] is True
    assert res['paginas_copiadas'] == 2
    assert res['formulario_nuevo_id'] != str(f.id)


def test_activate_version_sets_current_index_version(db):
    f = _create_basic_form()
    v = FormularioIndexVersion.objects.create(formulario=f)
    p = Pagina.objects.create(index_version=v, formulario=f, secuencia=1, nombre='P', descripcion='')
    Campo.objects.create(pagina=p, tipo='text', clase='base', nombre_campo='x', etiqueta='X', ayuda='',
                         config={}, requerido=True, sequence=1)

    fva = activar_version(f, v)
    assert isinstance(fva, FormularioActualVersion)
    assert fva.index_version_id == v.id_index_version


def test_activate_version_invalidate_raises(db):
    f1 = _create_basic_form()
    f2 = _create_basic_form()
    v2 = FormularioIndexVersion.objects.create(formulario=f2)
    with pytest.raises(ValidationError):
        activar_version(f1, v2)


def test_delete_form_hard_not_found(db):
    res = delete_formulario_hard("00000000-0000-0000-0000-000000000000")
    assert res['ok'] is False


def test_delete_form_hard_ok(db):
    f = _create_basic_form()
    v = FormularioIndexVersion.objects.create(formulario=f)
    Pagina.objects.create(index_version=v, formulario=f, secuencia=1, nombre='P', descripcion='')
    res = delete_formulario_hard(f.id)
    assert res['ok'] is True


def test_post_new_version_per_change(db):
    f = _create_basic_form()
    v = FormularioIndexVersion.objects.create(formulario=f)
    p = Pagina.objects.create(index_version=v, formulario=f, secuencia=1, nombre='P', descripcion='')

    # activar versión actual
    activar_version(f, v)

    res = crear_campo_bumpeando_version_actual(str(p.id_pagina), {
        "tipo": "text", "clase": "base", "nombre_campo": "nuevo", "etiqueta": "Nuevo",
        "ayuda": "", "config": {}, "requerido": False, "sequence": None
    })

    assert res["ok"] is True
    assert res["campo"].nombre_campo == "nuevo"
    assert res["version_nueva_id"] != v.id_index_version

    assert FormularioActualVersion.objects.get(formulario=f).index_version_id == res["version_nueva_id"]
