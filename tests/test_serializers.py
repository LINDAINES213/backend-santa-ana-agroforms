from formularios.serializers import CategoriaSerializer, FormularioSerializer, PaginaSerializer, UsuarioSerializer
from formularios.models import Formulario, Categoria, FormularioIndexVersion, Pagina, Rol, Usuario

def test_category_serializer_validates_required_fields():
    s = CategoriaSerializer(data={})  # falta 'nombre'
    assert not s.is_valid()
    assert 'nombre' in s.errors

def test_formulario_serializer_category_nombre(db):
    cat = Categoria.objects.create(nombre='CatZ', descripcion='')
    f = Formulario.objects.create(categoria=cat, nombre='F', descripcion='', permitir_fotos=False, permitir_gps=False,
                                  disponible_desde_fecha='2024-01-01', disponible_hasta_fecha='2024-12-31',
                                  estado='Activa', forma_envio='En Linea', es_publico=False, auto_envio=False)
    s = FormularioSerializer(instance=f)
    assert s.data['categoria_nombre'] == 'CatZ'

def test_pagina_serializer_includes_form_id(db):
    cat = Categoria.objects.create(nombre='Cat', descripcion='')
    f = Formulario.objects.create(
        categoria=cat, nombre='F1', descripcion='',
        permitir_fotos=False, permitir_gps=False,
        disponible_desde_fecha='2024-01-01', disponible_hasta_fecha='2024-12-31',
        estado='Activa', forma_envio='En Linea', es_publico=False, auto_envio=False
    )
    ver = FormularioIndexVersion.objects.create(formulario=f)
    p = Pagina.objects.create(index_version=ver, formulario=f, secuencia=1, nombre='P', descripcion='')
    s = PaginaSerializer(instance=p)
    assert str(s.data['formulario']) == str(f.id)

def test_usuario_serializer_role_name(db):
    rol = Rol.objects.create(nombre='admin', descripcion='')
    u = Usuario.objects.create(nombre='Ana', correo='a@a.com', contrasena='x', nombre_usuario='ana', activo=True, rol=rol)
    s = UsuarioSerializer(instance=u)
    assert s.data['rol_nombre'] == 'admin'

def test_pagina_serializer_has_expected_fields(db):
    cat = Categoria.objects.create(nombre='Cat', descripcion='')
    f = Formulario.objects.create(
        categoria=cat, nombre='F2', descripcion='',
        permitir_fotos=False, permitir_gps=False,
        disponible_desde_fecha='2024-01-01', disponible_hasta_fecha='2024-12-31',
        estado='Activa', forma_envio='En Linea', es_publico=False, auto_envio=False
    )
    ver = FormularioIndexVersion.objects.create(formulario=f)
    p = Pagina.objects.create(index_version=ver, formulario=f, secuencia=9, nombre='P9', descripcion='x')
    s = PaginaSerializer(instance=p)
    assert s.data['nombre'] == 'P9'
    assert 'id_pagina' in s.data
