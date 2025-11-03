from uuid import uuid4

def test_api_root_options(api_client):
    r = api_client.options("/api/")
    assert r.status_code in (200, 301, 302)

def test_categorias_options_and_head(api_client):
    r_opt = api_client.options("/api/categorias/")
    r_head = api_client.head("/api/categorias/")
    assert r_opt.status_code in (200, 204)
    assert r_head.status_code in (200, 204, 301, 302)

def test_formularios_pagination_params(api_client):
    r = api_client.get("/api/formularios/?page=1&page_size=2")
    # Si está protegido puede devolver 401/403; si no, 200
    assert r.status_code in (200, 401, 403)

def test_usuarios_pagination_and_search(api_client):
    r = api_client.get("/api/usuarios/?page=1&page_size=1&search=test")
    assert r.status_code in (200, 401, 403)

def test_campos_search_and_ordering(api_client):
    r = api_client.get("/api/campos/?search=x&ordering=nombre")
    assert r.status_code in (200, 401, 403)

def test_paginas_list_search_ordering(api_client):
    r = api_client.get("/api/paginas/?search=P&ordering=-nombre")
    assert r.status_code in (200, 401, 403)

def test_fuentes_datos_options(api_client):
    r = api_client.options("/api/fuentes-datos/")
    assert r.status_code in (200, 204)

def test_invalid_uuid_in_detail_routes(api_client):
    # UUID inválido en varias rutas de detalle debe responder 400/404
    bad = "not-a-uuid"
    for path in [
        f"/api/categorias/{bad}/",
        f"/api/formularios/{bad}/",
        f"/api/paginas/{bad}/",
        f"/api/fuentes-datos/{bad}/",
    ]:
        r = api_client.get(path)
        assert r.status_code in (400, 404)

def test_random_uuid_in_detail_routes(api_client):
    rnd = uuid4()
    for path in [
        f"/api/categorias/{rnd}/",
        f"/api/formularios/{rnd}/",
        f"/api/paginas/{rnd}/",
        f"/api/fuentes-datos/{rnd}/",
    ]:
        r = api_client.get(path)
        assert r.status_code in (400, 404)