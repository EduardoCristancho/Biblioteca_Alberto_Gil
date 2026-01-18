import os
import pymysql
from dotenv import load_dotenv

load_dotenv()


class ExternalUserClient:
    """Cliente para consultar usuarios en la base de datos externa (MySQL/TiDB)"""
    
    @staticmethod
    def _get_connection():
        """Establece conexión con la BD externa"""
        try:
            connection = pymysql.connect(
                host=os.getenv('DB_HOST'),
                port=int(os.getenv('DB_PORT', 4000)),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                database=os.getenv('DB_NAME'),
                ssl={'ssl': True} if os.getenv('DB_SSLMODE', 'true').lower() == 'true' else None,
                connect_timeout=10,
                charset='utf8mb4'
            )
            return connection
        except Exception as e:
            print(f"Error conectando a BD externa: {e}")
            return None

    @staticmethod
    def exists(user_id: int) -> bool:
        """Verifica si un usuario existe en la BD externa"""
        connection = ExternalUserClient._get_connection()
        if not connection:
            return False
        
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id_usuario FROM usuarios WHERE id_usuario = %s", (user_id,))
                result = cursor.fetchone()
                return result is not None
        except Exception as e:
            print(f"Error verificando usuario {user_id}: {e}")
            return False
        finally:
            connection.close()

    @staticmethod
    def fetch(user_id: int):
        """Obtiene los datos de un usuario desde la BD externa"""
        connection = ExternalUserClient._get_connection()
        if not connection:
            return None
        
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                query = """
                    SELECT 
                        u.id_usuario as id,
                        u.nombre,
                        u.apellido,
                        u.email,
                        u.id_rol as rol
                    FROM usuarios u
                    WHERE u.id_usuario = %s
                """
                cursor.execute(query, (user_id,))
                result = cursor.fetchone()
                
                if result:
                    return {
                        'id': result['id'],
                        'username': f"user{result['id']}",
                        'nombre': result['nombre'] or '',
                        'apellido': result['apellido'] or '',
                        'email': result.get('email'),
                        'rol': result.get('rol'),
                    }
                return None
        except Exception as e:
            print(f"Error obteniendo usuario {user_id}: {e}")
            return None
        finally:
            connection.close()
    
    @staticmethod
    def search(term: str, limit: int = 20):
        """Busca usuarios por ID, nombre o apellido en la BD externa"""
        connection = ExternalUserClient._get_connection()
        if not connection:
            return []
        
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                # Si el término es numérico, buscar por ID
                if term.isdigit():
                    query = """
                        SELECT id_usuario, nombre, apellido, email
                        FROM usuarios
                        WHERE id_usuario = %s
                        LIMIT %s
                    """
                    cursor.execute(query, (int(term), limit))
                else:
                    # Buscar por nombre o apellido
                    query = """
                        SELECT id_usuario, nombre, apellido, email
                        FROM usuarios
                        WHERE nombre LIKE %s OR apellido LIKE %s
                        ORDER BY nombre, apellido
                        LIMIT %s
                    """
                    search_term = f"%{term}%"
                    cursor.execute(query, (search_term, search_term, limit))
                
                results = cursor.fetchall()
                return [
                    {
                        'id_usuario': r['id_usuario'],
                        'nombre': r['nombre'] or '',
                        'apellido': r['apellido'] or '',
                        'email': r.get('email'),
                    }
                    for r in results
                ]
        except Exception as e:
            print(f"Error buscando usuarios con término '{term}': {e}")
            return []
        finally:
            connection.close()
