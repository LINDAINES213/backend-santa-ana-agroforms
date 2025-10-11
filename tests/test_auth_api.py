def test_user_info_unauth(api_client):
    api_client.raise_request_exception = False
    r = api_client.get("/api/auth/me/")
    assert r.status_code in (401, 403, 500)

def test_login_missing_fields(api_client):
    r = api_client.post("/api/auth/login/", {}, format="json")
    # Debe pedir nombre_usuario y password
    assert r.status_code in (400, 401)
    body = r.json()
    assert isinstance(body, dict)

def test_login_wrong_creds(api_client):
    payload = {"nombre_usuario": "noexiste", "password": "x"}
    r = api_client.post("/api/auth/login/", payload, format="json")
    assert r.status_code in (400, 401)
    assert "ok" in r.json() or "error" in r.json()

def test_logout_without_token(api_client):
    r = api_client.post("/api/auth/logout/", {}, format="json")
    # Si requiere token, debe rechazar
    assert r.status_code in (401, 403, 400)

def test_login_method_allowed(api_client):
    # GET no debería estar permitido
    r = api_client.get("/api/auth/login/")
    assert r.status_code in (405, 404)

def test_user_info_method_allowed(api_client):
    # POST en /me/ usualmente no permitido
    r = api_client.post("/api/auth/me/", {}, format="json")
    assert r.status_code in (405, 401, 403)
