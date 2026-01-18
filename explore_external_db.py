#!/usr/bin/env python
"""
Script para explorar la BD externa (SOLO LECTURA)
Uso: python explore_external_db.py
"""

import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'biblioteca.settings')
django.setup()

from core.external import ExternalUserClient


def show_tables():
    """Muestra todas las tablas de la BD externa"""
    print("\n" + "=" * 60)
    print("TABLAS EN LA BASE DE DATOS EXTERNA")
    print("=" * 60)
    
    connection = ExternalUserClient._get_connection()
    if not connection:
        print("✗ No se pudo conectar a la BD externa")
        return False
    
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            
            if tables:
                print(f"\n✓ Se encontraron {len(tables)} tablas:\n")
                for i, (table_name,) in enumerate(tables, 1):
                    print(f"{i:2d}. {table_name}")
                return True
            else:
                print("✗ No se encontraron tablas")
                return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        connection.close()


def describe_table(table_name):
    """Muestra la estructura de una tabla"""
    print(f"\n{'=' * 60}")
    print(f"ESTRUCTURA DE LA TABLA: {table_name}")
    print("=" * 60)
    
    connection = ExternalUserClient._get_connection()
    if not connection:
        print("✗ No se pudo conectar a la BD externa")
        return False
    
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DESCRIBE {table_name}")
            columns = cursor.fetchall()
            
            if columns:
                print(f"\n{'Campo':<30} {'Tipo':<20} {'Null':<8} {'Key':<8}")
                print("-" * 70)
                for col in columns:
                    field, type_, null, key = col[0], col[1], col[2], col[3]
                    print(f"{field:<30} {type_:<20} {null:<8} {key:<8}")
                return True
            else:
                print("✗ No se pudo obtener estructura")
                return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        connection.close()


def count_records(table_name):
    """Cuenta registros en una tabla"""
    connection = ExternalUserClient._get_connection()
    if not connection:
        return None
    
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            return count
    except Exception as e:
        print(f"✗ Error contando registros: {e}")
        return None
    finally:
        connection.close()


def preview_table(table_name, limit=5):
    """Muestra los primeros registros de una tabla"""
    print(f"\n{'=' * 60}")
    print(f"VISTA PREVIA: {table_name} (primeros {limit} registros)")
    print("=" * 60)
    
    connection = ExternalUserClient._get_connection()
    if not connection:
        print("✗ No se pudo conectar a la BD externa")
        return False
    
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
            rows = cursor.fetchall()
            
            # Obtener nombres de columnas
            cursor.execute(f"DESCRIBE {table_name}")
            columns = [col[0] for col in cursor.fetchall()]
            
            if rows:
                # Mostrar encabezados
                print("\n" + " | ".join(f"{col[:15]:<15}" for col in columns))
                print("-" * (len(columns) * 18))
                
                # Mostrar datos
                for row in rows:
                    print(" | ".join(f"{str(val)[:15]:<15}" for val in row))
                
                print(f"\n✓ Mostrando {len(rows)} de {count_records(table_name)} registros totales")
                return True
            else:
                print("✗ La tabla está vacía")
                return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        connection.close()


def execute_query(query):
    """Ejecuta una consulta SELECT personalizada"""
    print(f"\n{'=' * 60}")
    print(f"EJECUTANDO QUERY")
    print("=" * 60)
    print(f"Query: {query}\n")
    
    # Validar que sea solo SELECT (seguridad)
    if not query.strip().upper().startswith('SELECT'):
        print("✗ ERROR: Solo se permiten consultas SELECT")
        return False
    
    connection = ExternalUserClient._get_connection()
    if not connection:
        print("✗ No se pudo conectar a la BD externa")
        return False
    
    try:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()
            
            if rows:
                print(f"✓ Se encontraron {len(rows)} resultados:\n")
                for i, row in enumerate(rows, 1):
                    print(f"{i}. {row}")
                return True
            else:
                print("✗ No se encontraron resultados")
                return False
    except Exception as e:
        print(f"✗ Error ejecutando query: {e}")
        return False
    finally:
        connection.close()


def interactive_menu():
    """Menú interactivo"""
    while True:
        print("\n" + "=" * 60)
        print("EXPLORADOR DE BASE DE DATOS EXTERNA (SOLO LECTURA)")
        print("=" * 60)
        print("\nOpciones:")
        print("1. Ver todas las tablas")
        print("2. Ver estructura de una tabla")
        print("3. Vista previa de una tabla")
        print("4. Contar registros de una tabla")
        print("5. Ejecutar query SELECT personalizado")
        print("6. Buscar usuario por ID")
        print("7. Buscar usuario por nombre")
        print("0. Salir")
        
        choice = input("\nSelecciona una opción: ").strip()
        
        if choice == '1':
            show_tables()
        
        elif choice == '2':
            table = input("Nombre de la tabla: ").strip()
            if table:
                describe_table(table)
        
        elif choice == '3':
            table = input("Nombre de la tabla: ").strip()
            if table:
                limit = input("¿Cuántos registros mostrar? (default: 5): ").strip()
                limit = int(limit) if limit.isdigit() else 5
                preview_table(table, limit)
        
        elif choice == '4':
            table = input("Nombre de la tabla: ").strip()
            if table:
                count = count_records(table)
                if count is not None:
                    print(f"\n✓ La tabla '{table}' tiene {count:,} registros")
        
        elif choice == '5':
            print("\nEjemplo: SELECT * FROM usuarios WHERE id_usuario = 1")
            query = input("Query: ").strip()
            if query:
                execute_query(query)
        
        elif choice == '6':
            user_id = input("ID del usuario: ").strip()
            if user_id.isdigit():
                user = ExternalUserClient.fetch(int(user_id))
                if user:
                    print(f"\n✓ Usuario encontrado:")
                    print(f"  ID: {user['id']}")
                    print(f"  Nombre: {user['nombre']} {user['apellido']}")
                    print(f"  Email: {user.get('email', 'N/A')}")
                    print(f"  Rol: {user.get('rol', 'N/A')}")
                else:
                    print(f"\n✗ Usuario {user_id} no encontrado")
        
        elif choice == '7':
            term = input("Nombre a buscar: ").strip()
            if term:
                results = ExternalUserClient.search(term, limit=20)
                if results:
                    print(f"\n✓ Se encontraron {len(results)} usuarios:\n")
                    for i, u in enumerate(results, 1):
                        print(f"{i:2d}. ID: {u['id_usuario']} - {u['nombre']} {u['apellido']}")
                else:
                    print(f"\n✗ No se encontraron usuarios con '{term}'")
        
        elif choice == '0':
            print("\n👋 ¡Hasta luego!")
            break
        
        else:
            print("\n✗ Opción inválida")


def main():
    """Función principal"""
    print("\n🔍 Explorador de Base de Datos Externa")
    print("⚠️  MODO SOLO LECTURA - No se pueden modificar datos\n")
    
    # Verificar conexión
    connection = ExternalUserClient._get_connection()
    if connection:
        print("✓ Conexión exitosa a BD externa")
        connection.close()
        interactive_menu()
    else:
        print("✗ No se pudo conectar a la BD externa")
        print("\nVerifica las variables de entorno en .env:")
        print("  - DB_HOST")
        print("  - DB_PORT")
        print("  - DB_USER")
        print("  - DB_PASSWORD")
        print("  - DB_NAME")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Exploración interrumpida por el usuario.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
