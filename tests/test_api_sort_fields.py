from formularios.models import Pagina, Campo, FormularioIndexVersion

def _setup_page_with_fields(formulario):
    ver = FormularioIndexVersion.objects.create(formulario=formulario)
    p = Pagina.objects.create(index_version=ver, formulario=formulario, secuencia=1, nombre='P', descripcion='')
    c1 = Campo.objects.create(pagina=p, tipo='text', clase='base', nombre_campo='c1', etiqueta='C1', ayuda='', config={}, requerido=False, sequence=1)
    c2 = Campo.objects.create(pagina=p, tipo='text', clase='base', nombre_campo='c2', etiqueta='C2', ayuda='', config={}, requerido=False, sequence=2)
    c3 = Campo.objects.create(pagina=p, tipo='text', clase='base', nombre_campo='c3', etiqueta='C3', ayuda='', config={}, requerido=False, sequence=3)
    return p, (c1, c2, c3)

def test_reordenar_updates_sequences(api_client, formulario):
    p, (c1, c2, c3) = _setup_page_with_fields(formulario)
    r = api_client.post('/api/campos/reordenar/', {
        "items": [
            {"id_campo": str(c1.id_campo), "sequence": 3},
            {"id_campo": str(c2.id_campo), "sequence": 2},
            {"id_campo": str(c3.id_campo), "sequence": 1},
        ]
    }, format='json')
    assert r.status_code == 200
    assert r.data['updated'] == 3
    c1.refresh_from_db(); c2.refresh_from_db(); c3.refresh_from_db()
    assert [c1.sequence, c2.sequence, c3.sequence] == [3,2,1]

def test_reordenar_ignores_unknown_ids(api_client, formulario):
    p, (c1, c2, _) = _setup_page_with_fields(formulario)
    r = api_client.post('/api/campos/reordenar/', {
        "items": [
            {"id_campo": str(c1.id_campo), "sequence": 2},
            {"id_campo": "00000000-0000-0000-0000-000000000000", "sequence": 99},
        ]
    }, format='json')
    assert r.status_code == 200
    assert r.data['updated'] == 1
