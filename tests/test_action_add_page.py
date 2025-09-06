from formularios.models import Pagina, FormularioIndexVersion

def test_add_page_without_bump(api_client, formulario, version):
    assert Pagina.objects.count() == 0
    r = api_client.post(f'/api/formularios/{formulario.id}/agregar-pagina/?bump=0', {
        'nombre': 'P1',
        'descripcion': 'desc',
    }, format='json')
    assert r.status_code == 201, r.data
    assert r.data['pagina']['nombre'] == 'P1'
    assert Pagina.objects.count() == 1

def test_add_page_without_bump(api_client, formulario, version):
    count_ver = FormularioIndexVersion.objects.filter(formulario=formulario).count()
    r = api_client.post(f'/api/formularios/{formulario.id}/agregar-pagina/?bump=1', {
        'nombre': 'P2',
    }, format='json')
    assert r.status_code == 201, r.data
    assert FormularioIndexVersion.objects.filter(formulario=formulario).count() == count_ver + 1
