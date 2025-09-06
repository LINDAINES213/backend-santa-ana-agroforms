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
