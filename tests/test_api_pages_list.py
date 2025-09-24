def test_pages_list(api_client, formulario, version):
    # Crear y publicar la página
    r_add = api_client.post(
        f'/api/formularios/{formulario.id}/agregar-pagina/?bump=1',
        {'nombre': 'P1'},
        format='json'
    )
    assert r_add.status_code in (200, 201), r_add.data

    r = api_client.get('/api/paginas/')
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert any(p.get('nombre') == 'P1' for p in data)

def test_paginas_list_contains_created(api_client, formulario, version):
    r_add = api_client.post(
        f'/api/formularios/{formulario.id}/agregar-pagina/?bump=1',
        {'nombre': 'P-Y'}, format='json'
    )
    assert r_add.status_code in (200, 201)
    r = api_client.get('/api/paginas/')
    assert any(p.get('nombre') == 'P-Y' for p in r.json())

def test_page_retrieve_404(api_client):
    r = api_client.get('/api/paginas/00000000-0000-0000-0000-000000000000/')
    assert r.status_code in (404, 400)

