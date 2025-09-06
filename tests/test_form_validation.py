from datetime import date, timedelta

def test_create_form_without_state_shows_error(api_client, categoria):
    payload = {
        'categoria': str(categoria.id),
        'nombre': 'F invalido',
        'descripcion': '',
        'permitir_fotos': False,
        'permitir_gps': False,
        'disponible_desde_fecha': str(date.today()),
        'disponible_hasta_fecha': str(date.today() + timedelta(days=1)),
        'forma_envio': 'En Linea',
        'es_publico': False,
        'auto_envio': False,
    }
    r = api_client.post('/api/formularios/', payload, format='json')
    assert r.status_code in (400, 422), r.data
