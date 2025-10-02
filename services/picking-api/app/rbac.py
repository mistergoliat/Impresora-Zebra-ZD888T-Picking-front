from fastapi import status

from .errors import api_error
from .models import User

ROLE_HIERARCHY = {
    "operator": 0,
    "supervisor": 1,
    "admin": 2,
}


def require_role(user: User, role: str) -> None:
    required = ROLE_HIERARCHY.get(role)
    current = ROLE_HIERARCHY.get(user.role)
    if required is None:
        raise api_error(status.HTTP_403_FORBIDDEN, "auth.invalid_role", "Rol requerido inválido")
    if current is None or current < required:
        raise api_error(status.HTTP_403_FORBIDDEN, "auth.unauthorized", "No autorizado")
