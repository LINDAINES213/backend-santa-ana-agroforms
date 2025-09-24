# formularios/migrations/0010_fix_delete_cascade.py
from django.db import migrations

SQL = r"""
-- 1) formularios_paginaindex.id_pagina_id -> formularios_pagina.id_pagina
IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'formularios_paginaindex_id_pagina_id_30491fd5_fk_formularios_pagina_id_pagina')
BEGIN
  ALTER TABLE [dbo].[formularios_paginaindex]
    DROP CONSTRAINT [formularios_paginaindex_id_pagina_id_30491fd5_fk_formularios_pagina_id_pagina];
END
ALTER TABLE [dbo].[formularios_paginaindex]
  ADD CONSTRAINT [formularios_paginaindex_id_pagina_id_fk]
  FOREIGN KEY ([id_pagina_id])
  REFERENCES [dbo].[formularios_pagina] ([id_pagina])
  ON DELETE CASCADE;

-- 2) formularios_paginaindex.id_formulario_id -> formularios_formulario.id
IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'formularios_paginaindex_id_formulario_id_fk')
BEGIN
  ALTER TABLE [dbo].[formularios_paginaindex]
    DROP CONSTRAINT [formularios_paginaindex_id_formulario_id_fk];
END
ALTER TABLE [dbo].[formularios_paginaindex]
  ADD CONSTRAINT [formularios_paginaindex_id_formulario_id_fk]
  FOREIGN KEY ([id_formulario_id])
  REFERENCES [dbo].[formularios_formulario] ([id])
  ON DELETE CASCADE;

-- 3) formularios_paginaactualversion.pagina_id -> formularios_pagina.id_pagina
IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'formularios_paginaactualversion_pagina_id_b720a0fc_fk_formularios_pagina_id_pagina')
BEGIN
  ALTER TABLE [dbo].[formularios_paginaactualversion]
    DROP CONSTRAINT [formularios_paginaactualversion_pagina_id_b720a0fc_fk_formularios_pagina_id_pagina];
END
ALTER TABLE [dbo].[formularios_paginaactualversion]
  ADD CONSTRAINT [formularios_paginaactualversion_pagina_id_fk]
  FOREIGN KEY ([pagina_id])
  REFERENCES [dbo].[formularios_pagina] ([id_pagina])
  ON DELETE CASCADE;

-- 4) formularios_paginaactualversion.formulario_id -> formularios_formulario.id
IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'formularios_paginaactualversion_formulario_id_fk')
BEGIN
  ALTER TABLE [dbo].[formularios_paginaactualversion]
    DROP CONSTRAINT [formularios_paginaactualversion_formulario_id_fk];
END
ALTER TABLE [dbo].[formularios_paginaactualversion]
  ADD CONSTRAINT [formularios_paginaactualversion_formulario_id_fk]
  FOREIGN KEY ([formulario_id])
  REFERENCES [dbo].[formularios_formulario] ([id])
  ON DELETE CASCADE;

-- 5) formularios_paginaactualversion.version_activa_id -> formularios_formularioactualversion.id
IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'formularios_paginaactualversion_version_activa_id_fk')
BEGIN
  ALTER TABLE [dbo].[formularios_paginaactualversion]
    DROP CONSTRAINT [formularios_paginaactualversion_version_activa_id_fk];
END
ALTER TABLE [dbo].[formularios_paginaactualversion]
  ADD CONSTRAINT [formularios_paginaactualversion_version_activa_id_fk]
  FOREIGN KEY ([version_activa_id])
  REFERENCES [dbo].[formularios_formularioactualversion] ([id])
  ON DELETE CASCADE;

-- 6) formularios_campo2.pagina_id -> formularios_pagina.id_pagina
IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'formularios_campo2_pagina_id_fk')
BEGIN
  ALTER TABLE [dbo].[formularios_campo2]
    DROP CONSTRAINT [formularios_campo2_pagina_id_fk];
END
ALTER TABLE [dbo].[formularios_campo2]
  ADD CONSTRAINT [formularios_campo2_pagina_id_fk]
  FOREIGN KEY ([pagina_id])
  REFERENCES [dbo].[formularios_pagina] ([id_pagina])
  ON DELETE CASCADE;
"""

class Migration(migrations.Migration):
    dependencies = [
        ("formularios", "0009_alter_paginaactualversion_options_and_more"),
    ]
    operations = [
        migrations.RunSQL(SQL),
    ]
