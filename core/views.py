from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from datetime import datetime, timedelta
from django.contrib.auth.models import User, Group, Permission
from django.contrib.auth.hashers import check_password, make_password
from django.http import Http404
from django.views.decorators.csrf import ensure_csrf_cookie
from django.conf import settings
from django.utils import timezone
from django.db.models import Exists, OuterRef, Min, Q, F, Value, Count, Subquery, IntegerField, Case, When, Sum, CharField
from django.db.models.functions import Replace, Lower, Coalesce
from rest_framework import generics, viewsets, status, filters
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db import transaction
import unicodedata
import logging
logger = logging.getLogger(__name__)

from .serializers import (
    LoginSerializer, UserContextSerializer, UserCreateSerializer,
    AutorSerializer, UbicacionSerializer, CarreraSerializer,
    DocumentoCreateSerializer, DocumentoUpdateSerializer,
    EstadoEjemplarSerializer,
)
from .models import (
    Autores, Ubicaciones, Carreras, Documentos, Usuarios,
    Prestamos, DetallePrestamo, Ejemplares, Roles, EstadosEjemplar, LibroDetalle, DocumentoAcademico, DocumentoAutores, InformePasantiaDetalle
)
from .filters import DocumentoFilter


def _is_admin_user(user) -> bool:
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return True
    try:
        udom = Usuarios.objects.select_related('id_rol').get(id_usuario=user.id)
        return (udom.id_rol and str(udom.id_rol.nombre_rol).strip().lower() == 'admin')
    except Exception:
        return False


def _normalize_text(value: str) -> str:
    if value is None:
        return ''
    v = str(value).strip().lower()
    v = unicodedata.normalize('NFKD', v)
    v = ''.join(ch for ch in v if not unicodedata.combining(ch))
    v = ' '.join(v.split())
    return v


def _normalize_expr(expr):
    return Replace(
        Replace(
            Replace(
                Replace(
                    Replace(
                        Replace(
                            Replace(Lower(expr), Value('á'), Value('a')),
                            Value('é'), Value('e')
                        ),
                        Value('í'), Value('i')
                    ),
                    Value('ó'), Value('o')
                ),
                Value('ú'), Value('u')
            ),
            Value('ü'), Value('u')
        ),
        Value('ñ'), Value('n')
    )

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
        resp.set_cookie(
            'sessionid',
            request.session.session_key,
            httponly=True,
            secure=(not settings.DEBUG),
            samesite='Lax',
        )
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
class AutorListView(generics.GenericAPIView):
    queryset = Autores.objects.all()
    serializer_class = AutorSerializer

    def get(self, request, *args, **kwargs):
        qs = self.get_queryset()
        term = (request.GET.get('search') or '').strip()
        if term:
            term_n = _normalize_text(term)
            qs = qs.annotate(
                nombre_n=_normalize_expr(F('nombre')),
                apellido_n=_normalize_expr(F('apellido')),
            ).filter(
                Q(nombre_n__contains=term_n) |
                Q(apellido_n__contains=term_n)
            )
        if not qs.ordered:
            qs = qs.order_by('id_autor')
        ser = self.serializer_class(qs[:50], many=True)
        return Response(ser.data)

    def post(self, request, *args, **kwargs):
        nombre = (request.data.get('nombre') or '').strip()
        apellido = (request.data.get('apellido') or '').strip()
        if not nombre:
            return Response({'detail': 'nombre requerido'}, status=status.HTTP_400_BAD_REQUEST)

        nombre_n = _normalize_text(nombre)
        apellido_n = _normalize_text(apellido)

        existente = (
            Autores.objects
            .annotate(
                nombre_n=_normalize_expr(F('nombre')),
                apellido_n=_normalize_expr(F('apellido')),
            )
            .filter(nombre_n=nombre_n, apellido_n=apellido_n)
            .first()
        )
        if existente:
            ser = self.serializer_class(existente)
            data = ser.data
            data['created'] = False
            return Response(data, status=status.HTTP_200_OK)

        with transaction.atomic():
            a = Autores.objects.create(nombre=nombre, apellido=apellido)
        ser = self.serializer_class(a)
        data = ser.data
        data['created'] = True
        return Response(data, status=status.HTTP_201_CREATED)


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


class EstadoEjemplarViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = EstadosEjemplar.objects.all()
    serializer_class = EstadoEjemplarSerializer


# Documentos
class DocumentoListCreateView(generics.GenericAPIView):
    queryset = Documentos.objects.all()
    filterset_class = DocumentoFilter

    def get(self, request, *args, **kwargs):
        from rest_framework import serializers as sz
        from django.db.models import Count

        id_documento = request.GET.get('id_documento')
        if id_documento is not None:
            s = str(id_documento).strip()
            if not s.isdigit():
                return Response({'detail': 'id_documento inválido'}, status=status.HTTP_400_BAD_REQUEST)

        mode = (request.GET.get('mode') or '').strip().lower()
        if mode == 'inventory':
            qs = self.filterset_class(request.GET, queryset=self.get_queryset(), request=request).qs if self.filterset_class else self.get_queryset()

            if id_documento is not None:
                qs = qs.filter(id_documento=int(str(id_documento).strip()))

            term = request.GET.get('q')
            if term:
                term_n = _normalize_text(term)
                ej_activos_sub = (
                    Ejemplares.objects
                    .filter(id_documento_id=OuterRef('pk'))
                    .exclude(id_estado_ejemplar__nombre_estado__icontains='ELIMIN')
                    .exclude(unidad_fisica=0)
                )
                ej_cota_sub = (
                    Ejemplares.objects
                    .filter(id_documento_id=OuterRef('pk'))
                    .exclude(id_estado_ejemplar__nombre_estado__icontains='ELIMIN')
                    .exclude(unidad_fisica=0)
                    .annotate(cota_n=_normalize_expr(F('codigo_cota')))
                    .filter(cota_n__contains=term_n)
                )
                qs = qs.annotate(
                    titulo_n=_normalize_expr(F('titulo')),
                    cota_n=_normalize_expr(F('codigo_cota')),
                    autor_nombre_n=_normalize_expr(F('documentoautores__id_autor__nombre')),
                    autor_apellido_n=_normalize_expr(F('documentoautores__id_autor__apellido')),
                    ej_activo=Exists(ej_activos_sub),
                    ej_cota_match=Exists(ej_cota_sub),
                ).filter(
                    Q(titulo_n__contains=term_n) |
                    (Q(cota_n__contains=term_n) & Q(ej_activo=True)) |
                    Q(autor_nombre_n__contains=term_n) |
                    Q(autor_apellido_n__contains=term_n) |
                    Q(ej_cota_match=True)
                ).distinct()

            chip_titulos = [x for x in request.GET.getlist('titulo') if str(x).strip()]
            chip_autores = [x for x in request.GET.getlist('autor') if str(x).strip()]
            chip_cotas = [x for x in request.GET.getlist('cota') if str(x).strip()]
            chip_cotas_n = [_normalize_text(x) for x in chip_cotas]
            chip_cotas_n = [x for x in chip_cotas_n if x]

            if chip_titulos or chip_autores or chip_cotas:
                qs = qs.annotate(
                    chip_titulo_n=_normalize_expr(F('titulo')),
                    chip_cota_n=_normalize_expr(F('codigo_cota')),
                    chip_autor_nom_n=_normalize_expr(F('documentoautores__id_autor__nombre')),
                    chip_autor_ape_n=_normalize_expr(F('documentoautores__id_autor__apellido')),
                )
                for t in chip_titulos:
                    tn = _normalize_text(t)
                    if tn:
                        qs = qs.filter(chip_titulo_n__contains=tn)
                for cn in chip_cotas_n:
                    ej_chip_sub = (
                        Ejemplares.objects
                        .filter(id_documento_id=OuterRef('pk'))
                        .exclude(id_estado_ejemplar__nombre_estado__icontains='ELIMIN')
                        .exclude(unidad_fisica=0)
                        .annotate(cota_n=_normalize_expr(F('codigo_cota')))
                        .filter(cota_n__contains=cn)
                    )
                    qs = qs.annotate(_chip_ej_cota_match=Exists(ej_chip_sub)).filter(_chip_ej_cota_match=True)
                for a in chip_autores:
                    an = _normalize_text(a)
                    if not an:
                        continue
                    tokens = [x for x in an.split(' ') if x]
                    for tok in tokens:
                        qs = qs.filter(Q(chip_autor_nom_n__contains=tok) | Q(chip_autor_ape_n__contains=tok))
                qs = qs.distinct()

            docs_sub = qs.values('id_documento')
            ej_qs = (
                Ejemplares.objects
                .filter(id_documento_id__in=Subquery(docs_sub))
                .exclude(id_estado_ejemplar__nombre_estado__icontains='ELIMIN')
                .exclude(unidad_fisica=0)
            )

            if chip_cotas_n:
                q_cota = Q()
                for cn in chip_cotas_n:
                    q_cota |= Q(_cota_n__contains=cn)
                ej_qs = ej_qs.annotate(_cota_n=_normalize_expr(F('codigo_cota'))).filter(q_cota)

            open_sub = (
                DetallePrestamo.objects
                .filter(id_ejemplar_id=OuterRef('pk'), fecha_devolucion_real__isnull=True)
                .values('id_ejemplar_id')
                .annotate(c=Count('id_detalle_prestamo'))
                .values('c')
            )

            ej_qs = ej_qs.annotate(open_c=Coalesce(Subquery(open_sub, output_field=IntegerField()), Value(0)))
            ej_qs = ej_qs.annotate(av_raw=F('unidad_fisica') - F('open_c'))
            ej_qs = ej_qs.annotate(av=Case(When(av_raw__gt=0, then=F('av_raw')), default=Value(0), output_field=IntegerField()))

            # Filas por (documento + tomo) usando solo los campos necesarios para la tabla.
            # IMPORTANTE: no usar alias "id_documento" dentro del annotate porque colisiona con
            # el FK y rompe referencias tipo id_documento__titulo.
            rows_qs = (
                ej_qs
                .values('id_documento_id', 'tomo')
                .annotate(
                    doc_id=F('id_documento_id'),
                    titulo_v=F('id_documento__titulo'),
                    tipo_id=F('id_documento__id_tipo_documento_id'),
                    tipo_nombre=F('id_documento__id_tipo_documento__nombre_tipo'),
                    carrera_nombre=F('id_documento__id_carrera__nombre_carrera'),
                    disponibles=Sum('av'),
                    fisicas=Sum('unidad_fisica'),
                    ubic_count=Count('id_ubicacion_id', distinct=True),
                    ubic_one=Min('id_ubicacion__descripcion_completa'),
                )
                .values(
                    'doc_id',
                    'titulo_v',
                    'tipo_id',
                    'tipo_nombre',
                    'carrera_nombre',
                    'tomo',
                    'disponibles',
                    'fisicas',
                    'ubic_count',
                    'ubic_one',
                )
            )

            # Incluir también documentos que no tienen ejemplares activos (para carga inicial sin filtros)
            docs_sin_ej = qs.exclude(id_documento__in=Subquery(ej_qs.values('id_documento_id')))
            empty_rows_qs = (
                docs_sin_ej
                .values(
                    doc_id=F('id_documento'),
                    titulo_v=F('titulo'),
                    tipo_id=F('id_tipo_documento_id'),
                    tipo_nombre=F('id_tipo_documento__nombre_tipo'),
                    carrera_nombre=F('id_carrera__nombre_carrera'),
                    tomo=Value(None, output_field=CharField()),
                    disponibles=Value(0, output_field=IntegerField()),
                    fisicas=Value(0, output_field=IntegerField()),
                    ubic_count=Value(0, output_field=IntegerField()),
                    ubic_one=Value(None, output_field=CharField()),
                )
            )

            inv_estado = (request.GET.get('inv_estado') or '').strip().lower()
            inv_stock = (request.GET.get('inv_stock') or '').strip().lower()

            if inv_estado == 'disponible':
                rows_qs = rows_qs.filter(disponibles__gt=0)
                empty_rows_qs = empty_rows_qs.filter(disponibles__gt=0)
            elif inv_estado == 'prestado':
                rows_qs = rows_qs.filter(disponibles__lte=0)
                empty_rows_qs = empty_rows_qs.filter(disponibles__lte=0)

            if inv_stock == '0':
                rows_qs = rows_qs.filter(disponibles=0)
                empty_rows_qs = empty_rows_qs.filter(disponibles=0)
            elif inv_stock == '1-2':
                rows_qs = rows_qs.filter(disponibles__gte=1, disponibles__lte=2)
                empty_rows_qs = empty_rows_qs.filter(disponibles__gte=1, disponibles__lte=2)
            elif inv_stock == '>=3':
                rows_qs = rows_qs.filter(disponibles__gte=3)
                empty_rows_qs = empty_rows_qs.filter(disponibles__gte=3)

            # Unificar filas de documentos con y sin ejemplares
            rows_qs = rows_qs.union(empty_rows_qs, all=True)
            rows_qs = rows_qs.order_by('titulo_v', 'tomo', 'doc_id')

            page = self.paginate_queryset(rows_qs)
            out_rows = list(page) if page is not None else list(rows_qs)

            doc_ids = sorted({r.get('doc_id') for r in out_rows if r.get('doc_id') is not None})
            autores_map = {}
            if doc_ids:
                for rel in DocumentoAutores.objects.filter(id_documento_id__in=doc_ids).select_related('id_autor'):
                    autores_map.setdefault(rel.id_documento_id, []).append(
                        f"{(rel.id_autor.nombre or '').strip()} {(rel.id_autor.apellido or '').strip()}".strip()
                    )

            payload = []
            for r in out_rows:
                did = r.get('doc_id')
                ubic_count = int(r.get('ubic_count') or 0)
                ubic = r.get('ubic_one')
                if ubic_count <= 0:
                    ubicacion = 'Sin ubicación'
                elif ubic_count == 1:
                    ubicacion = ubic or 'Sin ubicación'
                else:
                    ubicacion = 'varias'

                payload.append({
                    'id_documento': did,
                    'titulo': r.get('titulo_v'),
                    'id_tipo_documento': r.get('tipo_id'),
                    'tipo_nombre': r.get('tipo_nombre'),
                    'carrera_nombre': r.get('carrera_nombre'),
                    'tomo': r.get('tomo'),
                    'ubicacion': ubicacion,
                    'disponibles': int(r.get('disponibles') or 0),
                    'unidades_fisicas': int(r.get('fisicas') or 0),
                    'autores': ', '.join([x for x in autores_map.get(did, []) if x]),
                })

            if page is not None:
                return self.get_paginated_response(payload)
            return Response(payload)

        class DocListSerializer(sz.ModelSerializer):
            autores = sz.SerializerMethodField()
            ejemplares = sz.SerializerMethodField()
            disponibles = sz.SerializerMethodField()
            tipo_nombre = sz.CharField(source='id_tipo_documento.nombre_tipo', read_only=True)
            carrera_nombre = sz.CharField(source='id_carrera.nombre_carrera', read_only=True)
            tutor_academico = sz.SerializerMethodField()
            area_de_conocimiento = sz.SerializerMethodField()

            class Meta:
                model = Documentos
                fields = ['id_documento', 'titulo', 'id_tipo_documento', 'tipo_nombre', 'fecha_publicacion', 'id_carrera','carrera_nombre', 'tutor_academico', 'area_de_conocimiento', 'autores', 'ejemplares', 'disponibles']

            def get_autores(self, obj):
                qs = DocumentoAutores.objects.filter(id_documento=obj).select_related('id_autor')
                return [{'id_autor': x.id_autor_id, 'nombre': x.id_autor.nombre, 'apellido': x.id_autor.apellido} for x in qs]

            def get_tutor_academico(self, obj):
                d = getattr(obj, 'documentoacademico', None)
                return getattr(d, 'tutor_academico', None) if d else None

            def get_area_de_conocimiento(self, obj):
                d = getattr(obj, 'librodetalle', None)
                return getattr(d, 'area_de_conocimiento', None) if d else None

            def get_ejemplares(self, obj):
                e_qs = (
                    Ejemplares.objects
                    .filter(id_documento=obj)
                    .exclude(id_estado_ejemplar__nombre_estado__icontains='ELIMIN')
                    .exclude(unidad_fisica=0)
                    .select_related('id_ubicacion', 'id_estado_ejemplar')
                )
                ids = list(e_qs.values_list('id_ejemplar', flat=True))
                if not ids:
                    return []
                abiertos = DetallePrestamo.objects.filter(
                    id_ejemplar_id__in=ids,
                    fecha_devolucion_real__isnull=True
                ).values('id_ejemplar_id').annotate(c=Count('id_ejemplar_id'))
                abiertos_map = {x['id_ejemplar_id']: x['c'] for x in abiertos}
                # Agrupar por tomo: cada subarreglo es un volumen con sus ejemplares físicos
                grupos = {}
                for e in e_qs:
                    usados = abiertos_map.get(e.id_ejemplar, 0)
                    disp = max((e.unidad_fisica or 0) - usados, 0)
                    tot = int(e.unidad_fisica or 0)
                    used = min(max(int(usados or 0), 0), tot)
                    unidades = ([{'estado_prestamo': 'Disponible'}] * disp) + ([{'estado_prestamo': 'Prestado'}] * used)
                    if len(unidades) < tot:
                        unidades = unidades + ([{'estado_prestamo': 'Prestado'}] * (tot - len(unidades)))
                    item = {
                        'id_ejemplar': e.id_ejemplar,
                        'id_ubicacion': e.id_ubicacion_id,
                        'ubicacion': (getattr(e.id_ubicacion, 'descripcion_completa', None) if getattr(e, 'id_ubicacion', None) else None),
                        'codigo_cota': e.codigo_cota,
                        'tomo': e.tomo,
                        'disponible': disp > 0,
                        'unidades': unidades,
                        'unidades_fisicas': tot,
                        'unidades_disponibles': disp,
                        'id_estado_ejemplar': e.id_estado_ejemplar_id,
                        'estado': (getattr(e.id_estado_ejemplar, 'nombre_estado', None) if getattr(e, 'id_estado_ejemplar', None) else None),
                        'estado_fisico': (getattr(e.id_estado_ejemplar, 'nombre_estado', None) if getattr(e, 'id_estado_ejemplar', None) else None),
                    }
                    if e.tomo in grupos:
                        grupos[e.tomo].append(item)
                    else:
                        grupos[e.tomo] = [item]
                # Devolver en el orden de inserción de los tomos (sin ordenar por ubicación ni id)
                return [v for v in grupos.values()]

            def get_disponibles(self, obj):
                e_qs = (
                    Ejemplares.objects
                    .filter(id_documento=obj)
                    .exclude(id_estado_ejemplar__nombre_estado__icontains='ELIMIN')
                    .exclude(unidad_fisica=0)
                )
                ids = list(e_qs.values_list('id_ejemplar', flat=True))
                if not ids:
                    return 0
                abiertos = DetallePrestamo.objects.filter(
                    id_ejemplar_id__in=ids,
                    fecha_devolucion_real__isnull=True
                ).values('id_ejemplar_id').annotate(c=Count('id_ejemplar_id'))
                abiertos_map = {x['id_ejemplar_id']: x['c'] for x in abiertos}
                total = 0
                for e in e_qs:
                    usados = abiertos_map.get(e.id_ejemplar, 0)
                    total += max((e.unidad_fisica or 0) - usados, 0)
                return total

        qs = self.filterset_class(request.GET, queryset=self.get_queryset(), request=request).qs if self.filterset_class else self.get_queryset()
        if id_documento is not None:
            qs = qs.filter(id_documento=int(str(id_documento).strip()))
        # búsqueda libre por título, cota o autor (ignora mayúsculas y acentos)
        term = request.GET.get('q')
        if term:
            term_l = term.strip().lower()
            # normalización básica de acentos en el término
            term_n = (
                term_l
                .replace('á', 'a')
                .replace('é', 'e')
                .replace('í', 'i')
                .replace('ó', 'o')
                .replace('ú', 'u')
            )
            # anotar versiones normalizadas (lower + sin acentos) para filtrar
            qs = qs.annotate(
                titulo_l=Lower('titulo'),
                cota_l=Lower('codigo_cota'),
                autor_nombre_l=Lower('documentoautores__id_autor__nombre'),
                autor_apellido_l=Lower('documentoautores__id_autor__apellido'),
            )
            qs = qs.annotate(
                titulo_n=Replace(Replace(Replace(Replace(Replace(F('titulo_l'), Value('á'), Value('a')), Value('é'), Value('e')), Value('í'), Value('i')), Value('ó'), Value('o')), Value('ú'), Value('u')),
                cota_n=Replace(Replace(Replace(Replace(Replace(F('cota_l'), Value('á'), Value('a')), Value('é'), Value('e')), Value('í'), Value('i')), Value('ó'), Value('o')), Value('ú'), Value('u')),
                autor_nombre_n=Replace(Replace(Replace(Replace(Replace(F('autor_nombre_l'), Value('á'), Value('a')), Value('é'), Value('e')), Value('í'), Value('i')), Value('ó'), Value('o')), Value('ú'), Value('u')),
                autor_apellido_n=Replace(Replace(Replace(Replace(Replace(F('autor_apellido_l'), Value('á'), Value('a')), Value('é'), Value('e')), Value('í'), Value('i')), Value('ó'), Value('o')), Value('ú'), Value('u')),
            ).filter(
                Q(titulo_n__contains=term_n) |
                Q(cota_n__contains=term_n) |
                Q(autor_nombre_n__contains=term_n) |
                Q(autor_apellido_n__contains=term_n)
            ).distinct()
        # Asegurar orden estable antes de paginar para evitar UnorderedObjectListWarning
        if not qs.ordered:
            qs = qs.order_by('id_documento')
        qs = qs.prefetch_related('librodetalle', 'documentoacademico')
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
        instance = self.get_object()
        
        # Verificar permisos de administrador
        if not _is_admin_user(request.user):
            return Response({
                'detail': 'No tiene permisos para eliminar documentos'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Verificar si hay préstamos activos para este documento
        prestamos_activos = DetallePrestamo.objects.filter(
            id_ejemplar__id_documento=instance,
            fecha_devolucion_real__isnull=True
        ).exists()
        
        if prestamos_activos:
            return Response({
                'detail': 'No se puede eliminar el documento porque tiene préstamos activos'
            }, status=status.HTTP_409_CONFLICT)
        
        with transaction.atomic():
            documento_id = instance.id_documento
            titulo = instance.titulo
            
            # 1. Obtener todos los ejemplares del documento
            ejemplares = Ejemplares.objects.filter(id_documento=instance)
            ejemplar_ids = list(ejemplares.values_list('id_ejemplar', flat=True))
            
            # 2. Eliminar detalles de préstamos históricos (ya concluidos)
            if ejemplar_ids:
                DetallePrestamo.objects.filter(
                    id_ejemplar_id__in=ejemplar_ids
                ).delete()
            
            # 3. Eliminar ejemplares (ahora sin referencias FK)
            ejemplares.delete()
            
            # 4. Eliminar relaciones con autores
            DocumentoAutores.objects.filter(id_documento=instance).delete()
            
            # 5. Eliminar detalles específicos del documento
            try:
                if hasattr(instance, 'documentoacademico'):
                    instance.documentoacademico.delete()
            except DocumentoAcademico.DoesNotExist:
                pass
            
            try:
                if hasattr(instance, 'librodetalle'):
                    instance.librodetalle.delete()
            except LibroDetalle.DoesNotExist:
                pass
            
            try:
                if hasattr(instance, 'informepasantiadetalle'):
                    instance.informepasantiadetalle.delete()
            except:
                pass
            
            # 6. Eliminar el documento principal
            instance.delete()
            
            # Auditoría
            uid = getattr(getattr(request, 'user', None), 'id', None)
            logger.info(
                'Documento eliminado: id=%s, titulo=%s, user=%s, ejemplares=%s', 
                documento_id, titulo, uid, len(ejemplar_ids)
            )
        
        return Response({
            'status': 'documento-eliminado', 
            'id_documento': documento_id,
            'titulo': titulo
        }, status=status.HTTP_200_OK)


# Ejemplares (update/delete)
class EjemplarUpdateDeleteView(generics.GenericAPIView):
    def put(self, request, ejemplar_id: int):
        return self.patch(request, ejemplar_id=ejemplar_id)

    def patch(self, request, ejemplar_id: int):
        # Campos permitidos para actualizar
        allowed = {'codigo_cota', 'tomo', 'unidad_fisica', 'id_ubicacion', 'id_estado_ejemplar'}
        data = {k: v for k, v in request.data.items() if k in allowed}
        if not data:
            return Response({'detail': 'Nada para actualizar'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            e = Ejemplares.objects.get(pk=ejemplar_id)
        except Ejemplares.DoesNotExist:
            return Response({'detail': 'Ejemplar no existe'}, status=status.HTTP_404_NOT_FOUND)
        # Asignaciones simples
        if 'codigo_cota' in data:
            e.codigo_cota = data['codigo_cota'] or None
        if 'tomo' in data:
            e.tomo = data['tomo'] or None
        if 'unidad_fisica' in data:
            try:
                e.unidad_fisica = int(data['unidad_fisica'])
            except (TypeError, ValueError):
                return Response({'detail': 'unidad_fisica inválida'}, status=status.HTTP_400_BAD_REQUEST)
        if 'id_ubicacion' in data:
            e.id_ubicacion_id = data['id_ubicacion'] or None
        if 'id_estado_ejemplar' in data:
            e.id_estado_ejemplar_id = data['id_estado_ejemplar']
        e.save()
        return Response({'status': 'actualizado', 'id_ejemplar': e.id_ejemplar})

    def delete(self, request, ejemplar_id: int):
        try:
            e = Ejemplares.objects.select_related('id_estado_ejemplar').get(pk=ejemplar_id)
        except Ejemplares.DoesNotExist:
            return Response({'detail': 'Ejemplar no existe'}, status=status.HTTP_404_NOT_FOUND)
        
        # Verificar si el ejemplar tiene préstamos activos
        prestamos_activos = DetallePrestamo.objects.filter(
            id_ejemplar=e,
            fecha_devolucion_real__isnull=True
        ).exists()
        
        if prestamos_activos:
            return Response({
                'detail': 'No se puede eliminar el ejemplar porque tiene préstamos activos'
            }, status=status.HTTP_409_CONFLICT)
        
        # Soft delete: cambiar estado a ELIMINADO (si existe) y poner unidad_fisica=0
        eliminado = EstadosEjemplar.objects.filter(nombre_estado__iexact='ELIMINADO').first()
        if eliminado:
            e.id_estado_ejemplar = eliminado
        # Mantener registro con unidades en 0
        try:
            e.unidad_fisica = 0
        except Exception:
            pass
        e.save(update_fields=['id_estado_ejemplar', 'unidad_fisica'] if eliminado else ['unidad_fisica'])
        # Auditoría
        uid = getattr(getattr(request, 'user', None), 'id', None)
        logger.info('Soft delete ejemplar: id=%s, doc=%s, user=%s, estado=%s', e.id_ejemplar, getattr(e.id_documento, 'id_documento', None), uid, getattr(e.id_estado_ejemplar, 'nombre_estado', None))
        return Response({'status': 'ejemplar-soft-deleted', 'id_ejemplar': ejemplar_id})


class EjemplarCreateView(generics.GenericAPIView):
    def post(self, request, documento_id: int):
        # Campos esperados
        payload = request.data
        try:
            doc = Documentos.objects.get(pk=documento_id)
        except Documentos.DoesNotExist:
            return Response({'detail': 'Documento no existe'}, status=status.HTTP_404_NOT_FOUND)

        # Validaciones básicas
        unidad_fisica = payload.get('unidad_fisica')
        if unidad_fisica is None:
            return Response({'detail': 'unidad_fisica es requerida'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            unidad_fisica = int(unidad_fisica)
            if unidad_fisica < 0:
                raise ValueError()
        except Exception:
            return Response({'detail': 'unidad_fisica inválida'}, status=status.HTTP_400_BAD_REQUEST)

        id_estado = payload.get('id_estado_ejemplar')
        if not id_estado:
            return Response({'detail': 'id_estado_ejemplar es requerido'}, status=status.HTTP_400_BAD_REQUEST)

        e = Ejemplares.objects.create(
            id_documento=doc,
            codigo_cota=payload.get('codigo_cota') or None,
            tomo=payload.get('tomo') or None,
            unidad_fisica=unidad_fisica,
            id_estado_ejemplar_id=id_estado,
            id_ubicacion_id=payload.get('id_ubicacion') or None,
        )
        return Response({'id_ejemplar': e.id_ejemplar}, status=status.HTTP_201_CREATED)


# Prestamos
class PrestamoListCreateView(generics.GenericAPIView):
    serializer_class = None

    def post(self, request):
        from .serializers import PrestamoCreateSerializer

        payload = request.data.copy()

        # Regla solicitada: tratar un único parámetro id_user como identificador del usuario
        id_user = payload.get('id_user')
        if id_user is not None:
            s = str(id_user).strip()
            if not s.isdigit():
                return Response({'detail': 'id_user inválido'}, status=status.HTTP_400_BAD_REQUEST)
            payload['id_usuario'] = int(s)
        elif payload.get('id_usuario') is not None:
            # compat: permitir id_usuario si viene (pero la API pública es id_user)
            pass
        else:
            return Response({'detail': 'id_user es requerido'}, status=status.HTTP_400_BAD_REQUEST)

        # Validación/creación: buscar en BD interna, si no existe buscar en externa y registrar
        if not Usuarios.objects.filter(id_usuario=payload['id_usuario']).exists():
            from .external import ExternalUserClient
            
            # Intentar obtener usuario de BD externa
            try:
                external_user = ExternalUserClient.fetch(payload['id_usuario'])
                
                if external_user:
                    # Usuario encontrado en BD externa, registrarlo en BD interna
                    rol_id = external_user.get('rol') or (Roles.objects.first().id_rol if Roles.objects.exists() else 1)
                    
                    # Asegurar que el rol existe
                    if not Roles.objects.filter(id_rol=rol_id).exists():
                        rol_id = Roles.objects.first().id_rol if Roles.objects.exists() else 1
                    
                    Usuarios.objects.create(
                        id_usuario=external_user['id'],
                        nombre=external_user['nombre'] or 'Usuario',
                        apellido=external_user['apellido'] or 'Externo',
                        email=external_user.get('email'),
                        password=None,  # Usuario externo no tiene contraseña local
                        id_rol_id=rol_id,
                    )
                    logger.info(f"Usuario {external_user['id']} registrado desde BD externa")
                else:
                    # Usuario no existe ni en BD interna ni externa
                    return Response(
                        {'detail': 'El usuario no existe. Verifique el ID ingresado.'}, 
                        status=status.HTTP_404_NOT_FOUND
                    )
            except Exception as e:
                logger.error(f"Error consultando BD externa para usuario {payload['id_usuario']}: {e}")
                return Response(
                    {'detail': 'Error al verificar usuario. Intente nuevamente.'}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        ser = PrestamoCreateSerializer(data=payload)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        # Validar usuario
        try:
            usuario = Usuarios.objects.get(id_usuario=data['id_usuario'])
        except Usuarios.DoesNotExist:
            return Response({'detail': 'Usuario no existe'}, status=status.HTTP_400_BAD_REQUEST)

        ejemplar_ids = [e['id_ejemplar'] for e in data['ejemplares']]
        # Validar existencia de ejemplares
        existentes = set(Ejemplares.objects.filter(id_ejemplar__in=ejemplar_ids).values_list('id_ejemplar', flat=True))
        faltantes = [x for x in ejemplar_ids if x not in existentes]
        if faltantes:
            return Response({'detail': 'Ejemplares no existen', 'ids': faltantes}, status=status.HTTP_400_BAD_REQUEST)

        # Validar disponibilidad (no prestamo activo)
        activos = DetallePrestamo.objects.filter(id_ejemplar_id__in=ejemplar_ids, fecha_devolucion_real__isnull=True).values_list('id_ejemplar_id', flat=True).distinct()
        activos = list(activos)
        if activos:
            return Response({'detail': 'Ejemplares en préstamo activo', 'ids': activos}, status=status.HTTP_409_CONFLICT)

        # Crear prestamo y detalles
        with transaction.atomic():
            # Usar fecha provista o fallback a now
            fecha_prestamo_val = data.get('fecha_prestamo') or timezone.now()
            prestamo = Prestamos.objects.create(
                id_usuario_id=usuario.id_usuario,
                fecha_prestamo=fecha_prestamo_val,
                observacion=data.get('observacion'),
            )
            # No existe columna fecha_vencimiento en Prestamos, por lo que se almacena en detalle
            for eid in ejemplar_ids:
                DetallePrestamo.objects.create(
                    id_prestamo=prestamo,
                    id_ejemplar_id=eid,
                    fecha_vencimiento=data['fecha_vencimiento'],
                    fecha_devolucion_real=None,
                )

        return Response({
            'id_prestamo': prestamo.id_prestamo,
            'id_usuario': prestamo.id_usuario_id,
            'fecha_prestamo': prestamo.fecha_prestamo,
            'fecha_vencimiento': data['fecha_vencimiento'],
            'ejemplares': ejemplar_ids,
        }, status=status.HTTP_201_CREATED)

    def get(self, request):
        qs = Prestamos.objects.all()

        # Filtros
        estado = request.GET.get('estado')  # activo | concluido | retrasado
        tipo_usuario = request.GET.get('tipo_usuario')  # estudiante | profesor | bibliotecario | administrador | id rol
        carrera = request.GET.get('carrera')  # id de carrera
        fecha_ini = request.GET.get('fecha_inicio')
        fecha_fin = request.GET.get('fecha_fin')
        id_documento = request.GET.get('id_documento')

        chip_titulos = [x for x in request.GET.getlist('titulo') if str(x).strip()]
        chip_autores = [x for x in request.GET.getlist('autor') if str(x).strip()]
        chip_cotas = [x for x in request.GET.getlist('cota') if str(x).strip()]
        chip_usuario_ids = [x for x in request.GET.getlist('usuario_id') if str(x).strip()]

        # Anotaciones para estado
        open_details = DetallePrestamo.objects.filter(id_prestamo=OuterRef('pk'), fecha_devolucion_real__isnull=True)
        qs = qs.annotate(
            has_open=Exists(open_details),
            min_due=Min('detalleprestamo__fecha_vencimiento'),
        )

        today = timezone.now().date()
        if estado == 'activo':
            qs = qs.filter(has_open=True, min_due__gte=today)
        elif estado == 'retrasado':
            qs = qs.filter(has_open=True, min_due__lt=today)
        elif estado == 'concluido':
            qs = qs.filter(has_open=False)

        if tipo_usuario:
            if tipo_usuario.isdigit():
                qs = qs.filter(id_usuario__id_rol_id=int(tipo_usuario))
            else:
                # Tolerar variaciones de nombre de rol en BD (mayúsculas/acentos y prefijos/sufijos)
                tipo_n = _normalize_text(tipo_usuario)
                if tipo_n:
                    qs = qs.annotate(
                        rol_n=_normalize_expr(F('id_usuario__id_rol__nombre_rol')),
                    ).filter(rol_n__contains=tipo_n)

        if carrera:
            # Filtrar préstamos que incluyen documentos de la carrera especificada
            qs = qs.filter(
                detalleprestamo__id_ejemplar__id_documento__id_carrera_id=carrera
            ).distinct()

        if fecha_ini:
            qs = qs.filter(fecha_prestamo__date__gte=fecha_ini)
        if fecha_fin:
            qs = qs.filter(fecha_prestamo__date__lte=fecha_fin)

        if id_documento:
            qs = qs.filter(detalleprestamo__id_ejemplar__id_documento_id=id_documento).distinct()

        for raw_uid in chip_usuario_ids:
            s = str(raw_uid).strip()
            if not s.isdigit():
                return Response({'detail': 'usuario_id inválido (debe ser numérico)'}, status=status.HTTP_400_BAD_REQUEST)
            qs = qs.filter(id_usuario_id=int(s))

        if chip_titulos or chip_autores or chip_cotas:
            # Usar subquery para evitar duplicados por múltiples joins
            prestamo_ids_filtrados = set()
            
            # Filtrar por títulos
            if chip_titulos:
                for t in chip_titulos:
                    tn = _normalize_text(t)
                    if tn:
                        ids = Prestamos.objects.annotate(
                            chip_titulo_n=_normalize_expr(F('detalleprestamo__id_ejemplar__id_documento__titulo'))
                        ).filter(chip_titulo_n__contains=tn).values_list('id_prestamo', flat=True)
                        if not prestamo_ids_filtrados:
                            prestamo_ids_filtrados = set(ids)
                        else:
                            prestamo_ids_filtrados &= set(ids)
            
            # Filtrar por cotas
            if chip_cotas:
                for c in chip_cotas:
                    cn = _normalize_text(c)
                    if cn:
                        ids = Prestamos.objects.annotate(
                            chip_cota_n=_normalize_expr(F('detalleprestamo__id_ejemplar__codigo_cota'))
                        ).filter(chip_cota_n__contains=cn).values_list('id_prestamo', flat=True)
                        if not prestamo_ids_filtrados:
                            prestamo_ids_filtrados = set(ids)
                        else:
                            prestamo_ids_filtrados &= set(ids)
            
            # Filtrar por autores
            if chip_autores:
                for a in chip_autores:
                    an = _normalize_text(a)
                    if not an:
                        continue
                    tokens = [t for t in an.split(' ') if t]
                    autor_ids = None
                    for tok in tokens:
                        ids = Prestamos.objects.annotate(
                            chip_autor_nom_n=_normalize_expr(F('detalleprestamo__id_ejemplar__id_documento__documentoautores__id_autor__nombre')),
                            chip_autor_ape_n=_normalize_expr(F('detalleprestamo__id_ejemplar__id_documento__documentoautores__id_autor__apellido'))
                        ).filter(
                            Q(chip_autor_nom_n__contains=tok) | Q(chip_autor_ape_n__contains=tok)
                        ).values_list('id_prestamo', flat=True)
                        if autor_ids is None:
                            autor_ids = set(ids)
                        else:
                            autor_ids &= set(ids)
                    if autor_ids is not None:
                        if not prestamo_ids_filtrados:
                            prestamo_ids_filtrados = autor_ids
                        else:
                            prestamo_ids_filtrados &= autor_ids
            
            # Aplicar filtro de IDs
            if prestamo_ids_filtrados:
                qs = qs.filter(id_prestamo__in=prestamo_ids_filtrados)

        qs = qs.order_by('-fecha_prestamo', '-id_prestamo')

        # Paginación y serialización
        page = self.paginate_queryset(qs)
        out_qs = page if page is not None else qs

        def estado_from(p):
            if p.has_open:
                return 'retrasado' if (p.min_due and p.min_due < today) else 'activo'
            return 'concluido'

        data = []

        prestamo_ids = [x.id_prestamo for x in out_qs]
        detalles_map = {}
        detalles_qs = (
            DetallePrestamo.objects
            .filter(id_prestamo_id__in=prestamo_ids)
            .select_related('id_ejemplar', 'id_ejemplar__id_documento', 'id_ejemplar__id_estado_ejemplar')
        )
        for d in detalles_qs:
            detalles_map.setdefault(d.id_prestamo_id, []).append(d)

        usuarios_map = {}
        for u in Usuarios.objects.filter(id_usuario__in=[x.id_usuario_id for x in out_qs]).select_related('id_rol'):
            usuarios_map[u.id_usuario] = u

        for p in out_qs:
            dlist = detalles_map.get(p.id_prestamo, [])
            u = usuarios_map.get(p.id_usuario_id)
            items = []
            for d in dlist:
                ej = getattr(d, 'id_ejemplar', None)
                doc = getattr(ej, 'id_documento', None) if ej else None
                items.append({
                    'id_detalle': getattr(d, 'id_detalle_prestamo', None),
                    'id_ejemplar': d.id_ejemplar_id,
                    'id_documento': getattr(doc, 'id_documento', None) if doc else None,
                    'titulo': getattr(doc, 'titulo', None) if doc else None,
                    'codigo_cota': getattr(ej, 'codigo_cota', None) if ej else None,
                    'tomo': getattr(ej, 'tomo', None) if ej else None,
                    'estado_ejemplar': getattr(getattr(ej, 'id_estado_ejemplar', None), 'nombre_estado', None) if ej else None,
                    'fecha_vencimiento': d.fecha_vencimiento,
                    'fecha_devolucion_real': d.fecha_devolucion_real,
                    'estado_item': 'devuelto' if d.fecha_devolucion_real else 'activo',
                })

            data.append({
                'id_prestamo': p.id_prestamo,
                'id_usuario': p.id_usuario_id,
                'usuario_nombre': getattr(u, 'nombre', None) if u else None,
                'usuario_apellido': getattr(u, 'apellido', None) if u else None,
                'usuario_tipo': getattr(getattr(u, 'id_rol', None), 'nombre_rol', None) if u else None,
                'fecha_prestamo': p.fecha_prestamo,
                'observacion': getattr(p, 'observacion', None),
                'estado': estado_from(p),
                'fecha_vencimiento_min': min([d.fecha_vencimiento for d in dlist]) if dlist else None,
                'items_count': len(items),
                'items': items,
            })

        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)


class PrestamoDetailView(generics.GenericAPIView):
    def put(self, request, prestamo_id: int):
        from .serializers import PrestamoUpdateSerializer
        try:
            prestamo = Prestamos.objects.get(pk=prestamo_id)
        except Prestamos.DoesNotExist:
            return Response({'detail': 'Préstamo no existe'}, status=status.HTTP_404_NOT_FOUND)

        # Validar que esté activo
        has_open = DetallePrestamo.objects.filter(id_prestamo=prestamo, fecha_devolucion_real__isnull=True).exists()
        if not has_open:
            return Response({'detail': 'Préstamo no está activo'}, status=status.HTTP_409_CONFLICT)

        ser = PrestamoUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        with transaction.atomic():
            # actualizar fecha_vencimiento en los detalles si viene
            if 'fecha_vencimiento' in data:
                if data['fecha_vencimiento'] < prestamo.fecha_prestamo.date():
                    return Response({'detail': 'fecha_vencimiento no puede ser menor que la fecha de creación del préstamo'}, status=status.HTTP_400_BAD_REQUEST)
                DetallePrestamo.objects.filter(id_prestamo=prestamo, fecha_devolucion_real__isnull=True).update(fecha_vencimiento=data['fecha_vencimiento'])

            if 'ejemplares' in data:
                new_ids = set([e['id_ejemplar'] for e in data['ejemplares']])
                # validar existencia
                existentes = set(Ejemplares.objects.filter(id_ejemplar__in=new_ids).values_list('id_ejemplar', flat=True))
                faltantes = [x for x in new_ids if x not in existentes]
                if faltantes:
                    return Response({'detail': 'Ejemplares no existen', 'ids': faltantes}, status=status.HTTP_400_BAD_REQUEST)

                # validar disponibilidad en otros préstamos activos
                conflictivos = DetallePrestamo.objects.filter(
                    id_ejemplar_id__in=new_ids,
                    fecha_devolucion_real__isnull=True
                ).exclude(id_prestamo=prestamo).values_list('id_ejemplar_id', flat=True).distinct()
                conflictivos = list(conflictivos)
                if conflictivos:
                    return Response({'detail': 'Ejemplares en otro préstamo activo', 'ids': conflictivos}, status=status.HTTP_409_CONFLICT)

                current_ids = set(DetallePrestamo.objects.filter(id_prestamo=prestamo).values_list('id_ejemplar_id', flat=True))
                # agregar nuevos
                to_add = new_ids - current_ids
                # determinar fecha de vencimiento efectiva para nuevos: si viene en payload usarla, si no, usar el mínimo actual
                effective_due = data.get('fecha_vencimiento') or DetallePrestamo.objects.filter(id_prestamo=prestamo).aggregate(m=Min('fecha_vencimiento'))['m']
                if effective_due and effective_due < prestamo.fecha_prestamo.date():
                    return Response({'detail': 'fecha_vencimiento efectiva no puede ser menor que la fecha de creación del préstamo'}, status=status.HTTP_400_BAD_REQUEST)
                for eid in to_add:
                    DetallePrestamo.objects.create(
                        id_prestamo=prestamo,
                        id_ejemplar_id=eid,
                        fecha_vencimiento=effective_due,
                        fecha_devolucion_real=None,
                    )
                # eliminar los que ya no están
                to_remove = current_ids - new_ids
                if to_remove:
                    DetallePrestamo.objects.filter(id_prestamo=prestamo, id_ejemplar_id__in=to_remove).delete()

            # actualizar observacion si viene
            if 'observacion' in data:
                prestamo.observacion = data['observacion']
                prestamo.save(update_fields=['observacion'])

        # respuesta
        nuevos = DetallePrestamo.objects.filter(id_prestamo=prestamo)
        return Response({
            'id_prestamo': prestamo.id_prestamo,
            'id_usuario': prestamo.id_usuario_id,
            'fecha_prestamo': prestamo.fecha_prestamo,
            'ejemplares': [d.id_ejemplar_id for d in nuevos],
        })

    def delete(self, request, prestamo_id: int):
        # eliminar físicamente el préstamo y sus detalles
        try:
            prestamo = Prestamos.objects.get(pk=prestamo_id)
        except Prestamos.DoesNotExist:
            return Response({'detail': 'Préstamo no existe'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            DetallePrestamo.objects.filter(id_prestamo=prestamo).delete()
            prestamo.delete()

        return Response({'status': 'prestamo-eliminado', 'id_prestamo': prestamo_id})


class PrestamoConcluirView(generics.GenericAPIView):
    def post(self, request, prestamo_id: int):
        # Concluir: setea fecha_devolucion_real en detalles abiertos y actualiza observacion
        try:
            prestamo = Prestamos.objects.get(pk=prestamo_id)
        except Prestamos.DoesNotExist:
            return Response({'detail': 'Préstamo no existe'}, status=status.HTTP_404_NOT_FOUND)

        observacion = request.data.get('observacion')

        with transaction.atomic():
            updated = DetallePrestamo.objects.filter(id_prestamo=prestamo, fecha_devolucion_real__isnull=True).update(fecha_devolucion_real=timezone.now())
            if observacion is not None:
                prestamo.observacion = observacion
                prestamo.save(update_fields=['observacion'])

        return Response({'status': 'prestamo-concluido', 'id_prestamo': prestamo.id_prestamo, 'detalles_actualizados': updated})


class AreaSugerenciaView(generics.GenericAPIView):
    def get(self, request):
        term = (request.GET.get('search') or '').strip()
        term_n = _normalize_text(term)
        qs = LibroDetalle.objects.exclude(area_de_conocimiento__isnull=True).exclude(area_de_conocimiento__exact='')
        vals = list(qs.values_list('area_de_conocimiento', flat=True).distinct()[:300])
        canon = {}
        for v in vals:
            k = _normalize_text(v)
            if k and k not in canon:
                canon[k] = v
        if term_n:
            out = [v for k, v in canon.items() if term_n in k]
        else:
            out = list(canon.values())
        return Response(out[:30])


class AreaCatalogoView(generics.GenericAPIView):
    def get(self, request):
        qs = LibroDetalle.objects.exclude(area_de_conocimiento__isnull=True).exclude(area_de_conocimiento__exact='')
        vals = list(qs.values_list('area_de_conocimiento', flat=True).distinct()[:1000])
        canon = {}
        for v in vals:
            k = _normalize_text(v)
            if k and k not in canon:
                canon[k] = v
        return Response(list(canon.values())[:500])


class TutorSugerenciaView(generics.GenericAPIView):
    def get(self, request):
        term = (request.GET.get('search') or '').strip()
        term_n = _normalize_text(term)
        qs = DocumentoAcademico.objects.exclude(tutor_academico__isnull=True).exclude(tutor_academico__exact='')
        vals = list(qs.values_list('tutor_academico', flat=True).distinct()[:300])
        canon = {}
        for v in vals:
            k = _normalize_text(v)
            if k and k not in canon:
                canon[k] = v
        if term_n:
            out = [v for k, v in canon.items() if term_n in k]
        else:
            out = list(canon.values())
        return Response(out[:30])


class UsuarioSugerenciaView(generics.GenericAPIView):
    """
    Vista para búsqueda de usuarios con fallback a BD externa.
    Flujo: BD interna → BD externa → combinar resultados
    """
    def get(self, request):
        term = (request.GET.get('search') or '').strip()
        if not term:
            return Response([])

        # 1. Buscar en BD interna (SQLite local)
        qs = Usuarios.objects.all()
        s = term.strip()
        if s.isdigit():
            qs = qs.filter(id_usuario=int(s))
        else:
            qs = qs.filter(Q(nombre__icontains=s) | Q(apellido__icontains=s))

        qs = qs.order_by('id_usuario')[:20]
        data_interna = [
            {
                'id_usuario': u.id_usuario,
                'nombre': u.nombre,
                'apellido': u.apellido,
                'source': 'internal'
            }
            for u in qs
        ]

        # 2. Si no hay suficientes resultados, buscar en BD externa
        data_externa = []
        if len(data_interna) < 5:  # Buscar en externa si hay pocos resultados
            from .external import ExternalUserClient
            try:
                external_results = ExternalUserClient.search(term, limit=20)
                # Filtrar usuarios que ya están en BD interna
                ids_internos = {u['id_usuario'] for u in data_interna}
                data_externa = [
                    {
                        'id_usuario': u['id_usuario'],
                        'nombre': u['nombre'],
                        'apellido': u['apellido'],
                        'source': 'external'
                    }
                    for u in external_results
                    if u['id_usuario'] not in ids_internos
                ]
            except Exception as e:
                logger.error(f"Error buscando en BD externa: {e}")

        # 3. Combinar resultados (internos primero, luego externos)
        data = data_interna + data_externa
        
        # Remover el campo 'source' antes de enviar respuesta
        for item in data:
            item.pop('source', None)
        
        return Response(data[:20])  # Limitar a 20 resultados totales


# ------------------------
# Vistas Web (Templates)
# ------------------------

def login_page(request):
    error = None
    username = ''
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = (request.POST.get('username', '') or '').strip()
        password = request.POST.get('password', '')
        if not username or not password:
            error = 'Ingrese usuario y contraseña'
        else:
            user = authenticate(request, username=username, password=password)
            if user is None:
                error = 'Credenciales inválidas'
            else:
                login(request, user)
                return redirect('dashboard')
    return render(request, 'login.html', {'error': error, 'username': username})


def logout_page(request):
    # Cierra sesión de Django si la hubiera y retorna al login
    try:
        logout(request)
    except Exception:
        pass
    return redirect('login')


@ensure_csrf_cookie
@login_required(login_url='login')
def dashboard_page(request):
    if not _is_admin_user(request.user):
        return redirect('gestion_prestamos')
    
    from django.db.models import Count, Sum, Q, F, Min
    from django.utils import timezone
    
    # 1. Total de documentos únicos (títulos)
    total_documentos = Documentos.objects.count()
    
    # Total de ítems físicos (copias)
    total_items = Ejemplares.objects.exclude(
        id_estado_ejemplar__nombre_estado__icontains='ELIMIN'
    ).exclude(unidad_fisica=0).aggregate(
        total=Sum('unidad_fisica')
    )['total'] or 0
    
    # 2. Préstamos activos (transacciones con detalles activos NO vencidos)
    # Esto coincide con el filtro "activo" del módulo de préstamos
    open_details = DetallePrestamo.objects.filter(
        id_prestamo=OuterRef('pk'),
        fecha_devolucion_real__isnull=True
    )
    
    today = timezone.now().date()
    
    # Préstamos con al menos un detalle activo
    prestamos_con_abiertos = Prestamos.objects.annotate(
        has_open=Exists(open_details),
        min_due=Min('detalleprestamo__fecha_vencimiento', 
                    filter=Q(detalleprestamo__fecha_devolucion_real__isnull=True))
    )
    
    # Préstamos activos (no vencidos)
    prestamos_activos = prestamos_con_abiertos.filter(
        has_open=True,
        min_due__gte=today
    ).count()
    
    # 3. Préstamos vencidos (retrasados)
    prestamos_vencidos = prestamos_con_abiertos.filter(
        has_open=True,
        min_due__lt=today
    ).count()
    
    # 4. Usuarios registrados
    usuarios_registrados = Usuarios.objects.count()
    
    # 5. Top 5 préstamos vencidos (más antiguos primero)
    detalles_vencidos = DetallePrestamo.objects.filter(
        fecha_devolucion_real__isnull=True,
        fecha_vencimiento__lt=today
    ).select_related(
        'id_prestamo__id_usuario',
        'id_ejemplar__id_documento'
    ).order_by('fecha_vencimiento')[:5]
    
    prestamos_vencidos_list = []
    for detalle in detalles_vencidos:
        dias_vencido = (today - detalle.fecha_vencimiento).days
        usuario = detalle.id_prestamo.id_usuario
        documento = detalle.id_ejemplar.id_documento
        prestamos_vencidos_list.append({
            'titulo': documento.titulo,
            'usuario': f"{usuario.nombre} {usuario.apellido}",
            'dias': dias_vencido
        })
    
    # 6. Inventario crítico (documentos sin ejemplares disponibles)
    # Subconsulta para contar préstamos activos por ejemplar
    prestamos_activos_sub = DetallePrestamo.objects.filter(
        id_ejemplar_id=OuterRef('pk'),
        fecha_devolucion_real__isnull=True
    ).values('id_ejemplar_id').annotate(c=Count('id_ejemplar_id')).values('c')
    
    # Ejemplares con disponibilidad calculada
    ejemplares_con_disp = Ejemplares.objects.exclude(
        id_estado_ejemplar__nombre_estado__icontains='ELIMIN'
    ).exclude(unidad_fisica=0).annotate(
        prestados=Coalesce(Subquery(prestamos_activos_sub, output_field=IntegerField()), Value(0)),
        disponibles=F('unidad_fisica') - F('prestados')
    )
    
    # Agrupar por documento y sumar disponibles
    docs_sin_stock = ejemplares_con_disp.values(
        'id_documento_id'
    ).annotate(
        total_disponibles=Sum('disponibles')
    ).filter(
        total_disponibles=0
    ).values_list('id_documento_id', flat=True)[:5]
    
    # Obtener información de documentos sin stock
    inventario_critico = []
    for doc_id in docs_sin_stock:
        try:
            doc = Documentos.objects.get(id_documento=doc_id)
            # Obtener primer autor
            autor_rel = DocumentoAutores.objects.filter(id_documento=doc).select_related('id_autor').first()
            autor = f"{autor_rel.id_autor.nombre} {autor_rel.id_autor.apellido}" if autor_rel else "Autor desconocido"
            inventario_critico.append({
                'titulo': doc.titulo,
                'autor': autor
            })
        except Documentos.DoesNotExist:
            continue
    
    # Calcular porcentajes para gráficas de dona
    # 1. Porcentaje de documentos con stock disponible vs sin stock
    docs_con_stock = ejemplares_con_disp.values(
        'id_documento_id'
    ).annotate(
        total_disponibles=Sum('disponibles')
    ).filter(
        total_disponibles__gt=0
    ).count()
    
    docs_sin_stock_count = ejemplares_con_disp.values(
        'id_documento_id'
    ).annotate(
        total_disponibles=Sum('disponibles')
    ).filter(
        total_disponibles=0
    ).count()
    
    # Documentos que no tienen ejemplares activos
    docs_sin_ejemplares = total_documentos - docs_con_stock - docs_sin_stock_count
    
    # Porcentajes para títulos únicos
    if total_documentos > 0:
        titulos_disponibles_pct = round((docs_con_stock / total_documentos) * 100)
        titulos_agotados_pct = round((docs_sin_stock_count / total_documentos) * 100)
        titulos_sin_ejemplares_pct = 100 - titulos_disponibles_pct - titulos_agotados_pct
    else:
        titulos_disponibles_pct = titulos_agotados_pct = titulos_sin_ejemplares_pct = 0
    
    # 2. Porcentaje de préstamos activos vs vencidos
    total_prestamos_abiertos = prestamos_activos + prestamos_vencidos
    if total_prestamos_abiertos > 0:
        prestamos_activos_pct = round((prestamos_activos / total_prestamos_abiertos) * 100)
        prestamos_vencidos_pct = 100 - prestamos_activos_pct
    else:
        prestamos_activos_pct = prestamos_vencidos_pct = 0
    
    # 3. Porcentaje de préstamos vencidos por urgencia (días)
    if prestamos_vencidos > 0:
        # Contar préstamos por rangos de días vencidos
        vencidos_1_7 = DetallePrestamo.objects.filter(
            fecha_devolucion_real__isnull=True,
            fecha_vencimiento__lt=today,
            fecha_vencimiento__gte=today - timezone.timedelta(days=7)
        ).count()
        
        vencidos_8_30 = DetallePrestamo.objects.filter(
            fecha_devolucion_real__isnull=True,
            fecha_vencimiento__lt=today - timezone.timedelta(days=7),
            fecha_vencimiento__gte=today - timezone.timedelta(days=30)
        ).count()
        
        vencidos_mas_30 = DetallePrestamo.objects.filter(
            fecha_devolucion_real__isnull=True,
            fecha_vencimiento__lt=today - timezone.timedelta(days=30)
        ).count()
        
        vencidos_criticos_pct = round((vencidos_mas_30 / prestamos_vencidos) * 100) if prestamos_vencidos > 0 else 0
        vencidos_moderados_pct = round((vencidos_8_30 / prestamos_vencidos) * 100) if prestamos_vencidos > 0 else 0
        vencidos_recientes_pct = 100 - vencidos_criticos_pct - vencidos_moderados_pct
    else:
        vencidos_criticos_pct = vencidos_moderados_pct = vencidos_recientes_pct = 0

    context = {
        'active_page': 'dashboard',
        'total_documentos': total_documentos,
        'total_items': total_items,
        'prestamos_activos': prestamos_activos,
        'prestamos_vencidos': prestamos_vencidos,
        'usuarios_registrados': usuarios_registrados,
        'prestamos_vencidos_list': prestamos_vencidos_list,
        'inventario_critico': inventario_critico,
        # Datos para gráficas de dona
        'titulos_disponibles_pct': titulos_disponibles_pct,
        'titulos_agotados_pct': titulos_agotados_pct,
        'titulos_sin_ejemplares_pct': titulos_sin_ejemplares_pct,
        'prestamos_activos_pct': prestamos_activos_pct,
        'prestamos_vencidos_pct': prestamos_vencidos_pct,
        'vencidos_criticos_pct': vencidos_criticos_pct,
        'vencidos_moderados_pct': vencidos_moderados_pct,
        'vencidos_recientes_pct': vencidos_recientes_pct,
    }
    
    return render(request, 'dashboard.html', context)


@ensure_csrf_cookie
@login_required(login_url='login')
def inventario_gestion_page(request):
    # Render-only: el front consumirá el API (o mock) vía JS
    if not _is_admin_user(request.user):
        return redirect('gestion_prestamos')
    return render(request, 'inventario_gestion.html', {'active_page': 'inventario'})


@ensure_csrf_cookie
@login_required(login_url='login')
def inventario_registrar_page(request):
    # Render-only: el front enviará POST al API (o mock) vía JS
    if not _is_admin_user(request.user):
        return redirect('gestion_prestamos')
    return render(request, 'inventario_registrar.html', {'active_page': 'inventario'})


@ensure_csrf_cookie
@login_required(login_url='login')
def inventario_registrar_libro_page(request):
    # Render-only: página específica para registrar libros
    if not _is_admin_user(request.user):
        return redirect('gestion_prestamos')
    return render(request, 'inventario_registrar_libro.html', {'active_page': 'inventario'})


@ensure_csrf_cookie
@login_required(login_url='login')
def inventario_registrar_tesis_page(request):
    # Render-only: página específica para registrar tesis
    if not _is_admin_user(request.user):
        return redirect('gestion_prestamos')
    return render(request, 'inventario_registrar_tesis.html', {'active_page': 'inventario'})


@ensure_csrf_cookie
@login_required(login_url='login')
def prestamos_gestion_page(request):
    # Render-only: el front consumirá el API (o mock) vía JS
    return render(request, 'prestamos_gestion.html', {'active_page': 'prestamos'})


@ensure_csrf_cookie
@login_required(login_url='login')
def prestamos_registrar_page(request):
    # Render-only: el front enviará POST al API (o mock) vía JS
    return render(request, 'prestamos_registrar.html', {'active_page': 'prestamos'})


@ensure_csrf_cookie
@login_required(login_url='login')
def usuarios_gestion_page(request):
    """Vista de gestión de usuarios"""
    if not _is_admin_user(request.user):
        return redirect('gestion_prestamos')
    
    from django.contrib.auth.models import User
    
    # Obtener todos los usuarios de la tabla de dominio
    usuarios_list = Usuarios.objects.select_related('id_rol').all().order_by('id_usuario')
    
    # Obtener IDs de usuarios con login
    usuarios_con_login = set(User.objects.values_list('id', flat=True))
    
    # Calcular préstamos activos y vencidos por usuario
    today = timezone.now().date()
    
    usuarios_data = []
    for usuario in usuarios_list:
        # Préstamos del usuario
        prestamos_usuario = Prestamos.objects.filter(id_usuario=usuario)
        
        # Préstamos activos (con detalles sin devolver)
        prestamos_activos = prestamos_usuario.filter(
            detalleprestamo__fecha_devolucion_real__isnull=True
        ).distinct().count()
        
        # Préstamos vencidos (activos con fecha vencida)
        prestamos_vencidos = prestamos_usuario.filter(
            detalleprestamo__fecha_devolucion_real__isnull=True,
            detalleprestamo__fecha_vencimiento__lt=today
        ).distinct().count()
        
        usuarios_data.append({
            'id_usuario': usuario.id_usuario,
            'nombre': usuario.nombre,
            'apellido': usuario.apellido,
            'email': usuario.email,
            'id_rol': usuario.id_rol,
            'tiene_login': usuario.id_usuario in usuarios_con_login,
            'tipo': 'con_login' if usuario.id_usuario in usuarios_con_login else 'sin_login',
            'prestamos_activos': prestamos_activos,
            'prestamos_vencidos': prestamos_vencidos,
        })
    
    # Obtener roles para el filtro
    roles = Roles.objects.all()
    
    context = {
        'active_page': 'usuarios',
        'usuarios': usuarios_data,
        'roles': roles,
    }
    
    return render(request, 'usuarios_gestion.html', context)


class CotaGeneratorView(generics.GenericAPIView):
    """
    Vista para generar cotas automáticamente basadas en sistemas bibliotecarios reales.
    Implementa el sistema Dewey modificado y considera la ubicación física.
    """
    permission_classes = [AllowAny]  # Permitir acceso sin autenticación para AJAX
    
    def post(self, request):
        """
        Genera una cota automática basada en los parámetros proporcionados.
        
        Parámetros esperados:
        - tipo_documento: 'LIBRO' o 'TESIS'
        - area_conocimiento: área temática (para libros)
        - carrera_id: ID de la carrera (para tesis)
        - autor_apellido: apellido del autor principal
        - titulo: título del documento
        - año: año de publicación
        - ubicacion_id: ID de la ubicación donde se almacenará (opcional)
        - tomo: número de tomo (opcional, default: 1)
        """
        
        tipo_doc = request.data.get('tipo_documento', '').upper()
        area = request.data.get('area_conocimiento', '').strip()
        carrera_id = request.data.get('carrera_id')
        autor_apellido = request.data.get('autor_apellido', '').strip()
        titulo = request.data.get('titulo', '').strip()
        año = request.data.get('año')
        ubicacion_id = request.data.get('ubicacion_id')
        tomo = request.data.get('tomo', 1)  # Default tomo 1
        
        if not tipo_doc or not autor_apellido or not titulo:
            return Response({
                'error': 'Faltan parámetros requeridos: tipo_documento, autor_apellido, titulo'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            if tipo_doc == 'LIBRO':
                cota = self._generar_cota_libro_realista(area, autor_apellido, titulo, año, ubicacion_id, tomo)
            elif tipo_doc == 'TESIS':
                cota = self._generar_cota_tesis_realista(carrera_id, autor_apellido, titulo, año, ubicacion_id, tomo)
            else:
                return Response({
                    'error': 'Tipo de documento no válido'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Verificar si la cota ya existe y sugerir alternativas
            cotas_existentes = self._verificar_cota_existente(cota)
            
            return Response({
                'cota_sugerida': cota,
                'existe': len(cotas_existentes) > 0,
                'cotas_existentes': cotas_existentes,
                'alternativas': self._generar_alternativas(cota) if cotas_existentes else []
            })
            
        except Exception as e:
            logger.error(f"Error generando cota: {e}")
            return Response({
                'error': 'Error interno generando cota'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _generar_cota_libro_realista(self, area, autor_apellido, titulo, año, ubicacion_id=None, tomo=None):
        """
        Genera cota para libros usando sistema Dewey modificado más realista
        Formato: [Dewey] [Autor][letra_area][año][tomo] [Ubicacion]
        Ejemplo: 004.678 GARp24-2 E3 (tomo 2)
        """
        
        # 1. Código Dewey basado en área de conocimiento
        codigo_dewey = self._obtener_codigo_dewey_detallado(area)
        
        # 2. Código del autor (primeras 3 letras del apellido)
        codigo_autor = self._limpiar_texto_cota(autor_apellido)[:3].upper()
        
        # 3. Letra específica del área de conocimiento
        letra_area = self._obtener_letra_area_conocimiento(area)
        
        # 4. Año (últimos 2 dígitos si está disponible)
        codigo_año = str(año)[-2:] if año else ''
        
        # 5. Código de tomo (si es diferente de 1)
        codigo_tomo = ''
        if tomo and int(tomo) > 1:
            codigo_tomo = f"-{tomo}"
        
        # 6. Código de ubicación (si está disponible)
        codigo_ubicacion = self._obtener_codigo_ubicacion(ubicacion_id)
        
        # Construir la cota
        cota_base = f"{codigo_dewey} {codigo_autor}{letra_area}{codigo_año}{codigo_tomo}"
            
        if codigo_ubicacion:
            cota_base += f" {codigo_ubicacion}"
        
        return cota_base
    
    def _generar_cota_tesis_realista(self, carrera_id, autor_apellido, titulo, año, ubicacion_id=None, tomo=None):
        """
        Genera cota para tesis usando sistema académico realista
        Formato: T[Carrera] [Año] [Autor] [letra_carrera][numero][tomo] [Ubicacion]
        Ejemplo: TSIST 2024 GAR s001-2 B2 (tomo 2)
        """
        
        # 1. Código de carrera
        codigo_carrera = self._obtener_codigo_carrera_detallado(carrera_id)
        
        # 2. Año completo
        codigo_año = str(año) if año else str(timezone.now().year)
        
        # 3. Código del autor (primeras 3 letras del apellido)
        codigo_autor = self._limpiar_texto_cota(autor_apellido)[:3].upper()
        
        # 4. Letra específica de la carrera
        letra_carrera = self._obtener_letra_carrera(carrera_id)
        
        # 5. Número secuencial para el año y carrera
        numero_secuencial = self._obtener_numero_secuencial_tesis(codigo_carrera, codigo_año)
        
        # 6. Código de tomo (si es diferente de 1)
        codigo_tomo = ''
        if tomo and int(tomo) > 1:
            codigo_tomo = f"-{tomo}"
        
        # 7. Código de ubicación
        codigo_ubicacion = self._obtener_codigo_ubicacion(ubicacion_id)
        
        # Construir la cota
        cota_base = f"T{codigo_carrera} {codigo_año} {codigo_autor} {letra_carrera}{numero_secuencial:03d}{codigo_tomo}"
        
        if codigo_ubicacion:
            cota_base += f" {codigo_ubicacion}"
        
        return cota_base
    
    def _obtener_codigo_dewey_detallado(self, area):
        """
        Mapeo detallado de áreas a códigos Dewey reales
        """
        dewey_detallado = {
            # Ciencias de la Computación
            'programacion': '005.1',
            'algoritmos': '005.1',
            'base de datos': '005.74',
            'bases de datos': '005.74',
            'redes': '004.6',
            'redes de computadores': '004.6',
            'sistemas operativos': '005.43',
            'ingenieria de software': '005.1',
            'inteligencia artificial': '006.3',
            'machine learning': '006.31',
            'web': '006.7',
            'desarrollo web': '006.7',
            'seguridad informatica': '005.8',
            'ciberseguridad': '005.8',
            
            # Matemáticas
            'matematicas': '510',
            'algebra': '512',
            'calculo': '515',
            'estadistica': '519.5',
            'probabilidad': '519.2',
            'geometria': '516',
            
            # Física
            'fisica': '530',
            'mecanica': '531',
            'termodinamica': '536',
            'electricidad': '537',
            'electronica': '537.5',
            
            # Química
            'quimica': '540',
            'quimica organica': '547',
            'quimica inorganica': '546',
            
            # Ingeniería
            'ingenieria civil': '624',
            'ingenieria mecanica': '621',
            'ingenieria electrica': '621.3',
            'ingenieria electronica': '621.381',
            'ingenieria industrial': '658.5',
            'ingenieria de sistemas': '004',
            
            # Administración y Negocios
            'administracion': '658',
            'marketing': '658.8',
            'finanzas': '658.15',
            'recursos humanos': '658.3',
            'contabilidad': '657',
            'economia': '330',
            
            # Medicina y Salud
            'medicina': '610',
            'enfermeria': '610.73',
            'farmacia': '615',
            'odontologia': '617.6',
            'psicologia': '150',
            
            # Ciencias Sociales
            'derecho': '340',
            'sociologia': '301',
            'antropologia': '301',
            'trabajo social': '361',
            'educacion': '370',
            'pedagogia': '371',
            
            # Metodología e Investigación
            'metodologia de la investigacion': '001.42',
            'metodologia': '001.42',
            'investigacion': '001.4',
            'metodos de investigacion': '001.42',
            'investigacion cientifica': '001.4',
            'investigacion cualitativa': '001.42',
            'investigacion cuantitativa': '001.42',
            'epistemologia': '121',
            'teoria del conocimiento': '121',
            
            # Artes y Literatura
            'literatura': '800',
            'arte': '700',
            'musica': '780',
            'teatro': '792',
            'cine': '791.43',
            
            # Historia y Geografía
            'historia': '900',
            'geografia': '910',
            'arqueologia': '930',
            
            # Filosofía y Religión
            'filosofia': '100',
            'etica': '170',
            'religion': '200',
        }
        
        area_norm = _normalize_text(area)
        
        # Buscar coincidencia exacta primero
        for key, codigo in dewey_detallado.items():
            if key in area_norm:
                return codigo
        
        # Buscar por palabras clave
        palabras_area = area_norm.split()
        for palabra in palabras_area:
            for key, codigo in dewey_detallado.items():
                if palabra in key or key in palabra:
                    return codigo
        
        # Default genérico
        return '000'
    
    def _obtener_codigo_carrera_detallado(self, carrera_id):
        """
        Obtiene código detallado de carrera basado en el nombre real
        """
        if not carrera_id:
            return 'GEN'
        
        try:
            carrera = Carreras.objects.get(id_carrera=carrera_id)
            nombre = carrera.nombre_carrera.upper()
            
            # Mapeo específico de carreras
            if 'SISTEMAS' in nombre or 'INFORMATICA' in nombre or 'COMPUTACION' in nombre:
                return 'SIST'
            elif 'INDUSTRIAL' in nombre:
                return 'IND'
            elif 'CIVIL' in nombre:
                return 'CIV'
            elif 'ELECTRONICA' in nombre or 'ELECTRICA' in nombre:
                return 'ELEC'
            elif 'MECANICA' in nombre:
                return 'MEC'
            elif 'ADMINISTRACION' in nombre or 'EMPRESAS' in nombre:
                return 'ADM'
            elif 'CONTADURIA' in nombre or 'CONTABLE' in nombre:
                return 'CONT'
            elif 'DERECHO' in nombre:
                return 'DER'
            elif 'MEDICINA' in nombre:
                return 'MED'
            elif 'ENFERMERIA' in nombre:
                return 'ENF'
            elif 'PSICOLOGIA' in nombre:
                return 'PSI'
            elif 'EDUCACION' in nombre or 'PEDAGOGIA' in nombre:
                return 'EDU'
            else:
                # Generar código basado en las primeras letras
                palabras = [p for p in nombre.split() if len(p) > 2]
                if len(palabras) >= 2:
                    return palabras[0][:2] + palabras[1][:2]
                elif len(palabras) == 1:
                    return palabras[0][:4]
                else:
                    return 'GEN'
                    
        except Carreras.DoesNotExist:
            return 'GEN'
    
    def _obtener_letra_area_conocimiento(self, area):
        """
        Obtiene una letra específica basada en el área de conocimiento
        """
        if not area:
            return 'g'  # General
        
        area_norm = _normalize_text(area)
        
        # Mapeo específico de áreas a letras identificativas
        letras_area = {
            # Ciencias de la Computación
            'programacion': 'p',
            'algoritmos': 'a',
            'base de datos': 'bd',
            'redes': 'r',
            'redes de computadores': 'rdc',
            'sistemas operativos': 'so',
            'ingenieria de software': 'ids',
            'inteligencia artificial': 'ia',
            'machine learning': 'ml',
            'web': 'w',
            'desarrollo web': 'dw',
            'seguridad informatica': 'sei',
            'ciberseguridad': 'cib',
            
            # Matemáticas
            'matematicas': 'm',
            'algebra': 'a',
            'calculo': 'c',
            'estadistica': 'e',
            'probabilidad': 'p',
            'geometria': 'g',
            
            # Física y Química
            'fisica': 'f',
            'quimica': 'q',
            'mecanica': 'mec',
            'termodinamica': 't',
            'electricidad': 'e',
            'electronica': 'l',
            
            # Ingeniería
            'ingenieria civil': 'ic',
            'ingenieria mecanica': 'im',
            'ingenieria electrica': 'ie',
            'ingenieria electronica': 'iel',
            'ingenieria industrial': 'iin',
            'ingenieria de sistemas': 'is',
            
            # Administración y Negocios
            'administracion': 'a',
            'marketing': 'k',
            'finanzas': 'f',
            'recursos humanos': 'h',
            'contabilidad': 'c',
            'economia': 'e',
            
            # Medicina y Salud
            'medicina': 'm',
            'enfermeria': 'n',
            'farmacia': 'f',
            'odontologia': 'o',
            'psicologia': 'p',
            
            # Ciencias Sociales
            'derecho': 'd',
            'sociologia': 's',
            'antropologia': 'a',
            'trabajo social': 't',
            'educacion': 'e',
            'pedagogia': 'p',
            
            # Metodología e Investigación
            'metodologia de la investigacion': 'mdli',
            'metodologia': 'met',
            'investigacion': 'inv',
            'metodos de investigacion': 'mdi',
            'investigacion cientifica': 'icie',
            'investigacion cualitativa': 'icual',
            'investigacion cuantitativa': 'icuan',
            'epistemologia': 'epi',
            'teoria del conocimiento': 'tdc',
            
            # Artes y Literatura
            'literatura': 'l',
            'arte': 'a',
            'musica': 'm',
            'teatro': 't',
            'cine': 'c',
            
            # Historia y Geografía
            'historia': 'h',
            'geografia': 'g',
            'arqueologia': 'a',
            
            # Filosofía y Religión
            'filosofia': 'f',
            'etica': 'e',
            'religion': 'r',
        }
        
        # Buscar coincidencia exacta primero
        for key, letra in letras_area.items():
            if key in area_norm:
                return letra
        
        # Buscar por palabras clave
        palabras_area = area_norm.split()
        for palabra in palabras_area:
            for key, letra in letras_area.items():
                if palabra in key or key in palabra:
                    return letra
        
        # Si no encuentra, usar la primera letra del área
        area_limpia = self._limpiar_texto_cota(area)
        return area_limpia[0].lower() if area_limpia else 'g'
    
    def _obtener_letra_carrera(self, carrera_id):
        """
        Obtiene una letra específica basada en la carrera
        """
        if not carrera_id:
            return 'g'  # General
        
        try:
            carrera = Carreras.objects.get(id_carrera=carrera_id)
            nombre = carrera.nombre_carrera.upper()
            
            # Mapeo específico de carreras a letras identificativas
            if 'SISTEMAS' in nombre or 'INFORMATICA' in nombre or 'COMPUTACION' in nombre:
                return 's'
            elif 'INDUSTRIAL' in nombre:
                return 'i'
            elif 'CIVIL' in nombre:
                return 'c'
            elif 'ELECTRONICA' in nombre:
                return 'l'
            elif 'ELECTRICA' in nombre:
                return 'e'
            elif 'MECANICA' in nombre:
                return 'm'
            elif 'ADMINISTRACION' in nombre or 'EMPRESAS' in nombre:
                return 'a'
            elif 'CONTADURIA' in nombre or 'CONTABLE' in nombre:
                return 't'
            elif 'DERECHO' in nombre:
                return 'd'
            elif 'MEDICINA' in nombre:
                return 'm'
            elif 'ENFERMERIA' in nombre:
                return 'n'
            elif 'PSICOLOGIA' in nombre:
                return 'p'
            elif 'EDUCACION' in nombre or 'PEDAGOGIA' in nombre:
                return 'e'
            else:
                # Usar la primera letra de la primera palabra significativa
                palabras = [p for p in nombre.split() if len(p) > 2]
                return palabras[0][0].lower() if palabras else 'g'
                
        except Carreras.DoesNotExist:
            return 'g'
    
    def _obtener_codigo_ubicacion(self, ubicacion_id):
        """
        Obtiene código de ubicación basado en la descripción real
        """
        if not ubicacion_id:
            return None
        
        try:
            ubicacion = Ubicaciones.objects.get(id_ubicacion=ubicacion_id)
            descripcion = ubicacion.descripcion_completa.upper()
            
            # Extraer códigos comunes de ubicación
            if 'ESTANTE' in descripcion or 'SHELF' in descripcion:
                # Buscar números en la descripción
                import re
                numeros = re.findall(r'\d+', descripcion)
                if numeros:
                    return f"E{numeros[0]}"
            
            if 'PISO' in descripcion or 'FLOOR' in descripcion:
                import re
                numeros = re.findall(r'\d+', descripcion)
                if numeros:
                    return f"P{numeros[0]}"
            
            if 'SECCION' in descripcion or 'SECTION' in descripcion:
                # Buscar letras después de sección
                import re
                letras = re.findall(r'[A-Z]', descripcion)
                if letras:
                    return f"S{letras[0]}"
            
            # Generar código basado en las primeras letras
            palabras = [p for p in descripcion.split() if len(p) > 1]
            if palabras:
                return palabras[0][:2]
            
            return f"U{ubicacion_id}"
            
        except Ubicaciones.DoesNotExist:
            return None
    
    def _obtener_numero_secuencial_tesis(self, codigo_carrera, año):
        """
        Obtiene el siguiente número secuencial para tesis de una carrera en un año específico
        """
        try:
            # Buscar tesis existentes con el mismo patrón
            patron = f"T{codigo_carrera} {año}"
            cotas_existentes = Ejemplares.objects.filter(
                codigo_cota__startswith=patron
            ).values_list('codigo_cota', flat=True)
            
            numeros = []
            for cota in cotas_existentes:
                try:
                    # Extraer el número secuencial de la cota
                    # Formato esperado: TSIST 2024 GAR s001
                    partes = cota.split()
                    if len(partes) >= 4:
                        numero_parte = partes[3]
                        # Extraer solo los dígitos del final
                        import re
                        match = re.search(r'(\d+)', numero_parte)
                        if match:
                            numeros.append(int(match.group(1)))
                except:
                    continue
            
            return max(numeros) + 1 if numeros else 1
            
        except Exception:
            return 1
    
    def _limpiar_texto_cota(self, texto):
        """Limpia texto para usar en cotas (sin acentos, espacios, caracteres especiales)"""
        if not texto:
            return ''
        
        # Normalizar y quitar acentos
        texto_limpio = _normalize_text(texto)
        
        # Quitar espacios y caracteres especiales, mantener solo letras y números
        import re
        texto_limpio = re.sub(r'[^a-z0-9]', '', texto_limpio)
        
        return texto_limpio
    
    def _verificar_cota_existente(self, cota):
        """Verifica si una cota ya existe y retorna las cotas similares"""
        
        cotas_existentes = list(
            Ejemplares.objects.filter(
                codigo_cota__iexact=cota
            ).values_list('codigo_cota', flat=True)
        )
        
        return cotas_existentes
    
    def _generar_alternativas(self, cota_base):
        """Genera cotas alternativas cuando la original ya existe"""
        
        alternativas = []
        
        # Para cotas con espacios (formato Dewey), agregar sufijos antes del último espacio
        if ' ' in cota_base:
            partes = cota_base.rsplit(' ', 1)
            base = partes[0]
            final = partes[1] if len(partes) > 1 else ''
            
            # Agregar sufijos alfabéticos
            for letra in ['a', 'b', 'c', 'd', 'e']:
                alt = f"{base} {final}{letra}" if final else f"{base}{letra}"
                if not self._verificar_cota_existente(alt):
                    alternativas.append(alt)
            
            # Agregar sufijos numéricos
            for i in range(1, 4):
                alt = f"{base} {final}-{i}" if final else f"{base}-{i}"
                if not self._verificar_cota_existente(alt):
                    alternativas.append(alt)
        else:
            # Para cotas sin espacios, agregar sufijos al final
            for letra in ['a', 'b', 'c', 'd', 'e']:
                alt = f"{cota_base}{letra}"
                if not self._verificar_cota_existente(alt):
                    alternativas.append(alt)
            
            for i in range(1, 4):
                alt = f"{cota_base}-{i}"
                if not self._verificar_cota_existente(alt):
                    alternativas.append(alt)
        
        return alternativas[:3]  # Retornar máximo 3 alternativas

@ensure_csrf_cookie
@login_required(login_url='login')
def reportes_page(request):
    """Vista de reportes (diario, semanal, mensual)"""
    if not _is_admin_user(request.user):
        return redirect('dashboard')
    
    periodo = request.GET.get('periodo', 'diario')
    
    # Obtener fechas personalizadas
    fecha_inicio_str = request.GET.get('fecha_inicio')
    fecha_fin_str = request.GET.get('fecha_fin')
    
    today = timezone.now().date()
    
    start_date = today
    end_date = today

    if fecha_inicio_str and fecha_fin_str:
        try:
            start_date = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
            periodo = 'personalizado'
        except ValueError:
            # Si hay error en formato, fallback a diario
            pass
    elif periodo == 'semanal':
        start_date = today - timedelta(days=today.weekday()) # Lunes de esta semana
        end_date = start_date + timedelta(days=6) # Domingo
    elif periodo == 'mensual':
        start_date = today.replace(day=1)
        # Fin de mes
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = next_month - timedelta(days=1)
    
    # Préstamos en el periodo
    prestamos_qs = Prestamos.objects.filter(
        fecha_prestamo__date__range=[start_date, end_date]
    )
    total_prestamos = prestamos_qs.count()
    
    # Devoluciones en el periodo
    devoluciones_qs = DetallePrestamo.objects.filter(
        fecha_devolucion_real__date__range=[start_date, end_date]
    )
    total_devoluciones = devoluciones_qs.count()
    
    # 1. Devoluciones a tiempo vs tardías
    devoluciones_tardias = devoluciones_qs.filter(
        fecha_devolucion_real__date__gt=F('fecha_vencimiento')
    ).count()
    
    devoluciones_a_tiempo = total_devoluciones - devoluciones_tardias
    
    porc_a_tiempo = round((devoluciones_a_tiempo / total_devoluciones * 100), 1) if total_devoluciones > 0 else 0
    porc_tardias = round((devoluciones_tardias / total_devoluciones * 100), 1) if total_devoluciones > 0 else 0
    
    # 2. Estadísticas por Tipo de Documento (Libro vs Tesis)
    stats_por_tipo = devoluciones_qs.values(
        'id_ejemplar__id_documento__id_tipo_documento__nombre_tipo'
    ).annotate(
        total=Count('id_detalle_prestamo'),
        tardias=Count(Case(
            When(fecha_devolucion_real__date__gt=F('fecha_vencimiento'), then=1),
            output_field=IntegerField()
        ))
    )
    
    stats_tipo_list = []
    for item in stats_por_tipo:
        total = item['total']
        tardias = item['tardias']
        a_tiempo = total - tardias
        stats_tipo_list.append({
            'tipo': item['id_ejemplar__id_documento__id_tipo_documento__nombre_tipo'],
            'total': total,
            'a_tiempo': a_tiempo,
            'tardias': tardias,
            'porc_a_tiempo': round((a_tiempo / total * 100), 1) if total > 0 else 0,
            'porc_tardias': round((tardias / total * 100), 1) if total > 0 else 0
        })

    # 3. Usuarios Puntuales vs Impuntuales (basado en devoluciones del periodo)
    usuarios_actividad = devoluciones_qs.values(
        'id_prestamo__id_usuario__id_usuario',
        'id_prestamo__id_usuario__nombre',
        'id_prestamo__id_usuario__apellido'
    ).annotate(
        total_dev=Count('id_detalle_prestamo'),
        total_tardias=Count(Case(
            When(fecha_devolucion_real__date__gt=F('fecha_vencimiento'), then=1),
            output_field=IntegerField()
        ))
    )
    
    usuarios_puntuales = []
    usuarios_impuntuales = []
    
    for u in usuarios_actividad:
        tardias = u['total_tardias']
        total = u['total_dev']
        user_data = {
            'nombre': f"{u['id_prestamo__id_usuario__nombre']} {u['id_prestamo__id_usuario__apellido']}",
            'total': total,
            'tardias': tardias,
            'porc_tardanza': round((tardias / total * 100), 1)
        }
        
        if tardias == 0:
            usuarios_puntuales.append(user_data)
        else:
            usuarios_impuntuales.append(user_data)
            
    # Ordenar por relevancia
    usuarios_puntuales.sort(key=lambda x: x['total'], reverse=True)
    usuarios_impuntuales.sort(key=lambda x: x['tardias'], reverse=True)

    # Libros más prestados
    detalles_prestados = DetallePrestamo.objects.filter(
        id_prestamo__fecha_prestamo__date__range=[start_date, end_date]
    )
    
    top_libros = detalles_prestados.values(
        'id_ejemplar__id_documento__titulo'
    ).annotate(
        total=Count('id_ejemplar__id_documento')
    ).order_by('-total')[:5]
    
    top_libros_list = []
    for item in top_libros:
        top_libros_list.append({
            'titulo': item['id_ejemplar__id_documento__titulo'],
            'total': item['total']
        })

    # Usuarios más activos
    top_usuarios = prestamos_qs.values(
        'id_usuario__nombre', 'id_usuario__apellido'
    ).annotate(
        total=Count('id_usuario')
    ).order_by('-total')[:5]
    
    top_usuarios_list = []
    for item in top_usuarios:
        top_usuarios_list.append({
            'nombre': f"{item['id_usuario__nombre']} {item['id_usuario__apellido']}",
            'total': item['total']
        })

    context = {
        'active_page': 'reportes',
        'periodo': periodo,
        'start_date': start_date,
        'end_date': end_date,
        'total_prestamos': total_prestamos,
        'total_devoluciones': total_devoluciones,
        'top_libros': top_libros_list,
        'top_usuarios': top_usuarios_list,
        # Nuevos datos
        'devoluciones_a_tiempo': devoluciones_a_tiempo,
        'devoluciones_tardias': devoluciones_tardias,
        'porc_a_tiempo': porc_a_tiempo,
        'porc_tardias': porc_tardias,
        'stats_tipo_list': stats_tipo_list,
        'usuarios_puntuales': usuarios_puntuales,
        'usuarios_impuntuales': usuarios_impuntuales,
    }
    return render(request, 'reportes.html', context)
