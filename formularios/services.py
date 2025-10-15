# # services.py
from hashlib import sha256
from io import BytesIO
import json
import uuid
from django.db import transaction, connection

from django.apps import apps
from typing import Dict, Any
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
import re
from argon2.low_level import hash_secret, verify_secret, Type
from os import urandom
import pandas as pd

from formularios.azure_storage import AzureBlobStorageService

from .models import (
    Formulario,
    FormularioIndexVersion,
    FuenteDatos,
    FuenteDatosValor,
    Grupo,
    Pagina,
    PaginaVersion,
    ClaseCampo,
    Campo,
    PaginaCampo,
    Pagina_Index_Version
)
from formularios import models

def _uuid32_no_dashes(s: str) -> str:
    s = s.strip().lower()
    # si ya viene sin guiones (32 hex), devuélvelo
    if re.fullmatch(r"[0-9a-f]{32}", s):
        return s
    # si viene con guiones (8-4-4-4-12), quítalos
    s = s.replace("-", "")
    if re.fullmatch(r"[0-9a-f]{32}", s):
        return s
    raise ValueError("id_pagina inválido: debe ser UUID v4.")

def uuid32(u) -> str:
    # acepta uuid.UUID o str
    s = str(u)
    return s.replace("-", "").lower()  # 32 chars

def _first_or_same(x):
    if isinstance(x, (list, tuple)) and x:
        return x[0]
    return x

def _ensure_str_uuid():
    return uuid.uuid4().hex  


@transaction.atomic
def activar_version(formulario, nueva_version) -> None:
    Formulario_Index_Version = apps.get_model("formularios", "Formulario_Index_Version")

    Formulario_Index_Version.objects.get_or_create(
        id_index_version=nueva_version,                 
        defaults={"id_formulario": formulario},
    )

    try:
        FormularioIndex = apps.get_model("formularios", "FormularioIndex")
    except LookupError:
        FormularioIndex = None

    if FormularioIndex:
        FormularioIndex.objects.update_or_create(
            id_formulario=formulario,
            defaults={"id_index_version": nueva_version},
        )

    try:
        PaginaIndex = apps.get_model("formularios", "PaginaIndex")
    except LookupError:
        PaginaIndex = None

    if PaginaIndex:
        from .models import Pagina
        for p in Pagina.objects.filter(index_version=nueva_version).only("id_pagina"):
            PaginaIndex.objects.update_or_create(
                id_pagina=p,
                defaults={
                    "id_index_version": nueva_version,
                    "id_formulario": formulario,
                },
            )

_CLASE_A_TIPO = {
    "string":  "texto",
    "text":    "texto",
    "list":    "texto",
    "hour":    "texto",
    "group":   "texto",
    "date":    "texto",
    "number":  "numerico",
    "calc":    "numerico",
    "boolean": "booleano",
    "firm":    "imagen",
    "dataset": "texto",
}

def _resolver_tipo_por_clase(clase: str) -> str:
    return _CLASE_A_TIPO.get((clase or "").strip().lower(), "texto")

def _ultima_pagina_version(pagina: Pagina) -> PaginaVersion | None:
    return (PaginaVersion.objects
            .filter(id_pagina=pagina)
            .order_by("-fecha_creacion")
            .first())

@transaction.atomic
def crear_campo_y_versionar_pagina(pagina: Pagina, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Crea Campo (tipo por clase) y publica nueva versión:
      - nueva FormularioIndexVersion
      - nueva PaginaVersion (fecha)
      - NO clona campos existentes, solo agrega el nuevo
      - actualiza punteros Pagina_Index_Version a la nueva index_version
    """
    clase = (data.get("clase") or "").strip().lower()
    if not clase:
        raise ValidationError("El campo 'clase' es obligatorio.")

    if not ClaseCampo.objects.filter(clase=clase).exists():
        raise ValidationError(f"La clase '{clase}' no existe en formularios_clase_campo.")

    tipo = _resolver_tipo_por_clase(clase)

    cfg = data.get("config") or {}
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg or "{}")
        except Exception:
            raise ValidationError("El campo 'config' debe ser JSON válido.")

    campo = Campo.objects.create(
        tipo=tipo,
        clase=clase,
        nombre_campo=(data.get("nombre_campo") or f"{clase}_{timezone.now().strftime('%H%M%S')}").strip(),
        etiqueta=(data.get("etiqueta") or "").strip(),
        ayuda=(data.get("ayuda") or "").strip(),
        config=cfg,
        requerido=bool(data.get("requerido", False)),
    )

    formulario = pagina.formulario_id
    nueva_version = FormularioIndexVersion.objects.create(formulario_id=formulario)

    prev_pv = _ultima_pagina_version(pagina)
    nueva_pv = PaginaVersion.objects.create(id_pagina=pagina)

    max_seq = 0
    if prev_pv:
        max_seq_result = (PaginaCampo.objects
                         .filter(id_pagina_version=prev_pv)
                         .aggregate(max_seq=models.Max('sequence')))
        max_seq = max_seq_result.get('max_seq') or 0

    sequence = data.get("sequence")
    try:
        sequence = int(sequence) if sequence is not None else None
    except Exception:
        sequence = None

    if sequence is None:
        sequence = (max_seq + 1) if max_seq else 1

    PaginaCampo.objects.create(
        id_campo=campo,
        id_pagina_version=nueva_pv,
        sequence=sequence,
    )

    for p in Pagina.objects.filter(formulario_id=formulario).only("id_pagina"):
        Pagina_Index_Version.objects.update_or_create(
            id_pagina=p,
            defaults={"id_index_version": nueva_version},
        )

    return {
        "campo_id": str(campo.id_campo),
        "formulario_id": str(formulario.id),
        "pagina_id": str(pagina.id_pagina),
        "nueva_version_id": str(nueva_version.id_index_version),
        "pagina_version_id": str(nueva_pv.id_pagina_version),
        "sequence": sequence,
    }
    
TIPO_POR_CLASE = {
    "number": "number",
    "boolean": "boolean",
    "text": "text",
    "string": "text",
    "date": "date",
    "hour": "hour",
    "list": "list",
    "group": "group",
    "calc": "calc",
    "dataset": "dataset",
    "firm": "firm",
}

def _uuid32() -> str:
    return uuid.uuid4().hex

def _pagina_version_actual_o_nueva(id_pagina: str) -> PaginaVersion:
    id_pagina_32 = _uuid32_no_dashes(id_pagina)

    pv = (PaginaVersion.objects
          .filter(id_pagina=id_pagina_32)
          .order_by("-fecha_creacion")
          .first())
    if pv:
        return pv

    nuevo_id = _uuid32()  
    pv = PaginaVersion.objects.create(
        id_pagina_version=nuevo_id,
        fecha_creacion=timezone.now(),   
        id_pagina=id_pagina_32,
    )
    return pv

def _siguiente_sequence(id_pagina_version: str) -> int:
    from django.db.models import Max
    mx = (PaginaCampo.objects
        .filter(id_pagina_version=id_pagina_version)
        .aggregate(Max('sequence'))['sequence__max'] or 0)
    return int(mx) + 1

@transaction.atomic
def crear_campo_en_pagina(id_pagina: str, payload: dict) -> dict:
    clase = payload["clase"]
    if not ClaseCampo.objects.filter(pk=clase).exists():
        raise ValueError(f"La clase '{clase}' no existe en formularios_clase_campo.")
    tipo = TIPO_POR_CLASE.get(clase, clase)

    nombre_campo = payload["nombre_campo"]
    etiqueta = payload["etiqueta"]
    ayuda = payload.get("ayuda")
    requerido = payload.get("requerido", None)

    cfg = payload.get("config")
    if isinstance(cfg, (dict, list)):
        cfg = json.dumps(cfg, ensure_ascii=False)

    id_campo = _uuid32()

    campo = Campo.objects.create(
        id_campo=id_campo,
        tipo=tipo,
        clase=clase,
        nombre_campo=nombre_campo,
        etiqueta=etiqueta,
        ayuda=ayuda,
        config=cfg,          
        requerido=requerido,
    )

    if (clase or "").lower() == "dataset":
        cfg_dict = {}
        if isinstance(cfg, dict):
            cfg_dict = cfg
        elif isinstance(cfg, str):
            try:
                cfg_dict = json.loads(cfg or "{}")
            except Exception:
                cfg_dict = {}

        # Valida config mínima
        ds = (cfg_dict.get("dataset") or {})
        if not ds.get("fuente_id"):
            raise ValueError("config.dataset.fuente_id es requerido para campos dataset")

        # Llama a la función sin versiones: devuelve SOLO n
        n = _materializar_dataset_para_campo(cfg_dict, campo)

        # Asegura que no quede 'version' viejo en el config
        if "dataset" in cfg_dict and isinstance(cfg_dict["dataset"], dict):
            cfg_dict["dataset"].pop("version", None)

        campo.config = json.dumps(cfg_dict, ensure_ascii=False)
        campo.save(update_fields=["config"])

    if (clase or "").lower() == "group":
        cfg_dict = {}
        if isinstance(cfg, dict):
            cfg_dict = cfg
        elif isinstance(cfg, str):
            try:
                cfg_dict = json.loads(cfg)
            except Exception:
                cfg_dict = {}

        id_group = _first_or_same(cfg_dict.get("id_group"))
        name     = _first_or_same(cfg_dict.get("name"))
        desc     = _first_or_same(cfg_dict.get("fieldCondition"))  

        if not id_group:
            id_group = _ensure_str_uuid()
            cfg_dict["id_group"] = id_group
        if not name:
            name = (etiqueta or nombre_campo or "Grupo")[:150]
            cfg_dict["name"] = name

        if isinstance(campo.config, dict):
            campo.config.update(cfg_dict)
            campo.save(update_fields=["config"])
        else:
            campo.config = json.dumps(cfg_dict, ensure_ascii=False)
            campo.save(update_fields=["config"])

        Grupo.objects.update_or_create(
            id_grupo=id_group,
            defaults={
                "id_campo_group": campo,
                "nombre": name,
            }
        )

    pv = _pagina_version_actual_o_nueva(id_pagina)

    seq = payload.get("sequence")
    if not seq:
        seq = _siguiente_sequence(pv.id_pagina_version)

    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO formularios_pagina_campo (id_campo, id_pagina_version, "sequence")
            VALUES (%s, %s, %s)
            """,
            [id_campo, pv.id_pagina_version, seq],
        )

    return {
        "id_campo": id_campo,
        "tipo": tipo,
        "clase": clase,
        "nombre_campo": nombre_campo,
        "etiqueta": etiqueta,
        "id_pagina": id_pagina,
        "id_pagina_version": pv.id_pagina_version,
        "sequence": seq,
    }

def hash_password(plain: str) -> str:
    salt = urandom(16)
    phc = hash_secret(
        secret=plain.encode("utf-8"),
        salt=salt,
        time_cost=3,
        memory_cost=65536,   
        parallelism=1,
        hash_len=32,
        type=Type.ID,
        version=19,
    )
    return phc.decode("utf-8")

def verify_password(hash_phc: str, plain: str) -> bool:
    return verify_secret(hash_phc.encode("utf-8"), plain.encode("utf-8"), Type.ID)

@transaction.atomic
def duplicar_formulario(formulario: Formulario, nuevo_nombre: str | None = None) -> Formulario:
    clon = Formulario.objects.create(
        categoria=formulario.categoria,
        nombre=nuevo_nombre or f"{formulario.nombre}_Copia",
        descripcion=formulario.descripcion,
        permitir_fotos=formulario.permitir_fotos,
        permitir_gps=formulario.permitir_gps,
        disponible_desde_fecha=formulario.disponible_desde_fecha,
        disponible_hasta_fecha=formulario.disponible_hasta_fecha,
        estado=formulario.estado,
        forma_envio=formulario.forma_envio,
        es_publico=formulario.es_publico,
        auto_envio=formulario.auto_envio,
    )

    idx_clon = FormularioIndexVersion.objects.create(formulario_id=clon)

    idx_orig = (FormularioIndexVersion.objects
                .filter(formulario_id=formulario)
                .order_by("-fecha_creacion")
                .first())

    if idx_orig:
        page_ids = (Pagina_Index_Version.objects
                    .filter(id_index_version=idx_orig)
                    .values_list("id_pagina", flat=True))
        paginas_origen = Pagina.objects.filter(id_pagina__in=page_ids).order_by("secuencia")
    else:
        paginas_origen = Pagina.objects.filter(formulario_id=formulario).order_by("secuencia")

    for p in paginas_origen:
        p_nueva = Pagina.objects.create(
            index_version=idx_clon,           
            formulario_id=clon,
            secuencia=p.secuencia,
            nombre=p.nombre,
            descripcion=p.descripcion,
        )

        Pagina_Index_Version.objects.create(
            id_pagina=p_nueva,
            id_index_version=idx_clon,
        )

        pid32 = _uuid32_no_dashes(str(p.id_pagina))
        pv_orig = (PaginaVersion.objects
                   .filter(id_pagina=pid32)
                   .order_by("-fecha_creacion")
                   .first())

        pv_nueva = PaginaVersion.objects.create(
            id_pagina_version=uuid32(uuid.uuid4()),
            id_pagina=_uuid32_no_dashes(str(p_nueva.id_pagina)),
            fecha_creacion=timezone.now(),
        )

        if pv_orig:
            links = (PaginaCampo.objects
                     .filter(id_pagina_version=pv_orig.id_pagina_version)
                     .order_by("sequence"))

            for l in links:
                c = l.id_campo
       

                c_nuevo = Campo.objects.create(
                    id_campo=uuid32(uuid.uuid4()),          
                    tipo=c.tipo,
                    clase=c.clase,
                    nombre_campo=c.nombre_campo,       
                    etiqueta=c.etiqueta,
                    ayuda=c.ayuda,
                    config=c.config,
                    requerido=c.requerido,
                )

                PaginaCampo.objects.create(
                    id_pagina_version=pv_nueva,        
                    id_campo=c_nuevo,                  
                    sequence=l.sequence,
                )

    return clon

def versionar_pagina_sin_clonar(pagina) -> PaginaVersion:
    """Crea una nueva PaginaVersion para 'pagina' reutilizando los mismos Campo (no clona)."""
    pid32 = _uuid32_no_dashes(str(pagina.id_pagina))

    prev = (
        PaginaVersion.objects
        .filter(id_pagina=pid32)
        .order_by('-fecha_creacion')
        .first()
    )

    nueva_pv = PaginaVersion.objects.create(
        id_pagina_version=uuid32(),
        id_pagina=pid32,
        fecha_creacion=timezone.now(),
    )

    if prev:
        links = (
            PaginaCampo.objects
            .filter(id_pagina_version=prev.id_pagina_version)
            .order_by('sequence')
        )
        PaginaCampo.objects.bulk_create([
            PaginaCampo(
                id_pagina_version=nueva_pv.id_pagina_version,
                id_campo=l.id_campo,          
                sequence=l.sequence
            )
            for l in links
        ])

    return nueva_pv

@transaction.atomic
def _materializar_dataset_para_campo(cfg: dict, campo):
    """
    Lee el blob de FuenteDatos y llena FuenteDatosValor para ESTE campo.
    **Sin versiones**: borra lo existente y re-materializa.
    Retorna rows_insertadas (int).
    """
    ds = (cfg or {}).get("dataset") or {}
    fuente_id = ds.get("fuente_id")
    mode = (ds.get("mode") or "pair").lower()  # "pair" o "single"
    alias = ds.get("column") or ds.get("label_column") or "dataset"

    if not fuente_id:
        raise ValidationError("dataset.fuente_id es requerido")

    f = FuenteDatos.objects.get(pk=fuente_id)

    storage = AzureBlobStorageService()
    content = storage.download_file(f.blob_name)
    ext = (f.archivo_nombre or f.blob_name).split(".")[-1].lower()
    file_obj = BytesIO(content)

    # Lee Excel/CSV como texto
    if ext in ("xlsx", "xls"):
        df = pd.read_excel(file_obj, dtype=str)
    else:
        df = pd.read_csv(file_obj, dtype=str)

    df = df.fillna("")
    df.columns = [str(c).strip() for c in df.columns]

    # Índice case-insensitive de columnas + chequeo de colisiones (p.ej. 'ID' y 'id')
    lower_idx = {}
    for c in df.columns:
        k = c.lower()
        if k in lower_idx and lower_idx[k] != c:
            raise ValidationError(
                f"Columnas duplicadas que solo difieren por mayúsculas/minúsculas: "
                f"'{lower_idx[k]}' y '{c}'. Renombra en la fuente."
            )
        lower_idx[k] = c

    def resolve_col(name: str | None, default: str | None = None) -> str:
        """
        Devuelve el nombre EXACTO presente en el DF, resolviendo case-insensitive.
        Si name es None, usa default. Lanza error si no existe.
        """
        target = (name or default or "").strip()
        if not target:
            raise ValidationError("No se especificó columna requerida.")
        real = lower_idx.get(target.lower())
        if not real:
            raise ValidationError(
                f"Columna '{name or default}' no existe en la fuente. "
                f"Disponibles: {sorted(df.columns)}"
            )
        return real

    # cols = set(map(str, df.columns))
    # if mode == "single":
    #     col = ds.get("column")
    #     if not col or col not in cols:
    #         raise ValidationError(
    #             f"Columna '{col}' no existe en la fuente. Disponibles: {sorted(cols)}"
    #         )
    # else:  # pair
    #     kcol, lcol = ds.get("key_column"), ds.get("label_column")
    #     missing = [x for x in (kcol, lcol) if not x or x not in cols]
    #     if missing:
    #         raise ValidationError(
    #             f"Columnas faltantes en la fuente: {missing}. Disponibles: {sorted(cols)}"
    #         )

    # --- (2) Resolver columnas según el modo (case-insensitive) ---
    if mode == "single":
        col_real = resolve_col(ds.get("column"))
        # Persistimos el nombre real de la columna en el config
        ds["column"] = col_real
        alias = col_real  # alias útil para rastrear en FuenteDatosValor.columna
    elif mode == "pair":
        # default 'id' si no viene key_column; resolverá 'ID', 'Id', etc.
        kcol_real = resolve_col(ds.get("key_column"), default="id")
        lcol_real = resolve_col(ds.get("label_column"))
        ds["key_column"] = kcol_real
        ds["label_column"] = lcol_real
        # Usamos label_column como alias por defecto (o puedes mantener tu criterio original)
        ds["column"] = lcol_real
        alias = ds.get("label_column") or "dataset"
    else:
        raise ValidationError("dataset.mode debe ser 'single' o 'pair'")

    # Trim de todas las columnas
    for c in df.columns:
        df[c] = df[c].astype(str).map(lambda x: x.strip())

    # Limpia valores previos del campo
    FuenteDatosValor.objects.filter(campo=campo).delete()

    # Construye filas
    rows = []
    if mode == "single":
        col = ds["column"]
        # únicos + ordenados; evita vacíos
        serie = (
            df[col]
            .dropna()
            .map(lambda x: x.strip())
            .loc[lambda s: s != ""]
            .drop_duplicates()
            .sort_values()
        )
        for v in serie:
            rows.append(
                FuenteDatosValor(
                    campo=campo,
                    fuente=f,               # <-- requiere tener FK fuente en el modelo
                    columna=alias,
                    key_text=None,
                    label_text=v,
                    valor_raw={"value": v},
                    extras={},
                )
            )
    else:
        kcol, lcol = ds["key_column"], ds["label_column"]
        tmp = (
            df[[kcol, lcol]]
            .dropna()
            .assign(
                **{
                    kcol: df[kcol].map(lambda x: (x or "").strip()),
                    lcol: df[lcol].map(lambda x: (x or "").strip()),
                }
            )
            .loc[lambda d: (d[kcol] != "") & (d[lcol] != "")]
            .drop_duplicates()
            .sort_values(by=[lcol, kcol])
        )

        for _, r in tmp.iterrows():
            k, l = r[kcol], r[lcol]
            rows.append(
                FuenteDatosValor(
                    campo=campo,
                    fuente=f,               # <-- requiere tener FK fuente en el modelo
                    columna=alias,
                    key_text=k,
                    label_text=l,
                    valor_raw={kcol: k, lcol: l},
                    extras={},
                )
            )

    if rows:
        # ajusta batch_size si manejas catálogos muy grandes
        FuenteDatosValor.objects.bulk_create(rows, batch_size=5000)

    # Limpia cualquier rastro viejo de versión en el config
    ds.pop("version", None)
    cfg["dataset"] = ds

    return len(rows)