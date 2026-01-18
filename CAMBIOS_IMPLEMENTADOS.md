# Cambios Implementados - Sistema de Usuarios con BD Externa

## Resumen

Se implementó un sistema de autenticación y búsqueda de usuarios que integra dos bases de datos:

- **BD Interna (SQLite)**: Usuarios registrados localmente
- **BD Externa (MySQL/TiDB)**: Base de datos de la universidad

## Archivos Modificados

### 1. `core/external.py` ✅

**Cambios**:

- Reemplazada la implementación mock con conexión real a MySQL/TiDB
- Agregado método `_get_connection()` para establecer conexión SSL
- Implementado `exists()` para verificar existencia de usuarios
- Implementado `fetch()` para obtener datos completos de un usuario
- Agregado `search()` para búsqueda por ID, nombre o apellido

**Tecnología**: PyMySQL con soporte SSL

### 2. `core/views.py` ✅

**Cambios en `UsuarioSugerenciaView`**:

- Implementada búsqueda con fallback a BD externa
- Primero busca en BD interna
- Si hay menos de 5 resultados, busca también en BD externa
- Combina y retorna hasta 20 resultados totales
- Filtra duplicados entre ambas BDs

**Cambios en `PrestamoListCreateView.post()`**:

- Implementado registro automático de usuarios externos
- Flujo: BD interna → BD externa → registrar → crear préstamo
- Si usuario no existe en ninguna BD, retorna error 404 descriptivo
- Manejo de errores con logging

### 3. `templates/prestamos_registrar.html` ✅

**Cambios**:

- Mejorada estructura HTML con contenedor `.lookup-box`
- Actualizado placeholder del input de búsqueda
- Mejorado JavaScript para mostrar sugerencias en tiempo real
- Agregada confirmación visual al seleccionar usuario
- Reducido umbral de búsqueda de 2 a 1 carácter

## Archivos Creados

### 1. `SISTEMA_USUARIOS.md` 📄

Documentación completa del sistema:

- Descripción de flujos (Login, Búsqueda, Préstamos)
- Referencia de API del `ExternalUserClient`
- Configuración de variables de entorno
- Guía de testing y troubleshooting
- Diagramas de flujo

### 2. `test_external_db.py` 🧪

Script de prueba interactivo:

- Verifica conexión a BD externa
- Prueba búsqueda por ID
- Prueba búsqueda por nombre
- Interfaz interactiva en consola

### 3. `CAMBIOS_IMPLEMENTADOS.md` 📋

Este archivo - resumen de cambios

## Flujos Implementados

### Login (Sin cambios)

```
Usuario ingresa credenciales
    ↓
Buscar SOLO en BD interna
    ↓
¿Existe y contraseña correcta?
    ├─ Sí → Acceso permitido
    └─ No → Acceso denegado
```

### Búsqueda de Usuarios (Nuevo)

```
Usuario escribe en campo de búsqueda
    ↓
Buscar en BD interna
    ↓
¿Menos de 5 resultados?
    ├─ Sí → Buscar también en BD externa
    └─ No → Retornar resultados internos
    ↓
Combinar resultados (sin duplicados)
    ↓
Mostrar hasta 20 sugerencias
```

### Registro de Préstamo (Mejorado)

```
Usuario ingresa ID en formulario de préstamo
    ↓
¿Existe en BD interna?
    ├─ Sí → Continuar con préstamo
    └─ No ↓
        Buscar en BD externa
            ↓
        ¿Existe en BD externa?
            ├─ Sí → Registrar en BD interna → Continuar
            └─ No → Error 404 "Usuario no encontrado"
```

## Configuración Requerida

### Variables de Entorno (.env)

```env
DB_ENGINE=mysql
DB_HOST=gateway01.us-east-1.prod.aws.tidbcloud.com
DB_PORT=4000
DB_NAME=psm_biblioteca
DB_USER=ZjQtQcTAGe8QSq4.root
DB_PASSWORD=Dl2ysFP4ih3BRb8y
DB_SSLMODE=true
```

### Dependencias

Ya incluidas en `requirements.txt`:

- PyMySQL==1.1.1
- python-dotenv==1.0.1

## Testing

### 1. Probar Conexión a BD Externa

```bash
python test_external_db.py
```

### 2. Probar Búsqueda de Usuarios

```bash
# Iniciar servidor
python manage.py runserver

# En navegador, ir a:
http://localhost:8000/api/sugerencias/usuarios?search=Juan
```

### 3. Probar Registro de Préstamo con Usuario Externo

1. Ir a "Registrar Préstamo"
2. Escribir ID de usuario que existe en BD externa pero no en interna
3. Seleccionar libros
4. Confirmar préstamo
5. Verificar que el usuario se registró automáticamente

## Características de Seguridad

✅ Conexión SSL/TLS a BD externa
✅ Timeout de 10 segundos para evitar bloqueos
✅ Validación de IDs antes de consultas
✅ Usuarios externos sin contraseña local (password=None)
✅ Logging de errores para debugging
✅ Manejo de excepciones en todas las operaciones

## Manejo de Errores

| Escenario                       | Comportamiento                            |
| ------------------------------- | ----------------------------------------- |
| BD externa no disponible        | Búsqueda solo retorna resultados internos |
| Usuario no existe en ninguna BD | Error 404 con mensaje descriptivo         |
| Error de conexión en préstamo   | Error 500 con mensaje de reintento        |
| Timeout de conexión             | Falla gracefully después de 10s           |

## Logs

Los errores se registran en el logger de Django:

```python
logger.error(f"Error consultando BD externa: {e}")
logger.info(f"Usuario {user_id} registrado desde BD externa")
```

## Próximos Pasos Sugeridos

1. **Testing en Producción**:
   - Verificar conectividad a BD externa desde servidor de producción
   - Probar con IDs reales de estudiantes/profesores

2. **Optimizaciones Futuras**:
   - Implementar caché para reducir consultas a BD externa
   - Agregar sincronización periódica de usuarios
   - Implementar búsqueda fuzzy para nombres con typos

3. **Monitoreo**:
   - Configurar alertas para errores de conexión a BD externa
   - Monitorear tiempo de respuesta de consultas
   - Trackear cantidad de usuarios registrados automáticamente

## Soporte

Para problemas o preguntas:

1. Revisar `SISTEMA_USUARIOS.md` para documentación detallada
2. Ejecutar `test_external_db.py` para diagnosticar problemas de conexión
3. Verificar logs de Django para errores específicos

---

**Fecha de Implementación**: 2025-01-18
**Versión**: 1.0
**Estado**: ✅ Completado y listo para testing
