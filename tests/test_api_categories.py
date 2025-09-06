def test_category_basic_crud(api_client):
    # create
    r = api_client.post('/api/categorias/', {'nombre': 'Nuevita', 'descripcion': ''}, format='json')
    assert r.status_code in (200, 201), r.data

    # list
    r2 = api_client.get('/api/categorias/')
    assert r2.status_code == 200
    assert any(item['nombre'] == 'Nuevita' for item in r2.json())

    # delete
    cat_id = next(item['id'] for item in r2.json() if item['nombre'] == 'Nuevita')
    r3 = api_client.delete(f'/api/categorias/{cat_id}/')
    assert r3.status_code in (200, 204)
