# app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from dotenv import load_dotenv
from openai import OpenAI

from usuarios_service import obtener_o_crear_usuario
from chats_service import (
    obtener_chats_por_usuario,
    crear_chat,
    eliminar_chat,
    actualizar_nombre_chat,
)
from mensajes_service import obtener_mensajes_de_chat, crear_mensaje

# -----------------------------
# CARGA ENV Y CLIENTE OPENAI
# -----------------------------
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# Switch para aislar la llamada a OpenAI en pruebas:
USE_OPENAI = os.getenv("USE_OPENAI", "true").lower() == "true"

client = None
if OPENAI_API_KEY and USE_OPENAI:
    client = OpenAI(api_key=OPENAI_API_KEY)

# -----------------------------
# FLASK + CORS
# -----------------------------
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "https://proy2-chatbot-legal-frontend.onrender.com",
    "https://honeydew-lark-508906.hostingersite.com",
    "https://www.honeydew-lark-508906.hostingersite.com",
]

app = Flask(__name__)

# CORS aplicado a /chat* y /chats*
CORS(
    app,
    resources={
        r"/chat*": {"origins": ALLOWED_ORIGINS},
        r"/chats*": {"origins": ALLOWED_ORIGINS},
    },
    methods=["GET", "POST", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# Garantiza que incluso las respuestas de error lleven CORS
@app.after_request
def add_cors_headers(resp):
    origin = request.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        resp.headers.setdefault("Access-Control-Allow-Origin", origin)
        resp.headers.setdefault("Vary", "Origin")
        resp.headers.setdefault("Access-Control-Allow-Methods", "GET,POST,DELETE,PATCH,OPTIONS")
        resp.headers.setdefault("Access-Control-Allow-Headers", "Content-Type")
    return resp

# Preflight explícito (ayuda con algunos proxies/CDN)
@app.route("/chats/<chat_id>/messages", methods=["OPTIONS"])
def preflight_messages(chat_id):
    return ("", 204)

# -----------------------------
# SYSTEM PROMPT
# -----------------------------
system_prompt = """Eres un asistente jurídico informativo para Perú.
- Explica en español claro.
- Cita normas con artículo y nombre (ej.: Constitución, art. 2).
- Advierte siempre: "no es asesoria legal, es una orientación".
- Si el usuario pide aperturar o reabrir carpeta fiscal, guía con pasos y requisitos según el CPP y lineamientos del MP, sin inventar artículos.

Restricciones:
- Solamente vas a responder sobre temas de derechos civiles, en materia de herencia intestada.
- En caso recibas una pregunta de otro tema, responde: "no che".

Salida:
- Tu respuesta debe ser breve, tipo conversación de chat.
- Todas tus respuestas deben estar basadas en la Constitución.
- Importante: indica el número de artículo o código de donde sale la respuesta según la Constitución y, luego, añade tu conocimiento adicional.
"""

# -----------------------------
# HEALTHCHECK
# -----------------------------
@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True})

# -----------------------------
# CHATS: LISTAR POR USUARIO
# -----------------------------
@app.route("/chats", methods=["GET"])
def listar_chats():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id es requerido"}), 400

    chats = obtener_chats_por_usuario(user_id)
    return jsonify({"chats": chats})

# -----------------------------
# MENSAJES: LISTAR POR CHAT
# -----------------------------
@app.route("/chats/<chat_id>/messages", methods=["GET"])
def listar_mensajes(chat_id):
    limit = int(request.args.get("limit", 200))
    mensajes = obtener_mensajes_de_chat(chat_id, limit)
    return jsonify({"messages": mensajes})

# -----------------------------
# CHATS: BORRAR
# -----------------------------
@app.route("/chats/<chat_id>", methods=["DELETE"])
def borrar_chat(chat_id):
    eliminar_chat(chat_id)
    return jsonify({"ok": True})

# -----------------------------
# CHATS: RENOMBRAR
# -----------------------------
@app.route("/chats/<chat_id>", methods=["PATCH"])
def renombrar_chat(chat_id):
    data = request.json or {}
    nuevo_nombre = data.get("nombre_chat")

    if not nuevo_nombre:
        return jsonify({"error": "nombre_chat es requerido"}), 400

    chat_actualizado = actualizar_nombre_chat(chat_id, nuevo_nombre)
    return jsonify({"chat": chat_actualizado})

# -----------------------------
# CHATS: CREAR (Y USUARIO SI HACE FALTA)
# -----------------------------
@app.route("/chats", methods=["POST"])
def crear_nuevo_chat():
    data = request.json or {}

    nombre_chat = data.get("nombre_chat")
    if not nombre_chat:
        return jsonify({"error": "nombre_chat es requerido"}), 400

    user_id = data.get("user_id")
    nombre = data.get("nombre") or "Invitado"
    email = data.get("email")
    contexto = data.get("contexto")

    # Asegura que el usuario exista (no chocará por UNIQUE(email))
    user_id = obtener_o_crear_usuario(nombre=nombre, email=email, user_id=user_id)

    chat = crear_chat(user_id=user_id, nombre_chat=nombre_chat, contexto=contexto)
    return jsonify({"chat": chat, "user_id": user_id})

# -----------------------------
# MENSAJES: ENVIAR (OPENAI o DEMO)
# -----------------------------
@app.route("/chats/<chat_id>/messages", methods=["POST"])
def enviar_mensaje(chat_id):
    data = request.json or {}
    user_msg = data.get("message", "")

    if not user_msg:
        return jsonify({"error": "message es requerido"}), 400

    try:
        # Guarda mensaje del usuario primero
        crear_mensaje(chat_id=chat_id, contenido=user_msg, sender="user")

        # ---- MODO DEMO PARA AISLAR ERRORES ----
        if not USE_OPENAI or not client:
            respuesta = f"(demo) Recibí tu consulta: {user_msg}"
        else:
            # Usa un modelo disponible; evita nombres no habilitados en la cuenta
            completion = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
            )
            respuesta = completion.choices[0].message.content

        # Guarda respuesta del asistente
        crear_mensaje(chat_id=chat_id, contenido=respuesta, sender="assistant")

        return jsonify({"respuesta": respuesta})

    except Exception as e:
        # Log en consola y devuelve JSON (after_request añadirá CORS)
        print("Error al procesar mensaje:", e)
        return jsonify({"error": "server_error", "detail": str(e)}), 500

# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    # Para desarrollo local
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)

