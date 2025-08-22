from rest_framework import serializers
from rest_framework.response import Response
from rest_framework import status
from .models import Formulario, Categoria, Pagina, FormularioIndexVersion

class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = '__all__'

class PaginaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pagina
        fields = "__all__"
        read_only_fields = ("id_pagina", "index_version", "formulario")

class FormularioSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.SerializerMethodField()
    paginas = serializers.SerializerMethodField()

    class Meta:
        model = Formulario
        fields = "__all__"

    def get_categoria_nombre(self, obj):
        return obj.categoria.nombre if obj.categoria else None

    def get_paginas(self, obj):
        last_version = FormularioIndexVersion.objects.filter(formulario=obj)\
                           .order_by("-fecha_creacion").first()
        if not last_version:
            return []
        qs = Pagina.objects.filter(index_version=last_version).order_by("secuencia")
        return PaginaSerializer(qs, many=True).data



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