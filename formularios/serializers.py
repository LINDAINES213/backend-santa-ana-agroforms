from .services import _uuid32_no_dashes, hash_password, uuid32
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework import status
from .models import Campo, Categoria, Formulario, FormularioIndexVersion, FuenteDatos, Grupo, Pagina, Pagina_Index_Version, PaginaCampo, PaginaVersion, Usuario
# from .validators import validate_config_against_schema
from django.db import connection
from rest_framework.validators import UniqueValidator
import uuid

class GrupoSerializer(serializers.ModelSerializer):
    # devolver solo el id del campo-group (no el objeto completo)
    id_campo_group = serializers.CharField(source="id_campo_group_id", read_only=True)

    class Meta:
        model = Grupo
        fields = ("id_grupo", "nombre", "id_campo_group")

class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'

class FuenteDatosSerializer(serializers.ModelSerializer):
    creado_por_nombre = serializers.CharField(source='creado_por.nombre', read_only=True)
    archivo = serializers.FileField(write_only=True, required=False)
    
    class Meta:
        model = FuenteDatos
        fields = [
            'id', 'nombre', 'descripcion', 'archivo_nombre', 
            'blob_url', 'tipo_archivo', 'columnas', 'preview_data',
            'fecha_subida', 'activo', 'creado_por', 'creado_por_nombre',
            'archivo'
        ]
        read_only_fields = [
            'id', 'blob_url', 'tipo_archivo', 'columnas', 
            'preview_data', 'fecha_subida', 'blob_name'
        ]
    
    def validate_archivo(self, value):
        """Valida el archivo subido"""
        if value:
            # Validar extensión
            filename = value.name
            extension = filename.split('.')[-1].lower()
            if extension not in ['xlsx', 'xls', 'csv']:
                raise serializers.ValidationError(
                    "Solo se permiten archivos Excel (.xlsx, .xls) o CSV (.csv)"
                )
            
            # Validar tamaño (máx 10MB)
            if value.size > 10 * 1024 * 1024:
                raise serializers.ValidationError(
                    "El archivo no puede superar los 10MB"
                )
        
        return value


class FuenteDatosCreateSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=200)
    descripcion = serializers.CharField(required=False, allow_blank=True)
    archivo = serializers.FileField()
    
    def validate_archivo(self, value):
        """Valida el archivo subido"""
        filename = value.name
        extension = filename.split('.')[-1].lower()
        if extension not in ['xlsx', 'xls', 'csv']:
            raise serializers.ValidationError(
                "Solo se permiten archivos Excel (.xlsx, .xls) o CSV (.csv)"
            )
        
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError(
                "El archivo no puede superar los 10MB"
            )
        
        return value
    
    def create(self, validated_data):
        archivo = validated_data.pop("archivo")
        request = self.context.get("request")
        usuario = getattr(request, "user", None)

        instancia = FuenteDatos.objects.create(
            nombre=validated_data.get("nombre"),
            descripcion=validated_data.get("descripcion", ""),
            archivo_nombre=archivo.name,
            creado_por=usuario,
            activo=True,
        )

        return instancia

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

# serializers.py

class FormularioListSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.SerializerMethodField()
    class Meta:
        model = Formulario
        fields = (
            "id",
            "categoria",            # FK (id de Categoria)
            "categoria_nombre",   # nombre de la categoría (read-only)
            "nombre",
            "descripcion",
            "permitir_fotos",
            "permitir_gps",
            "disponible_desde_fecha",
            "disponible_hasta_fecha",
            "estado",
            "forma_envio",
            "es_publico",
            "auto_envio",
        )

    def get_categoria_nombre(self, obj):
        return obj.categoria.nombre if obj.categoria else None


class PaginaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pagina
        # No expongamos FKs internos; con esto basta para el GET
        fields = ("id_pagina", "secuencia", "nombre", "descripcion")

class CrearCampoEnPaginaSerializer(serializers.Serializer):
    clase = serializers.CharField()
    nombre_campo = serializers.RegexField(r"^[a-zA-Z0-9_]+$", max_length=64)
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
        # 1) normalizar id_pagina a 32 sin guiones
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

        import json
        from .models import Grupo, CampoGrupo

        def _first(x):
            return (x[0] if isinstance(x, (list, tuple)) and x else x)

        def _cfg_dict(cfg):
            if isinstance(cfg, dict):
                return cfg
            if isinstance(cfg, str):
                try:
                    return json.loads(cfg)
                except Exception:
                    return {}
            return {}

        # 4) construir salida plana + índices
        out = []
        index = {}           # id_campo -> dict en out
        seq_by_campo = {}    # id_campo -> sequence en página
        for l in links:
            c = l.id_campo
            cfg = _cfg_dict(c.config)
            d = {
                "id_campo": str(c.id_campo),
                "sequence": l.sequence,
                "nombre_campo": c.nombre_campo,
                "etiqueta": c.etiqueta,
                "clase": c.clase,
                "tipo": c.tipo,
                "requerido": c.requerido,
                "config": cfg,
            }
            out.append(d)
            index[d["id_campo"]] = d
            seq_by_campo[d["id_campo"]] = l.sequence

        # 5) anidar hijos en cada group y recolectar ids que van DENTRO de grupos
        child_ids = set()
        for d in out:
            if (d.get("clase") or "").lower() != "group":
                continue

            gid = _first((d.get("config") or {}).get("id_group"))
            if not gid:
                d["children"] = []
                continue

            try:
                g = Grupo.objects.get(pk=gid)
            except Grupo.DoesNotExist:
                d["children"] = []
                continue

            miembros = (CampoGrupo.objects
                        .filter(id_grupo=g)
                        .values_list("id_campo_id", flat=True))

            hijos = [index[cid] for cid in miembros if cid in index]
            hijos.sort(key=lambda h: seq_by_campo.get(h["id_campo"], 10**9))
            d["children"] = hijos

            # marcar estos campos para NO mostrarlos al nivel raíz
            child_ids.update([h["id_campo"] for h in hijos])

        # 6) devolver solo: todos los groups + los campos que NO estén en child_ids
        top_level = [d for d in out if (d.get("clase","").lower()=="group") or (d["id_campo"] not in child_ids)]
        # mantener orden por sequence (ya viene ordenado), pero reordenamos por seguridad
        top_level.sort(key=lambda d: seq_by_campo.get(d["id_campo"], 10**9))
        return top_level


class FormularioSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.SerializerMethodField()
    paginas = serializers.SerializerMethodField()

    class Meta:
        model = Formulario
        fields = "__all__"

    def get_categoria_nombre(self, obj):
        return obj.categoria.nombre if obj.categoria else None

    def get_paginas(self, obj):
        # 1) última versión del formulario
        last_version = (
            FormularioIndexVersion.objects
            .filter(formulario_id=obj)
            .order_by("-fecha_creacion")
            .first()
        )
        if not last_version:
            return []

        # 2) IDs de páginas vigentes para esa versión
        page_ids = (
            Pagina_Index_Version.objects
            .filter(id_index_version=last_version)
            .values_list("id_pagina", flat=True)
        )

        # 3) Devuelve esas Páginas (ids estables)
        qs = Pagina.objects.filter(id_pagina__in=page_ids).order_by("secuencia")
        return PaginaConCamposSerializer(qs, many=True, context=self.context).data

class UsuarioDetalleSerializer(serializers.ModelSerializer):
    # usuario = UsuarioCreateSerializer(many=True, read_only=True)

    class Meta:
        model = Usuario
        fields = ("nombre_usuario", "nombre", "correo", "activo", "acceso_web")

class UsuarioCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})

    class Meta:
        model = Usuario
        fields = ("nombre_usuario", "nombre", "correo", "password", "activo", "acceso_web")

    def validate(self, attrs):
        if Usuario.objects.filter(correo=attrs["correo"]).exists():
            raise serializers.ValidationError({"correo": "Ya existe un usuario con este correo."})
        if Usuario.objects.filter(pk=attrs["nombre_usuario"]).exists():
            raise serializers.ValidationError({"nombre_usuario": "Ya existe un usuario con este nombre de usuario."})
        return attrs

    def create(self, validated):
        plain = validated.pop("password")
        validated["password"] = hash_password(plain)

        # crea usuario
        user = Usuario.objects.create(**validated)
        return user


class CampoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campo
        fields = ("id_campo", "tipo", "clase", "nombre_campo",
                  "etiqueta", "ayuda", "config", "requerido")
   