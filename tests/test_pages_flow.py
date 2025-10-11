def _add_page(api_client, fid, name="P-A", bump=1):
    return api_client.post(
        f"/api/formularios/{fid}/agregar-pagina/?bump={bump}",
        {"nombre": name},
        format="json"
    )

def test_agregar_pagina_bump_1(api_client, formulario, version):
    r = _add_page(api_client, formulario.id, "P1", bump=1)
    assert r.status_code in (200, 201), r.data

def test_agregar_pagina_bump_0(api_client, formulario, version):
    r = _add_page(api_client, formulario.id, "P2", bump=0)
    assert r.status_code in (200, 201)

def test_list_paginas_after_add(api_client, formulario, version):
    _add_page(api_client, formulario.id, "LP-1", bump=1)
    r = api_client.get("/api/paginas/")
    assert r.status_code == 200
    assert any(p.get("nombre") == "LP-1" for p in r.json())

def test_pagina_retrieve_with_campos_param(api_client, formulario, version):
    r_add = _add_page(api_client, formulario.id, "C-with", bump=1)
    assert r_add.status_code in (200, 201)
    pid = r_add.json().get("id_pagina") or r_add.json().get("id") or r_add.json().get("idPagina")

    r_det = api_client.get(f"/api/paginas/{pid}/?include_campos=1")
    assert r_det.status_code == 200
    body = r_det.json()
    assert isinstance(body, dict)

def test_pagina_retrieve_404(api_client):
    r = api_client.get("/api/paginas/00000000-0000-0000-0000-000000000000/")
    assert r.status_code in (404, 400)

def test_pagina_campos_subroute_without_campos(api_client, formulario, version):
    r_add = _add_page(api_client, formulario.id, "C-empty", bump=1)
    assert r_add.status_code in (200, 201)
    pid = r_add.json().get("id_pagina") or r_add.json().get("id")

    r_campos = api_client.get(f"/api/paginas/{pid}/?include_campos=1")
    assert r_campos.status_code == 200
    body = r_campos.json()
    assert "campos" in body
    assert isinstance(body["campos"], list)

def test_pagina_methods_not_allowed(api_client):
    r = api_client.post("/api/paginas/", {}, format="json")
    assert r.status_code in (405, 404, 400)
