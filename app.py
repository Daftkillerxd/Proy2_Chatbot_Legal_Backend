# app.py
import os
from dotenv import load_dotenv

from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI

# --- Servicios locales (no tocar) ---
from usuarios_service import obtener_o_crear_usuario
from chats_service import (
    obtener_chats_por_usuario,
    crear_chat,
    eliminar_chat,
    actualizar_nombre_chat,
)
from mensajes_service import obtener_mensajes_de_chat, crear_mensaje

# ================== Config ==================
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-5-mini")
USE_OPENAI     = os.getenv("USE_OPENAI", "true").lower() == "true"

ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "https://proy2-chatbot-legal-frontend.onrender.com",
    "https://honeydew-lark-508906.hostingersite.com",
    "https://www.honeydew-lark-508906.hostingersite.com",
}

client = OpenAI(api_key=OPENAI_API_KEY) if (OPENAI_API_KEY and USE_OPENAI) else None

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

# CORS normal
CORS(
    app,
    resources={r"/chats*": {"origins": list(ALLOWED_ORIGINS)}},
    supports_credentials=False,
    methods=["GET", "POST", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

def _origin_allowed(origin: str | None) -> bool:
    return bool(origin) and origin in ALLOWED_ORIGINS

# CORS también en errores
@app.after_request
def add_cors_headers(resp):
    origin = request.headers.get("Origin")
    if _origin_allowed(origin):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, PATCH, OPTIONS"
        resp.headers["Access-Control-Max-Age"] = "86400"
    return resp

# ================== Errores JSON ==================
@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "not_found"}), 404

@app.errorhandler(405)
def method_not_allowed(_e):
    return jsonify({"error": "method_not_allowed"}), 405

@app.errorhandler(Exception)
def unhandled(e):
    print("Unhandled exception:", repr(e))
    return jsonify({
        "error": "server_error",
        "detail": str(e)[:500],
        "hint": "Revisa Logs (Live tail) en Render."
    }), 500

# ================== Prompt ==================
system_prompt = """Eres un asistente jurídico informativo para Perú.
- Explica en español claro.
- Cita normas con artículo y nombre (p. ej., Constitución, art. 2).
- Advierte: "no es asesoría legal, es una orientación".
- Si piden abrir o reabrir carpeta fiscal, guía con pasos y requisitos según el CPP y lineamientos del MP (sin inventar artículos).
Restricciones:
- Solo respondes sobre herencia intestada (derecho civil). Si te piden otro tema, responde: "no che".
Salida:
- Respuesta breve, estilo chat.
"""

# ================== Utils / Preflight ==================
@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True})

@app.route("/chats/<chat_id>/messages", methods=["OPTIONS"])
def preflight_messages(chat_id):
    return ("", 204)

# ================== Rutas ==================
@app.route("/chats", methods=["GET"])
def listar_chats():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id es requerido"}), 400
    chats = obtener_chats_por_usuario(user_id)
    return jsonify({"chats": chats})

@app.route("/chats/<chat_id>/messages", methods=["GET"])
def listar_mensajes(chat_id):
    limit = int(request.args.get("limit", 200))
    mensajes = obtener_mensajes_de_chat(chat_id, limit)
    return jsonify({"messages": mensajes})

@app.route("/chats/<chat_id>", methods=["DELETE"])
def borrar_chat(chat_id):
    eliminar_chat(chat_id)
    return jsonify({"ok": True})

@app.route("/chats/<chat_id>", methods=["PATCH"])
def renombrar_chat(chat_id):
    data = request.get_json(silent=True) or {}
    nuevo_nombre = (data.get("nombre_chat") or "").strip()
    if not nuevo_nombre:
        return jsonify({"error": "nombre_chat es requerido"}), 400
    chat_actualizado = actualizar_nombre_chat(chat_id, nuevo_nombre)
    return jsonify({"chat": chat_actualizado})

@app.route("/chats", methods=["POST"])
def crear_nuevo_chat():
    data = request.get_json(silent=True) or {}
    nombre_chat = (data.get("nombre_chat") or "").strip()
    if not nombre_chat:
        return jsonify({"error": "nombre_chat es requerido"}), 400

    user_id = data.get("user_id")
    nombre  = data.get("nombre") or "Invitado"
    email   = data.get("email")
    user_id = obtener_o_crear_usuario(nombre=nombre, email=email, user_id=user_id)
    contexto = data.get("contexto")
    chat = crear_chat(user_id=user_id, nombre_chat=nombre_chat, contexto=contexto)
    return jsonify({"chat": chat, "user_id": user_id})

# ===== Enviar mensaje (gpt-5-mini sin parámetros no soportados) =====
@app.route("/chats/<chat_id>/messages", methods=["POST"])
def post_mensaje(chat_id):
    data = request.get_json(silent=True) or {}
    user_msg = (data.get("message") or "").strip()
    if not user_msg:
        return jsonify({"error": "message es requerido"}), 400

    # Guarda mensaje de usuario
    crear_mensaje(chat_id=chat_id, contenido=user_msg, sender="user")

    # Modo demo si no hay OpenAI activo
    if not (USE_OPENAI and client):
        respuesta = f"(demo) Recibí tu consulta: {user_msg}"
        crear_mensaje(chat_id=chat_id, contenido=respuesta, sender="assistant")
        return jsonify({"respuesta": respuesta})

    # Intento principal: Chat Completions (sin temperature/top_p/etc.)
    try:
        comp = client.chat.completions.create(
            model=OPENAI_MODEL,  # gpt-5-mini
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_msg},
            ]
            # Importante: NO enviar temperature/top_p/frequency_penalty con gpt-5-mini
        )
        respuesta = comp.choices[0].message.content
        crear_mensaje(chat_id=chat_id, contenido=respuesta, sender="assistant")
        return jsonify({"respuesta": respuesta})

    except Exception as ce:
        print("OpenAI completions error:", ce)
        # Respuesta amable al usuario + detalle para debugging
        return jsonify({
            "error": "openai_error",
            "detail": str(ce),
            "hint": "No envíes parámetros de sampling con gpt-5-mini o verifica tu acceso al modelo."
        }), 502

# ================== Main ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
