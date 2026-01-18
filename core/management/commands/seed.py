from datetime import timedelta
import random

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password

from core.models import (
    Autores,
    Carreras,
    DetallePrestamo,
    Documentos,
    DocumentoAcademico,
    DocumentoAutores,
    Ejemplares,
    EstadosEjemplar,
    LibroDetalle,
    Prestamos,
    Roles,
    TipoDocumento,
    Ubicaciones,
    Usuarios,
)


class Command(BaseCommand):
    help = 'Carga datos de ejemplo (SQLite) para Biblioteca: catálogos, 30+ documentos, 20 usuarios y 15 préstamos.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Borra datos de dominio antes de cargar (no toca auth_user).')

    def handle(self, *args, **options):
        reset = bool(options.get('reset'))

        with transaction.atomic():
            if reset:
                # Borrado en orden por FKs
                DetallePrestamo.objects.all().delete()
                Prestamos.objects.all().delete()
                Ejemplares.objects.all().delete()
                DocumentoAcademico.objects.all().delete()
                LibroDetalle.objects.all().delete()
                DocumentoAutores.objects.all().delete()
                Documentos.objects.all().delete()
                Autores.objects.all().delete()
                Usuarios.objects.all().delete()
                Ubicaciones.objects.all().delete()
                Carreras.objects.all().delete()
                TipoDocumento.objects.all().delete()
                EstadosEjemplar.objects.all().delete()
                Roles.objects.all().delete()

            self._seed_catalogs()
            self._seed_autores()
            self._seed_documentos_y_ejemplares()
            self._seed_usuarios()
            self._seed_prestamos()
            self._seed_auth_users()

        self.stdout.write(self.style.SUCCESS('Seed completado.'))

    def _seed_catalogs(self):
        Roles.objects.get_or_create(id_rol=1, defaults={'nombre_rol': 'Admin'})
        Roles.objects.get_or_create(id_rol=2, defaults={'nombre_rol': 'Estudiante'})
        Roles.objects.get_or_create(id_rol=3, defaults={'nombre_rol': 'Profesor'})

        TipoDocumento.objects.get_or_create(id_tipo_documento=1, defaults={'nombre_tipo': 'Libro'})
        TipoDocumento.objects.get_or_create(id_tipo_documento=2, defaults={'nombre_tipo': 'Tesis'})

        EstadosEjemplar.objects.get_or_create(id_estado_ejemplar=1, defaults={'nombre_estado': 'DISPONIBLE'})
        EstadosEjemplar.objects.get_or_create(id_estado_ejemplar=2, defaults={'nombre_estado': 'PRESTADO'})
        EstadosEjemplar.objects.get_or_create(id_estado_ejemplar=3, defaults={'nombre_estado': 'ELIMINADO'})

        if not Carreras.objects.exists():
            carreras = [
                'Ingeniería de Sistemas',
                'Ingeniería Industrial',
                'Administración',
                'Contaduría',
                'Educación',
                'Derecho',
            ]
            for i, c in enumerate(carreras, start=1):
                Carreras.objects.create(id_carrera=i, nombre_carrera=c)

        if not Ubicaciones.objects.exists():
            ubicaciones = [
                ('A', '1', 'Pasillo A · Estante 1'),
                ('A', '2', 'Pasillo A · Estante 2'),
                ('B', '1', 'Pasillo B · Estante 1'),
                ('B', '2', 'Pasillo B · Estante 2'),
                ('C', '1', 'Pasillo C · Estante 1'),
                ('C', '2', 'Pasillo C · Estante 2'),
            ]
            for i, (p, e, d) in enumerate(ubicaciones, start=1):
                Ubicaciones.objects.create(id_ubicacion=i, pasillo=p, estante=e, descripcion_completa=d)

    def _seed_autores(self):
        if Autores.objects.count() >= 15:
            return
        autores = [
            ('María', 'González'),
            ('Carlos', 'Rodríguez'),
            ('Ana', 'López'),
            ('Pedro', 'Martín'),
            ('Elena', 'Jiménez'),
            ('José', 'Pérez'),
            ('Luis', 'Fernández'),
            ('Carmen', 'Sánchez'),
            ('Jorge', 'Ramírez'),
            ('Paula', 'Torres'),
            ('Miguel', 'Castillo'),
            ('Daniela', 'Vargas'),
            ('Sofía', 'Mendoza'),
            ('Andrés', 'Rojas'),
            ('Valentina', 'Suárez'),
        ]
        for nombre, apellido in autores:
            Autores.objects.get_or_create(nombre=nombre, apellido=apellido)

    def _seed_documentos_y_ejemplares(self):
        if Documentos.objects.count() >= 30:
            return

        tipo_libro = TipoDocumento.objects.get(id_tipo_documento=1)
        tipo_tesis = TipoDocumento.objects.get(id_tipo_documento=2)

        areas = [
            'Programación',
            'Bases de Datos',
            'Redes',
            'Ingeniería de Software',
            'Sistemas Operativos',
            'Inteligencia Artificial',
            'Seguridad Informática',
            'Metodología de la Investigación',
        ]
        tutores = [
            'Dr. José Gil Alfonzo',
            'Dra. Mariana Ortega',
            'Ing. Luis Herrera',
            'MSc. Carmen Salazar',
        ]

        titulos_libros = [
            'Introducción a Python para PSM',
            'Estructuras de Datos y Algoritmos',
            'Bases de Datos con SQLite',
            'Arquitectura de Software',
            'Redes de Computadoras I',
            'Sistemas Operativos Modernos',
            'Criptografía Aplicada',
            'Desarrollo Web con Django',
            'Ingeniería de Requisitos',
            'Patrones de Diseño',
            'Testing y Calidad de Software',
            'Gestión de Proyectos TI',
            'Fundamentos de IA',
            'Machine Learning Básico',
            'Seguridad en Aplicaciones Web',
            'Análisis de Sistemas',
        ]

        titulos_tesis = [
            'Sistema de Gestión Bibliotecaria para PSM',
            'Modelo de Predicción de Demanda de Préstamos',
            'Optimización de Inventario Bibliográfico',
            'Análisis de Seguridad en Sistemas Académicos',
            'Plataforma de Recomendación de Lecturas',
            'Digitalización y Catalogación de Tesis',
            'Automatización de Reportes Bibliotecarios',
            'Control de Préstamos con Notificaciones',
            'Migración de BD Online a SQLite Local',
            'Dashboard Analítico para Biblioteca Universitaria',
            'Sistema de Gestión de Usuarios Estudiante/Docente',
            'Evaluación de Rendimiento en Django + SQLite',
            'Diseño de API REST para Biblioteca',
            'Gestión de Roles y Permisos en Django',
        ]

        carreras = list(Carreras.objects.all())
        ubicaciones = list(Ubicaciones.objects.all())
        estado_disp = EstadosEjemplar.objects.get(nombre_estado__iexact='DISPONIBLE')

        def pick_autores():
            a = list(Autores.objects.order_by('?')[: random.choice([1, 2])])
            return a

        # Crear libros
        for i, titulo in enumerate(titulos_libros, start=1):
            carrera = random.choice(carreras)
            doc = Documentos.objects.create(
                titulo=titulo,
                codigo_cota=None,
                fecha_publicacion=timezone.now().date() - timedelta(days=random.randint(365, 365 * 8)),
                id_tipo_documento=tipo_libro,
                id_carrera=carrera,
            )
            LibroDetalle.objects.create(id_documento=doc, area_de_conocimiento=random.choice(areas))
            for au in pick_autores():
                DocumentoAutores.objects.create(id_documento=doc, id_autor=au)

            # 1-3 ejemplares
            for n in range(random.randint(1, 3)):
                ub = random.choice(ubicaciones)
                Ejemplares.objects.create(
                    id_documento=doc,
                    id_ubicacion=ub,
                    tomo=str(random.choice([1, 1, 1, 2, 3])),
                    unidad_fisica=1,
                    id_estado_ejemplar=estado_disp,
                    codigo_cota=f'PSM-{doc.id_documento:04d}-{n+1}',
                )

        # Crear tesis
        for i, titulo in enumerate(titulos_tesis, start=1):
            carrera = random.choice(carreras)
            doc = Documentos.objects.create(
                titulo=titulo,
                codigo_cota=None,
                fecha_publicacion=timezone.now().date() - timedelta(days=random.randint(30, 365 * 5)),
                id_tipo_documento=tipo_tesis,
                id_carrera=carrera,
            )
            DocumentoAcademico.objects.create(id_documento=doc, tutor_academico=random.choice(tutores))
            for au in pick_autores():
                DocumentoAutores.objects.create(id_documento=doc, id_autor=au)

            # 1-2 ejemplares
            for n in range(random.randint(1, 2)):
                ub = random.choice(ubicaciones)
                Ejemplares.objects.create(
                    id_documento=doc,
                    id_ubicacion=ub,
                    tomo=str(random.choice([1, 1, 2])),
                    unidad_fisica=1,
                    id_estado_ejemplar=estado_disp,
                    codigo_cota=f'TESIS-{doc.id_documento:04d}-{n+1}',
                )

    def _seed_usuarios(self):
        if Usuarios.objects.count() >= 20:
            return

        rol_admin = Roles.objects.get(nombre_rol__iexact='Admin')
        rol_est = Roles.objects.get(nombre_rol__iexact='Estudiante')
        rol_prof = Roles.objects.get(nombre_rol__iexact='Profesor')

        base = [
            ('Admin', 'Biblioteca', 'admin@psm.edu', rol_admin, 1001, 'admin123'),
            ('Juan', 'Pérez', 'juan.perez@psm.edu', rol_est, 2001, 'psm#123'),
            ('María', 'Rivas', 'maria.rivas@psm.edu', rol_est, 2002, 'psm#123'),
            ('Carlos', 'Soto', 'carlos.soto@psm.edu', rol_est, 2003, 'psm#123'),
            ('Laura', 'Mora', 'laura.mora@psm.edu', rol_est, 2004, 'psm#123'),
            ('Luis', 'Herrera', 'luis.herrera@psm.edu', rol_prof, 3001, 'psm#123'),
            ('Carmen', 'Salazar', 'carmen.salazar@psm.edu', rol_prof, 3002, 'psm#123'),
        ]

        # Completar hasta 20
        nombres = ['Andrea', 'Diego', 'Sofía', 'Miguel', 'Paola', 'José', 'Valentina', 'Andrés', 'Gabriela', 'Ricardo', 'Elena', 'Pedro', 'Daniela']
        apellidos = ['García', 'Rodríguez', 'López', 'Martínez', 'Sánchez', 'Torres', 'Ramírez', 'Vargas', 'Castillo']

        items = list(base)
        next_id = 2005
        while len(items) < 20:
            if len(items) % 5 == 0:
                rol = rol_prof
                uid = 3000 + (len(items) - 6)
            else:
                rol = rol_est
                uid = next_id
                next_id += 1
            n = random.choice(nombres)
            a = random.choice(apellidos)
            email = f'{n.lower()}.{a.lower()}{uid}@psm.edu'
            items.append((n, a, email, rol, uid, 'psm#123'))

        for nombre, apellido, email, rol, uid, pwd in items:
            Usuarios.objects.get_or_create(
                id_usuario=uid,
                defaults={
                    'nombre': nombre,
                    'apellido': apellido,
                    'email': email,
                    'password': make_password(pwd),
                    'id_rol': rol,
                }
            )

    def _seed_prestamos(self):
        if Prestamos.objects.count() >= 15:
            return

        usuarios = list(Usuarios.objects.exclude(id_rol__nombre_rol__iexact='Admin'))
        ejemplares = list(Ejemplares.objects.all())
        if not usuarios or not ejemplares:
            return

        now = timezone.now()

        # Crear 10 activos/vencidos (fecha_devolucion_real NULL)
        for i in range(10):
            u = random.choice(usuarios)
            fecha_p = now - timedelta(days=random.randint(1, 20))
            prestamo = Prestamos.objects.create(id_usuario=u, fecha_prestamo=fecha_p, observacion='Préstamo de prueba')
            due = (fecha_p.date() + timedelta(days=random.choice([7, 10, 14])))

            # 1-2 ejemplares
            picks = random.sample(ejemplares, k=random.choice([1, 2]))
            for ej in picks:
                DetallePrestamo.objects.create(
                    id_prestamo=prestamo,
                    id_ejemplar=ej,
                    fecha_vencimiento=due,
                    fecha_devolucion_real=None,
                )

        # Crear 5 concluidos
        for i in range(5):
            u = random.choice(usuarios)
            fecha_p = now - timedelta(days=random.randint(10, 60))
            prestamo = Prestamos.objects.create(id_usuario=u, fecha_prestamo=fecha_p, observacion='Concluido')
            due = (fecha_p.date() + timedelta(days=10))
            picks = random.sample(ejemplares, k=1)
            for ej in picks:
                DetallePrestamo.objects.create(
                    id_prestamo=prestamo,
                    id_ejemplar=ej,
                    fecha_vencimiento=due,
                    fecha_devolucion_real=fecha_p + timedelta(days=random.randint(1, 12)),
                )

    def _seed_auth_users(self):
        # Crear usuarios en auth_user solo para acceso al panel admin/login futuro.
        # No sobrescribimos si ya existen.
        for u in Usuarios.objects.all():
            if User.objects.filter(id=u.id_usuario).exists():
                continue
            username = u.email or str(u.id_usuario)
            auth_user = User.objects.create(
                id=u.id_usuario,
                username=username,
                first_name=u.nombre,
                last_name=u.apellido,
                is_active=True,
            )
            if u.password:
                auth_user.password = u.password
                auth_user.save(update_fields=['password'])
