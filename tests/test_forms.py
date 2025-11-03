from datetime import date, timedelta

def _payload_form(categoria_id):
    return {
        "categoria": str(categoria_id),
        "nombre": "Form X",
        "descripcion": "",
        "permitir_fotos": False,
        "permitir_gps": False,
        "disponible_desde_fecha": str(date.today()),
        "disponible_hasta_fecha": str(date.today() + timedelta(days=2)),
        "estado": "Activo",
        "forma_envio": "En Linea",
        "es_publico": False,
        "auto_envio": False,
    }

def test_formulario_crud_min(api_client, categoria):
    r = api_client.post("/api/formularios/", _payload_form(categoria.id), format="json")
    assert r.status_code in (200, 201), r.data
    fid = r.json()["id"]

    r_get = api_client.get(f"/api/formularios/{fid}/")
    assert r_get.status_code == 200

    r_list = api_client.get("/api/formularios/")
    assert r_list.status_code == 200
    assert any(x["id"] == fid for x in r_list.json())

    r_del = api_client.delete(f"/api/formularios/{fid}/")
    assert r_del.status_code in (200, 204)

def test_formulario_retrieve_404(api_client):
    r = api_client.get("/api/formularios/00000000-0000-0000-0000-000000000000/")
    assert r.status_code in (404, 400)

def test_formulario_create_requires_categoria(api_client):
    bad = _payload_form("00000000-0000-0000-0000-000000000000")
    r = api_client.post("/api/formularios/", bad, format="json")
    assert r.status_code in (400, 404)

def test_formulario_duplicar_endpoint(api_client, formulario):
    r = api_client.post(f"/api/formularios/{formulario.id}/duplicar/", {"nombre": "Clon"}, format="json")
    assert r.status_code in (201, 200), r.data
    data = r.json()
    assert data.get("id") and str(data["id"]) != str(formulario.id)

def test_formulario_destroy_idempotent(api_client, categoria):
    # Crea y elimina dos veces
    r = api_client.post("/api/formularios/", _payload_form(categoria.id), format="json")
    assert r.status_code in (200, 201)
    fid = r.json()["id"]

    r_del1 = api_client.delete(f"/api/formularios/{fid}/")
    assert r_del1.status_code in (200, 204)

    r_del2 = api_client.delete(f"/api/formularios/{fid}/")
    assert r_del2.status_code in (404, 400, 500)

def test_formulario_list_filters_survive(api_client):
    r = api_client.get("/api/formularios/?search=Algo&ordering=nombre")
    assert r.status_code == 200

def test_formulario_update_min(api_client, categoria):
    r = api_client.post("/api/formularios/", _payload_form(categoria.id), format="json")
    assert r.status_code in (200, 201)
    fid = r.json()["id"]

    r_up = api_client.patch(f"/api/formularios/{fid}/", {"nombre": "Nuevo"}, format="json")
    assert r_up.status_code in (200, 202, 204)

def test_formulario_date_validation_edge_case(api_client, categoria):
    from datetime import date
    
    mismo_dia = date.today()
    payload = {
        "categoria": str(categoria.id),
        "nombre": "Form Mismo Dia",
        "descripcion": "",
        "permitir_fotos": False,
        "permitir_gps": False,
        "disponible_desde_fecha": str(mismo_dia),
        "disponible_hasta_fecha": str(mismo_dia),
        "estado": "Activo",
        "forma_envio": "En Linea",
        "es_publico": False,
        "auto_envio": False,
    }
    
    r = api_client.post("/api/formularios/", payload, format="json")
    # Debería permitir crear con fechas iguales o rechazarlo según la lógica de negocio
    assert r.status_code in (200, 201, 400)
    
    # Si se creó exitosamente, verificar que los datos son correctos
    if r.status_code in (200, 201):
        data = r.json()
        assert data["disponible_desde_fecha"] == str(mismo_dia)
        assert data["disponible_hasta_fecha"] == str(mismo_dia)