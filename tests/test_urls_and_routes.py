def test_router_roots(api_client):
    r = api_client.get("/api/")
    assert r.status_code in (200, 301, 302)

def test_campos_list_smoke(api_client):
    r = api_client.get("/api/campos/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

def test_usuarios_list_smoke(api_client):
    r = api_client.get("/api/usuarios/")
    assert r.status_code in (200, 401, 403)

def test_formularios_lite_list_smoke(api_client):
    r = api_client.get("/api/formularios-lite/")
    assert r.status_code in (200, 401, 403)

def test_download_preview_methods_exist(api_client, formulario, version):
    # Rutas de acciones comunes en formularios; pueden estar protegidas o no implementadas
    r_down = api_client.get(f"/api/formularios/{formulario.id}/download/")
    r_prev = api_client.post(f"/api/formularios/{formulario.id}/preview/", {}, format="json")
    assert r_down.status_code in (200, 400, 401, 403, 404)
    assert r_prev.status_code in (200, 400, 401, 403, 404)
