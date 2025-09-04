# validators.py
from typing import Any

def _is_number(v): return isinstance(v, (int, float)) and not isinstance(v, bool)

def _type_ok(value: Any, rule: str) -> bool:
    if rule == "string":  return isinstance(value, str)
    if rule == "number":  return _is_number(value)
    if rule == "boolean": return isinstance(value, bool)
    if rule.endswith("[]"):
        base = rule[:-2]
        return isinstance(value, list) and all(_type_ok(x, base) for x in value)
    return False

def validate_config_against_schema(config: dict, schema) -> list[str]:
    """
    Soporta:
      - tipos: "string","number","boolean","string[]",...
      - enums: ["A","B","C"] (con o sin None, p.ej. [None,"A","B"])
      - opcional: presencia de None en la lista => valor puede ser null/omitido
    """
    if schema is None:
        return [] if (config in (None, {}, [])) else ["Esta clase no acepta 'config'"]

    if not isinstance(schema, dict):
        return ["Schema inválido en catálogo"]

    def is_type_token(s: str) -> bool:
        return isinstance(s, str) and (s in ("string","number","boolean") or s.endswith("[]"))

    errors = []
    allowed = set(schema.keys())
    unknown = set((config or {}).keys()) - allowed
    if unknown:
        errors.append(f"Claves desconocidas: {', '.join(sorted(unknown))}")

    for key, spec in schema.items():
        val = (config or {}).get(key, None)
        tokens = list(spec) if isinstance(spec, list) else []

        # ¿es opcional?
        optional = any(t is None for t in tokens)
        if val is None:
            if optional:
                continue
            errors.append(f"'{key}' es requerido")
            continue

        # separa enums vs tipos
        enum_tokens  = [t for t in tokens if t is not None and isinstance(t, str) and not is_type_token(t)]
        type_tokens  = [t for t in tokens if t is not None and is_type_token(t)]

        if enum_tokens and not type_tokens:
            # puro enum (con o sin None)
            if val not in enum_tokens:
                errors.append(f"'{key}' debe ser uno de {enum_tokens}")
            continue

        if type_tokens:
            if not any(_type_ok(val, t) for t in type_tokens):
                expect = " | ".join(type_tokens + (["None"] if optional else []))
                errors.append(f"'{key}' tiene tipo inválido (esperado: {expect})")
            continue
        
    return errors
