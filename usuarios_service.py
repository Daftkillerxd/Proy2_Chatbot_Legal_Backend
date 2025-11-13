# usuarios_service.py
from conexion import obtener_cliente

supabase = obtener_cliente()

def obtener_o_crear_usuario(nombre: str | None, email: str | None, user_id: str | None):
    """
    Devuelve el id del usuario. Si existe por email, lo reutiliza.
    Si no existe, lo crea. user_id siempre tiene prioridad.
    Compatible con supabase-py que NO soporta .select() encadenado tras upsert().
    """
    # 1) Si ya te pasan el id, úsalo
    if user_id:
        return user_id

    # Normaliza entradas
    nombre = (nombre or "Invitado").strip() or "Invitado"
    email = (email or "").strip().lower() or None

    # 2) Si hay email, upsert por email y luego consulta el id
    if email:
        # upsert sin .select() encadenado
        supabase.table("users").upsert(
            {"email": email, "nombre": nombre},
            on_conflict="email"
        ).execute()

        # ahora sí, consulta el id por email
        res = (
            supabase.table("users")
            .select("id")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]["id"]
        # Si por alguna razón no devolvió nada, crea explícito (fallback)
        res = (
            supabase.table("users")
            .insert({"email": email, "nombre": nombre})
            .select("id")
            .execute()
        )
        return res.data[0]["id"]

    # 3) Sin email: inserta sin email (NULL) para no chocar con UNIQUE(email)
    res = (
        supabase.table("users")
        .insert({"nombre": nombre})
        .select("id")
        .execute()
    )
    return res.data[0]["id"]
