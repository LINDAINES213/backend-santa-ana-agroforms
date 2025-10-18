# services.py (al final, o en un nuevo archivo e impórtalo en views)
from collections import OrderedDict
from io import BytesIO
import pandas as pd
from django.utils.timezone import localtime
from zipfile import ZipFile, ZIP_DEFLATED
from django.utils import timezone
from .models import FormularioEntry


def _to_naive_local(dt):
    """
    Convierte un datetime (aware o naive) a naive en hora local.
    """
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return dt  # ya es naive
    # pasa a hora local y quita tzinfo
    return timezone.localtime(dt).replace(tzinfo=None)

def _sanitize_filename(name: str, maxlen: int = 60) -> str:
    safe = "".join(ch if ch.isalnum() or ch in " _-.,()" else "_" for ch in (name or ""))
    return safe[:maxlen] or "export"


def _build_field_catalog(form_json: dict) -> list[dict]:
    """
    Del form_json construye un catálogo de campos con:
    id_pagina, id_campo, nombre_interno, etiqueta, clase, requerido, sequence
    """
    out = []
    if not isinstance(form_json, dict):
        return out
    paginas = (form_json.get("paginas") or []) if isinstance(form_json.get("paginas"), list) else []
    for p in paginas:
        pid = p.get("id_pagina")
        campos = p.get("campos") or []
        for c in campos:
            out.append({
                "id_pagina": pid,
                "id_campo": c.get("id_campo"),
                "nombre_interno": c.get("nombre_interno"),
                "etiqueta": c.get("etiqueta"),
                "clase": (c.get("clase") or "").lower(),
                "tipo":  (c.get("tipo") or "").lower(),
                "requerido": bool(c.get("requerido")),
                "sequence": c.get("sequence") or 0,
            })
    # orden estable: por secuencia; si no existe, mantiene inserción
    out.sort(key=lambda r: r.get("sequence") or 0)
    return out

def _flatten_entry_row(entry: FormularioEntry) -> dict:
    """
    Convierte 1 registro de formularios_entry en una fila plana (dict) con:
    metadatos + columnas de respuestas (con etiqueta legible).
    """
    base = OrderedDict()
    base["Nombre Formulario"] = entry.form_name
    base["Usuario"] = entry.id_usuario  # ya es texto
    base["Status"] = entry.status
    base["Llenado"] = _to_naive_local(entry.filled_at_local)
    base["Actualizado"]      = _to_naive_local(entry.updated_at)

    form_json = entry.form_json or {}
    fill_json = entry.fill_json or {}

    catalog = _build_field_catalog(form_json)

    for meta in catalog:
        etiqueta = meta.get("etiqueta") or meta.get("nombre_interno") or meta.get("id_campo")
        etiqueta_col = str(etiqueta).strip()
        pid = meta.get("id_pagina")
        nombre_interno = meta.get("nombre_interno")
        clase = (meta.get("clase") or "").lower()

        valor = None
        # Buscar en la página correspondiente
        if pid and nombre_interno:
            page_dict = fill_json.get(str(pid)) or fill_json.get(pid)
            if isinstance(page_dict, dict):
                valor = page_dict.get(nombre_interno)

        # Normalizaciones rápidas por clase
        if clase == "boolean":
            if isinstance(valor, str):
                valor = valor.strip().lower() in ("1", "true", "t", "yes", "si", "sí")
            valor = bool(valor) if valor is not None else None

        # (opcional) dataset: si tu app guarda pares id/label, normaliza a label
        if clase == "dataset":
            # puede venir como string, dict {"id": "...", "label": "..."}, lista, etc.
            if isinstance(valor, dict):
                valor = valor.get("label") or valor.get("label_text") or valor.get("value") or valor.get("id") or None
            elif isinstance(valor, (list, tuple)):
                # lista de selecciones→ concat
                valor = ", ".join([ (v.get("label") if isinstance(v, dict) else str(v)) for v in valor ])

        base[etiqueta_col] = valor

    return base

def dataframe_por_form(form_id) -> pd.DataFrame:
    """
    Devuelve un DataFrame con TODAS las respuestas de un form_id.
    """
    qs = (FormularioEntry.objects
          .filter(form_id=form_id)
          .order_by("filled_at_local", "created_at"))
    rows = [_flatten_entry_row(e) for e in qs]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)

    # Ordena columnas: metadatos primero
    meta_cols = ["Nombre Formulario","Usuario","Status","Llenado","Actualizado"]
    other_cols = [c for c in df.columns if c not in meta_cols]
    df = df[meta_cols + other_cols]
    return df

def excel_bytes_para_un_form(form_id) -> tuple[str, bytes]:
    """
    Crea 1 Excel con hoja 'Respuestas' y hoja 'Diccionario' para ese form_id.
    Retorna (filename, bytes).
    """
    qs = FormularioEntry.objects.filter(form_id=form_id).order_by("-created_at")
    if not qs.exists():
        return (f"{form_id}.xlsx", b"")
    form_name = (qs.first().form_name or str(form_id)).strip()

    # DataFrame de respuestas
    df = dataframe_por_form(form_id)

    # Diccionario de datos (desde el form_json más reciente)
    cat = _build_field_catalog(qs.first().form_json or {})
    df_dict = pd.DataFrame(cat) if cat else pd.DataFrame(columns=["id_pagina","id_campo","nombre_interno","etiqueta","clase","tipo","requerido","sequence"])

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        (df if df is not None else pd.DataFrame()).to_excel(xw, index=False, sheet_name="Respuestas")
        (df_dict if df_dict is not None else pd.DataFrame()).to_excel(xw, index=False, sheet_name="Diccionario")
    buf.seek(0)
    safe_name = "".join(ch if ch.isalnum() or ch in " _-.,()" else "_" for ch in form_name)[:60]
    fname = f"{safe_name}__{form_id}.xlsx"
    return (fname, buf.read())


def _cleanup_df_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    """Quita tz y formatea columnas datetime."""
    if df is None or df.empty:
        return df
    for col in df.columns:
        s = df[col]
        try:
            if hasattr(s, "dt") and getattr(s.dt, "tz", None) is not None:
                df[col] = s.dt.tz_localize(None)
        except Exception:
            pass
    # si quieres formatear sin milisegundos:
    for c in ("filled_at_local", "created_at", "updated_at"):
        if c in df.columns:
            try:
                df[c] = pd.to_datetime(df[c]).dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
    return df

def content_bytes_para_un_form(form_id, fmt: str = "xlsx"):
    """
    Devuelve (filename, bytes, mimetype) del formulario en formato elegido.
    - xlsx: incluye hoja 'Respuestas' (y opcionalmente 'Diccionario' si quieres)
    - csv/json: solo 'Respuestas'
    """
    fmt = (fmt or "xlsx").lower()
    qs = FormularioEntry.objects.filter(form_id=form_id).order_by("-created_at")
    if not qs.exists():
        # aún devolvemos filename para headers consistentes
        return (f"{form_id}.{fmt}", b"", "application/octet-stream")

    form_name = (qs.first().form_name or str(form_id)).strip()
    safe_name = _sanitize_filename(form_name)
    df = dataframe_por_form(form_id)

    if fmt == "xlsx":
        df = _cleanup_df_for_excel(df.copy())
        # Si quieres agregar hoja de diccionario:
        cat = _build_field_catalog(qs.first().form_json or {})
        df_dict = pd.DataFrame(cat) if cat else pd.DataFrame(
            columns=["id_pagina","id_campo","nombre_interno","etiqueta","clase","tipo","requerido","sequence"]
        )
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            (df if df is not None else pd.DataFrame()).to_excel(xw, index=False, sheet_name="Respuestas")
            df_dict.to_excel(xw, index=False, sheet_name="Diccionario")
        buf.seek(0)
        return (f"{safe_name}__{form_id}.xlsx", buf.read(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    elif fmt == "csv":
        # CSV compatible con Excel (BOM)
        out = df.to_csv(index=False).encode("utf-8-sig")
        return (f"{safe_name}__{form_id}.csv", out, "text/csv")

    elif fmt == "json":
        # Array de objetos (registros)
        out = df.to_json(orient="records", force_ascii=False).encode("utf-8")
        return (f"{safe_name}__{form_id}.json", out, "application/json")

    else:
        # fallback: xlsx
        return content_bytes_para_un_form(form_id, "xlsx")

def zip_bytes_todos_los_forms(fmt: str = "xlsx"):
    """
    Genera un ZIP con 1 archivo por form_id en el formato elegido.
    Retorna (filename, bytes)
    """
    ids = (FormularioEntry.objects.values_list("form_id", flat=True).distinct())
    mem = BytesIO()
    with ZipFile(mem, mode="w", compression=ZIP_DEFLATED) as zf:
        for fid in ids:
            fname, content, _mime = content_bytes_para_un_form(fid, fmt)
            if content:
                zf.writestr(fname, content)
    mem.seek(0)
    return (f"formularios_respuestas_{fmt}.zip", mem.read())