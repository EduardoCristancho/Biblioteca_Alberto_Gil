class ExternalUserClient:
    @staticmethod
    def exists(user_id: int) -> bool:
        return user_id % 2 == 0

    @staticmethod
    def fetch(user_id: int):
        if not ExternalUserClient.exists(user_id):
            return None
        role = 2 if user_id % 4 == 0 else 3
        return {
            'id': user_id,
            'username': f'user{user_id}',
            'nombre': f'Nombre{user_id}',
            'apellido': f'Apellido{user_id}',
            'rol': role,
        }
