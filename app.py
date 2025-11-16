# app.py
import os
from dotenv import load_dotenv

from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI

# --- Servicios locales ---
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

# ================== Logs utilitarios ==================
def log(msg):
    print(f"[LOG] {msg}")

def log_request():
    print(f"[REQ] {request.method} {request.path} | ORIGIN={request.headers.get('Origin')}")

# ================== CORS ==================
CORS(
    app,
    resources={r"/chats*": {"origins": list(ALLOWED_ORIGINS)}},
    supports_credentials=False,
    methods=["GET", "POST", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

def _origin_allowed(origin: str | None) -> bool:
    ok = bool(origin) and origin in ALLOWED_ORIGINS
    log(f"Validando origen: {origin} → {ok}")
    return ok

@app.after_request
def add_cors_headers(resp):
    origin = request.headers.get("Origin")
    if _origin_allowed(origin):
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, PATCH, OPTIONS"
        resp.headers["Access-Control-Max-Age"] = "86400"
        log(f"CORS aplicado a respuesta para origen permitido: {origin}")
    return resp

# ================== Errores JSON ==================
@app.errorhandler(404)
def not_found(_e):
    log("Error 404: recurso no encontrado")
    return jsonify({"error": "not_found"}), 404

@app.errorhandler(405)
def method_not_allowed(_e):
    log("Error 405: método no permitido")
    return jsonify({"error": "method_not_allowed"}), 405

@app.errorhandler(Exception)
def unhandled(e):
    log(f"Excepción no manejada: {repr(e)}")
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
    log_request()
    log("Ruta /ping llamada")
    return jsonify({"ok": True})

@app.route("/chats/<chat_id>/messages", methods=["OPTIONS"])
def preflight_messages(chat_id):
    log_request()
    log(f"Preflight OPTIONS para chat_id={chat_id}")
    return ("", 204)

# ================== Rutas ==================
@app.route("/chats", methods=["GET"])
def listar_chats():
    log_request()
    user_id = request.args.get("user_id")
    log(f"Listando chats para user_id={user_id}")

    if not user_id:
        log("Error: user_id faltante")
        return jsonify({"error": "user_id es requerido"}), 400

    chats = obtener_chats_por_usuario(user_id)
    log(f"{len(chats)} chats devueltos")
    return jsonify({"chats": chats})

@app.route("/chats/<chat_id>/messages", methods=["GET"])
def listar_mensajes(chat_id):
    log_request()
    limit = int(request.args.get("limit", 5))
    log(f"Listando mensajes para chat_id={chat_id}, limit={limit}")

    mensajes = obtener_mensajes_de_chat(chat_id, limit)
    log(f"{len(mensajes)} mensajes devueltos")
    return jsonify({"messages": mensajes})

@app.route("/chats/<chat_id>", methods=["DELETE"])
def borrar_chat(chat_id):
    log_request()
    log(f"Eliminando chat_id={chat_id}")

    eliminar_chat(chat_id)
    return jsonify({"ok": True})

@app.route("/chats/<chat_id>", methods=["PATCH"])
def renombrar_chat(chat_id):
    log_request()
    data = request.get_json(silent=True) or {}
    nuevo_nombre = (data.get("nombre_chat") or "").strip()

    log(f"Renombrando chat_id={chat_id} a '{nuevo_nombre}'")

    if not nuevo_nombre:
        log("Error: nuevo nombre vacío")
        return jsonify({"error": "nombre_chat es requerido"}), 400

    chat_actualizado = actualizar_nombre_chat(chat_id, nuevo_nombre)
    return jsonify({"chat": chat_actualizado})

@app.route("/chats", methods=["POST"])
def crear_nuevo_chat():
    log_request()
    data = request.get_json(silent=True) or {}
    nombre_chat = (data.get("nombre_chat") or "").strip()

    log(f"Creando nuevo chat con nombre='{nombre_chat}'")

    if not nombre_chat:
        log("Error: nombre_chat vacío")
        return jsonify({"error": "nombre_chat es requerido"}), 400

    user_id = data.get("user_id")
    nombre  = data.get("nombre") or "Invitado"
    email   = data.get("email")

    log(f"Obteniendo/creando usuario: name={nombre}, email={email}, user_id={user_id}")
    user_id = obtener_o_crear_usuario(nombre=nombre, email=email, user_id=user_id)

    contexto = data.get("contexto")
    chat = crear_chat(user_id=user_id, nombre_chat=nombre_chat, contexto=contexto)

    log(f"Chat creado con id={chat.get('id')}")
    return jsonify({"chat": chat, "user_id": user_id})

# ===== Enviar mensaje =====
@app.route("/chats/<chat_id>/messages", methods=["POST"])
def post_mensaje(chat_id):
    log_request()
    data = request.get_json(silent=True) or {}
    user_msg = (data.get("message") or "").strip()

    log(f"Nuevo mensaje recibido en chat_id={chat_id}: {user_msg}")

    if not user_msg:
        log("Error: message vacío")
        return jsonify({"error": "message es requerido"}), 400

    crear_mensaje(chat_id=chat_id, contenido=user_msg, sender="user")
    log("Mensaje del usuario guardado")

    try:
        log("Consultando OpenAI...")
        comp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_msg},
            ]
        )
        respuesta = comp.choices[0].message.content
        log(f"Respuesta OpenAI generada: {respuesta}")

        crear_mensaje(chat_id=chat_id, contenido=respuesta, sender="assistant")
        log("Respuesta guardada")
        return jsonify({"respuesta": respuesta})

    except Exception as ce:
        log(f"Error OpenAI: {ce}")
        return jsonify({
            "error": "openai_error",
            "detail": str(ce),
            "hint": "No envíes parámetros de sampling con gpt-5-mini o verifica tu acceso al modelo."
        }), 502


# ================== Main ==================
if __name__ == "__main__":
    log("Servidor Flask iniciado en modo local")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)