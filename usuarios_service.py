# usuarios_service.py
from conexion import obtener_cliente

supabase = obtener_cliente()

def obtener_o_crear_usuario(nombre: str | None, email: str | None, user_id: str | None):
    """
    Devuelve el id del usuario. Si existe por email, lo reutiliza.
    Si no existe, lo crea. user_id siempre tiene prioridad.
    """
    # 1) Si ya te pasan el id, úsalo
    if user_id:
        return user_id

    # 2) Si viene email, hacemos UPSERT por email (evita el duplicate key)
    if email:
        # Nota: el supabase-py soporta on_conflict="email"
        res = (
            supabase
            .table("users")
            .upsert(
                {"email": email, "nombre": (nombre or "Invitado")},
                on_conflict="email"
            )
            .select("id")
            .single()
            .execute()
        )
        return res.data["id"]

    # 3) Si no viene email, creamos un usuario sin email (NULL no rompe el UNIQUE)
    res = (
        supabase
        .table("users")
        .insert({"nombre": (nombre or "Invitado")})
        .select("id")
        .single()
        .execute()
    )
    return res.data["id"]

