from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("formularios", "0007_fuentedatos_tipo_fuente_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # Lo que se ejecuta en la BD (condicional)
            database_operations=[
                migrations.RunSQL(
                    """
                    ALTER TABLE formularios_consulta_sql
                        DROP COLUMN IF EXISTS columna_label,
                        DROP COLUMN IF EXISTS columna_value,
                        DROP COLUMN IF EXISTS columnas_extra;
                    """,
                    reverse_sql=migrations.RunSQL.noop,  # sin reversa
                ),
            ],
            # Lo que Django registra en el estado de modelos
            state_operations=[
                migrations.RemoveField(
                    model_name="consultasql",
                    name="columna_label",
                ),
                migrations.RemoveField(
                    model_name="consultasql",
                    name="columna_value",
                ),
                migrations.RemoveField(
                    model_name="consultasql",
                    name="columnas_extra",
                ),
            ],
        ),
    ]