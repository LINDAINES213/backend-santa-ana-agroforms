from formularios.validators import validate_config_against_schema

def test_schema_none_allows_empty():
    assert validate_config_against_schema({}, None) == []

def test_schema_none_rejects_non_empty():
    errs = validate_config_against_schema({"x": 1}, None)
    assert errs and "no acepta 'config'" in errs[0]

def test_unknown_keys_reported():
    errs = validate_config_against_schema({"b": "x"}, {"a": ["string"]})
    assert "Claves desconocidas" in errs[0]

def test_required_missing_key():
    errs = validate_config_against_schema({}, {"a": ["string"]})
    assert "'a' es requerido" in errs[0]

def test_optional_allows_missing():
    errs = validate_config_against_schema({}, {"a": [None, "string"]})
    assert errs == []

def test_type_string_ok():
    assert validate_config_against_schema({"a": "hola"}, {"a": ["string"]}) == []

def test_type_string_bad():
    errs = validate_config_against_schema({"a": 123}, {"a": ["string"]})
    assert errs and "tipo inválido" in errs[0]

def test_type_number_ok():
    assert validate_config_against_schema({"n": 3.14}, {"n": ["number"]}) == []

def test_type_boolean_ok():
    assert validate_config_against_schema({"b": True}, {"b": ["boolean"]}) == []

def test_array_type_ok():
    assert validate_config_against_schema({"tags": ["a", "b"]}, {"tags": ["string[]"]}) == []

def test_array_type_bad():
    errs = validate_config_against_schema({"nums": [1, "x"]}, {"nums": ["number[]"]})
    assert errs and "tipo inválido" in errs[0]

def test_pure_enum_ok():
    assert validate_config_against_schema({"m": "A"}, {"m": ["A", "B", None]}) == []

def test_pure_enum_bad():
    errs = validate_config_against_schema({"m": "Z"}, {"m": ["A", "B"]})
    assert errs and "debe ser uno de" in errs[0]