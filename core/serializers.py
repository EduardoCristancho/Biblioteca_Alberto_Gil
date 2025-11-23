from django.contrib.auth.models import User, Permission
from django.contrib.auth.hashers import make_password
from django.core.validators import RegexValidator
from django.db import transaction
from rest_framework import serializers

from .models import (
    Documentos, Ejemplares, Autores, Ubicaciones, Carreras, TipoDocumento,
    Usuarios, EstadosEjemplar
)


class LoginSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=True)
    password = serializers.CharField(min_length=3, write_only=True)


class UserContextSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    role = serializers.CharField()
    permissions = serializers.SerializerMethodField()

    def get_permissions(self, obj):
        perms = set()
        for g in obj.groups.all():
            perms.update(Permission.objects.filter(group=g).values_list('codename', flat=True))
        return sorted(list(perms))


class UserCreateSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nombre = serializers.CharField()
    apellido = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=3, validators=[
        RegexValidator(regex=r'.*[#%&].*', message='La contraseña debe contener al menos uno de: # % &')
    ])

    def validate(self, attrs):
        from .external import ExternalUserClient
        ext = ExternalUserClient.fetch(attrs['id'])
        if ext is None:
            raise serializers.ValidationError('Usuario no existe en sistema externo', code='422')
        attrs['_ext'] = ext
        return attrs

    def create(self, validated_data):
        # Crea usuario en tabla de autenticación para login y también en tabla de dominio Usuarios
        ext = validated_data['_ext']
        
        # Evita colisión con auth_user
        if User.objects.filter(id=validated_data['id']).exists():
            raise serializers.ValidationError('Ya existe localmente', code='409')
        with transaction.atomic():
            auth_user = User.objects.create(
                id=validated_data['id'],
                username=ext['username'],
                first_name=validated_data['nombre'],
                last_name=validated_data['apellido'],
            )
            # Set password for Django auth user (hashed)
            auth_user.password = make_password(validated_data['password'])
            auth_user.save(update_fields=["password"]) 
            # Upsert a Usuarios (tabla de dominio)
            user = Usuarios.objects.update_or_create(
                id_usuario=validated_data['id'],
                defaults={
                    'nombre': validated_data['nombre'],
                    'apellido': validated_data['apellido'],
                    'password': make_password(validated_data['password']),
                    'id_rol_id': ext['rol'],
                }
            )
        return auth_user


class AutorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Autores
        fields = ['id_autor', 'nombre', 'apellido']


class UbicacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ubicaciones
        fields = ['id_ubicacion', 'pasillo', 'estante', 'descripcion_completa']


class CarreraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Carreras
        fields = ['id_carrera', 'nombre_carrera']


class DocumentoCreateSerializer(serializers.Serializer):
    titulo = serializers.CharField()
    id_carrera = serializers.PrimaryKeyRelatedField(queryset=Carreras.objects.all(), required=False, allow_null=True)
    id_tipo_documento = serializers.PrimaryKeyRelatedField(queryset=TipoDocumento.objects.all())
    fecha_publicacion = serializers.DateField(required=False, allow_null=True)

    autores = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    tutor_academico = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    autor_academico = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # Datos del Ejemplar
    id_ubicacion = serializers.PrimaryKeyRelatedField(queryset=Ubicaciones.objects.all(), required=False, allow_null=True)
    codigo_cota = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    tomo = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    unidad_fisica = serializers.IntegerField(required=False, min_value=1, default=1)
    id_estado_ejemplar = serializers.PrimaryKeyRelatedField(queryset=EstadosEjemplar.objects.all())

    def validate(self, data):
        tipo = data['id_tipo_documento'].nombre_tipo.upper()
        if tipo == 'TESIS' and not data.get('tutor_academico'):
            raise serializers.ValidationError('tutor_academico requerido para TESIS')
        if tipo == 'PASANTIA' and not data.get('autor_academico'):
            raise serializers.ValidationError('autor_academico requerido para PASANTIA')

        cota = data.get('codigo_cota')
        tomo = data.get('tomo')
        if cota and tomo:
            if Ejemplares.objects.filter(codigo_cota=cota, tomo=tomo).exists():
                raise serializers.ValidationError('Conflicto: Ya existe un ejemplar con esa cota y tomo.', code='409')
        return data

    def create(self, validated):
        autores_nombres = validated.pop('autores')
        tutor_name = validated.pop('tutor_academico', None)
        autor_acad_name = validated.pop('autor_academico', None)

        # datos ejemplar
        ubic = validated.pop('id_ubicacion', None)
        cota = validated.pop('codigo_cota', None)
        tomo = validated.pop('tomo', None)
        unidades = validated.pop('unidad_fisica', 1)
        estado_ej = validated.pop('id_estado_ejemplar')

        with transaction.atomic():
            # Autores
            autores_objs = []
            for full in autores_nombres:
                parts = full.split(' ', 1)
                a, _ = Autores.objects.get_or_create(nombre=parts[0], apellido=(parts[1] if len(parts) > 1 else ''))
                autores_objs.append(a)

            # Crear documento
            doc = Documentos.objects.create(**validated)

            # Relaciones autores
            from .models import DocumentoAutores
            for a in autores_objs:
                DocumentoAutores.objects.create(id_documento=doc, id_autor=a)

            # Campos académicos opcionales en tablas detalle
            from .models import DocumentoAcademico, InformePasantiaDetalle
            if tutor_name:
                DocumentoAcademico.objects.update_or_create(
                    id_documento=doc, defaults={'tutor_academico': tutor_name}
                )
            if autor_acad_name:
                InformePasantiaDetalle.objects.update_or_create(
                    id_documento=doc, defaults={'autor_academico': autor_acad_name}
                )

            # Crear ejemplar si hay datos suficientes
            if tomo or cota:
                Ejemplares.objects.create(
                    id_documento=doc,
                    id_ubicacion=ubic,
                    tomo=tomo,
                    unidad_fisica=unidades,
                    id_estado_ejemplar=estado_ej,
                    codigo_cota=cota,
                )
        return doc


class DocumentoUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Documentos
        fields = ['titulo', 'id_carrera', 'id_tipo_documento', 'fecha_publicacion']

