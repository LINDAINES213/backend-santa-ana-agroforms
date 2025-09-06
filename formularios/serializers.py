from rest_framework import serializers
from rest_framework.response import Response
from rest_framework import status
from .models import Formulario, Categoria, Pagina, FormularioIndexVersion, ClaseCampo, Campo, PaginaActualVersion, FormularioActualVersion
from .validators import validate_config_against_schema
from django.utils.text import slugify
import uuid


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
        activos = (PaginaActualVersion.objects
                   .filter(formulario=obj)
                   .select_related("pagina")
                   )
        if activos.exists():
            paginas = [a.pagina for a in activos]
            from .serializers import PaginaConCamposSerializer
            return PaginaConCamposSerializer(paginas, many=True, context=self.context).data

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

        # 1) resolver fila de catálogo
        qs = list(ClaseCampo.objects.all())
        row = next((c for c in qs if (c.clase or "").strip().lower() == clase_norm), None)
        if not row:
            disponibles = [ (c.clase or "").strip() for c in qs ]
            raise serializers.ValidationError({
                "clase": f"Clase no registrada en catálogo. Recibido='{raw_clase}'. Disponibles: {', '.join(disponibles)}"
            })

        # 2) Autogenerar ids en config
        cfg = attrs.get("config") or {}
        if clase_norm == "list":
            if not cfg.get("id_list"):
                base = attrs.get("nombre_campo") or "lista"
                slug = slugify(base) or "lista"
                cfg["id_list"] = f"{slug}-{uuid.uuid4().hex[:6]}"
                attrs["config"] = cfg  # reinyecta
        elif clase_norm == "group":
            if not cfg.get("id_group"):
                base = attrs.get("nombre_campo") or "grupo"
                slug = slugify(base) or "grupo"
                cfg["id_group"] = f"{slug}-{uuid.uuid4().hex[:6]}"
                attrs["config"] = cfg  # reinyecta


        # 3) validar config contra el schema
        schema = row.schema if isinstance(row.schema, dict) else None
        errs = validate_config_against_schema(cfg, schema)
        if errs:
            raise serializers.ValidationError({"config": errs})

        # 4) coherencia tipo<->clase
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
        
        grupo = attrs.get("grupo") or getattr(self.instance, "grupo", None)
        if grupo:
            # el padre debe ser un campo de clase 'group'
            if (grupo.clase or "").strip().lower() != "group":
                raise serializers.ValidationError({"grupo": "El campo 'grupo' debe apuntar a un campo de clase 'group'."})
            pagina = attrs.get("pagina") or getattr(self.instance, "pagina", None)
            if pagina and grupo.pagina_id != pagina.id_pagina:
                raise serializers.ValidationError({"grupo": "El 'grupo' debe pertenecer a la misma página."})

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