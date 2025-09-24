from django.urls import resolve

def test_router_endpoints_names_one():
    assert resolve('/api/formularios/').url_name == 'formulario-list'
    assert resolve('/api/categorias/').url_name == 'categoria-list'
    assert resolve('/api/paginas/').url_name == 'pagina-list'

def test_router_endpoints_names_two():
    assert resolve('/api/campos/').url_name == 'campos-list'
    assert resolve('/api/catalogos/clases-campo/').url_name == 'catalogos-clases'
    assert resolve('/api/usuarios/').url_name == 'usuario-list'
    assert resolve('/api/roles/').url_name == 'rol-list'