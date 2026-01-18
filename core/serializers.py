from django.contrib.auth.models import User, Permission
from django.contrib.auth.hashers import make_password
from django.core.validators import RegexValidator
from django.db import transaction
import unicodedata
from rest_framework import serializers

from .models import (
    Documentos, Ejemplares, Autores, Ubicaciones, Carreras, TipoDocumento,
    Usuarios, EstadosEjemplar, LibroDetalle, DocumentoAcademico
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


class EstadoEjemplarSerializer(serializers.ModelSerializer):
    class Meta:
        model = EstadosEjemplar
        fields = ['id_estado_ejemplar', 'nombre_estado']


class CarreraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Carreras
        fields = ['id_carrera', 'nombre_carrera']


class DocumentoCreateSerializer(serializers.Serializer):
    titulo = serializers.CharField()
    id_carrera = serializers.PrimaryKeyRelatedField(queryset=Carreras.objects.all(), required=False, allow_null=True)
    id_tipo_documento = serializers.PrimaryKeyRelatedField(queryset=TipoDocumento.objects.all())
    fecha_publicacion = serializers.DateField(required=False, allow_null=True)

    autores = serializers.ListField(child=serializers.CharField(), required=False, allow_empty=True)
    autores_ids = serializers.ListField(child=serializers.IntegerField(), required=False, allow_empty=True)
    tutor_academico = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    autor_academico = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    area_de_conocimiento = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # Datos del Ejemplar
    id_ubicacion = serializers.PrimaryKeyRelatedField(queryset=Ubicaciones.objects.all(), required=False, allow_null=True)
    codigo_cota = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    tomo = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    unidad_fisica = serializers.IntegerField(required=False, min_value=1, default=1)
    id_estado_ejemplar = serializers.PrimaryKeyRelatedField(queryset=EstadosEjemplar.objects.all(), required=False, allow_null=True)

    def validate(self, data):
        tipo = data['id_tipo_documento'].nombre_tipo.upper()
        if tipo == 'TESIS' and not data.get('tutor_academico'):
            raise serializers.ValidationError('tutor_academico requerido para TESIS')
        if tipo == 'PASANTIA' and not data.get('autor_academico'):
            raise serializers.ValidationError('autor_academico requerido para PASANTIA')

        if not (data.get('autores') or data.get('autores_ids')):
            raise serializers.ValidationError('Debe enviar autores o autores_ids')

        # Si se envía un ejemplar en el mismo POST, debe venir con estado
        if (data.get('tomo') or data.get('codigo_cota')) and not data.get('id_estado_ejemplar'):
            raise serializers.ValidationError('id_estado_ejemplar requerido cuando se envía tomo/codigo_cota')

        cota = data.get('codigo_cota')
        tomo = data.get('tomo')
        if cota and tomo:
            if Ejemplares.objects.filter(codigo_cota=cota, tomo=tomo).exists():
                raise serializers.ValidationError('Conflicto: Ya existe un ejemplar con esa cota y tomo.', code='409')

        # Normalizar área de conocimiento para consistencia (sin restringir a catálogo)
        if tipo == 'LIBRO' and data.get('area_de_conocimiento'):
            def norm(v: str) -> str:
                v = (v or '').strip().lower()
                v = unicodedata.normalize('NFKD', v)
                v = ''.join(ch for ch in v if not unicodedata.combining(ch))
                v = ' '.join(v.split())
                return v

            area_in = data.get('area_de_conocimiento')
            # Buscar si ya existe un área similar (para reutilizar la forma canónica)
            existing = list(
                LibroDetalle.objects.exclude(area_de_conocimiento__isnull=True)
                .exclude(area_de_conocimiento__exact='')
                .values_list('area_de_conocimiento', flat=True)
                .distinct()[:1000]
            )
            if existing:
                existing_norm = {norm(x): x for x in existing if norm(x)}
                k = norm(area_in)
                # Si el área ya existe (normalizada), usar la forma canónica existente
                if k in existing_norm:
                    data['area_de_conocimiento'] = existing_norm[k]
                # Si no existe, permitir crear nueva área (no lanzar error)
        return data

    def create(self, validated):
        autores_nombres = validated.pop('autores', None)
        autores_ids = validated.pop('autores_ids', None)
        tutor_name = validated.pop('tutor_academico', None)
        autor_acad_name = validated.pop('autor_academico', None)
        area_name = validated.pop('area_de_conocimiento', None)

        def norm(v: str) -> str:
            v = (v or '').strip().lower()
            v = unicodedata.normalize('NFKD', v)
            v = ''.join(ch for ch in v if not unicodedata.combining(ch))
            v = ' '.join(v.split())
            return v

        # Canonicalizar tutor para evitar duplicados por mayúsculas/acentos
        if tutor_name:
            k = norm(tutor_name)
            existing = list(
                DocumentoAcademico.objects.exclude(tutor_academico__isnull=True)
                .exclude(tutor_academico__exact='')
                .values_list('tutor_academico', flat=True)
                .distinct()[:1000]
            )
            canon = {norm(x): x for x in existing if norm(x)}
            if k in canon:
                tutor_name = canon[k]

        # Canonicalizar área (si viene) por consistencia
        if area_name:
            k = norm(area_name)
            existing = list(
                LibroDetalle.objects.exclude(area_de_conocimiento__isnull=True)
                .exclude(area_de_conocimiento__exact='')
                .values_list('area_de_conocimiento', flat=True)
                .distinct()[:1000]
            )
            canon = {norm(x): x for x in existing if norm(x)}
            if k in canon:
                area_name = canon[k]

        # datos ejemplar
        ubic = validated.pop('id_ubicacion', None)
        cota = validated.pop('codigo_cota', None)
        tomo = validated.pop('tomo', None)
        unidades = validated.pop('unidad_fisica', 1)
        estado_ej = validated.pop('id_estado_ejemplar', None)

        with transaction.atomic():
            # Autores
            autores_objs = []
            if autores_ids:
                autores_objs = list(Autores.objects.filter(id_autor__in=autores_ids))
            else:
                for full in (autores_nombres or []):
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
            from .models import InformePasantiaDetalle
            if tutor_name:
                DocumentoAcademico.objects.update_or_create(
                    id_documento=doc, defaults={'tutor_academico': tutor_name}
                )
            if autor_acad_name:
                InformePasantiaDetalle.objects.update_or_create(
                    id_documento=doc, defaults={'autor_academico': autor_acad_name}
                )
            if area_name:
                LibroDetalle.objects.update_or_create(
                    id_documento=doc, defaults={'area_de_conocimiento': area_name}
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


# Prestamos
class PrestamoItemSerializer(serializers.Serializer):
    id_ejemplar = serializers.IntegerField()


class PrestamoCreateSerializer(serializers.Serializer):
    id_usuario = serializers.IntegerField()
    fecha_vencimiento = serializers.DateField()
    ejemplares = PrestamoItemSerializer(many=True)
    observacion = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class PrestamoUpdateSerializer(serializers.Serializer):
    fecha_vencimiento = serializers.DateField(required=False)
    ejemplares = PrestamoItemSerializer(many=True, required=False)
    observacion = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError('Debe enviar al menos un campo para actualizar')
        return attrs

