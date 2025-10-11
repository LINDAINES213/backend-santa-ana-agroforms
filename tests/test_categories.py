def test_categoria_list_empty_ok(api_client):
    r = api_client.get("/api/categorias/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)

def test_categoria_create_update_delete(api_client):
    r = api_client.post("/api/categorias/", {"nombre": "Z", "descripcion": ""}, format="json")
    assert r.status_code in (200, 201), r.data
    cid = r.json()["id"]

    r_up = api_client.patch(f"/api/categorias/{cid}/", {"descripcion": "ok"}, format="json")
    assert r_up.status_code in (200, 202, 204)

    r_del = api_client.delete(f"/api/categorias/{cid}/")
    assert r_del.status_code in (200, 204)

def test_categoria_retrieve_404(api_client):
    r = api_client.get("/api/categorias/00000000-0000-0000-0000-000000000000/")
    assert r.status_code in (404, 400)

def test_categoria_method_not_allowed(api_client):
    r = api_client.put("/api/categorias/", {}, format="json")
    assert r.status_code in (405, 404)

def test_categoria_create_min_required(api_client):
    r = api_client.post("/api/categorias/", {"nombre": "SoloNombre"}, format="json")
    assert r.status_code in (200, 201)
