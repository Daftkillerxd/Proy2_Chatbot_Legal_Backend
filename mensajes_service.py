# mensajes_service.py
from typing import List, Dict
from supabase import Client
from conexion import obtener_cliente

supabase: Client = obtener_cliente()


def obtener_mensajes_de_chat(chat_id: str, limit: int = 5) -> List[Dict]:
    """
    Devuelve los mensajes de un chat ordenados del más antiguo al más nuevo.
    """
    res = (
        supabase
        .table("messages")
        .select("id, chat_id, contenido, sender, fecha_envio")
        .eq("chat_id", chat_id)
        .order("fecha_envio", desc=False)
        .limit(limit)
        .execute()
    )
    return res.data or []


def crear_mensaje(chat_id: str, contenido: str, sender: str) -> Dict:
    """
    Crea un mensaje en un chat (sender: 'user' o 'assistant').
    """
    res = (
        supabase
        .table("messages")
        .insert({
            "chat_id": chat_id,
            "contenido": contenido,
            "sender": sender
        })
        .execute()
    )
    return res.data[0]