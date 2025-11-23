# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255)
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class AuthUser(models.Model):
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.IntegerField()
    username = models.CharField(unique=True, max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.CharField(max_length=254)
    is_staff = models.IntegerField()
    is_active = models.IntegerField()
    date_joined = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'auth_user'


class AuthUserGroups(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_groups'
        unique_together = (('user', 'group'),)


class AuthUserUserPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_user_permissions'
        unique_together = (('user', 'permission'),)


class Autores(models.Model):
    id_autor = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'autores'


class Carreras(models.Model):
    id_carrera = models.AutoField(primary_key=True)
    nombre_carrera = models.CharField(max_length=150)

    class Meta:
        managed = False
        db_table = 'carreras'


class DetallePrestamo(models.Model):
    id_detalle_prestamo = models.AutoField(primary_key=True)
    id_prestamo = models.ForeignKey('Prestamos', models.DO_NOTHING, db_column='id_prestamo')
    id_ejemplar = models.ForeignKey('Ejemplares', models.DO_NOTHING, db_column='id_ejemplar')
    fecha_vencimiento = models.DateField()
    fecha_devolucion_real = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'detalle_prestamo'


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.PositiveSmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100)
    model = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40)
    session_data = models.TextField()
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'


class DocumentoAcademico(models.Model):
    id_documento = models.OneToOneField('Documentos', models.DO_NOTHING, db_column='id_documento', primary_key=True)
    tutor_academico = models.CharField(max_length=150, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'documento_academico'


class DocumentoAutores(models.Model):
    id_documento_autor = models.AutoField(primary_key=True)
    id_documento = models.ForeignKey('Documentos', models.DO_NOTHING, db_column='id_documento')
    id_autor = models.ForeignKey(Autores, models.DO_NOTHING, db_column='id_autor')

    class Meta:
        managed = False
        db_table = 'documento_autores'


class Documentos(models.Model):
    id_documento = models.AutoField(primary_key=True)
    titulo = models.CharField(max_length=255)
    codigo_cota = models.CharField(unique=True, max_length=50, blank=True, null=True)
    fecha_publicacion = models.DateField(blank=True, null=True)
    id_tipo_documento = models.ForeignKey('TipoDocumento', models.DO_NOTHING, db_column='id_tipo_documento')
    id_carrera = models.ForeignKey(Carreras, models.DO_NOTHING, db_column='id_carrera', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'documentos'


class Ejemplares(models.Model):
    id_ejemplar = models.AutoField(primary_key=True)
    id_documento = models.ForeignKey(Documentos, models.DO_NOTHING, db_column='id_documento')
    id_ubicacion = models.ForeignKey('Ubicaciones', models.DO_NOTHING, db_column='id_ubicacion', blank=True, null=True)
    tomo = models.CharField(max_length=50, blank=True, null=True)
    unidad_fisica = models.IntegerField()
    id_estado_ejemplar = models.ForeignKey('EstadosEjemplar', models.DO_NOTHING, db_column='id_estado_ejemplar')
    codigo_cota = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ejemplares'


class EstadosEjemplar(models.Model):
    id_estado_ejemplar = models.AutoField(primary_key=True)
    nombre_estado = models.CharField(max_length=50)

    class Meta:
        managed = False
        db_table = 'estados_ejemplar'


class InformePasantiaDetalle(models.Model):
    id_documento = models.OneToOneField(Documentos, models.DO_NOTHING, db_column='id_documento', primary_key=True)
    autor_academico = models.CharField(max_length=150, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'informe_pasantia_detalle'


class LibroDetalle(models.Model):
    id_documento = models.OneToOneField(Documentos, models.DO_NOTHING, db_column='id_documento', primary_key=True)
    area_de_conocimiento = models.CharField(max_length=150, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'libro_detalle'


class Prestamos(models.Model):
    id_prestamo = models.AutoField(primary_key=True)
    id_usuario = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='id_usuario')
    fecha_prestamo = models.DateTimeField(blank=True, null=True)
    observacion = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'prestamos'


class Roles(models.Model):
    id_rol = models.AutoField(primary_key=True)
    nombre_rol = models.CharField(max_length=50)

    class Meta:
        managed = False
        db_table = 'roles'


class TipoDocumento(models.Model):
    id_tipo_documento = models.AutoField(primary_key=True)
    nombre_tipo = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'tipo_documento'


class Ubicaciones(models.Model):
    id_ubicacion = models.AutoField(primary_key=True)
    pasillo = models.CharField(max_length=50, blank=True, null=True)
    estante = models.CharField(max_length=50, blank=True, null=True)
    descripcion_completa = models.CharField(max_length=150, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ubicaciones'


class Usuarios(models.Model):
    id_usuario = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    email = models.CharField(unique=True, max_length=150, blank=True, null=True)
    password = models.CharField(max_length=128, blank=True, null=True)
    id_rol = models.ForeignKey(Roles, models.DO_NOTHING, db_column='id_rol')

    class Meta:
        managed = False
        db_table = 'usuarios'
