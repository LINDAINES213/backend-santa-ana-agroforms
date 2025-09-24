from formularios.models import Categoria, Rol, Usuario, Pagina, Formulario, FormularioIndexVersion

def test_category_str():
    c = Categoria.objects.create(nombre='Cat A', descripcion="")
    assert str(c) == 'Cat A'

def test_usuario_str_includes_estado_and_rol(db):
    r = Rol.objects.create(nombre='admin', descripcion='')
    u = Usuario.objects.create(nombre='Ana', correo='anita@yahoo.com', contrasena='x', nombre_usuario='ana', activo=False, rol=r)
    s = str(u)
    assert 'Inactivo' in s and 'admin' in s

def test_pagina_ordering_by_secuencia(db):
    f = Formulario.objects.create(categoria=None, nombre='F', descripcion='', permitir_fotos=False, permitir_gps=False,
                                  disponible_desde_fecha='2024-01-01', disponible_hasta_fecha='2024-12-31',
                                  estado='Activa', forma_envio='En Linea', es_publico=False, auto_envio=False)
    v = FormularioIndexVersion.objects.create(formulario=f)
    p1 = Pagina.objects.create(index_version=v, formulario=f, secuencia=2, nombre='P2', descripcion='')
    p2 = Pagina.objects.create(index_version=v, formulario=f, secuencia=1, nombre='P1', descripcion='')
    nombres = list(Pagina.objects.filter(index_version=v).values_list('nombre', flat=True))
    assert nombres == ['P1','P2']