from datetime import date, timedelta

def _payload_form(categoria_id):
    return {
        'categoria': str(categoria_id) if categoria_id else None,
        'nombre': 'F1',
        'descripcion': 'desc',
        'permitir_fotos': True,
        'permitir_gps': False,
        'disponible_desde_fecha': str(date.today()),
        'disponible_hasta_fecha': str(date.today() + timedelta(days=2)),
        'estado': 'Activa',
        'forma_envio': 'En Linea',
        'es_publico': False,
        'auto_envio': False,
    }

def test_form_create_retrieve_update_delete(api_client, categoria):
    # create
    r = api_client.post('/api/formularios/', _payload_form(categoria.id), format='json')
    assert r.status_code in (200, 201), r.data
    fid = r.data['id']

    # retrieve
    r2 = api_client.get(f'/api/formularios/{fid}/')
    assert r2.status_code == 200
    assert r2.data['nombre'] == 'F1'

    # update
    r3 = api_client.patch(f'/api/formularios/{fid}/', {'nombre': 'F-Edit'}, format='json')
    assert r3.status_code == 200
    assert r3.data['nombre'] == 'F-Edit'

    # delete
    r4 = api_client.delete(f'/api/formularios/{fid}/')
    assert r4.status_code in (200, 204)

def test_form_list_returns_collection(api_client, categoria):
    # asegura que hay al menos uno
    api_client.post('/api/formularios/', _payload_form(categoria.id), format='json')
    r = api_client.get('/api/formularios/')
    assert r.status_code == 200
    assert isinstance(r.json(), list)

def test_form_create_requires_estado(api_client, categoria):
    p = _payload_form(categoria.id)
    p.pop('estado')
    r = api_client.post('/api/formularios/', p, format='json')
    assert r.status_code in (400, 422)

def test_form_invalid_dates_range(api_client, categoria):
    p = _payload_form(categoria.id)
    p['disponible_hasta_fecha'] = str(date.today() - timedelta(days=1))
    r = api_client.post('/api/formularios/', p, format='json')
    assert r.status_code in (200, 201)