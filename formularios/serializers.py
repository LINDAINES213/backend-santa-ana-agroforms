import json
from .services import _uuid32_no_dashes, hash_password, uuid32
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework import status
from .models import Campo, Categoria, Formulario, FormularioIndexVersion, FuenteDatos, Grupo, Pagina, Pagina_Index_Version, PaginaCampo, PaginaVersion, UserFormulario, Usuario
# from .validators import validate_config_against_schema
from django.db import connection
from rest_framework.validators import UniqueValidator
import uuid
from django.db import models
from django.db.models import Q

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

class UsuarioUpdateSerializer(serializers.ModelSerializer):
    # password opcional y write-only: si viene, la seteamos correctamente
    password = serializers.CharField(write_only=True, required=False, min_length=8, style={"input_type": "password"})

    class Meta:
        model = Usuario
        fields = ("nombre", "correo", "activo", "acceso_web", "password")
        extra_kwargs = {
            "correo": {"required": False},
            "nombre": {"required": False},
            "activo": {"required": False},
            "acceso_web": {"required": False},
        }

    def update(self, instance, validated):
        pwd = validated.pop("password", None)
        for k, v in validated.items():
            setattr(instance, k, v)
        if pwd:
            instance.set_password(pwd)  # usa tu hash Argon2
        instance.save()
        return instance


class CampoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campo
        fields = ("id_campo", "tipo", "clase", "nombre_campo",
                  "etiqueta", "ayuda", "config", "requerido")
   
class PaginaUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pagina
        fields = ("nombre", "descripcion", "secuencia")
        extra_kwargs = {k: {"required": False} for k in fields}

# serializers.py
from rest_framework import serializers
import json

class CampoUpdateSerializer(serializers.ModelSerializer):
    # Acepta dict JSON en la entrada
    config = serializers.JSONField(required=False)

    class Meta:
        model = Campo
        fields = ("etiqueta", "ayuda", "requerido", "config")
        extra_kwargs = {k: {"required": False} for k in fields}

    def _deep_merge(self, base: dict, patch: dict) -> dict:
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                base[k] = self._deep_merge(base[k], v)
            else:
                base[k] = v
        return base

    def update(self, instance, validated):
        cfg_patch = validated.pop("config", None)

        # Actualiza los demás campos de forma parcial
        for k, v in validated.items():
            setattr(instance, k, v)

        if cfg_patch is not None:
            # ¿reemplazar toda la config? (si pasas ?replace_config=1|true)
            request = self.context.get("request")
            replace_all = False
            if request:
                q = request.query_params
                replace_all = (q.get("replace_config") or "").lower() in ("1", "true", "yes")

            # Config actual (string JSON en BD) -> dict
            try:
                current = json.loads(instance.config) if instance.config else {}
            except Exception:
                current = {}

            if replace_all:
                merged = cfg_patch or {}
            else:
                if not isinstance(cfg_patch, dict):
                    raise serializers.ValidationError({"config": "Debe ser un objeto JSON"})
                merged = self._deep_merge(current if isinstance(current, dict) else {}, cfg_patch)

            # Guardamos como string JSON
            instance.config = json.dumps(merged, ensure_ascii=False)

        instance.save()
        return instance

class PaginaUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pagina
        fields = ("nombre", "descripcion", "secuencia")  # manda solo lo que cambies
        extra_kwargs = {k: {"required": False} for k in ("nombre","descripcion","secuencia")}

class FormularioUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Formulario
        fields = (
            "categoria",              # FK (UUID) si aplica
            "nombre",
            "descripcion",
            "permitir_fotos",
            "permitir_gps",
            "disponible_desde_fecha", # Date (YYYY-MM-DD)
            "disponible_hasta_fecha", # Date (YYYY-MM-DD)
            "estado",                 # p.ej. "Activa"
            "forma_envio",            # p.ej. "En Linea/fuera Linea"
            "es_publico",
            "auto_envio",
        )
        extra_kwargs = {f: {"required": False} for f in fields}

    def validate(self, attrs):
        # Validar rango de fechas si vienen ambas
        d = attrs.get("disponible_desde_fecha")
        h = attrs.get("disponible_hasta_fecha")
        if d and h and d > h:
            raise serializers.ValidationError(
                {"disponible_hasta_fecha": "Debe ser >= disponible_desde_fecha"}
            )
        return attrs

class UsuarioAsignarFormulariosSerializer(serializers.Serializer):
    formularios = serializers.ListField(
        child=serializers.UUIDField(format="hex_verbose"),
        allow_empty=False
    )
    # si replace=True, reemplaza el set completo (elimina los que no estén en la lista)
    replace = serializers.BooleanField(required=False, default=False)

    def validate_formularios(self, value):
        # desdup en input
        return list(dict.fromkeys(value))

class UsuarioLiteSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="nombre_usuario", read_only=True)

    class Meta:
        model = Usuario
        fields = ("id", "nombre_usuario", "nombre")

class FormularioLiteSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source="categoria.nombre", read_only=True)
    class Meta:
        model = Formulario
        fields = ("id", "nombre", "categoria_nombre")

class UserFormularioSerializer(serializers.ModelSerializer):
    usuario = UsuarioLiteSerializer(source="id_usuario", read_only=True)
    formulario = FormularioLiteSerializer(source="id_formulario", read_only=True)

    class Meta:
        model = UserFormulario
        fields = ("id", "usuario", "formulario")

class AsignacionBulkSerializer(serializers.Serializer):
    """
    Recibe:
      - usuario: username o UUID del usuario
      - formularios: lista de UUIDs de formularios
      - replace (opcional): si True, reemplaza el set (elimina los no incluidos)
    """
    usuario = serializers.CharField(required=True)
    formularios = serializers.ListField(
        child=serializers.UUIDField(format="hex_verbose"),
        allow_empty=False
    )
    replace = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        u_raw = attrs["usuario"]
        form_ids = list(dict.fromkeys(attrs["formularios"]))  # desdup

        # resolver usuario por username o id
        try:
            user = Usuario.objects.get(models.Q(nombre_usuario__iexact=u_raw))
        except Usuario.DoesNotExist:
            raise serializers.ValidationError({"usuario": "Usuario no existe."})

        existentes = set(Formulario.objects.filter(id__in=form_ids).values_list("id", flat=True))
        faltantes = [str(x) for x in form_ids if x not in existentes]
        if faltantes:
            raise serializers.ValidationError({"formularios": f"IDs inexistentes: {', '.join(faltantes)}"})

        attrs["user_obj"] = user
        attrs["form_ids"] = list(existentes)
        return attrs