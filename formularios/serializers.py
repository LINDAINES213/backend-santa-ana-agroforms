from rest_framework import serializers
from rest_framework.response import Response
from rest_framework import status
from .models import Formulario, Categoria, Pagina, FormularioIndexVersion, ClaseCampo, Campo, PaginaActualVersion, FormularioActualVersion
from .validators import validate_config_against_schema


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'

class PaginaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pagina
        fields = "__all__"
        read_only_fields = ("id_pagina", "index_version", "formulario")

class PaginaConCamposSerializer(serializers.ModelSerializer):
    campos = serializers.SerializerMethodField()

    class Meta:
        model = Pagina
        fields = ("id_pagina","secuencia","nombre","descripcion","index_version","formulario","campos")

    def get_campos(self, obj):
        qs = obj.campos.all().order_by("sequence","id_campo")
        return CampoSerializer(qs, many=True).data

class FormularioSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.SerializerMethodField()
    paginas = serializers.SerializerMethodField()
    class Meta:
        model = Formulario
        fields = "__all__"

    def get_categoria_nombre(self, obj):
        return obj.categoria.nombre if obj.categoria else None

    # def get_paginas(self, obj):
    #     # Tomar SIEMPRE la última versión
    #     last_version = (FormularioIndexVersion.objects
    #                     .filter(formulario=obj).order_by("-fecha_creacion").first())
    #     if not last_version:
    #         return []

    #     qs = Pagina.objects.filter(index_version=last_version).order_by("secuencia")

    #     from .serializers import PaginaConCamposSerializer 
    #     return PaginaConCamposSerializer(qs, many=True, context=self.context).data
    def get_paginas(self, obj):
        # 1) intentar vía “vigente”
        activos = (PaginaActualVersion.objects
                   .filter(formulario=obj)
                   .select_related("pagina")
                   )
        if activos.exists():
            paginas = [a.pagina for a in activos]
            from .serializers import PaginaConCamposSerializer
            return PaginaConCamposSerializer(paginas, many=True, context=self.context).data

        # 2) fallback: última versión histórica (como ya lo tenías)
        last_version = (FormularioIndexVersion.objects
                        .filter(formulario=obj).order_by("-fecha_creacion").first())
        if not last_version:
            return []
        qs = Pagina.objects.filter(index_version=last_version).order_by("secuencia")
        from .serializers import PaginaConCamposSerializer
        return PaginaConCamposSerializer(qs, many=True, context=self.context).data

import logging

logger = logging.getLogger(__name__)

class CampoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campo
        fields = "__all__"
        read_only_fields = ("id_campo","creado","actualizado","pagina")

    def validate(self, attrs):
        raw_clase  = (attrs.get("clase") or getattr(self.instance, "clase", "") or "")
        clase_norm = raw_clase.strip().lower()

        qs = list(ClaseCampo.objects.all())
        catalogo_raw  = [ (c.clase or "") for c in qs ]
        catalogo_norm = [ (c.clase or "").strip().lower() for c in qs ]
        logger.warning("CATALOGO DEBUG raw=%s norm=%s input_raw=%r input_norm=%r  (model=%s, db_table=%s)",
                       catalogo_raw, catalogo_norm, raw_clase, clase_norm,
                       ClaseCampo.__module__ + "." + ClaseCampo.__name__,
                       getattr(getattr(ClaseCampo._meta, 'db_table', None), '__str__', lambda: ClaseCampo._meta.db_table)())

        row = None
        for c in qs:
            if ((c.clase or "").strip().lower() == clase_norm):
                row = c
                break

        if not row:
            disponibles = [ (s or "").strip() for s in catalogo_raw ]
            raise serializers.ValidationError({
                "clase": f"Clase no registrada en catálogo. Recibido='{raw_clase}'. Disponibles: {', '.join(disponibles)}"
            })

        # --- Validar config contra schema ---
        cfg    = attrs.get("config", {}) or {}
        schema = row.schema if isinstance(row.schema, dict) else None  
        errs = validate_config_against_schema(cfg, schema)
        if errs:
            logger.warning("CONFIG ERROR para clase=%s cfg=%s schema=%s -> %s", raw_clase, cfg, schema, errs)
            raise serializers.ValidationError({"config": errs})

        matrix = {
            "number":  "numerico",
            "boolean": "booleano",
            "date":    "date",
            "hour":    "hour",
            "img":     "texto",
            "dataset": "texto",
            "list":    "texto",
            "calc":    "numerico",
            "string":  "texto",
            "text":    "texto",
            "group":   "string",
        }
        tipo = attrs.get("tipo") or getattr(self.instance, "tipo", None)
        esperado = matrix.get(clase_norm)
        if esperado and tipo != esperado:
            raise serializers.ValidationError({"tipo": f"tipo '{tipo}' no coincide con clase '{raw_clase}' (esperado '{esperado}')"})

        # DEBUG ok
        logger.warning("VALIDACION OK: clase=%r (match=%r) tipo=%r config=%r", raw_clase, row.clase, tipo, cfg)
        return attrs

class FormularioActualSerializer(serializers.ModelSerializer):
    """
    Renderiza un formulario usando SIEMPRE la versión ACTUAL:
    delega en FormularioSerializer (que ya lee PaginaActualVersion)
    pero añade metadatos de la versión activa.
    """
    class Meta:
        model = FormularioActualVersion
        fields = ("formulario", "index_version", "publicada_en")  # no se usan tal cual

    def to_representation(self, obj):
        # Reusar la salida del FormularioSerializer (ya usa PaginaActualVersion)
        data = FormularioSerializer(obj.formulario, context=self.context).data
        # extra útil: id de la versión activa + timestamp de publicación
        data["version_activa_id"] = str(obj.index_version_id)
        data["publicada_en"] = obj.publicada_en.isoformat() if obj.publicada_en else None
        return data
    
class PaginaActualSerializer(serializers.Serializer):
    """
    Representa una página VIGENTE a partir de PaginaActualVersion.
    Devuelve exactamente el payload de PaginaConCamposSerializer de la Pagina asociada,
    más metadatos útiles (orden, formulario, etc).
    """
    def to_representation(self, obj: PaginaActualVersion):
        pagina = obj.pagina
        data = PaginaConCamposSerializer(pagina, context=self.context).data
        # data["orden_vigente"] = obj.orden
        data["formulario_id"] = str(obj.formulario_id)
        return data
# class CampoSerializer(serializers.ModelSerializer):
#     es_grupo = serializers.BooleanField(write_only=True, default=False)

#     class Meta:
#         model  = Campo
#         fields = [
#             'id', 'formulario', 'grupo', 'nombre_campo',
#             'tipo', 'requerido', 'pertenece_grupo', 'es_grupo',
#         ]
#         read_only_fields = ['formulario', 'pertenece_grupo']  # lo calculamos, no se envía desde frontend

#     def validate(self, attrs):
#         grupo = attrs.get('grupo', None)
#         # Si grupo está asignado, pertenece_grupo es True, si no False
#         attrs['pertenece_grupo'] = bool(grupo)
#         return attrs

#     def create(self, validated_data):
#         es_grupo = validated_data.pop('es_grupo', False)
#         formulario = validated_data.pop('formulario', None)
#         nombre_campo = validated_data.get('nombre_campo')

#         if es_grupo:
#             # Crear Grupo si es grupo
#             grupo = Grupo.objects.create(formulario=formulario, nombre=nombre_campo)
#             return grupo

#         # Para campo normal, con pertenece_grupo ya calculado
#         campo = Campo.objects.create(formulario=formulario, **validated_data)
#         return campo

# class CampoSoloLecturaSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Campo
#         fields = ['id', 'nombre_campo', 'tipo', 'requerido', 'pertenece_grupo', 'grupo']


# class GrupoConCamposSerializer(serializers.ModelSerializer):
#     campos = CampoSoloLecturaSerializer(many=True, read_only=True)

#     class Meta:
#         model = Grupo
#         fields = ['id', 'nombre', 'campos']


# class FormularioDetalleSerializer(serializers.ModelSerializer):
#     campos = serializers.SerializerMethodField()
#     grupos = GrupoConCamposSerializer(many=True, read_only=True)

#     class Meta:
#         model = Formulario
#         fields = ['id', 'nombre', 'descripcion', 'fecha_creacion', 'campos', 'grupos']

#     def get_campos(self, obj):
#         # Solo campos que NO pertenecen a ningún grupo
#         campos = obj.campos.filter(grupo__isnull=True)
#         return CampoSoloLecturaSerializer(campos, many=True).data