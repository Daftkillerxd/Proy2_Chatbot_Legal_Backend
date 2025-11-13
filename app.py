# app.py
import os
from dotenv import load_dotenv

from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI

# --- Servicios existentes (no los toques) ---
from usuarios_service import obtener_o_crear_usuario
from chats_service import (
    obtener_chats_por_usuario,
    crear_chat,
    eliminar_chat,
    actualizar_nombre_chat,
)
from mensajes_service import obtener_mensajes_de_chat, crear_mensaje

# ================== Config base ==================
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-5-mini")  # usamos gpt-5-mini
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

# CORS normal (para respuestas 2xx)
CORS(
    app,
    resources={r"/chats*": {"origins": list(ALLOWED_ORIGINS)}},
    supports_credentials=False,
    methods=["GET", "POST", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

def _origin_allowed(origin: str | None) -> bool:
    return bool(origin) and origin in ALLOWED_ORIGINS

# CORS también en errores 4xx/5xx (evita que el navegador oculte el error)
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
        "hint": "Revisa Live tail en Render."
    }), 500

# ================== Prompt ==================
system_prompt = """Eres un asistente jurídico informativo para Perú.
- Explica en español claro.
- Cita normas con artículo y nombre (ej.: Constitución, art. 2).
- Advierte: "no es asesoría legal, es una orientación".
- Si piden abrir o reabrir carpeta fiscal, guía con pasos y requisitos según el CPP y lineamientos del MP (sin inventar artículos).
Restricciones:
- Solo respondes sobre herencia intestada (derecho civil). Si te piden otro tema, responde: "no che".
Salida:
- Respuesta breve, estilo chat.
"""

# ================== Utils & preflight ==================
@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True})

# Algunos proxies exigen OPTIONS dedicado
@app.route("/chats/<chat_id>/messages", methods=["OPTIONS"])
def preflight_messages(chat_id):
    return ("", 204)

# ================== Rutas ==================
# 1) Listar chats por usuario
@app.route("/chats", methods=["GET"])
def listar_chats():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id es requerido"}), 400
    chats = obtener_chats_por_usuario(user_id)
    return jsonify({"chats": chats})

# 2) Obtener mensajes de un chat
@app.route("/chats/<chat_id>/messages", methods=["GET"])
def listar_mensajes(chat_id):
    limit = int(request.args.get("limit", 200))
    mensajes = obtener_mensajes_de_chat(chat_id, limit)
    return jsonify({"messages": mensajes})

# 3) Borrar chat
@app.route("/chats/<chat_id>", methods=["DELETE"])
def borrar_chat(chat_id):
    eliminar_chat(chat_id)
    return jsonify({"ok": True})

# 3b) Renombrar chat
@app.route("/chats/<chat_id>", methods=["PATCH"])
def renombrar_chat(chat_id):
    data = request.get_json(silent=True) or {}
    nuevo_nombre = (data.get("nombre_chat") or "").strip()
    if not nuevo_nombre:
        return jsonify({"error": "nombre_chat es requerido"}), 400
    chat_actualizado = actualizar_nombre_chat(chat_id, nuevo_nombre)
    return jsonify({"chat": chat_actualizado})

# 4) Crear nuevo chat (crea/obtiene usuario)
@app.route("/chats", methods=["POST"])
def crear_nuevo_chat():
    data = request.get_json(silent=True) or {}
    nombre_chat = (data.get("nombre_chat") or "").strip()
    if not nombre_chat:
        return jsonify({"error": "nombre_chat es requerido"}), 400

    user_id = data.get("user_id")
    nombre  = data.get("nombre") or "Invitado"
    email   = data.get("email")  # puede ser None

    user_id = obtener_o_crear_usuario(nombre=nombre, email=email, user_id=user_id)
    contexto = data.get("contexto")
    chat = crear_chat(user_id=user_id, nombre_chat=nombre_chat, contexto=contexto)
    return jsonify({"chat": chat, "user_id": user_id})

# 5) Enviar mensaje (GPT-5 vía Responses API)
@app.route("/chats/<chat_id>/messages", methods=["POST"])
def post_mensaje(chat_id):
    data = request.get_json(silent=True) or {}
    user_msg = (data.get("message") or "").strip()
    if not user_msg:
        return jsonify({"error": "message es requerido"}), 400

    # guarda el mensaje del usuario
    crear_mensaje(chat_id=chat_id, contenido=user_msg, sender="user")

    # Modo demo si no hay OpenAI
    if not (USE_OPENAI and client):
        respuesta = f"(demo) Recibí tu consulta: {user_msg}"
        crear_mensaje(chat_id=chat_id, contenido=respuesta, sender="assistant")
        return jsonify({"respuesta": respuesta})

    try:
        res = client.responses.create(
            model=OPENAI_MODEL,             # "gpt-5-mini"
            max_output_tokens=400,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_msg},
            ],
        )

        # --- extracción robusta del texto ---
        respuesta = None

        # 1) helper moderno
        respuesta = getattr(res, "output_text", None)

        # 2) parse helper (algunas versiones lo traen)
        if not respuesta:
            try:
                parsed = client.responses.parse(res)
                respuesta = getattr(parsed, "output_text", None)
            except Exception:
                pass

        # 3) recorrido manual seguro
        if not respuesta:
            out = getattr(res, "output", None) or []
            for item in out:
                for c in getattr(item, "content", []) or []:
                    if getattr(c, "type", "") in ("text", "output_text"):
                        respuesta = getattr(c, "text", None) or getattr(c, "output_text", None)
                        if respuesta:
                            break
                if respuesta:
                    break

        if not respuesta:
            # Loguea el crudo para inspección en Render > Logs
            try:
                print("Responses raw:", res.model_dump())
            except Exception:
                print("Responses raw (repr):", repr(res))
            respuesta = "No pude generar respuesta por ahora. Inténtalo de nuevo en unos segundos."

    except Exception as oe:
        print("OpenAI error:", oe)
        return jsonify({
            "error": "openai_error",
            "detail": str(oe),
            "hint": "Verifica acceso al modelo gpt-5-mini y versión del SDK (Responses API)."
        }), 502

    crear_mensaje(chat_id=chat_id, contenido=respuesta, sender="assistant")
    return jsonify({"respuesta": respuesta})

# ================== Main ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
