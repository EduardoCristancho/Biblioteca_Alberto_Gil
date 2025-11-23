from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User, Group, Permission
from django.contrib.auth.hashers import check_password, make_password
from django.http import Http404
from rest_framework import generics, viewsets, status, filters
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db import transaction

from .serializers import (
    LoginSerializer, UserContextSerializer, UserCreateSerializer,
    AutorSerializer, UbicacionSerializer, CarreraSerializer,
    DocumentoCreateSerializer, DocumentoUpdateSerializer,
)
from .models import (
    Autores, Ubicaciones, Carreras, Documentos, Usuarios
)
from .filters import DocumentoFilter

# Auth
class LoginView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        # Autenticación contra tabla Usuarios por id y contraseña
        uid = ser.validated_data['id']
        raw_password = ser.validated_data['password']
        try:
            udom = Usuarios.objects.select_related('id_rol').get(id_usuario=uid)
        except Usuarios.DoesNotExist:
            return Response({'detail': 'Usuario no encontrado'}, status=status.HTTP_401_UNAUTHORIZED)

        if not udom.password or not check_password(raw_password, udom.password):
            return Response({'detail': 'Credenciales inválidas'}, status=status.HTTP_401_UNAUTHORIZED)

        # Asegurar existencia/sincronización del auth_user
        with transaction.atomic():
            auth_user, created = User.objects.get_or_create(
                id=uid,
                defaults={
                    'username': str(uid),
                    'first_name': udom.nombre,
                    'last_name': udom.apellido,
                }
            )
            if created:
                # Copiar hash ya calculado desde Usuarios a auth_user
                auth_user.password = udom.password
                auth_user.is_active = True
                auth_user.save(update_fields=["password", "is_active", "first_name", "last_name"])
            else:
                # Mantener nombres alineados (no tocamos password aquí)
                changed = False
                if auth_user.first_name != udom.nombre:
                    auth_user.first_name = udom.nombre
                    changed = True
                if auth_user.last_name != udom.apellido:
                    auth_user.last_name = udom.apellido
                    changed = True
                if changed:
                    auth_user.save(update_fields=["first_name", "last_name"])

            # Mapear rol de dominio a Group de Django para permisos
            if getattr(udom, 'id_rol_id', None):
                gname = udom.id_rol.nombre_rol
                group, _ = Group.objects.get_or_create(name=gname)
                if not auth_user.groups.filter(id=group.id).exists():
                    auth_user.groups.add(group)

        # Iniciar sesión en Django
        login(request, auth_user, backend='django.contrib.auth.backends.ModelBackend')
        resp = Response({'message': 'Login exitoso'})
        resp.set_cookie('sessionid', request.session.session_key, httponly=True, secure=True, samesite='Strict')
        return resp

class LogoutView(generics.GenericAPIView):
    def post(self, request):
        logout(request)
        resp = Response({'message': 'OK'})
        resp.delete_cookie('sessionid')
        return resp

class MeView(generics.RetrieveAPIView):
    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        user = self.get_object()
        perms = Permission.objects.filter(group__in=user.groups.all()).values_list('codename', flat=True)
        data = {
            'id': user.id,
            'username': user.first_name + ' ' + user.last_name,
            'role': ','.join([g.name for g in user.groups.all()]),
            'permissions': sorted(set(perms)),
        }
        return Response(data)

# Users
class UserRetrieveView(generics.RetrieveAPIView):
    queryset = User.objects.all()
    lookup_field = 'id'

    def get_object(self):
        try:
            return super().get_object()
        except Http404:
            from .external import ExternalUserClient
            ext = ExternalUserClient.fetch(int(self.kwargs['id']))
            if not ext:
                raise
            with transaction.atomic():
                user, _ = User.objects.get_or_create(id=ext['id'], defaults={'username': ext['username'], 'first_name': ext['nombre'], 'last_name': ext['apellido']})
                # Upsert a tabla de dominio Usuarios para mantener consistencia
                try:
                    udom = Usuarios.objects.get(id_usuario=ext['id'])
                except Usuarios.DoesNotExist:
                    udom = Usuarios(id_usuario=ext['id'])
                udom.nombre = ext['nombre']
                udom.apellido = ext['apellido']
                # asignar rol si viene del externo
                if 'rol' in ext and ext['rol'] is not None:
                    udom.id_rol_id = ext['rol']
                udom.save()
            return user

    def retrieve(self, request, *args, **kwargs):
        user = self.get_object()
        perms = Permission.objects.filter(group__in=user.groups.all()).values_list('codename', flat=True)
        data = {
            'id': user.id,
            'name': user.first_name + ' ' + user.last_name,
            'role': ','.join([g.name for g in user.groups.all()]),
            'permissions': sorted(set(perms)),
        }
        return Response(data)

class UserCreateView(generics.CreateAPIView):
    serializer_class = UserCreateSerializer

class UserUpdateView(generics.UpdateAPIView):
    queryset = User.objects.all()
    lookup_field = 'id'
    serializer_class = UserCreateSerializer

    def update(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ext = ser.validated_data['_ext']
        instance = self.get_object()
        with transaction.atomic():
            instance.username = ext['username']
            instance.first_name = request.data.get('nombre', instance.first_name)
            instance.last_name = request.data.get('apellido', instance.last_name)
            # Si viene password en la petición, actualizar en auth_user
            raw_pwd = request.data.get('password')
            if raw_pwd:
                instance.password = make_password(raw_pwd)
            instance.save()

            # Sincronizar también la tabla de dominio Usuarios
            try:
                udom = Usuarios.objects.get(id_usuario=instance.id)
            except Usuarios.DoesNotExist:
                udom = Usuarios(id_usuario=instance.id)
            udom.nombre = request.data.get('nombre', udom.nombre)
            udom.apellido = request.data.get('apellido', udom.apellido)
            if raw_pwd:
                udom.password = instance.password  # ya viene hasheado
            udom.save()
        return Response({'id': instance.id, 'nombre': instance.first_name, 'apellido': instance.last_name})


# Autores
class AutorListView(generics.ListAPIView):
    queryset = Autores.objects.all()
    serializer_class = AutorSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['id_autor', 'nombre']


class AutorUpdateView(generics.UpdateAPIView):
    queryset = Autores.objects.all()
    serializer_class = AutorSerializer

    def perform_update(self, serializer):
        if not self.request.data.get('nombre'):
            raise ValueError('nombre no puede estar vacío')
        serializer.save()


# Ubicaciones y Carreras
class UbicacionViewSet(viewsets.ModelViewSet):
    queryset = Ubicaciones.objects.all()
    serializer_class = UbicacionSerializer

    def perform_destroy(self, instance):
        # set NULL en documentos que referencian esta ubicacion a través de ejemplares no aplica
        # aquí solo eliminamos la ubicación; Documentos no tiene FK directa en este esquema
        super().perform_destroy(instance)


class CarreraViewSet(viewsets.ModelViewSet):
    queryset = Carreras.objects.all()
    serializer_class = CarreraSerializer


# Documentos
class DocumentoListCreateView(generics.GenericAPIView):
    queryset = Documentos.objects.all()
    filterset_class = DocumentoFilter

    def get(self, request, *args, **kwargs):
        from rest_framework import serializers as sz
        from .models import DocumentoAutores

        class DocListSerializer(sz.ModelSerializer):
            autores = sz.SerializerMethodField()

            class Meta:
                model = Documentos
                fields = ['id_documento', 'titulo', 'id_tipo_documento', 'fecha_publicacion', 'id_carrera', 'autores']

            def get_autores(self, obj):
                qs = DocumentoAutores.objects.filter(id_documento=obj).select_related('id_autor')
                return [{'id_autor': x.id_autor_id, 'nombre': x.id_autor.nombre, 'apellido': x.id_autor.apellido} for x in qs]

        qs = self.filterset_class(request.GET, queryset=self.get_queryset(), request=request).qs if self.filterset_class else self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            ser = DocListSerializer(page, many=True)
            return self.get_paginated_response(ser.data)
        ser = DocListSerializer(qs, many=True)
        return Response(ser.data)

    def post(self, request, *args, **kwargs):
        ser = DocumentoCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        doc = ser.save()
        return Response({'id_documento': doc.id_documento, 'titulo': doc.titulo}, status=status.HTTP_201_CREATED)


class DocumentoUpdateView(generics.UpdateAPIView):
    queryset = Documentos.objects.all()
    serializer_class = DocumentoUpdateSerializer


class DocumentoDeleteView(generics.DestroyAPIView):
    queryset = Documentos.objects.all()

    def delete(self, request, *args, **kwargs):
        # No hay columna deleted_at en el esquema actual; respondemos 200 sin borrar físicamente.
        instance = self.get_object()
        return Response({'status': 'soft-delete-simulado', 'id_documento': instance.pk}, status=status.HTTP_200_OK)
