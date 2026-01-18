# Sistema de Autenticación y Búsqueda de Usuarios

## Descripción General

Este sistema implementa una arquitectura de dos bases de datos:

- **BD Interna (SQLite)**: Base de datos local para usuarios registrados y operaciones del sistema
- **BD Externa (MySQL/TiDB)**: Base de datos de la universidad con información de estudiantes y profesores

## Flujos Implementados

### 1. Login (Autenticación)

**Ubicación**: `core/views.py` → `LoginView`

**Flujo**:

1. Usuario ingresa ID y contraseña
2. Sistema busca **únicamente en BD interna**
3. Si existe y la contraseña es correcta → acceso permitido
4. Si no existe o contraseña incorrecta → acceso denegado

**Nota**: Los usuarios externos NO pueden hacer login hasta que sean registrados en la BD interna (esto ocurre automáticamente al crear un préstamo).

### 2. Búsqueda de Usuarios (Sugerencias)

**Ubicación**: `core/views.py` → `UsuarioSugerenciaView`

**Endpoint**: `GET /api/sugerencias/usuarios?search=<término>`

**Flujo**:

1. Buscar en **BD interna** por ID, nombre o apellido
2. Si hay menos de 5 resultados → buscar también en **BD externa**
3. Combinar resultados (internos primero, luego externos)
4. Retornar hasta 20 resultados totales

**Ejemplo de uso**:

```javascript
// Buscar por ID
fetch("/api/sugerencias/usuarios?search=12345");

// Buscar por nombre
fetch("/api/sugerencias/usuarios?search=Juan");
```

### 3. Registro de Préstamos

**Ubicación**: `core/views.py` → `PrestamoListCreateView.post()`

**Endpoint**: `POST /api/prestamo`

**Flujo**:

1. Recibir `id_user` en el payload
2. Buscar usuario en **BD interna**
3. Si NO existe:
   - Consultar **BD externa** usando `ExternalUserClient.fetch()`
   - Si existe en BD externa → **registrarlo automáticamente** en BD interna
   - Si NO existe en BD externa → retornar error 404
4. Validar disponibilidad de ejemplares
5. Crear préstamo y detalles

**Ejemplo de payload**:

```json
{
  "id_user": 12345,
  "fecha_vencimiento": "2025-12-31",
  "ejemplares": [{ "id_ejemplar": 1 }, { "id_ejemplar": 2 }]
}
```

## Cliente de BD Externa

**Ubicación**: `core/external.py` → `ExternalUserClient`

### Métodos Disponibles

#### `exists(user_id: int) -> bool`

Verifica si un usuario existe en la BD externa.

#### `fetch(user_id: int) -> dict | None`

Obtiene los datos completos de un usuario por ID.

**Retorna**:

```python
{
    'id': 12345,
    'username': 'user12345',
    'nombre': 'Juan',
    'apellido': 'Pérez',
    'email': 'juan.perez@universidad.edu',
    'rol': 2  # ID del rol
}
```

#### `search(term: str, limit: int = 20) -> list`

Busca usuarios por ID, nombre o apellido.

**Retorna**:

```python
[
    {
        'id_usuario': 12345,
        'nombre': 'Juan',
        'apellido': 'Pérez',
        'email': 'juan.perez@universidad.edu'
    },
    ...
]
```

## Configuración

### Variables de Entorno (.env)

```env
# BD Externa (MySQL/TiDB Cloud)
DB_ENGINE=mysql
DB_HOST=gateway01.us-east-1.prod.aws.tidbcloud.com
DB_PORT=4000
DB_NAME=psm_biblioteca
DB_USER=ZjQtQcTAGe8QSq4.root
DB_PASSWORD=Dl2ysFP4ih3BRb8y
DB_SSLMODE=true
```

### Dependencias

Asegúrate de tener instalado:

```bash
pip install PyMySQL==1.1.1
```

## Manejo de Errores

### Errores de Conexión

Si la BD externa no está disponible:

- La búsqueda de sugerencias solo retornará resultados de BD interna
- El registro de préstamos retornará error 500 con mensaje descriptivo

### Usuario No Encontrado

- **Login**: "Credenciales inválidas" (no revela si el usuario existe)
- **Préstamo**: "El usuario no existe. Verifique el ID ingresado."

### Logs

Los errores se registran en el logger de Django:

```python
logger.error(f"Error consultando BD externa: {e}")
```

## Seguridad

1. **Contraseñas**: Los usuarios externos NO tienen contraseña en BD interna (campo `password=None`)
2. **SSL**: La conexión a BD externa usa SSL/TLS
3. **Timeout**: Conexión con timeout de 10 segundos para evitar bloqueos
4. **Validación**: Todos los IDs se validan antes de consultar la BD

## Testing

### Probar Búsqueda de Usuarios

```bash
# Iniciar servidor
python manage.py runserver

# En otra terminal, probar endpoint
curl "http://localhost:8000/api/sugerencias/usuarios?search=12345"
```

### Probar Registro de Préstamo con Usuario Externo

```bash
curl -X POST http://localhost:8000/api/prestamo \
  -H "Content-Type: application/json" \
  -d '{
    "id_user": 12345,
    "fecha_vencimiento": "2025-12-31",
    "ejemplares": [{"id_ejemplar": 1}]
  }'
```

## Diagrama de Flujo

```
┌─────────────────┐
│  Usuario busca  │
│   en préstamo   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  BD Interna?    │◄─── Primera búsqueda
└────┬───────┬────┘
     │ Sí    │ No
     │       │
     │       ▼
     │  ┌─────────────────┐
     │  │  BD Externa?    │◄─── Fallback
     │  └────┬───────┬────┘
     │       │ Sí    │ No
     │       │       │
     │       ▼       ▼
     │  ┌─────────┐ ┌──────────┐
     │  │Registrar│ │Error 404 │
     │  │en BD    │ └──────────┘
     │  │Interna  │
     │  └────┬────┘
     │       │
     ▼       ▼
┌─────────────────┐
│ Crear Préstamo  │
└─────────────────┘
```

## Notas Importantes

1. **Sincronización**: Los usuarios externos se registran automáticamente en BD interna al crear un préstamo
2. **Roles**: Si el rol del usuario externo no existe en BD interna, se asigna el primer rol disponible
3. **Performance**: La búsqueda en BD externa solo se activa si hay menos de 5 resultados en BD interna
4. **Caché**: No hay caché implementado, cada consulta va directo a la BD

## Mantenimiento

### Verificar Conexión a BD Externa

```python
from core.external import ExternalUserClient

# Probar conexión
connection = ExternalUserClient._get_connection()
if connection:
    print("✓ Conexión exitosa")
    connection.close()
else:
    print("✗ Error de conexión")
```

### Limpiar Usuarios Externos Registrados

```python
# En Django shell
from core.models import Usuarios

# Ver usuarios sin contraseña (externos)
externos = Usuarios.objects.filter(password__isnull=True)
print(f"Usuarios externos: {externos.count()}")

# Opcional: eliminar usuarios externos
# externos.delete()
```
