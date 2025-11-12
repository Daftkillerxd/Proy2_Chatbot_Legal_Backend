# chats_service.py
from typing import List, Dict, Optional
from supabase import Client
from conexion import obtener_cliente

supabase: Client = obtener_cliente()


def obtener_chats_por_usuario(user_id: str) -> List[Dict]:
    """
    Devuelve todos los chats de un usuario, ordenados del más nuevo al más antiguo.
    """
    res = (
        supabase
        .table("chats")
        .select("id, user_id, nombre_chat, fecha_creacion, contexto")
        .eq("user_id", user_id)
        .order("fecha_creacion", desc=True)
        .execute()
    )
    return res.data or []


def crear_chat(user_id: str, nombre_chat: str, contexto: Optional[str] = None) -> Dict:
    """
    Crea un nuevo chat para un usuario.
    """
    res = (
        supabase
        .table("chats")
        .insert({
            "user_id": user_id,
            "nombre_chat": nombre_chat,
            "contexto": contexto
        })
        .execute()
    )
    return res.data[0]


def eliminar_chat(chat_id: str) -> None:
    """
    Borra primero los mensajes del chat y luego el chat.
    """
    supabase.table("messages").delete().eq("chat_id", chat_id).execute()
    supabase.table("chats").delete().eq("id", chat_id).execute()
