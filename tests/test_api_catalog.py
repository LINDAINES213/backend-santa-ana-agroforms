from formularios.models import ClaseCampo

def test_catalogos_clases_lista(api_client, db):
    ClaseCampo.objects.create(clase='texto', schema={"max_length": ["number", None]})
    ClaseCampo.objects.create(clase='numero', schema={"min": ["number", None]})
    r = api_client.get('/api/catalogos/clases-campo/')
    assert r.status_code == 200
    data = r.json()
    clases = {d['clase'] for d in data}
    assert {'texto','numero'}.issubset(clases)

def test_check_clase_match_true(api_client, db):
    ClaseCampo.objects.create(clase='Texto', schema=None)
    r = api_client.get('/api/catalogos/check-clase/?clase=texto')
    assert r.status_code == 200
    assert r.json()['match'] is True

def test_check_clase_match_false(api_client, db):
    r = api_client.get('/api/catalogos/check-clase/?clase=inexistente')
    assert r.status_code == 200
    assert r.json()['match'] is False
