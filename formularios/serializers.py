from .services import _uuid32_no_dashes
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework import status
from .models import Campo, Categoria, Formulario, FormularioIndexVersion, Pagina, PaginaCampo, PaginaVersion
# from .validators import validate_config_against_schema
from django.utils.text import slugify
import uuid


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'

# class PaginaSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Pagina
#         fields = "__all__"
#         read_only_fields = ("id_pagina", "index_version", "formulario")

# class PaginaConCamposSerializer(serializers.ModelSerializer):
#     campos = serializers.SerializerMethodField()

#     class Meta:
#         model = Pagina
#         fields = ("id_pagina","secuencia","nombre","descripcion","index_version","formulario","campos")

#     def get_campos(self, obj):
#         qs = obj.campos.all().order_by("sequence","id_campo")
#         return CampoSerializer(qs, many=True).data

class PaginaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pagina
        # No expongamos FKs internos; con esto basta para el GET
        fields = ("id_pagina", "secuencia", "nombre", "descripcion")

class CrearCampoEnPaginaSerializer(serializers.Serializer):
    clase = serializers.CharField()
    nombre_campo = serializers.RegexField(r"^[a-z0-9_]+$", max_length=64)
    etiqueta = serializers.CharField(max_length=100)
    ayuda = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)
    requerido = serializers.BooleanField(required=False)
    config = serializers.JSONField(required=False)     # se valida con isjson() en la BD
    sequence = serializers.IntegerField(required=False, min_value=1)  # posición opcional

class PaginaConCamposSerializer(PaginaSerializer):
    campos = serializers.SerializerMethodField()

    class Meta(PaginaSerializer.Meta):
        fields = PaginaSerializer.Meta.fields + ("campos",)

    def get_campos(self, obj):
        # 1) normalizar id_pagina a 32 sin guiones (la tabla usa char(32))
        try:
            id_pagina_32 = _uuid32_no_dashes(str(obj.id_pagina))
        except Exception:
            return []

        # 2) última versión de esa página
        pv = (PaginaVersion.objects
              .filter(id_pagina=id_pagina_32)
              .order_by("-fecha_creacion")
              .first())
        if not pv:
            return []

        # 3) enlaces de esa versión → campos
        links = (PaginaCampo.objects
                 .filter(id_pagina_version=pv.id_pagina_version)
                 .select_related("id_campo")
                 .order_by("sequence"))

        out = []
        for l in links:
            c: Campo = l.id_campo
            out.append({
                "id_campo": str(c.id_campo),
                "sequence": l.sequence,
                "nombre_campo": c.nombre_campo,
                "etiqueta": c.etiqueta,
                "clase": c.clase,
                "tipo": c.tipo,
                "requerido": c.requerido,
                "config": c.config,
            })
        return out


class FormularioSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.SerializerMethodField()
    paginas = serializers.SerializerMethodField()

    class Meta:
        model = Formulario
        fields = "__all__"

    def get_categoria_nombre(self, obj):
        return obj.categoria.nombre if obj.categoria else None

    def get_paginas(self, obj):
        # Siempre la versión más reciente por fecha
        last_version = (FormularioIndexVersion.objects
                        .filter(formulario_id=obj)         # FK correcto
                        .order_by("-fecha_creacion")
                        .first())
        if not last_version:
            return []
        qs = Pagina.objects.filter(index_version=last_version).order_by("secuencia")
        return PaginaConCamposSerializer(qs, many=True, context=self.context).data
    
    # def get_paginas(self, obj):
    #     activos = (PaginaActualVersion.objects
    #                .filter(formulario=obj)
    #                .select_related("pagina")
    #                )
    #     if activos.exists():
    #         paginas = [a.pagina for a in activos]
    #         from .serializers import PaginaConCamposSerializer
    #         return PaginaConCamposSerializer(paginas, many=True, context=self.context).data

    #     last_version = (FormularioIndexVersion.objects
    #                     .filter(formulario=obj).order_by("-fecha_creacion").first())
    #     if not last_version:
    #         return []
    #     qs = Pagina.objects.filter(index_version=last_version).order_by("secuencia")
    #     from .serializers import PaginaConCamposSerializer
    #     return PaginaConCamposSerializer(qs, many=True, context=self.context).data

# import logging

# logger = logging.getLogger(__name__)

# class CampoSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Campo
#         fields = "__all__"
#         read_only_fields = ("id_campo","creado","actualizado","pagina")
#         extra_kwargs = {
#             "tipo": {"required": False, "allow_blank": True},
#         }

#     def validate(self, attrs):
#         raw = (attrs.get("clase") or getattr(self.instance, "clase", "") or "")
#         clase = raw.strip().lower()

#         # 1) clase válida en catálogo
#         row = next((c for c in ClaseCampo.objects.all()
#                     if (c.clase or "").strip().lower() == clase), None)
#         if not row:
#             disponibles = [ (c.clase or "").strip() for c in ClaseCampo.objects.all() ]
#             raise serializers.ValidationError({"clase": f"Clase no registrada. Usa: {', '.join(disponibles)}"})

#         # 2) autogenerar IDs en config si aplica
#         cfg = attrs.get("config") or {}
#         if clase == "list" and not cfg.get("id_list"):
#             base = attrs.get("nombre_campo") or "lista"
#             cfg["id_list"] = f"{slugify(base) or 'lista'}-{uuid.uuid4().hex[:6]}"
#             attrs["config"] = cfg
#         if clase == "group" and not cfg.get("id_group"):
#             base = attrs.get("nombre_campo") or "grupo"
#             cfg["id_group"] = f"{slugify(base) or 'grupo'}-{uuid.uuid4().hex[:6]}"
#             attrs["config"] = cfg

#         # 3) validar config ↔ schema
#         schema = row.schema if isinstance(row.schema, dict) else None
#         errs = validate_config_against_schema(cfg, schema)
#         if errs:
#             raise serializers.ValidationError({"config": errs})

#         # 4) AUTORRELLENO de 'tipo' por 'clase'
#         matrix = {
#             "number":  "numerico",
#             "boolean": "booleano",
#             "date":    "date",
#             "hour":    "hour",
#             "img":     "texto",
#             "dataset": "texto",
#             "list":    "texto",
#             "calc":    "numerico",
#             "string":  "texto",
#             "text":    "texto",
#             "group":   "string",
#         }
#         esperado = matrix.get(clase)
#         if esperado:
#             attrs["tipo"] = esperado

#         # 5) si viene 'grupo', que sea de clase 'group' y de la misma página
#         grupo = attrs.get("grupo") or getattr(self.instance, "grupo", None)
#         if grupo:
#             if (grupo.clase or "").strip().lower() != "group":
#                 raise serializers.ValidationError({"grupo": "El 'grupo' debe ser de clase 'group'."})
#             pagina = attrs.get("pagina") or getattr(self.instance, "pagina", None)
#             if pagina and getattr(grupo, "pagina_id", None) != getattr(pagina, "id_pagina", None):
#                 raise serializers.ValidationError({"grupo": "El 'grupo' debe pertenecer a la misma página."})

#         return attrs

# class FormularioActualSerializer(serializers.ModelSerializer):
#     """
#     Renderiza un formulario usando SIEMPRE la versión ACTUAL:
#     delega en FormularioSerializer (que ya lee PaginaActualVersion)
#     pero añade metadatos de la versión activa.
#     """
#     class Meta:
#         model = FormularioActualVersion
#         fields = ("formulario", "index_version", "publicada_en")

#     def to_representation(self, obj):
#         # Reusar la salida del FormularioSerializer (ya usa PaginaActualVersion)
#         data = FormularioSerializer(obj.formulario, context=self.context).data
#         # extra útil: id de la versión activa + timestamp de publicación
#         data["version_activa_id"] = str(obj.index_version_id)
#         data["publicada_en"] = obj.publicada_en.isoformat() if obj.publicada_en else None
#         return data
    
# class PaginaActualSerializer(serializers.Serializer):
#     """
#     Representa una página VIGENTE a partir de PaginaActualVersion.
#     Devuelve exactamente el payload de PaginaConCamposSerializer de la Pagina asociada,
#     más metadatos útiles (orden, formulario, etc).
#     """
#     def to_representation(self, obj: PaginaActualVersion):
#         pagina = obj.pagina
#         data = PaginaConCamposSerializer(pagina, context=self.context).data
#         # data["orden_vigente"] = obj.orden
#         data["formulario_id"] = str(obj.formulario_id)
#         return data
    
# class UsuarioSerializer(serializers.ModelSerializer):
#     rol_nombre = serializers.CharField(source="rol.nombre", read_only=True)

#     class Meta:
#         model = Usuario
#         fields = "__all__"

# class RolSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Rol
#         fields = "__all__"