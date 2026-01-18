#!/usr/bin/env python
"""
Script de prueba para verificar la conexión a la BD externa
Uso: python test_external_db.py
"""

import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'biblioteca.settings')
django.setup()

from core.external import ExternalUserClient


def test_connection():
    """Prueba la conexión a la BD externa"""
    print("=" * 60)
    print("PRUEBA DE CONEXIÓN A BASE DE DATOS EXTERNA")
    print("=" * 60)
    
    connection = ExternalUserClient._get_connection()
    if connection:
        print("✓ Conexión exitosa a BD externa")
        connection.close()
        return True
    else:
        print("✗ Error al conectar a BD externa")
        print("\nVerifica las variables de entorno en .env:")
        print("  - DB_HOST")
        print("  - DB_PORT")
        print("  - DB_USER")
        print("  - DB_PASSWORD")
        print("  - DB_NAME")
        return False


def test_search_by_id(user_id):
    """Prueba búsqueda de usuario por ID"""
    print(f"\n{'=' * 60}")
    print(f"BÚSQUEDA POR ID: {user_id}")
    print("=" * 60)
    
    # Verificar existencia
    exists = ExternalUserClient.exists(user_id)
    print(f"¿Existe usuario {user_id}? {exists}")
    
    if exists:
        # Obtener datos completos
        user = ExternalUserClient.fetch(user_id)
        if user:
            print("\nDatos del usuario:")
            print(f"  ID: {user['id']}")
            print(f"  Nombre: {user['nombre']}")
            print(f"  Apellido: {user['apellido']}")
            print(f"  Email: {user.get('email', 'N/A')}")
            print(f"  Rol: {user.get('rol', 'N/A')}")
            return True
        else:
            print("✗ Error al obtener datos del usuario")
            return False
    else:
        print(f"✗ Usuario {user_id} no encontrado en BD externa")
        return False


def test_search_by_name(term):
    """Prueba búsqueda de usuarios por nombre"""
    print(f"\n{'=' * 60}")
    print(f"BÚSQUEDA POR NOMBRE: '{term}'")
    print("=" * 60)
    
    results = ExternalUserClient.search(term, limit=10)
    
    if results:
        print(f"\n✓ Se encontraron {len(results)} resultados:\n")
        for i, user in enumerate(results, 1):
            print(f"{i}. ID: {user['id_usuario']} - {user['nombre']} {user['apellido']}")
            if user.get('email'):
                print(f"   Email: {user['email']}")
        return True
    else:
        print(f"✗ No se encontraron usuarios con el término '{term}'")
        return False


def main():
    """Función principal"""
    print("\n🔍 Iniciando pruebas de BD externa...\n")
    
    # 1. Probar conexión
    if not test_connection():
        print("\n❌ No se pudo conectar a la BD externa. Abortando pruebas.")
        sys.exit(1)
    
    # 2. Probar búsqueda por ID (puedes cambiar estos valores)
    print("\n" + "=" * 60)
    print("PRUEBAS DE BÚSQUEDA")
    print("=" * 60)
    
    # Prueba con IDs de ejemplo (ajusta según tu BD)
    test_ids = [1, 100, 999]
    
    print("\nIngresa un ID de usuario para buscar (o presiona Enter para usar IDs de prueba):")
    user_input = input("ID: ").strip()
    
    if user_input:
        if user_input.isdigit():
            test_search_by_id(int(user_input))
        else:
            print("✗ ID inválido. Debe ser un número.")
    else:
        print("\nProbando con IDs de ejemplo...")
        for test_id in test_ids:
            test_search_by_id(test_id)
            if test_id != test_ids[-1]:
                print("\n" + "-" * 60)
    
    # 3. Probar búsqueda por nombre
    print("\n\nIngresa un nombre para buscar (o presiona Enter para omitir):")
    name_input = input("Nombre: ").strip()
    
    if name_input:
        test_search_by_name(name_input)
    else:
        print("\nPrueba de búsqueda por nombre omitida.")
    
    print("\n" + "=" * 60)
    print("✓ PRUEBAS COMPLETADAS")
    print("=" * 60)
    print("\nSi todas las pruebas fueron exitosas, el sistema está listo para usar.")
    print("Si hubo errores, verifica la configuración en el archivo .env\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Pruebas interrumpidas por el usuario.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
