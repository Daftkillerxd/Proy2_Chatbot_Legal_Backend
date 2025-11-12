# usuarios_service.py
from typing import Optional
from supabase import Client
from conexion import obtener_cliente

supabase: Client = obtener_cliente()


def obtener_o_crear_usuario(nombre: str, email: str, user_id: Optional[str] = None) -> str:
    """
    Si viene user_id lo devuelve tal cual.
    Si no viene, crea un usuario nuevo con nombre y email y devuelve su id.
    """
    if user_id:
        return user_id

    if not email:
        # aquí puedes lanzar error o poner un email genérico
        email = "anon@chatbotlegal.local"

    res = (
        supabase
        .table("users")
        .insert({
            "nombre": nombre,
            "email": email
        })
        .execute()
    )
    return res.data[0]["id"]
