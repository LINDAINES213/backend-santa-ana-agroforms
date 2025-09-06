from datetime import date, timedelta

def test_create_min_form(api_client, categoria):
    payload = {
        'categoria': str(categoria.id),
        'nombre': 'F1',
        'descripcion': '',
        'permitir_fotos': False,
        'permitir_gps': False,
        'disponible_desde_fecha': str(date.today()),
        'disponible_hasta_fecha': str(date.today() + timedelta(days=1)),
        'estado': 'Activa',
        'forma_envio': 'En Linea',
        'es_publico': False,
        'auto_envio': False,
    }
    r = api_client.post('/api/formularios/', payload, format='json')
    assert r.status_code in (200, 201), r.data
    assert r.data.get('id')
