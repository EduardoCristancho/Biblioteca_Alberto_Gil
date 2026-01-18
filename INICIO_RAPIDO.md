# 🚀 Inicio Rápido - Sistema de Usuarios con BD Externa

## ✅ Verificación Previa

### 1. Verificar Dependencias

```bash
python -c "import pymysql; print('✓ PyMySQL OK')"
python -c "import dotenv; print('✓ python-dotenv OK')"
```

Si falta alguna dependencia:

```bash
pip install -r requirements.txt
```

### 2. Verificar Archivo .env

Asegúrate de que `.env` contenga:

```env
DB_ENGINE=mysql
DB_HOST=gateway01.us-east-1.prod.aws.tidbcloud.com
DB_PORT=4000
DB_NAME=psm_biblioteca
DB_USER=ZjQtQcTAGe8QSq4.root
DB_PASSWORD=Dl2ysFP4ih3BRb8y
DB_SSLMODE=true
```

## 🧪 Pruebas

### Paso 1: Probar Conexión a BD Externa

```bash
python test_external_db.py
```

**Resultado esperado**:

```
✓ Conexión exitosa a BD externa
```

Si falla, verifica:

- Conexión a internet
- Credenciales en `.env`
- Firewall/VPN

### Paso 2: Iniciar Servidor

```bash
python manage.py runserver
```

### Paso 3: Probar Búsqueda de Usuarios

**Opción A - Navegador**:

```
http://localhost:8000/api/sugerencias/usuarios?search=1
```

**Opción B - curl**:

```bash
curl "http://localhost:8000/api/sugerencias/usuarios?search=Juan"
```

**Resultado esperado**: JSON con lista de usuarios

### Paso 4: Probar Registro de Préstamo

1. Ir a: `http://localhost:8000` (hacer login primero)
2. Navegar a "Registrar Préstamo"
3. En el campo "Identificación del Usuario":
   - Escribir un ID que existe en BD externa pero NO en interna
   - Deberías ver sugerencias aparecer
   - Seleccionar el usuario
4. Agregar libros al préstamo
5. Confirmar préstamo

**Resultado esperado**:

- Préstamo creado exitosamente
- Usuario registrado automáticamente en BD interna

## 📊 Verificar Resultados

### Ver Usuarios Registrados Automáticamente

```bash
python manage.py shell
```

```python
from core.models import Usuarios

# Ver usuarios sin contraseña (registrados desde BD externa)
externos = Usuarios.objects.filter(password__isnull=True)
print(f"Usuarios externos registrados: {externos.count()}")

for u in externos:
    print(f"ID: {u.id_usuario} - {u.nombre} {u.apellido}")
```

## 🔍 Troubleshooting

### Error: "No se pudo conectar a BD externa"

**Solución**:

1. Verificar `.env` tiene las credenciales correctas
2. Verificar conexión a internet
3. Probar conexión manual:
   ```bash
   python test_external_db.py
   ```

### Error: "Usuario no encontrado"

**Causa**: El ID no existe ni en BD interna ni externa

**Solución**: Verificar que el ID sea correcto

### Las sugerencias no aparecen

**Solución**:

1. Abrir consola del navegador (F12)
2. Verificar errores en la pestaña "Console"
3. Verificar que el endpoint responda:
   ```
   http://localhost:8000/api/sugerencias/usuarios?search=test
   ```

### Error: "ModuleNotFoundError: No module named 'pymysql'"

**Solución**:

```bash
pip install PyMySQL==1.1.1
```

## 📝 Casos de Uso

### Caso 1: Usuario Nuevo de la Universidad

**Escenario**: Estudiante viene por primera vez a la biblioteca

1. Bibliotecario va a "Registrar Préstamo"
2. Escribe la cédula del estudiante
3. Sistema busca en BD externa y muestra sugerencia
4. Bibliotecario selecciona el usuario
5. Agrega libros y confirma
6. ✅ Usuario queda registrado automáticamente

### Caso 2: Usuario Ya Registrado

**Escenario**: Estudiante que ya tiene préstamos previos

1. Bibliotecario escribe la cédula
2. Sistema encuentra usuario en BD interna inmediatamente
3. Muestra sugerencia con nombre completo
4. Continúa con el préstamo normalmente

### Caso 3: Usuario No Existe

**Escenario**: ID incorrecto o persona externa

1. Bibliotecario escribe ID
2. Sistema busca en BD interna → no existe
3. Sistema busca en BD externa → no existe
4. ❌ Muestra error: "Usuario no encontrado"

## 🎯 Flujo Visual

```
┌─────────────────────────────────────────────┐
│  Bibliotecario escribe ID en formulario    │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
         ┌─────────────────┐
         │ Buscar en BD    │
         │ Interna (local) │
         └────┬────────┬───┘
              │        │
         ¿Existe?      │
              │        │
        ┌─────┘        └─────┐
        │ SÍ                 │ NO
        │                    │
        ▼                    ▼
   ┌─────────┐      ┌──────────────┐
   │ Mostrar │      │ Buscar en BD │
   │ Usuario │      │ Externa      │
   └─────────┘      └──────┬───────┘
                           │
                      ¿Existe?
                           │
                    ┌──────┴──────┐
                    │ SÍ          │ NO
                    │             │
                    ▼             ▼
            ┌──────────────┐  ┌────────┐
            │ Registrar en │  │ Error  │
            │ BD Interna   │  │ 404    │
            └──────┬───────┘  └────────┘
                   │
                   ▼
            ┌──────────────┐
            │ Mostrar      │
            │ Usuario      │
            └──────────────┘
```

## 📚 Documentación Adicional

- **Documentación Completa**: Ver `SISTEMA_USUARIOS.md`
- **Lista de Cambios**: Ver `CAMBIOS_IMPLEMENTADOS.md`
- **Script de Prueba**: Ejecutar `test_external_db.py`

## ✨ Características Implementadas

✅ Búsqueda en tiempo real con sugerencias
✅ Fallback automático a BD externa
✅ Registro automático de usuarios externos
✅ Validación de existencia antes de crear préstamo
✅ Manejo de errores con mensajes descriptivos
✅ Conexión segura SSL/TLS a BD externa
✅ Logging de operaciones para debugging

## 🎉 ¡Listo!

Si todas las pruebas pasaron, el sistema está funcionando correctamente.

**Próximos pasos**:

1. Probar con IDs reales de tu universidad
2. Verificar que los roles se asignen correctamente
3. Monitorear logs para detectar errores

---

**¿Necesitas ayuda?** Revisa la sección de Troubleshooting o consulta `SISTEMA_USUARIOS.md`
