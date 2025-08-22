# services.py
from typing import Dict, Optional
from django.db import connection, transaction
from django.core.exceptions import ObjectDoesNotExist
from .models import Formulario  # importa tu modelo real
# Si ya tienes un modelo Instancia_formulario, importa también:
# from .models import InstanciaFormulario

def _quote(name: str) -> str:
    return connection.ops.quote_name(name)

def _table_exists(table: str) -> bool:
    with connection.cursor() as cur:
        return table in connection.introspection.table_names()

def _get_columns(table: str):
    with connection.cursor() as cur:
        return [c.name for c in connection.introspection.get_table_description(cur, table)]

def _list_res_tables(prefix: str = "res_"):
    with connection.cursor() as cur:
        tables = connection.introspection.table_names()
    return [t for t in tables if t.startswith(prefix)]

def _get_instancia_table_name() -> Optional[str]:
    # Si tienes modelo ORM:
    # return InstanciaFormulario._meta.db_table
    # Si aún no lo tienes mapeado por ORM, pon el nombre físico:
    candidate = "instancia_formulario"
    return candidate if _table_exists(candidate) else None

def _delete_rows_in_res_tables(formulario_id) -> Dict[str, int]:
    """
    Limpia filas en tablas res_* asociadas al formulario.
    - Preferido: join vía id_instancia -> instancia_formulario(formulario_id)
    - Plan B: columna directa formulario_id / id_formulario en la tabla hoja
    """
    deleted = {}
    inst_tbl = _get_instancia_table_name()
    res_tables = _list_res_tables()

    with connection.cursor() as cur:
        for t in res_tables:
            cols = set(_get_columns(t))

            # 1) vía instancia (si existe la tabla y la columna)
            id_inst_col = None
            if "id_instancia_id" in cols:
                id_inst_col = "id_instancia_id"
            elif "id_instancia" in cols:
                id_inst_col = "id_instancia"

            if inst_tbl and id_inst_col:
                sql = (
                    f"DELETE r FROM {_quote(t)} r "
                    f"INNER JOIN {_quote(inst_tbl)} i "
                    f"ON r.{_quote(id_inst_col)} = i.{_quote('id_instancia')} "
                    f"WHERE i.{_quote('id_formulario')} = %s"
                )
                cur.execute(sql, [str(formulario_id)])
                deleted[t] = cur.rowcount
                continue

            # 2) columna directa en la hoja
            form_col = None
            if "formulario_id" in cols:
                form_col = "formulario_id"
            elif "id_formulario" in cols:
                form_col = "id_formulario"

            if form_col:
                sql = f"DELETE FROM {_quote(t)} WHERE {_quote(form_col)} = %s"
                cur.execute(sql, [str(formulario_id)])
                deleted[t] = cur.rowcount
                continue

            # 3) no se pudo filtrar
            deleted[t] = 0

    return deleted

@transaction.atomic
def delete_formulario_hard(formulario_id):
    """
    Limpia respuestas en res_* y borra el formulario (cascade del resto).
    Retorna un resumen.
    """
    try:
        form = (Formulario.objects
                .select_for_update()
                .get(pk=formulario_id))
    except ObjectDoesNotExist:
        return {"ok": False, "error": "Formulario no existe"}

    hojas = _delete_rows_in_res_tables(formulario_id)
    form.delete()

    return {
        "ok": True,
        "formulario_id": str(formulario_id),
        "respuestas_borradas": hojas
    }
