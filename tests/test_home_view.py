from django.test import Client

def test_home_ok():
    client = Client()
    resp = client.get('/')
    assert resp.status_code == 200
    assert 'Bienvenido a la API de Formularios' in resp.content.decode('utf-8')
