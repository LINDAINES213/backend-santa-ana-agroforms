from django.urls import resolve

def test_router_endpoints_names():
    assert resolve('/api/formularios/').url_name == 'formulario-list'
    assert resolve('/api/categorias/').url_name == 'categoria-list'
    assert resolve('/api/paginas/').url_name == 'pagina-list'
