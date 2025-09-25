from .services import _uuid32_no_dashes, hash_password, uuid32
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework import status
from .models import Campo, Categoria, Formulario, FormularioIndexVersion, Pagina, PaginaCampo, PaginaVersion, Rol, RolUser, Usuario
# from .validators import validate_config_against_schema
from django.db import connection
from rest_framework.validators import UniqueValidator
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

class RolLiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rol
        fields = ("id", "nombre", "descripcion")

class UsuarioDetalleSerializer(serializers.ModelSerializer):
    roles = RolLiteSerializer(many=True, read_only=True)

    class Meta:
        model = Usuario
        fields = ("nombre_usuario", "nombre", "correo", "activo", "roles")

class UsuarioCreateSerializer(serializers.ModelSerializer):
    contrasena = serializers.CharField(write_only=True, min_length=8, style={"input_type": "password"})
    roles = serializers.PrimaryKeyRelatedField(
        many=True,
        required=False,
        queryset=Rol.objects.all(),
        help_text="Selecciona uno o varios roles (Ctrl/Cmd + click)."
    )

    class Meta:
        model = Usuario
        fields = ("nombre_usuario", "nombre", "correo", "contrasena", "activo", "roles")

    def validate(self, attrs):
        if Usuario.objects.filter(correo=attrs["correo"]).exists():
            raise serializers.ValidationError({"correo": "Ya existe un usuario con este correo."})
        if Usuario.objects.filter(pk=attrs["nombre_usuario"]).exists():
            raise serializers.ValidationError({"nombre_usuario": "Ya existe un usuario con este nombre de usuario."})
        return attrs

    def create(self, validated):
        roles_objs = validated.pop("roles", [])
        plain = validated.pop("contrasena")
        validated["contrasena"] = hash_password(plain)

        # crea usuario
        user = Usuario.objects.create(**validated)

        # INSERTS a la tabla puente con SQL crudo (evita la columna 'id')
        if roles_objs:
            # evitar duplicados actuales
            existentes = set(
                RolUser.objects
                .filter(nombre_de_usuario=user, id_rol__in=[r.id for r in roles_objs])
                .values_list("id_rol_id", flat=True)
            )
            # Normalízalos por si vienen con mayúsculas
            existentes = { (e or "").replace("-", "").lower() for e in existentes }

            # filas a insertar (id_rol debe ir como 32 chars)
            filas = [(uuid32(r.id), str(user.nombre_usuario))
                    for r in roles_objs if uuid32(r.id) not in existentes]

            if filas:
                with connection.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO formularios_rol_user (id_rol, nombre_usuario) VALUES (%s, %s)",
                        filas
                    )
                return user

class UsuarioReplaceRolesSerializer(serializers.Serializer):
    roles = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Rol.objects.all(),
        required=True,
        help_text="Selecciona los roles finales del usuario."
    )

    def update(self, user: Usuario, validated):
        new_ids = {r.id for r in validated["roles"]}
        cur_ids = set(
            Rol.objects.filter(roluser__nombre_de_usuario=user)
            .values_list("id", flat=True)
        )
        # normaliza a 32
        cur_ids = { uuid32(x) for x in cur_ids }

        new_ids = { uuid32(r.id) for r in validated["roles"] }

        to_add = new_ids - cur_ids
        to_del = cur_ids - new_ids

        if to_del:
            # OJO: si id_rol en la tabla puente está en 32 chars, hay que pasar 32
            RolUser.objects.filter(
                nombre_de_usuario=user,
                id_rol_id__in=list(to_del)
            ).delete()

        if to_add:
            filas = [(rid, str(user.nombre_usuario)) for rid in to_add]  # rid ya viene 32
            with connection.cursor() as cur:
                cur.executemany(
                    "INSERT INTO formularios_rol_user (id_rol, nombre_usuario) VALUES (%s, %s)",
                    filas
                )
    
class RolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rol
        fields = ("id", "nombre", "descripcion")


class RolCreateUpdateSerializer(serializers.ModelSerializer):
    # unicidad case-insensitive para evitar “Admin” vs “admin”
    nombre = serializers.CharField(
        max_length=50,
        validators=[UniqueValidator(queryset=Rol.objects.all(), lookup="iexact")]
    )

    class Meta:
        model = Rol
        fields = ("id", "nombre", "descripcion")
        read_only_fields = ("id",)

class CampoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campo
        fields = ("id_campo", "tipo", "clase", "nombre_campo",
                  "etiqueta", "ayuda", "config", "requerido")
   